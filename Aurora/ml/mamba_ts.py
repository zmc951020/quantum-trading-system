#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mamba 状态空间时间序列预测模型
基于 Mamba 架构（选择性状态空间模型 S6），2024 年最新架构
专为长序列金融时间序列设计，替代 Transformer 的 O(n²) 复杂度
"""

import numpy as np
import pandas as pd
from typing import Dict, Optional, Tuple, List, Any
from sklearn.preprocessing import StandardScaler
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset
import os
import json
from datetime import datetime
import warnings

warnings.filterwarnings('ignore')


# ═══════════════════════════════════════════════
# Mamba 核心组件实现
# ═══════════════════════════════════════════════

class MambaBlock(nn.Module):
    """
    Mamba 基础块
    选择性 SSM（状态空间模型）核心
    """

    def __init__(self, d_model: int, d_state: int = 16, d_conv: int = 4, expand: int = 2):
        super().__init__()
        self.d_model = d_model
        self.d_state = d_state
        self.d_conv = d_conv
        self.expand = expand
        d_inner = int(expand * d_model)

        # 输入投影
        self.in_proj = nn.Linear(d_model, d_inner * 2, bias=False)

        # 1D 深度卷积
        self.conv1d = nn.Conv1d(
            in_channels=d_inner,
            out_channels=d_inner,
            kernel_size=d_conv,
            padding=d_conv - 1,
            groups=d_inner
        )

        # SSM 参数
        self.x_proj = nn.Linear(d_inner, d_state * 2 + d_state, bias=False)
        self.dt_proj = nn.Linear(d_inner, d_inner, bias=True)

        # 输出投影
        self.out_proj = nn.Linear(d_inner, d_model, bias=False)

        # 初始化
        self._init_weights()

    def _init_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Linear):
                nn.init.xavier_uniform_(m.weight)
                if m.bias is not None:
                    nn.init.zeros_(m.bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (batch, seq_len, d_model)
        Returns:
            (batch, seq_len, d_model)
        """
        batch, seq_len, d_model = x.shape

        # 输入投影
        x_and_res = self.in_proj(x)
        x_proj, z = x_and_res.split([self.expand * d_model, self.expand * d_model], dim=-1)

        # 深度卷积
        x_conv = x_proj.permute(0, 2, 1)  # (B, D, L)
        x_conv = F.silu(self.conv1d(x_conv))
        x_conv = x_conv[:, :, :seq_len]
        x_conv = x_conv.permute(0, 2, 1)  # (B, L, D)

        # SSM 选择性扫描（简化版本）
        ssm_out = self._selective_scan(x_conv)

        # 门控
        z = F.silu(z)
        out = ssm_out * z

        # 输出投影
        out = self.out_proj(out)

        return out

    def _selective_scan(self, x: torch.Tensor) -> torch.Tensor:
        """
        选择性状态空间扫描
        简化版 SSM 核心算子
        """
        batch, seq_len, d_inner = x.shape

        # 投影到 SSM 参数
        ssm_params = self.x_proj(x)  # (B, L, 3*d_state)

        # 时间步采样（离散化）
        dt = F.softplus(self.dt_proj(x))  # (B, L, d_inner)

        # 简化 SSM 递归
        h = torch.zeros(batch, self.d_state, device=x.device)
        outputs = []

        for t in range(seq_len):
            h = self._step(h, x[:, t:t + 1, :], dt[:, t:t + 1, :])
            outputs.append(h)

        return torch.stack(outputs, dim=1).mean(dim=-1, keepdim=True).expand(-1, -1, d_inner)

    def _step(self, h: torch.Tensor, x_t: torch.Tensor, dt_t: torch.Tensor) -> torch.Tensor:
        """单步 SSM 递归"""
        alpha = torch.exp(-dt_t.mean(dim=-1, keepdim=True))
        h_new = alpha * h + (1 - alpha) * x_t.mean(dim=-1, keepdim=True)
        return h_new


class MambaEncoder(nn.Module):
    """
    Mamba 编码器 - 堆叠多层 Mamba 块
    """

    def __init__(self, d_model: int = 128, n_layers: int = 4, d_state: int = 16,
                 d_conv: int = 4, expand: int = 2, dropout: float = 0.1):
        super().__init__()
        self.layers = nn.ModuleList([
            MambaBlock(d_model, d_state, d_conv, expand)
            for _ in range(n_layers)
        ])
        self.norms = nn.ModuleList([nn.LayerNorm(d_model) for _ in range(n_layers)])
        self.dropouts = nn.ModuleList([nn.Dropout(dropout) for _ in range(n_layers)])

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (batch, seq_len, d_model)
        Returns:
            (batch, seq_len, d_model)
        """
        for layer, norm, dropout in zip(self.layers, self.norms, self.dropouts):
            residual = x
            x = norm(x)
            x = layer(x)
            x = dropout(x)
            x = x + residual
        return x


# ═══════════════════════════════════════════════
# Mamba 时间序列预测模型
# ═══════════════════════════════════════════════

class MambaTimeSeries(nn.Module):
    """
    Mamba 时间序列预测模型
    - 输入: (batch, seq_len, n_features)
    - 输出: 预测值 (batch, pred_len) 或 (batch, pred_len, 1)
    """

    def __init__(self, n_features: int, d_model: int = 128, n_layers: int = 4,
                 d_state: int = 16, d_conv: int = 4, expand: int = 2,
                 dropout: float = 0.1, pred_len: int = 1):
        super().__init__()
        self.n_features = n_features
        self.d_model = d_model
        self.pred_len = pred_len

        # 特征嵌入
        self.input_proj = nn.Linear(n_features, d_model)

        # 位置编码
        self.pos_encoder = nn.Parameter(torch.randn(1, 500, d_model) * 0.02)

        # Mamba 编码器
        self.mamba_encoder = MambaEncoder(
            d_model=d_model, n_layers=n_layers,
            d_state=d_state, d_conv=d_conv, expand=expand, dropout=dropout
        )

        # 预测头
        self.pred_head = nn.Sequential(
            nn.LayerNorm(d_model),
            nn.Linear(d_model, d_model // 2),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(d_model // 2, pred_len)
        )

        # 不确定性头
        self.uncertainty_head = nn.Sequential(
            nn.LayerNorm(d_model),
            nn.Linear(d_model, d_model // 2),
            nn.GELU(),
            nn.Linear(d_model // 2, pred_len),
            nn.Softplus()
        )

    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Args:
            x: (batch, seq_len, n_features)
        Returns:
            (prediction, uncertainty)
        """
        batch, seq_len, _ = x.shape

        # 特征嵌入 + 位置编码
        x = self.input_proj(x)
        if seq_len <= self.pos_encoder.shape[1]:
            x = x + self.pos_encoder[:, :seq_len, :]
        else:
            x = x + self.pos_encoder[:, :500, :].mean(dim=1, keepdim=True)

        # Mamba 编码
        x = self.mamba_encoder(x)

        # 取最后一个时间步的输出进行预测
        x_last = x[:, -1, :]

        # 预测
        pred = self.pred_head(x_last)
        uncertainty = self.uncertainty_head(x_last)

        return pred, uncertainty


# ═══════════════════════════════════════════════
# Mamba 训练器
# ═══════════════════════════════════════════════

class MambaTrainer:
    """
    Mamba 时间序列预测模型训练器
    """

    def __init__(self, n_features: int, config: Optional[Dict] = None):
        self.config = config or {}
        self.n_features = n_features
        self.scaler = StandardScaler()
        self.model: Optional[MambaTimeSeries] = None
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

        # 超参数
        self.d_model = self.config.get('d_model', 128)
        self.n_layers = self.config.get('n_layers', 4)
        self.d_state = self.config.get('d_state', 16)
        self.d_conv = self.config.get('d_conv', 4)
        self.expand = self.config.get('expand', 2)
        self.dropout = self.config.get('dropout', 0.1)
        self.seq_len = self.config.get('seq_len', 64)
        self.pred_len = self.config.get('pred_len', 5)
        self.batch_size = self.config.get('batch_size', 32)
        self.lr = self.config.get('lr', 1e-4)
        self.epochs = self.config.get('epochs', 100)
        self.patience = self.config.get('patience', 15)

        # 模型目录
        self.model_dir = self.config.get('model_dir', './model_storage/mamba/')
        os.makedirs(self.model_dir, exist_ok=True)

        # 训练历史
        self.train_history: List[Dict] = []
        self.is_trained = False

    def _create_sequences(self, data: np.ndarray) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        创建时间序列样本
        Args:
            data: (n_samples, n_features)
        Returns:
            X: (batch, seq_len, n_features), y: (batch, pred_len)
        """
        X_list, y_list = [], []
        for i in range(len(data) - self.seq_len - self.pred_len + 1):
            X_list.append(data[i:i + self.seq_len])
            y_list.append(data[i + self.seq_len:i + self.seq_len + self.pred_len, 0])  # 第0列为目标

        if not X_list:
            raise ValueError(f"数据不足: 需要至少 {self.seq_len + self.pred_len} 行")

        return torch.FloatTensor(np.array(X_list)), torch.FloatTensor(np.array(y_list))

    def fit(self, df: pd.DataFrame, feature_cols: Optional[List[str]] = None,
            target_col: str = 'target', verbose: bool = True) -> 'MambaTrainer':
        """
        训练 Mamba 模型
        Args:
            df: 训练数据
            feature_cols: 特征列（第一列应为target）
            target_col: 目标列（默认'target'）
        """
        # 特征准备
        if feature_cols is None:
            exclude = ['date', 'datetime', 'symbol', 'code']
            feature_cols = [c for c in df.columns if c not in exclude]

        if target_col in df.columns and target_col not in feature_cols:
            feature_cols = [target_col] + feature_cols

        data = df[feature_cols].values.astype(np.float32)
        data = np.nan_to_num(data, nan=0.0, posinf=1e6, neginf=-1e6)

        # 标准化
        data_scaled = self.scaler.fit_transform(data)

        # 创建序列
        X, y = self._create_sequences(data_scaled)

        # 划分训练/验证集 (80/20)
        split_idx = int(len(X) * 0.8)
        X_train, X_val = X[:split_idx], X[split_idx:]
        y_train, y_val = y[:split_idx], y[split_idx:]

        if len(X_train) < self.batch_size:
            print(f"[WARNING] 训练数据不足 ({len(X_train)} 样本 < {self.batch_size} 批次大小)")
            return self

        # 数据加载器
        train_loader = DataLoader(
            TensorDataset(X_train, y_train),
            batch_size=self.batch_size, shuffle=True, drop_last=True
        )
        val_loader = DataLoader(
            TensorDataset(X_val, y_val),
            batch_size=self.batch_size, shuffle=False
        )

        # 构建模型
        self.model = MambaTimeSeries(
            n_features=len(feature_cols),
            d_model=self.d_model,
            n_layers=self.n_layers,
            d_state=self.d_state,
            d_conv=self.d_conv,
            expand=self.expand,
            dropout=self.dropout,
            pred_len=self.pred_len
        ).to(self.device)

        # 优化器
        optimizer = optim.AdamW(self.model.parameters(), lr=self.lr, weight_decay=1e-5)
        scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode='min', factor=0.5, patience=5)
        criterion = nn.MSELoss()

        best_val_loss = float('inf')
        patience_counter = 0

        for epoch in range(self.epochs):
            # 训练
            self.model.train()
            train_loss = 0.0
            for X_batch, y_batch in train_loader:
                X_batch, y_batch = X_batch.to(self.device), y_batch.to(self.device)
                optimizer.zero_grad()

                pred, uncertainty = self.model(X_batch)

                # 损失 = MSE + 不确定性正则化
                mse_loss = criterion(pred, y_batch)
                unc_reg = uncertainty.mean() * 0.01
                loss = mse_loss + unc_reg

                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
                optimizer.step()

                train_loss += loss.item()

            train_loss /= len(train_loader)

            # 验证
            self.model.eval()
            val_loss = 0.0
            with torch.no_grad():
                for X_batch, y_batch in val_loader:
                    X_batch, y_batch = X_batch.to(self.device), y_batch.to(self.device)
                    pred, _ = self.model(X_batch)
                    val_loss += criterion(pred, y_batch).item()
            val_loss /= len(val_loader)

            scheduler.step(val_loss)

            if verbose and epoch % max(1, self.epochs // 10) == 0:
                print(f"[Mamba] Epoch {epoch}/{self.epochs} | Train Loss: {train_loss:.6f} | Val Loss: {val_loss:.6f}")

            # 早停
            if val_loss < best_val_loss:
                best_val_loss = val_loss
                patience_counter = 0
                self._save_checkpoint(epoch, val_loss)
            else:
                patience_counter += 1

            if patience_counter >= self.patience:
                if verbose:
                    print(f"[Mamba] 早停于 epoch {epoch}, 最佳验证损失: {best_val_loss:.6f}")
                break

        self.is_trained = True
        self.train_history.append({
            'timestamp': datetime.now().isoformat(),
            'best_val_loss': best_val_loss,
            'epochs_completed': epoch + 1
        })

        return self

    def _save_checkpoint(self, epoch: int, val_loss: float):
        """保存检查点"""
        torch.save({
            'model_state_dict': self.model.state_dict(),
            'scaler': self.scaler,
            'config': self.config,
            'epoch': epoch,
            'val_loss': val_loss
        }, os.path.join(self.model_dir, 'mamba_best.pt'))

    def predict(self, df: pd.DataFrame,
                feature_cols: Optional[List[str]] = None,
                target_col: str = 'target') -> Tuple[np.ndarray, np.ndarray]:
        """
        预测
        Args:
            df: 特征数据（需要至少 seq_len 行）
        Returns:
            (预测值, 不确定性)
        """
        if not self.is_trained or self.model is None:
            raise RuntimeError("模型未训练，请先调用 fit()")

        if feature_cols is None:
            exclude = ['date', 'datetime', 'symbol', 'code']
            feature_cols = [c for c in df.columns if c not in exclude]

        if target_col in df.columns and target_col not in feature_cols:
            feature_cols = [target_col] + feature_cols

        data = df[feature_cols].values.astype(np.float32)
        data = np.nan_to_num(data, nan=0.0, posinf=1e6, neginf=-1e6)
        data_scaled = self.scaler.transform(data)

        # 取最后 seq_len 行
        if len(data_scaled) < self.seq_len:
            pad = self.seq_len - len(data_scaled)
            data_scaled = np.vstack([np.zeros((pad, data_scaled.shape[1])), data_scaled])

        X = torch.FloatTensor(data_scaled[-self.seq_len:]).unsqueeze(0).to(self.device)

        self.model.eval()
        with torch.no_grad():
            pred_scaled, uncertainty = self.model(X)

        pred_scaled = pred_scaled.cpu().numpy()[0]
        uncertainty = uncertainty.cpu().numpy()[0]

        # 反标准化（仅对目标列）
        pred_orig = self.scaler.inverse_transform(
            np.column_stack([pred_scaled, np.zeros((len(pred_scaled), len(feature_cols) - 1))])
        )[:, 0]

        return pred_orig, uncertainty

    def predict_next(self, features: Dict[str, float],
                     history_df: pd.DataFrame) -> Tuple[float, float]:
        """
        预测下一个值（策略调用接口）
        Args:
            features: 当前特征
            history_df: 历史数据（需要 seq_len - 1 行）
        Returns:
            (预测值, 不确定性)
        """
        # 合并历史和当前特征
        current_row = pd.DataFrame([features])
        df = pd.concat([history_df, current_row], ignore_index=True)

        try:
            preds, uncertainties = self.predict(df)
            return float(preds[0]), float(uncertainties[0])
        except Exception as e:
            print(f"[Mamba] 预测失败: {e}")
            return 0.0, 1.0

    def save(self, path: Optional[str] = None):
        """保存模型"""
        save_path = path or os.path.join(self.model_dir, 'mamba_final.pt')
        torch.save({
            'model_state_dict': self.model.state_dict(),
            'scaler': self.scaler,
            'config': self.config,
            'train_history': self.train_history,
            'is_trained': self.is_trained,
            'n_features': self.n_features
        }, save_path)
        print(f"[Mamba] 模型已保存: {save_path}")

    @classmethod
    def load(cls, path: str) -> 'MambaTrainer':
        """加载模型"""
        checkpoint = torch.load(path, map_location='cpu')
        config = checkpoint.get('config', {})
        n_features = checkpoint.get('n_features', config.get('n_features', 1))

        instance = cls(n_features=n_features, config=config)
        instance.scaler = checkpoint['scaler']
        instance.is_trained = checkpoint.get('is_trained', True)
        instance.train_history = checkpoint.get('train_history', [])

        instance.model = MambaTimeSeries(
            n_features=n_features,
            d_model=config.get('d_model', 128),
            n_layers=config.get('n_layers', 4),
            d_state=config.get('d_state', 16),
            d_conv=config.get('d_conv', 4),
            expand=config.get('expand', 2),
            dropout=config.get('dropout', 0.1),
            pred_len=config.get('pred_len', 5)
        )
        instance.model.load_state_dict(checkpoint['model_state_dict'])
        instance.model.eval()

        print(f"[Mamba] 模型已加载: {path}")
        return instance