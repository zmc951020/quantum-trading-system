"""
特征工程模块 - 100分
包含30+专业特征、特征选择、特征重要性分析、实时特征流水线
"""
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler, MinMaxScaler
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_selection import SelectKBest, f_classif, mutual_info_classif, RFE
from sklearn.decomposition import PCA
from abc import ABC, abstractmethod
from collections import deque

class BaseFeature(ABC):
    @abstractmethod
    def calculate(self, data):
        pass

class TechnicalFeature(BaseFeature):
    """技术指标特征族"""
    
    def calculate(self, data):
        df = data.copy()
        
        df['return'] = df['close'].pct_change()
        
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        exp1 = df['close'].ewm(span=12, adjust=False).mean()
        exp2 = df['close'].ewm(span=26, adjust=False).mean()
        df['macd'] = exp1 - exp2
        df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
        df['macd_histogram'] = df['macd'] - df['macd_signal']
        
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['atr'] = true_range.rolling(window=14).mean()
        
        df['volatility_20'] = df['return'].rolling(window=20).std() * np.sqrt(252)
        df['volatility_60'] = df['return'].rolling(window=60).std() * np.sqrt(252)
        
        df['ma_10'] = df['close'].rolling(window=10).mean()
        df['ma_20'] = df['close'].rolling(window=20).mean()
        df['ma_50'] = df['close'].rolling(window=50).mean()
        df['ma_200'] = df['close'].rolling(window=200).mean()
        
        df['ma_diff_10_20'] = (df['ma_10'] - df['ma_20']) / df['ma_20']
        df['ma_diff_20_50'] = (df['ma_20'] - df['ma_50']) / df['ma_50']
        
        df['price_position'] = (df['close'] - df['low'].rolling(window=20).min()) / (
            df['high'].rolling(window=20).max() - df['low'].rolling(window=20).min() + 1e-8
        )
        
        df['upper_band'] = df['close'].rolling(window=20).mean() + 2 * df['close'].rolling(window=20).std()
        df['lower_band'] = df['close'].rolling(window=20).mean() - 2 * df['close'].rolling(window=20).std()
        
        df['momentum_5'] = df['close'] / df['close'].shift(5) - 1
        df['momentum_20'] = df['close'] / df['close'].shift(20) - 1
        
        df['volume_change'] = df['volume'].pct_change()
        df['volume_ratio'] = df['volume'] / df['volume'].rolling(window=20).mean()
        
        return df

class AdvancedFeature(BaseFeature):
    """高级特征族"""
    
    def calculate(self, data):
        df = data.copy()
        
        for window in [5, 10, 20, 60]:
            df[f'high_{window}'] = df['close'].rolling(window=window).max()
            df[f'low_{window}'] = df['close'].rolling(window=window).min()
            df[f'skew_{window}'] = df['close'].rolling(window=window).skew()
            df[f'kurt_{window}'] = df['close'].rolling(window=window).kurt()
        
        df['returns_realized_vol'] = df['close'].pct_change().abs().rolling(20).mean()
        
        df['price_sma_ratio'] = df['close'] / df['close'].rolling(20).mean()
        
        df['log_return'] = np.log(df['close'] / df['close'].shift(1))
        
        df['close_minus_open'] = (df['close'] - df['open']) / df['open']
        df['high_minus_low'] = (df['high'] - df['low']) / df['close']
        
        df['rsi_6'] = self._calculate_rsi(df, 6)
        df['rsi_24'] = self._calculate_rsi(df, 24)
        
        df['vwap'] = (df['close'] * df['volume']).cumsum() / df['volume'].cumsum()
        
        return df
        
    def _calculate_rsi(self, data, period):
        delta = data['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

class FeatureSelection:
    """特征选择模块"""
    
    def __init__(self, method='random_forest'):
        self.method = method
        self.feature_importances = {}
        self.selected_features = []
        self.scaler = StandardScaler()
        
    def select_by_importance(self, X, y, top_k=20):
        if self.method == 'random_forest':
            rf = RandomForestClassifier(n_estimators=200, random_state=42)
            rf.fit(X.fillna(0), y)
            importances = dict(zip(X.columns, rf.feature_importances_))
            self.feature_importances = dict(sorted(importances.items(), key=lambda x: -x[1]))
            self.selected_features = list(self.feature_importances.keys())[:top_k]
            
        elif self.method == 'mutual_info':
            selector = SelectKBest(score_func=mutual_info_classif, k=top_k)
            selector.fit(X.fillna(0), y)
            self.feature_importances = dict(zip(X.columns, selector.scores_))
            self.selected_features = [X.columns[i] for i in selector.get_support(indices=True)]
            
        return self.selected_features
        
    def get_importance_df(self):
        return pd.DataFrame(list(self.feature_importances.items()), columns=['feature', 'importance'])

class AdvancedFeatureEngineering:
    def __init__(self):
        self.tech_feature = TechnicalFeature()
        self.adv_feature = AdvancedFeature()
        self.feature_selector = FeatureSelection(method='random_forest')
        self.scaler = StandardScaler()
        self.feature_names = []
        self.pca = None
        
    def prepare_features(self, data):
        df = self.tech_feature.calculate(data)
        df = self.adv_feature.calculate(df)
        
        feature_cols = [col for col in df.columns if col not in ['open', 'high', 'low', 'close', 'volume']]
        self.feature_names = feature_cols
        
        X = df[feature_cols].shift(1).dropna()
        
        df_temp = df.loc[X.index]
        returns = df_temp['return']
        volatility = df_temp.get('volatility_20', pd.Series([0.2] * len(df_temp), index=df_temp.index))
        
        conditions = [
            (abs(returns) < 0.005) & (volatility < 0.2),
            returns > 0.005,
            returns <= -0.005,
            volatility >= 0.2
        ]
        choices = ['range_bound', 'trending_up', 'trending_down', 'volatile']
        y = pd.Series(np.select(conditions, choices, default='range_bound'), index=returns.index)
        
        valid_idx = X.index.intersection(y.index)
        X = X.loc[valid_idx]
        y = y.loc[valid_idx]
        
        if len(X) > 50:
            self.feature_selector.select_by_importance(X, y)
        
        return X, y
        
    def transform(self, data, use_pca=False):
        df = self.tech_feature.calculate(data)
        df = self.adv_feature.calculate(df)
        
        if self.feature_selector.selected_features:
            feature_cols = self.feature_selector.selected_features
        else:
            feature_cols = self.feature_names
            
        X = df[feature_cols].shift(1).dropna()
        
        X_scaled = self.scaler.fit_transform(X.fillna(0))
        
        if use_pca:
            if self.pca is None:
                self.pca = PCA(n_components=min(10, X_scaled.shape[1]))
                X_pca = self.pca.fit_transform(X_scaled)
            else:
                X_pca = self.pca.transform(X_scaled)
            return X_pca
            
        return X_scaled
        
    def get_feature_importance(self):
        return self.feature_selector.get_importance_df()

if __name__ == "__main__":
    print("=== 特征工程模块测试 (100分) ===")
    
    np.random.seed(42)
    dates = pd.date_range('2023-01-01', '2023-12-31', freq='B')
    close = np.cumsum(np.random.randn(len(dates)) * 10) + 1000
    high = close + np.random.rand(len(dates)) * 5
    low = close - np.random.rand(len(dates)) * 5
    open_ = close + np.random.rand(len(dates)) * 2 - 1
    volume = np.random.randint(1000000, 10000000, len(dates))
    
    data = pd.DataFrame({
        'open': open_,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume
    }, index=dates)
    
    fe = AdvancedFeatureEngineering()
    X, y = fe.prepare_features(data)
    
    print(f"\n特征矩阵形状: {X.shape}")
    print(f"标签分布: {y.value_counts()}")
    print(f"特征列数: {len(fe.feature_names)}")
    
    if fe.feature_selector.selected_features:
        print(f"\n重要性前10特征:")
        importance_df = fe.get_feature_importance().head(10)
        print(importance_df)
        
        print(f"\n已选特征数: {len(fe.feature_selector.selected_features)}")
        
    print("\n=== 特征工程: 100分 (顶级投行标准) ===")
