#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Temporal Fusion Transformer (TFT) - 多尺度时间融合预测模型
Google Research 提出的金融级时间序列模型
"""

import numpy as np
import pandas as pd
from typing import Dict, Optional, Tuple, List
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset
from sklearn.preprocessing import StandardScaler
import os
from datetime import datetime
import warnings

warnings.filterwarnings('ignore')


class GLU(nn.Module):
    """门控线性单元"""
    def __init__(self, input_size: int, output_size: int):
        super().__init__()
        self.fc = nn.Linear(input_size, output_size)
        self.gate = nn.Linear(input_size, output_size)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.fc(x) * torch.sigmoid(self.gate(x))


class VariableSelectionNetwork(nn.Module):
    """变量选择网络"""
    def __init__(self, input_size: int, hidden_size: int, num_variables: int):
        super().__init__()
        self.num_variables = num_variables
        self.hidden_size = hidden_size

        self.grns = nn.ModuleList([
            GRN(input_size, hidden_size) for _ in range(num_variables)
        ])
        self.selection_grn = GRN(
            input_size * num_variables, num_variables,
            output_activation=nn.Softmax(dim=-1)
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (batch, seq_len, num_variables, input_size)
        Returns:
            (batch, seq_len, hidden_size)
        """
        processed = []
        for i in range(self.num_variables):
            processed.append(self.grns[i](x[:, :, i, :]))
        flat = torch.cat(processed, dim=-1)
        weights = self.selection_grn(flat)
        weighted = sum(w[:, :, i:i + 1] * processed[i] for i, w in enumerate(weights.unbind(-1)))
        return weighted


class GRN(nn.Module):
    """门控残差网络"""
    def __init__(self, input_size: int, hidden_size: int,
                 output_size: Optional[int] = None, dropout: float = 0.1,
                 output_activation=None):
        super().__init__()
        self.output_size = output_size or input_size
        self.input_size = input_size
        self.hidden_size = hidden_size

        self.fc1 = nn.Linear(input_size, hidden_size)
        self.fc2 = nn.Linear(hidden_size, self.output_size)
        self.gate = nn.Linear(self.output_size, self.output_size)
        self.norm = nn.LayerNorm(self.output_size)
        self.dropout = nn.Dropout(dropout)
        self.output_activation = output_activation

        if input_size != self.output_size:
            self.residual = nn.Linear(input_size, self.output_size)
        else:
            self.residual = None

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        residual = x if self.residual is None else self.residual(x)
        h = F.elu(self.fc1(x))
        h = self.fc2(h)
        h = self.dropout(h)
        gated = h * torch.sigmoid(self.gate(h))
        out = self.norm(residual + gated)
        if self.output_activation:
            out = self.output_activation(out)
        return out


class TemporalFusionTransformer(nn.Module):
    """
    TFT 模型 - 适用于金融市场多尺度预测
    """
    def __init__(self, n_features: int, hidden_size: int = 64, num_heads: int = 4,
                 num_layers: int = 2, seq_len: int = 60, pred_len: int = 10,
                 dropout: float = 0.1):
        super().__init__()
        self.n_features = n_features
        self.hidden_size = hidden_size
        self.seq_len = seq_len
        self.pred_len = pred_len

        # 变量选择
        self.vsn = VariableSelectionNetwork(1, hidden_size, n_features)

        # LSTM 编码器
        self.lstm_encoder = nn.LSTM(
            hidden_size, hidden_size, num_layers=1,
            batch_first=True, dropout=dropout
        )

        # 多头注意力
        self.mha = nn.MultiheadAttention(
            hidden_size, num_heads, dropout=dropout, batch_first=True
        )
        self.mha_norm = nn.LayerNorm(hidden_size)

        # 位置编码
        self.pos_encoder = nn.Parameter(torch.randn(1, 500, hidden_size) * 0.02)

        # 输出层
        self.output_grn = GRN(hidden_size, hidden_size * 2, hidden_size, dropout=dropout)
        self.fc_out = nn.Linear(hidden_size, pred_len)
        self.uncertainty_fc = nn.Linear(hidden_size, pred_len)

    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Args:
            x: (batch, seq_len, n_features)
        Returns:
            (pred, uncertainty)
        """
        batch, seq_len, _ = x.shape

        # 变量选择
        x_expanded = x.unsqueeze(-1)  # (B, L, F, 1)
        x_selected = self.vsn(x_expanded)  # (B, L, H)

        # 位置编码
        if seq_len <= self.pos_encoder.shape[1]:
            x_selected = x_selected + self.pos_encoder[:, :seq_len, :]

        # LSTM 编码
        lstm_out, _ = self.lstm_encoder(x_selected)

        # 多头注意力
        att_out, _ = self.mha(lstm_out, lstm_out, lstm_out)
        x_att = self.mha_norm(lstm_out + att_out)

        # 输出
        x_last = x_att[:, -1, :]
        x_out = self.output_grn(x_last)
        pred = self.fc_out(x_out)
        uncertainty = F.softplus(self.uncertainty_fc(x_out))

        return pred, uncertainty


class TFTTrainer:
    """TFT 训练器"""
    def __init__(self, n_features: int, config: Optional[Dict] = None):
        self.config = config or {}
        self.n_features = n_features
        self.scaler = StandardScaler()
        self.model: Optional[TemporalFusionTransformer] = None
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.hidden_size = config.get('hidden_size', 64)
        self.num_heads = config.get('num_heads', 4)
        self.num_layers = config.get('num_layers', 2)
        self.seq_len = config.get('seq_len', 60)
        self.pred_len = config.get('pred_len', 10)
        self.dropout = config.get('dropout', 0.1)
        self.batch_size = config.get('batch_size', 32)
        self.lr = config.get('lr', 1e-3)
        self.epochs = config.get('epochs', 80)
        self.patience = config.get('patience', 10)
        self.model_dir = config.get('model_dir', './model_storage/tft/')
        os.makedirs(self.model_dir, exist_ok=True)
        self.is_trained = False

    def _create_sequences(self, data: np.ndarray):
        X_list, y_list = [], []
        for i in range(len(data) - self.seq_len - self.pred_len + 1):
            X_list.append(data[i:i + self.seq_len])
            y_list.append(data[i + self.seq_len:i + self.seq_len + self.pred_len, 0])
        if not X_list:
            raise ValueError(f"数据不足")
        return torch.FloatTensor(np.array(X_list)), torch.FloatTensor(np.array(y_list))

    def fit(self, df: pd.DataFrame, feature_cols: Optional[List[str]] = None,
            target_col: str = 'target', verbose: bool = True) -> 'TFTTrainer':
        if feature_cols is None:
            exclude = ['date', 'datetime', 'symbol', 'code']
            feature_cols = [c for c in df.columns if c not in exclude]
        if target_col in df.columns and target_col not in feature_cols:
            feature_cols = [target_col] + feature_cols

        data = df[feature_cols].values.astype(np.float32)
        data = np.nan_to_num(data, nan=0.0, posinf=1e6, neginf=-1e6)
        data_scaled = self.scaler.fit_transform(data)

        X, y = self._create_sequences(data_scaled)
        split = int(len(X) * 0.8)
        X_train, X_val = X[:split], X[split:]
        y_train, y_val = y[:split], y[split:]

        if len(X_train) < self.batch_size:
            return self

        train_loader = DataLoader(TensorDataset(X_train, y_train), batch_size=self.batch_size, shuffle=True, drop_last=True)
        val_loader = DataLoader(TensorDataset(X_val, y_val), batch_size=self.batch_size)

        self.model = TemporalFusionTransformer(
            n_features=len(feature_cols), hidden_size=self.hidden_size,
            num_heads=self.num_heads, num_layers=self.num_layers,
            seq_len=self.seq_len, pred_len=self.pred_len, dropout=self.dropout
        ).to(self.device)

        optimizer = optim.AdamW(self.model.parameters(), lr=self.lr, weight_decay=1e-5)
        scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=self.epochs)
        criterion = nn.MSELoss()

        best_loss = float('inf')
        patience_cnt = 0

        for epoch in range(self.epochs):
            self.model.train()
            train_loss = 0
            for Xb, yb in train_loader:
                Xb, yb = Xb.to(self.device), yb.to(self.device)
                optimizer.zero_grad()
                pred, unc = self.model(Xb)
                loss = criterion(pred, yb) + unc.mean() * 0.01
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
                optimizer.step()
                train_loss += loss.item()
            train_loss /= len(train_loader)

            self.model.eval()
            val_loss = 0
            with torch.no_grad():
                for Xb, yb in val_loader:
                    Xb, yb = Xb.to(self.device), yb.to(self.device)
                    pred, _ = self.model(Xb)
                    val_loss += criterion(pred, yb).item()
            val_loss /= len(val_loader)
            scheduler.step()

            if verbose and epoch % max(1, self.epochs // 10) == 0:
                print(f"[TFT] Epoch {epoch}: Train={train_loss:.6f} Val={val_loss:.6f}")

            if val_loss < best_loss:
                best_loss = val_loss
                patience_cnt = 0
            else:
                patience_cnt += 1
            if patience_cnt >= self.patience:
                break

        self.is_trained = True
        return self

    def predict_next(self, features: Dict[str, float], history_df: pd.DataFrame) -> Tuple[float, float]:
        current_row = pd.DataFrame([features])
        df = pd.concat([history_df, current_row], ignore_index=True)
        exclude = ['date', 'datetime', 'symbol', 'code']
        feature_cols = [c for c in df.columns if c not in exclude]

        data = df[feature_cols].values.astype(np.float32)
        data = np.nan_to_num(data, nan=0.0)
        data_scaled = self.scaler.transform(data)

        if len(data_scaled) < self.seq_len:
            data_scaled = np.vstack([np.zeros((self.seq_len - len(data_scaled), data_scaled.shape[1])), data_scaled])

        X = torch.FloatTensor(data_scaled[-self.seq_len:]).unsqueeze(0).to(self.device)
        self.model.eval()
        with torch.no_grad():
            pred, unc = self.model(X)
        return float(pred[0, 0].item()), float(unc[0, 0].item())

    def save(self, path: Optional[str] = None):
        save_path = path or os.path.join(self.model_dir, 'tft_final.pt')
        torch.save({
            'model_state_dict': self.model.state_dict(),
            'scaler': self.scaler, 'config': self.config,
            'n_features': self.n_features, 'is_trained': self.is_trained
        }, save_path)

    @classmethod
    def load(cls, path: str) -> 'TFTTrainer':
        ckpt = torch.load(path, map_location='cpu')
        instance = cls(n_features=ckpt['n_features'], config=ckpt.get('config', {}))
        instance.scaler = ckpt['scaler']
        instance.is_trained = ckpt.get('is_trained', True)
        instance.model = TemporalFusionTransformer(
            n_features=ckpt['n_features'],
            hidden_size=ckpt['config'].get('hidden_size', 64),
            num_heads=ckpt['config'].get('num_heads', 4),
            num_layers=ckpt['config'].get('num_layers', 2),
            seq_len=ckpt['config'].get('seq_len', 60),
            pred_len=ckpt['config'].get('pred_len', 10),
            dropout=ckpt['config'].get('dropout', 0.1)
        )
        instance.model.load_state_dict(ckpt['model_state_dict'])
        instance.model.eval()
        return instance