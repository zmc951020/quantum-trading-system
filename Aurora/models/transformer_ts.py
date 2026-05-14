"""
Transformer 时间序列预测模型
替换旧的LSTM模型，支持长序列预测
"""
import torch
import torch.nn as nn
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from typing import Tuple, Optional


# Informer 核心实现
class ProbAttention(nn.Module):
    def __init__(self, mask_flag=True, factor=5, scale=None, attention_dropout=0.1):
        super(ProbAttention, self).__init__()
        self.factor = factor
        self.scale = scale
        self.mask_flag = mask_flag
        self.dropout = nn.Dropout(attention_dropout)

    def forward(self, queries, keys, values, attn_mask):
        B, L, H, D = queries.shape
        _, S, _, _ = keys.shape
        
        queries = queries.permute(0, 2, 1, 3)
        keys = keys.permute(0, 2, 1, 3)
        values = values.permute(0, 2, 1, 3)
        
        scale = self.scale or 1./np.sqrt(D)
        scores = torch.einsum("bhld,bhsd->bhls", queries, keys)
        
        if self.mask_flag:
            if attn_mask is None:
                attn_mask = torch.ones_like(scores, device=scores.device)
                attn_mask = torch.tril(attn_mask)
            scores.masked_fill_(attn_mask == 0, -np.inf)
        
        A = self.dropout(torch.softmax(scale * scores, dim=-1))
        V = torch.einsum("bhls,bhsd->bhld", A, values)
        
        return V.permute(0, 2, 1, 3)


class DataEmbedding(nn.Module):
    def __init__(self, c_in, d_model, dropout=0.1):
        super(DataEmbedding, self).__init__()
        self.value_embedding = TokenEmbedding(c_in, d_model)
        self.position_embedding = PositionalEmbedding(d_model)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x, x_mark):
        x = self.value_embedding(x) + self.position_embedding(x)
        return self.dropout(x)


class TokenEmbedding(nn.Module):
    def __init__(self, c_in, d_model):
        super(TokenEmbedding, self).__init__()
        self.tokenConv = nn.Conv1d(in_channels=c_in, out_channels=d_model,
                                   kernel_size=3, padding=1, padding_mode='circular')
        for m in self.modules():
            if isinstance(m, nn.Conv1d):
                nn.init.kaiming_normal_(m.weight, mode='fan_in', nonlinearity='leaky_relu')

    def forward(self, x):
        x = self.tokenConv(x.permute(0, 2, 1)).transpose(1,2)
        return x


class PositionalEmbedding(nn.Module):
    def __init__(self, d_model, max_len=5000):
        super(PositionalEmbedding, self).__init__()
        pe = torch.zeros(max_len, d_model).float()
        pe.require_grad = False
        position = torch.arange(0, max_len).float().unsqueeze(1)
        div_term = (torch.arange(0, d_model, 2).float() * -(np.log(10000.0) / d_model)).exp()
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        pe = pe.unsqueeze(0)
        self.register_buffer('pe', pe)

    def forward(self, x):
        return self.pe[:, :x.size(1)]


class EncoderLayer(nn.Module):
    def __init__(self, attention, d_model, n_heads, d_ff=None, dropout=0.1):
        super(EncoderLayer, self).__init__()
        d_ff = d_ff or 4*d_model
        self.attention = attention
        self.conv1 = nn.Conv1d(in_channels=d_model, out_channels=d_ff, kernel_size=1)
        self.conv2 = nn.Conv1d(in_channels=d_ff, out_channels=d_model, kernel_size=1)
        self.norm1 = nn.LayerNorm(d_model)
        self.norm2 = nn.LayerNorm(d_model)
        self.dropout = nn.Dropout(dropout)
        self.activation = nn.GELU()

    def forward(self, x, attn_mask=None):
        new_x, attn = self.attention(x, x, x, attn_mask=attn_mask)
        x = x + self.dropout(new_x)
        y = x = self.norm1(x)
        y = self.activation(self.conv1(y.transpose(-1,1)))
        y = self.conv2(y).transpose(-1,1)
        return self.norm2(x + self.dropout(y)), attn


class Encoder(nn.Module):
    def __init__(self, attn_layers, norm_layer=None):
        super(Encoder, self).__init__()
        self.attn_layers = nn.ModuleList(attn_layers)
        self.norm = norm_layer

    def forward(self, x, attn_mask=None):
        attns = []
        for attn_layer in self.attn_layers:
            x, attn = attn_layer(x, attn_mask=attn_mask)
            attns.append(attn)
        if self.norm is not None:
            x = self.norm(x)
        return x, attns


class DecoderLayer(nn.Module):
    def __init__(self, self_attention, cross_attention, d_model, n_heads,
                 d_ff=None, dropout=0.1):
        super(DecoderLayer, self).__init__()
        d_ff = d_ff or 4*d_model
        self.self_attention = self_attention
        self.cross_attention = cross_attention
        self.conv1 = nn.Conv1d(in_channels=d_model, out_channels=d_ff, kernel_size=1)
        self.conv2 = nn.Conv1d(in_channels=d_ff, out_channels=d_model, kernel_size=1)
        self.norm1 = nn.LayerNorm(d_model)
        self.norm2 = nn.LayerNorm(d_model)
        self.norm3 = nn.LayerNorm(d_model)
        self.dropout = nn.Dropout(dropout)
        self.activation = nn.GELU()

    def forward(self, x, cross, x_mask=None, cross_mask=None):
        x = x + self.dropout(self.self_attention(x, x, x, attn_mask=x_mask)[0])
        x = self.norm1(x)
        
        x = x + self.dropout(self.cross_attention(x, cross, cross, attn_mask=cross_mask)[0])
        y = x = self.norm2(x)
        y = self.activation(self.conv1(y.transpose(-1,1)))
        y = self.conv2(y).transpose(-1,1)
        return self.norm3(x + self.dropout(y))


class Decoder(nn.Module):
    def __init__(self, layers, norm_layer=None):
        super(Decoder, self).__init__()
        self.layers = nn.ModuleList(layers)
        self.norm = norm_layer

    def forward(self, x, cross, x_mask=None, cross_mask=None):
        for layer in self.layers:
            x = layer(x, cross, x_mask=x_mask, cross_mask=cross_mask)
        if self.norm is not None:
            x = self.norm(x)
        return x


class Informer(nn.Module):
    def __init__(self, enc_in, dec_in, c_out, seq_len, label_len, out_len,
                 d_model=512, n_heads=8, e_layers=3, d_layers=2,
                 factor=5, dropout=0.05, device='cuda:0'):
        super(Informer, self).__init__()
        self.pred_len = out_len
        self.seq_len = seq_len
        self.label_len = label_len
        
        self.enc_embedding = DataEmbedding(enc_in, d_model, dropout)
        self.encoder = Encoder(
            [
                EncoderLayer(
                    ProbAttention(False, factor, attention_dropout=dropout),
                    d_model, n_heads, d_ff=4*d_model, dropout=dropout
                ) for _ in range(e_layers)
            ],
            norm_layer=nn.LayerNorm(d_model)
        )
        
        self.dec_embedding = DataEmbedding(dec_in, d_model, dropout)
        self.decoder = Decoder(
            [
                DecoderLayer(
                    ProbAttention(True, factor, attention_dropout=dropout),
                    ProbAttention(False, factor, attention_dropout=dropout),
                    d_model, n_heads, d_ff=4*d_model, dropout=dropout,
                ) for _ in range(d_layers)
            ],
            norm_layer=nn.LayerNorm(d_model)
        )
        
        self.projection = nn.Linear(d_model, c_out, bias=True)
        self.device = device

    def forward(self, x_enc, x_mark_enc, x_dec, x_mark_dec,
                enc_self_mask=None, dec_self_mask=None, dec_enc_mask=None):
        enc_out = self.enc_embedding(x_enc, x_mark_enc)
        enc_out, attns = self.encoder(enc_out, attn_mask=enc_self_mask)
        
        dec_out = self.dec_embedding(x_dec, x_mark_dec)
        dec_out = self.decoder(dec_out, enc_out, x_mask=dec_self_mask, cross_mask=dec_enc_mask)
        dec_out = self.projection(dec_out)
        
        return dec_out[:, -self.pred_len:, :]


# 对外接口类
class TransformerTimeSeries:
    def __init__(self, enc_in=300, seq_len=96, pred_len=20, device='cuda:0'):
        self.device = torch.device(device if torch.cuda.is_available() else 'cpu')
        self.model = Informer(
            enc_in=enc_in,
            dec_in=1,
            c_out=1,
            seq_len=seq_len,
            label_len=48,
            out_len=pred_len,
            d_model=512,
            n_heads=8,
            e_layers=3,
            d_layers=2,
            device=self.device
        ).to(self.device)
        self.scaler = StandardScaler()
        self.seq_len = seq_len
        self.pred_len = pred_len
        self.label_len = 48
    
    def preprocess_data(self, data: pd.DataFrame) -> Tuple[torch.Tensor, torch.Tensor]:
        """数据预处理"""
        scaled_data = self.scaler.fit_transform(data)
        x_enc = scaled_data[:-self.pred_len]
        x_dec = np.zeros((self.pred_len, scaled_data.shape[1]))
        x_dec = np.concatenate([scaled_data[-self.label_len:, :], x_dec], axis=0)
        
        return (
            torch.FloatTensor(x_enc).unsqueeze(0).to(self.device),
            torch.FloatTensor(x_dec).unsqueeze(0).to(self.device)
        )
    
    def predict(self, data: pd.DataFrame) -> np.ndarray:
        """预测未来20天收益率"""
        self.model.eval()
        with torch.no_grad():
            x_enc, x_dec = self.preprocess_data(data)
            x_mark_enc = torch.zeros_like(x_enc[:, :, 0:1])
            x_mark_dec = torch.zeros_like(x_dec[:, :, 0:1])
            
            pred = self.model(x_enc, x_mark_enc, x_dec, x_mark_dec)
            pred = pred.cpu().numpy()
            
        pred = self.scaler.inverse_transform(pred.reshape(-1, 1))
        return pred.flatten()
    
    def train(self, data: pd.DataFrame, epochs=100, lr=0.0001):
        """训练模型"""
        optimizer = torch.optim.Adam(self.model.parameters(), lr=lr)
        criterion = nn.MSELoss()
        
        self.model.train()
        for epoch in range(epochs):
            optimizer.zero_grad()
            optimizer.step()