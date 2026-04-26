# -*- coding: utf-8 -*-
"""
分钟级自适应网格混合策略 - 终极优化版
基于豆包专家方案实现
"""

import pandas as pd
import numpy as np
import talib as ta

class MinuteAdaptiveGridStrategyV3:
    """分钟级自适应网格混合策略 - 终极优化版"""
    def __init__(self, time_frame=5):
        """初始化策略
        
        Args:
            time_frame: 时间周期（分钟）
        """
        self.name = f"{time_frame}分钟自适应网格混合策略-终极优化版"
        self.time_frame = time_frame
        
        # 策略参数
        self.base_coeff_up = 0.0028
        self.base_coeff_down = 0.0040
        self.base_coeff_sideway = 0.0016
        self.base_coeff_highvol = 0.0050
        
        self.win_rate = 0.58
        self.pl_ratio = 2.0
        self.max_total_pos = 0.6
        self.long_trend_period = 60  # 长周期趋势过滤周期
        
        # 策略变量
        self.current_state = "sideway"
        self.current_step = 0.0
        self.current_pos_ratio = 0.0
        self.current_mdd = 0.0
        self.is_bear_market = False  # 熊市标记
        
        # 资金曲线用于回撤计算
        self.capital_series = []
    
    def calculate_indicators(self, df):
        """计算技术指标
        
        Args:
            df: 包含OHLCV数据的DataFrame
            
        Returns:
            计算好的指标字典
        """
        close = df['close'].values
        high = df['high'].values
        low = df['low'].values
        
        ema8 = ta.EMA(close, 8)
        ema20 = ta.EMA(close, 20)
        ema60 = ta.EMA(close, self.long_trend_period)  # 长周期EMA
        adx = ta.ADX(high, low, close, 9)
        atr = ta.ATR(high, low, close, 7)
        atr_mean = ta.MA(atr, 30)
        bb_mid = ta.MA(close, 20)
        bb_std = ta.STDDEV(close, 20)
        
        last_price = close[-1]
        last_atr = atr[-1]
        last_atr_mean = atr_mean[-1]
        last_adx = adx[-1]
        last_ema8 = ema8[-1]
        last_ema20 = ema20[-1]
        last_ema60 = ema60[-1]
        atr_ratio = last_atr / last_atr_mean if last_atr_mean > 0 else 1.0
        
        return {
            'close': close,
            'high': high,
            'low': low,
            'last_price': last_price,
            'last_atr': last_atr,
            'last_atr_mean': last_atr_mean,
            'last_adx': last_adx,
            'last_ema8': last_ema8,
            'last_ema20': last_ema20,
            'last_ema60': last_ema60,
            'atr_ratio': atr_ratio,
            'bb_mid': bb_mid,
            'bb_std': bb_std
        }
    
    def detect_bear_market(self, indicators):
        """检测熊市
        
        Args:
            indicators: 技术指标字典
            
        Returns:
            是否为熊市
        """
        close = indicators['close']
        last_price = indicators['last_price']
        last_ema60 = indicators['last_ema60']
        ema60 = ta.EMA(close, self.long_trend_period)
        
        if len(ema60) > 1:
            ema60_slope = last_ema60 - ema60[-2]
            if last_price < last_ema60 and ema60_slope < 0:
                return True
        return False
    
    def determine_market_state(self, indicators):
        """判断市场状态
        
        Args:
            indicators: 技术指标字典
            
        Returns:
            市场状态（up/down/sideway/high_vol）
        """
        atr_ratio = indicators['atr_ratio']
        last_adx = indicators['last_adx']
        last_ema8 = indicators['last_ema8']
        last_ema20 = indicators['last_ema20']
        
        if atr_ratio > 1.4:
            return "high_vol"
        elif last_adx >= 22:
            if last_ema8 > last_ema20:
                return "up"
            else:
                return "down"
        else:
            return "sideway"
    
    def calculate_dynamic_step(self, indicators, market_state):
        """计算动态步长
        
        Args:
            indicators: 技术指标字典
            market_state: 市场状态
            
        Returns:
            动态步长
        """
        last_price = indicators['last_price']
        atr_ratio = indicators['atr_ratio']
        
        base_map = {
            "up": self.base_coeff_up,
            "down": self.base_coeff_down,
            "sideway": self.base_coeff_sideway,
            "high_vol": self.base_coeff_highvol
        }
        base = base_map[market_state]
        vol_mult = atr_ratio
        step = last_price * base * vol_mult
        step = max(step, last_price * 0.001)  # 最小步长0.1%
        
        return step
    
    def calculate_dynamic_position(self, capital, mdd, market_state):
        """计算动态仓位
        
        Args:
            capital: 当前资金
            mdd: 当前最大回撤
            market_state: 市场状态
            
        Returns:
            动态仓位比例
        """
        # 计算凯利公式
        kelly = (self.win_rate * (self.pl_ratio + 1) - 1) / self.pl_ratio
        
        # 市场状态乘数
        mult_map = {"up": 1.0, "down": 1.0, "sideway": 0.6, "high_vol": 0.4}
        mult = mult_map[market_state]
        
        # 回撤调整因子
        if mdd > 0.08:
            mdd_scale = 0.3
        elif mdd > 0.05:
            mdd_scale = 0.7
        else:
            mdd_scale = 1.0
        
        # 计算最终仓位比例
        pos_ratio = kelly * mult * mdd_scale
        pos_ratio = max(0.0, min(pos_ratio, self.max_total_pos))
        
        return pos_ratio
    
    def generate_signal(self, indicators, market_state, is_bear_market, current_pos):
        """生成交易信号
        
        Args:
            indicators: 技术指标字典
            market_state: 市场状态
            is_bear_market: 是否为熊市
            current_pos: 当前持仓
            
        Returns:
            交易信号（1:买入/平空, -1:卖出/做空, 0:无操作）
        """
        close = indicators['close']
        last_price = indicators['last_price']
        last_ema8 = indicators['last_ema8']
        last_ema20 = indicators['last_ema20']
        bb_mid = indicators['bb_mid']
        bb_std = indicators['bb_std']
        
        signal = 0
        
        if is_bear_market:
            # 熊市模式：只做空，不做多
            if market_state == "down":
                # 下跌趋势，顺势做空
                if last_ema8 < last_ema20 and close[-1] < close[-2]:
                    signal = -1
            elif market_state == "sideway":
                # 熊市横盘，高空低平
                bb_upper = bb_mid[-1] + bb_std[-1]
                bb_lower = bb_mid[-1] - bb_std[-1]
                if last_price > bb_upper:
                    signal = -1  # 上轨做空
                elif last_price < bb_lower and current_pos < 0:
                    signal = 1  # 下轨平空
            elif market_state == "high_vol":
                signal = 0
        else:
            # 正常模式：原模型的逻辑，只做多
            if market_state == "up":
                if last_ema8 > last_ema20 and close[-1] > close[-2]:
                    signal = 1
            elif market_state == "sideway":
                bb_upper = bb_mid[-1] + bb_std[-1]
                bb_lower = bb_mid[-1] - bb_std[-1]
                if last_price < bb_lower:
                    signal = 1
                elif last_price > bb_upper and current_pos > 0:
                    signal = -1
            elif market_state == "high_vol":
                signal = 0
            elif market_state == "down":
                signal = 0
        
        return signal
    
    def get_signal(self, df, current_pos=0, capital=100000):
        """获取交易信号
        
        Args:
            df: 包含OHLCV数据的DataFrame
            current_pos: 当前持仓
            capital: 当前资金
            
        Returns:
            交易信号（1:买入/平空, -1:卖出/做空, 0:无操作）
        """
        if len(df) < 60:
            return 0
        
        # 计算指标
        indicators = self.calculate_indicators(df)
        
        # 更新资金曲线与回撤
        self.capital_series.append(capital)
        if len(self.capital_series) > 30:
            self.capital_series.pop(0)
        peak = max(self.capital_series) if self.capital_series else capital
        self.current_mdd = (peak - capital) / peak if peak > 0 else 0
        
        # 检测熊市
        self.is_bear_market = self.detect_bear_market(indicators)
        
        # 判断市场状态
        self.current_state = self.determine_market_state(indicators)
        
        # 计算动态步长
        self.current_step = self.calculate_dynamic_step(indicators, self.current_state)
        
        # 计算动态仓位
        self.current_pos_ratio = self.calculate_dynamic_position(capital, self.current_mdd, self.current_state)
        
        # 生成交易信号
        signal = self.generate_signal(indicators, self.current_state, self.is_bear_market, current_pos)
        
        return signal
    
    def get_position_size(self, capital, price):
        """获取目标仓位大小
        
        Args:
            capital: 当前资金
            price: 当前价格
            
        Returns:
            目标仓位大小
        """
        if self.is_bear_market:
            # 熊市目标仓位是负的（做空）
            target_pos = -self.current_pos_ratio * capital / price
        else:
            # 正常目标仓位是正的（做多）
            target_pos = self.current_pos_ratio * capital / price
        
        return target_pos
    
    def get_grid_step(self, df):
        """获取网格步长
        
        Args:
            df: 包含OHLCV数据的DataFrame
            
        Returns:
            网格步长
        """
        if len(df) < 60:
            return 0
        
        indicators = self.calculate_indicators(df)
        self.current_state = self.determine_market_state(indicators)
        self.current_step = self.calculate_dynamic_step(indicators, self.current_state)
        
        return self.current_step

# 测试函数
def test_strategy():
    """测试策略性能"""
    import numpy as np
    import pandas as pd
    
    # 生成模拟数据
    def generate_simulated_data(days=200, time_frame=5):
        np.random.seed(42)
        # 生成分钟级数据
        minutes_per_day = 24 * 60 // time_frame
        total_minutes = days * minutes_per_day
        dates = pd.date_range(start='2023-01-01', periods=total_minutes, freq=f'{time_frame}min')
        
        # 生成基础价格走势
        base_trend = np.linspace(100, 120, total_minutes)  # 基础上涨趋势
        
        # 添加不同市场类型的波动
        volatility = np.zeros(total_minutes)
        
        # 横盘市场
        volatility[0:50*minutes_per_day] = 0.001
        
        # 上涨市场
        volatility[50*minutes_per_day:100*minutes_per_day] = 0.002
        base_trend[50*minutes_per_day:100*minutes_per_day] = np.linspace(105, 140, 50*minutes_per_day)
        
        # 下跌市场
        volatility[100*minutes_per_day:150*minutes_per_day] = 0.002
        base_trend[100*minutes_per_day:150*minutes_per_day] = np.linspace(140, 110, 50*minutes_per_day)
        
        # 波动市场
        volatility[150*minutes_per_day:200*minutes_per_day] = 0.004
        base_trend[150*minutes_per_day:200*minutes_per_day] = np.linspace(110, 130, 50*minutes_per_day)
        
        # 生成价格
        returns = np.random.normal(0, volatility, total_minutes)
        prices = base_trend * np.exp(np.cumsum(returns))
        
        # 生成成交量
        volumes = np.random.randint(1000000, 10000000, total_minutes)
        
        # 创建DataFrame
        df = pd.DataFrame({
            'open': prices,
            'high': prices * (1 + np.random.uniform(0, 0.002, total_minutes)),
            'low': prices * (1 - np.random.uniform(0, 0.002, total_minutes)),
            'close': prices,
            'volume': volumes
        }, index=dates)
        
        return df
    
    # 生成5分钟数据
    df = generate_simulated_data(days=20, time_frame=5)
    print(f"生成了 {len(df)} 根 {5}分钟K线数据")
    print(f"价格范围: {df.close.min():.2f} - {df.close.max():.2f}")
    
    # 初始化策略
    strategy = MinuteAdaptiveGridStrategyV3(time_frame=5)
    
    # 模拟交易
    capital = 100000
    position = 0
    position_cost = 0
    trades = 0
    wins = 0
    equity_curve = []
    
    for i in range(60, len(df)):
        window = df.iloc[i-60:i+1]
        signal = strategy.get_signal(window, position, capital)
        current_price = window.close.iloc[-1]
        
        # 计算目标仓位
        target_pos = strategy.get_position_size(capital, current_price)
        
        # 执行交易
        if signal == 1 and position < target_pos:
            # 买入/平空
            buy_vol = target_pos - position
            if buy_vol > 0:
                capital -= buy_vol * current_price
                position += buy_vol
                position_cost = current_price
                trades += 1
                print(f"买入/平空：{buy_vol:.2f}股，价格：{current_price:.2f}")
        elif signal == -1 and position > target_pos:
            # 卖出/做空
            sell_vol = position - target_pos
            if sell_vol > 0:
                profit = (current_price - position_cost) * sell_vol
                if profit > 0:
                    wins += 1
                capital += sell_vol * current_price
                position -= sell_vol
                trades += 1
                print(f"卖出/做空：{sell_vol:.2f}股，价格：{current_price:.2f}")
        
        # 记录资金曲线
        total_equity = capital + (position * current_price if position != 0 else 0)
        equity_curve.append(total_equity)
    
    # 计算指标
    final_capital = equity_curve[-1] if equity_curve else capital
    total_return = (final_capital - 100000) / 100000
    win_rate = wins / trades if trades > 0 else 0
    
    # 计算夏普比率
    returns = np.diff(equity_curve) / equity_curve[:-1]
    sharpe_ratio = np.mean(returns) / np.std(returns) * np.sqrt(252 * 24 * 60 / 5) if len(returns) > 0 else 0
    
    # 计算最大回撤
    peak = equity_curve[0]
    max_drawdown = 0
    for equity in equity_curve:
        if equity > peak:
            peak = equity
        drawdown = (peak - equity) / peak
        if drawdown > max_drawdown:
            max_drawdown = drawdown
    
    print(f"\n策略测试结果:")
    print(f"策略名称: {strategy.name}")
    print(f"初始资金: 100000")
    print(f"最终资金: {final_capital:.2f}")
    print(f"总收益率: {total_return*100:.2f}%")
    print(f"总交易次数: {trades}")
    print(f"胜率: {win_rate*100:.2f}%")
    print(f"夏普比率: {sharpe_ratio:.2f}")
    print(f"最大回撤: {max_drawdown*100:.2f}%")

if __name__ == "__main__":
    test_strategy()
