import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
import talib
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

class MarketClassifier:
    """市场类型分类器"""
    
    def __init__(self):
        self.model = RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            random_state=42
        )
        self.scaler = StandardScaler()
        self.is_trained = False
        
    def extract_features(self, df):
        """提取市场特征"""
        features = pd.DataFrame(index=df.index)
        
        # 价格特征 - 转换为float64以兼容talib
        close = df['close'].values.astype(np.float64)
        high = df['high'].values.astype(np.float64)
        low = df['low'].values.astype(np.float64)
        volume = df['volume'].values.astype(np.float64)
        
        # 波动率特征
        features['volatility'] = df['close'].pct_change().rolling(20).std()
        features['volatility_5'] = df['close'].pct_change().rolling(5).std()
        
        # 趋势强度
        features['trend_strength'] = abs(df['close'] - df['close'].rolling(20).mean()) / df['close'].rolling(20).std()
        
        # RSI
        features['rsi'] = talib.RSI(close, timeperiod=14)
        
        # MACD
        macd, signal, hist = talib.MACD(close)
        features['macd'] = macd
        features['macd_signal'] = signal
        features['macd_hist'] = hist
        
        # 布林带
        upper, middle, lower = talib.BBANDS(close)
        features['bb_position'] = (close - lower) / (upper - lower)
        
        # 成交量特征
        features['volume_ratio'] = volume / np.mean(volume[-20:])
        features['volume_trend'] = talib.SMA(volume, timeperiod=5) / talib.SMA(volume, timeperiod=20)
        
        # 动量特征
        features['momentum'] = talib.MOM(close, timeperiod=10)
        features['rate_of_change'] = talib.ROC(close, timeperiod=10)
        
        # 价格位置
        features['price_position'] = (close - np.min(close[-20:])) / (np.max(close[-20:]) - np.min(close[-20:]) + 1e-10)
        
        # 移动平均线关系
        features['ma_5_20'] = talib.SMA(close, timeperiod=5) / talib.SMA(close, timeperiod=20) - 1
        features['ma_20_60'] = talib.SMA(close, timeperiod=20) / talib.SMA(close, timeperiod=60) - 1
        
        return features.dropna()
    
    def label_market_type(self, df, lookback=20):
        """标记市场类型"""
        labels = []
        
        for i in range(lookback, len(df)):
            window = df.iloc[i-lookback:i]
            
            # 计算市场特征
            returns = window['close'].pct_change().dropna()
            volatility = returns.std()
            trend = (window['close'].iloc[-1] / window['close'].iloc[0] - 1)
            
            # 分类逻辑
            if trend > 0.05 and volatility < 0.02:
                labels.append(0)  # 上涨市场
            elif abs(trend) < 0.02 and volatility < 0.015:
                labels.append(1)  # 横盘市场
            elif trend < -0.05:
                labels.append(2)  # 下跌市场
            else:
                labels.append(3)  # 波动市场
        
        return labels
    
    def train(self, df):
        """训练模型"""
        features = self.extract_features(df)
        labels = self.label_market_type(df)
        
        # 对齐数据
        min_len = min(len(features), len(labels))
        features = features.iloc[-min_len:]
        labels = labels[-min_len:]
        
        # 标准化
        features_scaled = self.scaler.fit_transform(features)
        
        # 训练模型
        self.model.fit(features_scaled, labels)
        self.is_trained = True
        
        return self
    
    def predict(self, df):
        """预测市场类型"""
        if not self.is_trained:
            return 3  # 默认波动市场
        
        features = self.extract_features(df)
        if len(features) == 0:
            return 3
        
        features_scaled = self.scaler.transform(features.iloc[-1:])
        prediction = self.model.predict(features_scaled)[0]
        
        return prediction

class DynamicGridStrategy:
    """动态网格交易策略"""
    
    def __init__(self, initial_capital=100000):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.position = 0
        self.trades = []
        self.grid_levels = []
        self.stop_loss = None
        
    def calculate_grid_params(self, market_type, current_price, volatility):
        """根据市场类型计算网格参数"""
        if market_type == 0:  # 上涨市场
            grid_spacing = max(0.005, volatility * 2)  # 0.5%-2%
            num_grids = 5
            position_ratio = 0.8
            stop_loss_pct = 0.05
            
        elif market_type == 1:  # 横盘市场
            grid_spacing = max(0.001, volatility * 0.5)  # 0.1%-0.3%
            num_grids = 10
            position_ratio = 0.7
            stop_loss_pct = 0.03
            
        elif market_type == 2:  # 下跌市场
            grid_spacing = max(0.01, volatility * 1.5)  # 1%-3%
            num_grids = 8
            position_ratio = 0.5
            stop_loss_pct = 0.05
            
        else:  # 波动市场
            grid_spacing = max(0.003, volatility)  # 0.3%-1%
            num_grids = 6
            position_ratio = 0.6
            stop_loss_pct = 0.04
            
        return grid_spacing, num_grids, position_ratio, stop_loss_pct
    
    def setup_grids(self, current_price, grid_spacing, num_grids):
        """设置网格层级"""
        grids = []
        for i in range(-num_grids // 2, num_grids // 2 + 1):
            price = current_price * (1 + i * grid_spacing)
            grids.append({
                'price': price,
                'type': 'buy' if i <= 0 else 'sell',
                'filled': False
            })
        return grids
    
    def calculate_position_size(self, market_type, current_price, volatility):
        """计算仓位大小"""
        grid_spacing, num_grids, position_ratio, _ = self.calculate_grid_params(
            market_type, current_price, volatility
        )
        
        # 每个网格的仓位
        capital_per_grid = self.capital * position_ratio / num_grids
        position_size = capital_per_grid / current_price
        
        return position_size
    
    def execute_trade(self, price, volume, trade_type, timestamp):
        """执行交易"""
        cost = price * volume
        
        if trade_type == 'buy':
            if cost <= self.capital:
                self.capital -= cost
                self.position += volume
                self.trades.append({
                    'timestamp': timestamp,
                    'type': 'buy',
                    'price': price,
                    'volume': volume,
                    'cost': cost
                })
                return True
        else:  # sell
            if volume <= self.position:
                self.capital += cost
                self.position -= volume
                self.trades.append({
                    'timestamp': timestamp,
                    'type': 'sell',
                    'price': price,
                    'volume': volume,
                    'revenue': cost
                })
                return True
        
        return False
    
    def check_stop_loss(self, current_price, stop_loss_pct, entry_price):
        """检查止损"""
        if entry_price > 0:
            loss_pct = (current_price - entry_price) / entry_price
            if loss_pct <= -stop_loss_pct:
                return True
        return False

class KeyLevelAnalyzer:
    """关键点位分析器"""
    
    def __init__(self):
        self.support_levels = []
        self.resistance_levels = []
        
    def find_support_resistance(self, df, lookback=50):
        """寻找支撑位和压力位"""
        close = df['close'].values
        high = df['high'].values
        low = df['low'].values
        
        # 使用局部极值点
        from scipy.signal import argrelextrema
        
        # 寻找局部最小值（支撑位）
        local_min = argrelextrema(low, np.less, order=5)[0]
        self.support_levels = low[local_min][-5:] if len(local_min) > 0 else [np.min(low[-20:])]
        
        # 寻找局部最大值（压力位）
        local_max = argrelextrema(high, np.greater, order=5)[0]
        self.resistance_levels = high[local_max][-5:] if len(local_max) > 0 else [np.max(high[-20:])]
        
        return self.support_levels, self.resistance_levels
    
    def fibonacci_levels(self, high, low):
        """计算斐波那契回撤位"""
        diff = high - low
        levels = {
            '0.236': high - diff * 0.236,
            '0.382': high - diff * 0.382,
            '0.5': high - diff * 0.5,
            '0.618': high - diff * 0.618,
            '0.786': high - diff * 0.786
        }
        return levels
    
    def vwap(self, df):
        """计算成交量加权平均价"""
        vwap = (df['close'] * df['volume']).sum() / df['volume'].sum()
        return vwap

class AdaptiveTradingSystem:
    """自适应交易系统"""
    
    def __init__(self, initial_capital=100000):
        self.classifier = MarketClassifier()
        self.strategy = DynamicGridStrategy(initial_capital)
        self.analyzer = KeyLevelAnalyzer()
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.reserve_capital = initial_capital * 0.2  # 风险储备金
        self.available_capital = initial_capital * 0.8
        self.entry_price = 0
        self.current_market_type = 3
        
    def update_market_type(self, df):
        """更新市场类型"""
        if len(df) > 60:
            self.classifier.train(df)
            self.current_market_type = self.classifier.predict(df)
        return self.current_market_type
    
    def calculate_dynamic_position(self, market_type, current_price, volatility):
        """计算动态仓位"""
        # 基础仓位
        base_position = self.strategy.calculate_position_size(
            market_type, current_price, volatility
        )
        
        # 根据市场类型调整
        if market_type == 0:  # 上涨市场 - 激进
            multiplier = 1.2
        elif market_type == 1:  # 横盘市场 - 中等
            multiplier = 1.0
        elif market_type == 2:  # 下跌市场 - 保守
            multiplier = 0.6
        else:  # 波动市场 - 适中
            multiplier = 0.8
            
        return base_position * multiplier
    
    def execute_strategy(self, df, current_price, timestamp):
        """执行策略"""
        # 更新市场类型
        market_type = self.update_market_type(df)
        
        # 计算波动率
        volatility = df['close'].pct_change().rolling(20).std().iloc[-1]
        
        # 获取关键点位
        supports, resistances = self.analyzer.find_support_resistance(df)
        fib_levels = self.analyzer.fibonacci_levels(
            df['high'].max(), df['low'].min()
        )
        
        # 计算网格参数
        grid_spacing, num_grids, position_ratio, stop_loss_pct = \
            self.strategy.calculate_grid_params(market_type, current_price, volatility)
        
        # 设置网格
        grids = self.strategy.setup_grids(current_price, grid_spacing, num_grids)
        
        # 计算仓位
        position_size = self.calculate_dynamic_position(
            market_type, current_price, volatility
        )
        
        # 执行交易逻辑
        trades_executed = []
        
        for grid in grids:
            if not grid['filled']:
                # 检查价格是否触及网格
                if grid['type'] == 'buy' and current_price <= grid['price']:
                    if self.strategy.execute_trade(
                        current_price, position_size, 'buy', timestamp
                    ):
                        grid['filled'] = True
                        trades_executed.append({
                            'type': 'buy',
                            'price': current_price,
                            'volume': position_size
                        })
                        self.entry_price = current_price if self.entry_price == 0 else \
                            (self.entry_price + current_price) / 2
                        
                elif grid['type'] == 'sell' and current_price >= grid['price']:
                    if self.strategy.execute_trade(
                        current_price, position_size, 'sell', timestamp
                    ):
                        grid['filled'] = True
                        trades_executed.append({
                            'type': 'sell',
                            'price': current_price,
                            'volume': position_size
                        })
        
        # 检查止损
        if self.strategy.check_stop_loss(current_price, stop_loss_pct, self.entry_price):
            # 平仓止损
            if self.strategy.position > 0:
                self.strategy.execute_trade(
                    current_price, self.strategy.position, 'sell', timestamp
                )
                trades_executed.append({
                    'type': 'stop_loss',
                    'price': current_price,
                    'volume': self.strategy.position
                })
                self.entry_price = 0
        
        return trades_executed
    
    def get_performance_metrics(self):
        """获取性能指标"""
        total_trades = len(self.strategy.trades)
        if total_trades == 0:
            return {
                'total_return': 0,
                'sharpe_ratio': 0,
                'win_rate': 0,
                'max_drawdown': 0,
                'total_trades': 0
            }
        
        # 计算收益率（FIX T5b-20261020：真账本在 DynamicGridStrategy.capital，
        # AdaptiveTradingSystem.capital 是初始副本恒 100000，用它计算恒为 0）
        total_return = (self.strategy.capital - self.initial_capital) / self.initial_capital
        
        # 计算胜率
        winning_trades = [t for t in self.strategy.trades if t['type'] == 'sell']
        win_rate = len(winning_trades) / total_trades if total_trades > 0 else 0
        
        # 计算最大回撤
        capital_history = [self.initial_capital]
        for trade in self.strategy.trades:
            if trade['type'] == 'buy':
                capital_history.append(capital_history[-1] - trade['cost'])
            else:
                capital_history.append(capital_history[-1] + trade['revenue'])
        
        max_drawdown = 0
        peak = capital_history[0]
        for value in capital_history:
            if value > peak:
                peak = value
            drawdown = (peak - value) / peak
            max_drawdown = max(max_drawdown, drawdown)
        
        return {
            'total_return': total_return,
            'win_rate': win_rate,
            'max_drawdown': max_drawdown,
            'total_trades': total_trades,
            'current_position': self.strategy.position,
            'available_capital': self.strategy.capital
        }

    def get_param_space(self) -> dict:
        """获取各市场类型grid_spacing/num_grids/position_ratio搜索空间"""
        return {
            'uptrend_grid_spacing': {'type': 'uniform', 'min': 0.003, 'max': 0.03, 'default': 0.01},
            'uptrend_num_grids': {'type': 'int_uniform', 'min': 3, 'max': 10, 'default': 5},
            'uptrend_position_ratio': {'type': 'uniform', 'min': 0.5, 'max': 1.0, 'default': 0.8},
            'sideways_grid_spacing': {'type': 'uniform', 'min': 0.0005, 'max': 0.005, 'default': 0.0015},
            'sideways_num_grids': {'type': 'int_uniform', 'min': 5, 'max': 15, 'default': 10},
            'sideways_position_ratio': {'type': 'uniform', 'min': 0.4, 'max': 0.9, 'default': 0.7},
            'downtrend_grid_spacing': {'type': 'uniform', 'min': 0.005, 'max': 0.04, 'default': 0.015},
            'downtrend_num_grids': {'type': 'int_uniform', 'min': 3, 'max': 12, 'default': 8},
            'downtrend_position_ratio': {'type': 'uniform', 'min': 0.2, 'max': 0.7, 'default': 0.5},
            'volatile_grid_spacing': {'type': 'uniform', 'min': 0.002, 'max': 0.015, 'default': 0.005},
            'volatile_num_grids': {'type': 'int_uniform', 'min': 3, 'max': 10, 'default': 6},
            'volatile_position_ratio': {'type': 'uniform', 'min': 0.3, 'max': 0.8, 'default': 0.6},
        }

    def get_adaptive_params(self, market_type: int, volatility: float) -> dict:
        """根据市场分类结果动态调整网格参数"""
        base = {
            0: {'grid_spacing': 0.01, 'num_grids': 5, 'position_ratio': 0.8},
            1: {'grid_spacing': 0.002, 'num_grids': 10, 'position_ratio': 0.7},
            2: {'grid_spacing': 0.015, 'num_grids': 8, 'position_ratio': 0.5},
            3: {'grid_spacing': 0.005, 'num_grids': 6, 'position_ratio': 0.6},
        }
        params = base.get(market_type, base[3]).copy()
        if volatility > 0.03:
            params['grid_spacing'] *= 1.5
            params['position_ratio'] *= 0.7
        elif volatility < 0.01:
            params['grid_spacing'] *= 0.7
            params['position_ratio'] *= 1.2
        params['position_ratio'] = max(0.2, min(1.0, params['position_ratio']))
        return params

    def apply_adaptive_params(self, params: dict):
        """应用自适应参数"""
        self._adaptive_params = params

    def update_price(self, current_price: float, data=None) -> dict:
        """FIX T5-20261020 协议接口：逐bar驱动（状态化网格）。
        与 execute_strategy 批处理不同：网格状态持久保持（_grids），
        避免每 bar 重建网格导致同一价位重复触发买入/卖出。
        资金以 DynamicGridStrategy.capital 为真账本（AdaptiveTradingSystem.capital 是初始副本）。"""
        if data is not None and hasattr(data, 'columns'):
            self._df = data
        df = getattr(self, '_df', None)
        if df is None or len(df) < 30:
            return {'action': 'hold', 'price': current_price,
                    'balance': self.strategy.capital, 'position': self.strategy.position,
                    'signal': 'neutral'}
        ts = df.index[-1]
        # 市场类型与波动率（复用现有逻辑）
        market_type = self.update_market_type(df)
        vol = df['close'].pct_change().rolling(20).std().iloc[-1]
        if vol is None or (hasattr(vol, 'item') and np.isnan(float(vol))):
            vol = 0.0
        vol = float(vol) if not np.isnan(float(vol)) else 0.0
        # 网格初始化（首次）或平仓后重建
        grids = getattr(self, '_grids', None)
        if not grids:
            params = self.get_adaptive_params(market_type, vol)
            self._stop_loss_pct = {0: 0.05, 1: 0.03, 2: 0.05}.get(market_type, 0.04)
            self._grids = self.strategy.setup_grids(current_price, params['grid_spacing'], params['num_grids'])
            grids = self._grids
        action = 'hold'
        qty = 0.0
        position_size = self.calculate_dynamic_position(market_type, current_price, vol)
        for g in grids:
            if g['filled']:
                continue
            if g['type'] == 'buy' and current_price <= g['price']:
                if self.strategy.execute_trade(current_price, position_size, 'buy', ts):
                    g['filled'] = True
                    action = 'buy'
                    qty = position_size
                    self.entry_price = current_price if self.entry_price == 0 else \
                        (self.entry_price + current_price) / 2
                    break
            elif g['type'] == 'sell' and current_price >= g['price'] and self.strategy.position > 0:
                sell_qty = min(position_size, self.strategy.position)
                if self.strategy.execute_trade(current_price, sell_qty, 'sell', ts):
                    g['filled'] = True
                    action = 'sell'
                    qty = sell_qty
                    break
        # 止损（无网格触发时）
        if action == 'hold' and self.strategy.position > 0:
            if self.strategy.check_stop_loss(current_price, self._stop_loss_pct, self.entry_price):
                self.strategy.execute_trade(current_price, self.strategy.position, 'sell', ts)
                action = 'sell'
                qty = self.strategy.position
                self.entry_price = 0
                self._grids = None  # 平仓后重建网格
        # 网格全部成交则重置（新一轮网格）
        if grids and all(g['filled'] for g in grids):
            self._grids = None
        return {'action': action, 'price': current_price, 'quantity': qty,
                'balance': self.strategy.capital, 'position': self.strategy.position,
                'signal': action}

def backtest_strategy(data, initial_capital=100000):
    """回测策略（FIX T5b-20261020：改用状态化 update_price 逐bar驱动。
    原 execute_strategy 批处理每 bar 重建网格（filled 全重置）→ 价格持续低于
    buy 网格时每 bar 重复买入，资金打爆且永不卖出；实测 180 bar 买 120 次、
    资金 100000 → 7.03。update_price 状态化网格买卖平衡、资金健康。）"""
    system = AdaptiveTradingSystem(initial_capital)
    results = []

    for i in range(60, len(data)):  # 需要至少60个数据点训练分类器
        df_window = data.iloc[:i+1]
        current_price = data['close'].iloc[i]
        timestamp = data.index[i]

        # 状态化逐bar驱动（复用 T5-20261020 协议接口）
        r = system.update_price(float(current_price), df_window)
        if r['action'] in ('buy', 'sell'):
            results.append({
                'timestamp': timestamp,
                'price': current_price,
                'trade_type': r['action'],
                'volume': r['quantity'],
                'capital': system.strategy.capital,
                'position': system.strategy.position
            })

    # 计算最终性能（真账本）
    performance = system.get_performance_metrics()

    return results, performance

# 示例使用
if __name__ == "__main__":
    # 生成示例数据
    np.random.seed(42)
    dates = pd.date_range('2023-01-01', periods=500, freq='H')
    
    # 创建不同市场类型的数据
    trend = np.linspace(0, 0.3, 500)  # 上涨趋势
    noise = np.random.randn(500) * 0.02
    price = 100 * (1 + trend + noise)
    
    data = pd.DataFrame({
        'open': price * (1 + np.random.randn(500) * 0.005),
        'high': price * (1 + abs(np.random.randn(500)) * 0.01),
        'low': price * (1 - abs(np.random.randn(500)) * 0.01),
        'close': price,
        'volume': np.random.randint(1000, 10000, 500)
    }, index=dates)
    
    # 运行回测
    results, performance = backtest_strategy(data)
    
    print("=== 策略回测结果 ===")
    print(f"总收益率: {performance['total_return']*100:.2f}%")
    print(f"胜率: {performance['win_rate']*100:.2f}%")
    print(f"最大回撤: {performance['max_drawdown']*100:.2f}%")
    print(f"总交易次数: {performance['total_trades']}")
    print(f"当前仓位: {performance['current_position']:.2f}")
    print(f"可用资金: {performance['available_capital']:.2f}")