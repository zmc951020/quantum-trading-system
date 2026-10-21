#!/usr/bin/env python3
"""
金碗破冰·价值潜伏策略 (Golden Bowl Ice Break · Value Ambush Strategy)
=====================================================================
融合基本面安全垫 + 技术面碗型冰线 + 盘口量化触发 的完整选股策略。

三种模式（通过 mode 参数切换）：
  value_six      — 基本面安全垫 + 六大蛰伏条件（灵敏度最高，适合震荡市）
  value_bowl     — 基本面安全垫 + 碗型冰线突破（趋势确认，适合趋势市）
  value_six_bowl — 基本面安全垫 + 六大条件 + 碗型冰线突破（最严格，当前默认）

设计理念：
  - 基本面保证即使短线被套，长期也有解套获利可能
  - 碗型冰线保证买入在主力成本区附近，而非半山腰
  - 六大条件保证买入时市场合力最强，效率最高
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Any, Tuple
from collections import deque


class GoldenBowlIceBreakStrategy:
    """
    金碗破冰·价值潜伏策略

    三种模式：
      value_six      — 基本面 + 六大蛰伏条件（无碗型/冰线要求，灵敏度最高）
      value_bowl     — 基本面 + 碗型识别 + 冰线突破（无六大条件，趋势确认）
      value_six_bowl — 基本面 + 六大条件 + 碗型冰线（全部条件，最严格）

    策略流程：
    1. 基本面初筛（ROE/PE/毛利率）
    2. 按模式分支执行碗型/六大条件/冰线突破
    3. 止损止盈风控
    """

    # ================================================================
    # 模式配置
    # ================================================================
    MODE_CONFIG = {
        "value_six": {
            "label": "六大蛰伏",
            "description": "基本面安全垫 + 六大条件触发，无需碗型/冰线，适合震荡市",
            "requires_bowl": False,
            "requires_six": True,
            "requires_ice_breakout": False,
        },
        "value_bowl": {
            "label": "碗型冰线",
            "description": "基本面安全垫 + 碗型识别 + 冰线突破，无需六大条件，适合趋势市",
            "requires_bowl": True,
            "requires_six": False,
            "requires_ice_breakout": True,
        },
        "value_six_bowl": {
            "label": "全条件共振",
            "description": "基本面 + 六大条件 + 碗型冰线，全部条件必须满足，最严格",
            "requires_bowl": True,
            "requires_six": True,
            "requires_ice_breakout": True,
        },
    }

    # ================================================================
    # 风控参数配置（可配置字典，禁止硬编码）
    # ================================================================
    RISK_CONFIG = {
        # 止损 — 冰线回破止损
        "ice_line_stop_days": 3,       # 突破后跌破冰线N天内收不回则止损
        "ice_line_stop_pct": -0.02,    # 跌破冰线幅度阈值
        # 止盈 — 阶梯止盈
        "take_profit_tier1": 0.10,     # 第一阶梯：获利10%减仓一半
        "take_profit_tier2": 0.20,     # 第二阶梯：获利20%清仓
        "trailing_stop_ma": 10,        # 趋势跟踪：收盘跌破10日均线止盈
        # 仓位
        "max_position_pct": 0.95,      # 最大仓位比例
        "single_trade_risk": 0.02,     # 单笔风险敞口
    }

    # ================================================================
    # 六大条件阈值（可通过优化器调整）
    # ================================================================
    SIX_CONDITIONS = {
        "volume_ratio_min": 1.0,       # 量比下限（日线适配，放量即可）
        "volume_ratio_max": 10.0,      # 量比上限（防止天量出货）
        "change_pct_min": 0.005,       # 涨幅下限 0.5%（日线适配）
        "change_pct_max": 0.08,        # 涨幅上限 8%（避免追高）
        "price_min": 4.0,              # 最低价格（剔除仙股）
        "turnover_min": 0.005,         # 换手率下限 0.5%（日线适配）
        "turnover_max": 0.20,          # 换手率上限 20%（避免异常）
        "amount_min": 1e7,             # 成交额下限 0.1亿（日线适配）
        "amount_max": 2e9,             # 成交额上限 20亿
        "speed_min": 0,                # 涨速 > 0（即时上涨）
    }

    # ================================================================
    # 碗型形态参数
    # ================================================================
    BOWL_CONFIG = {
        "bowl_period_short": 5,        # 短期碗型检测窗口
        "bowl_period_long": 10,        # 长期碗型检测窗口
        "bowl_depth_min": 0.05,        # 碗型最小深度（5%）
        "bowl_depth_max": 0.25,        # 碗型最大深度（25%，避免深跌）
        "volume_contraction": 0.5,     # 碗底量能萎缩比例（<均量50%）
        "volume_expansion": 1.5,       # 右侧量能放大比例（>均量150%）
        "ice_line_ma": 60,             # 冰线辅助均线
    }

    # ================================================================
    # 冰线真突破确认技术栈参数
    # ================================================================
    BREAKOUT_CONFIRM_CONFIG = {
        # 多K线确认（避免假突破，训练有素的突破至少需要2根K线确认）
        "confirmation_bars": 2,        # 连续N根K线收盘站上冰线
        # 放量确认（真正突破必须有量能配合）
        "volume_surge_ratio": 1.5,     # 突破日量能 > N倍20日均量
        "volume_ma_period": 20,        # 量能均线周期
        # 均线多头排列（趋势确认）
        "ma_bullish_short": 5,         # 短期均线
        "ma_bullish_mid": 10,          # 中期均线
        "ma_bullish_long": 20,         # 长期均线
        "require_ma_bullish": True,    # 是否要求均线多头排列
        # 背离检测（RSI顶背离则假突破概率高）
        "rsi_period": 14,              # RSI周期
        "rsi_divergence_threshold": 70, # RSI > 70 时检查顶背离
        # 突破幅度确认
        "breakout_pct_min": 0.01,      # 突破幅度至少1%（避免毛刺）
    }

    # ================================================================
    # 六大条件买入点确认参数
    # ================================================================
    ENTRY_CONFIRM_CONFIG = {
        "confirmation_bars": 2,        # 连续N根K线满足六大条件才买入
        "entry_timing": "close",       # 买入时机: close(收盘价) / next_open(次日开盘)
        "max_signals_per_period": 3,   # 单周期内最大信号数（避免频繁交易）
        "cooldown_bars": 5,            # 买入后冷却期（避免连续买入）
    }

    # ================================================================
    # 基本面筛选参数
    # ================================================================
    FUNDAMENTAL_CONFIG = {
        "roe_min": 0.10,               # ROE > 10%
        "pe_max": 30,                  # PE < 30
        "gross_margin_min": 0.20,      # 毛利率 > 20%
        "profit_growth_min": 0.15,     # 净利润增长率 > 15%
        "peg_max": 1.0,                # PEG < 1.0
        "debt_ratio_max": 0.60,        # 资产负债率 < 60%
        "market_cap_min": 50e8,        # 市值 > 50亿（避免小盘操纵）
    }

    def __init__(self, initial_balance: float = 100000,
                 mode: str = "value_six",
                 # 六大条件参数
                 volume_ratio_min: float = 1.0,
                 volume_ratio_max: float = 10.0,
                 change_pct_min: float = 0.005,
                 change_pct_max: float = 0.08,
                 price_min: float = 4.0,
                 turnover_min: float = 0.005,
                 turnover_max: float = 0.20,
                 amount_min: float = 1e7,
                 amount_max: float = 2e9,
                 # 碗型参数
                 bowl_period: int = 10,
                 bowl_depth_min: float = 0.05,
                 bowl_depth_max: float = 0.25,
                 ice_line_ma: int = 60,
                 # 风控参数
                 take_profit_tier1: float = 0.10,
                 take_profit_tier2: float = 0.20,
                 ice_line_stop_pct: float = -0.02,
                 **kwargs):
        """
        初始化金碗破冰策略

        Args:
            initial_balance: 初始资金
            mode: 策略模式 'value_six' | 'value_bowl' | 'value_six_bowl'
            volume_ratio_min: 量比下限
            volume_ratio_max: 量比上限
            change_pct_min: 涨幅下限
            change_pct_max: 涨幅上限
            price_min: 最低价格
            turnover_min: 换手率下限
            turnover_max: 换手率上限
            amount_min: 成交额下限
            amount_max: 成交额上限
            bowl_period: 碗型检测周期
            bowl_depth_min: 碗型最小深度
            bowl_depth_max: 碗型最大深度
            ice_line_ma: 冰线均线周期
            take_profit_tier1: 第一阶梯止盈比例
            take_profit_tier2: 第二阶梯止盈比例
            ice_line_stop_pct: 冰线止损幅度
        """
        self.initial_balance = initial_balance
        self.current_balance = initial_balance

        # 模式
        self.mode = mode if mode in self.MODE_CONFIG else "value_six_bowl"
        self.mode_info = self.MODE_CONFIG[self.mode]

        # 六大条件参数
        self.volume_ratio_min = volume_ratio_min
        self.volume_ratio_max = volume_ratio_max
        self.change_pct_min = change_pct_min
        self.change_pct_max = change_pct_max
        self.price_min = price_min
        self.turnover_min = turnover_min
        self.turnover_max = turnover_max
        self.amount_min = amount_min
        self.amount_max = amount_max
        self.speed_min = self.SIX_CONDITIONS["speed_min"]

        # 碗型参数
        self.bowl_period = bowl_period
        self.bowl_depth_min = bowl_depth_min
        self.bowl_depth_max = bowl_depth_max
        self.ice_line_ma = ice_line_ma

        # 风控参数
        self.take_profit_tier1 = take_profit_tier1
        self.take_profit_tier2 = take_profit_tier2
        self.ice_line_stop_pct = ice_line_stop_pct

        # 持仓状态
        self.position = 0
        self.entry_price = 0
        self.ice_line_price = 0        # 突破时的冰线价格
        self.below_ice_line_days = 0   # 跌破冰线持续天数
        self.trades: List[Dict] = []
        self.price_history: List[float] = []
        self.volume_history: List[float] = []
        self.equity_curve: List[Dict] = []

        # 信号历史
        self.signal_history: List[Dict] = []
        self.bowl_patterns: List[Dict] = []

        # 买入确认与冷却
        self._six_confirm_count: int = 0       # 六大条件连续满足计数
        self._breakout_confirm_count: int = 0  # 冰线突破连续确认计数
        self._last_buy_bar: int = 0            # 上次买入的K线序号
        self._bar_index: int = 0               # 当前K线序号
        self._trade_count: int = 0             # 已交易次数（用于max_signals限制）

        # 基本面评分缓存
        self.fundamental_score: float = 0.0
        self.fundamental_checks: Dict[str, bool] = {}

    # ================================================================
    # 核心接口
    # ================================================================

    def update_price(self, current_price: float, data: pd.Series = None):
        """更新价格并执行交易决策

        Args:
            current_price: 当前价格
            data: 历史价格序列（用于指标计算），支持DataFrame/Series
        """
        self.price_history.append(current_price)
        self._bar_index += 1

        # 提取成交量数据（signal_adapter传入DataFrame时含volume列）
        if isinstance(data, pd.DataFrame) and 'volume' in data.columns:
            vol_series = data['volume']
            if len(vol_series) > len(self.volume_history):
                self.volume_history = list(vol_series.values)
        elif isinstance(data, pd.Series) and hasattr(data, 'name') and data.name == 'volume':
            self.volume_history.append(current_price)  # 不适用，跳过

        # 计算当前权益
        if self.position > 0:
            current_equity = self.current_balance + self.position * (current_price - self.entry_price)
        else:
            current_equity = self.current_balance
        self.equity_curve.append({'price': current_price, 'equity': current_equity})

        # 需要足够历史数据才能生成信号
        if self.mode_info["requires_bowl"]:
            min_data = max(self.bowl_period + 5, self.ice_line_ma)
        else:
            min_data = 10
        if data is None or len(data) < min_data:
            return {"action": "hold", "balance": self.current_balance, "position": self.position}

        # 1. 先检查持仓管理（止损止盈）
        if self.position > 0:
            result = self._manage_position(current_price, data)
            if result:
                return result

        # 2. 冷却期检查：买入后N根K线内不开新仓
        if self._last_buy_bar > 0:
            bars_since_buy = self._bar_index - self._last_buy_bar
            if bars_since_buy < self.ENTRY_CONFIRM_CONFIG["cooldown_bars"]:
                return {"action": "hold", "balance": self.current_balance, "position": self.position}

        # 3. 最大交易次数限制
        if self._trade_count >= self.ENTRY_CONFIRM_CONFIG["max_signals_per_period"]:
            return {"action": "hold", "balance": self.current_balance, "position": self.position}

        # 4. 生成交易信号
        signal = self._get_signal_from_data(data, current_price)

        # 5. 执行交易
        if self.position == 0 and signal == 1:
            return self._execute_buy(current_price, data)
        elif self.position > 0 and signal == -1:
            return self._execute_sell(current_price, "signal_exit")

        return {"action": "hold", "balance": self.current_balance, "position": self.position}

    def get_performance(self, current_price: float = None) -> Dict[str, Any]:
        """获取策略性能指标"""
        if current_price is not None and self.position > 0:
            current_equity = self.current_balance + self.position * (current_price - self.entry_price)
        else:
            current_equity = self.current_balance

        total_return = (current_equity - self.initial_balance) / self.initial_balance * 100

        # 最大回撤
        max_drawdown = 0
        if self.equity_curve:
            eq = [e['equity'] for e in self.equity_curve]
            peak = eq[0]
            for v in eq:
                peak = max(peak, v)
                dd = (v - peak) / peak * 100
                max_drawdown = min(max_drawdown, dd)

        # 交易统计
        total_trades = len([t for t in self.trades if t['type'] == 'BUY'])
        profits = [t['profit'] for t in self.trades if t['type'] == 'SELL']
        winning_trades = sum(1 for p in profits if p > 0)
        losing_trades = sum(1 for p in profits if p <= 0)
        win_rate = (winning_trades / len(profits) * 100) if profits else 0

        # 夏普比率
        returns = []
        if len(self.equity_curve) > 1:
            for i in range(1, len(self.equity_curve)):
                prev = self.equity_curve[i - 1]['equity']
                curr = self.equity_curve[i]['equity']
                if prev > 0:
                    returns.append((curr - prev) / prev)
        sharpe = 0
        if returns:
            mean_ret = np.mean(returns)
            std_ret = np.std(returns)
            sharpe = (mean_ret / std_ret * np.sqrt(252)) if std_ret > 0 else 0

        # 盈亏比
        gross_profit = sum(p for p in profits if p > 0)
        gross_loss = abs(sum(p for p in profits if p <= 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

        return {
            "balance": current_equity,
            "initial_balance": self.initial_balance,
            "total_return": total_return,
            "max_drawdown": abs(max_drawdown),
            "sharpe_ratio": sharpe,
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "bowl_patterns_detected": len(self.bowl_patterns),
        }

    def get_signal(self, data: pd.Series) -> int:
        """获取当前交易信号

        Args:
            data: 价格序列

        Returns:
            -1: 卖出, 0: 持有, 1: 买入
        """
        # 根据模式确定最小数据需求
        if self.mode_info["requires_bowl"]:
            min_len = max(self.bowl_period + 5, self.ice_line_ma)
        else:
            min_len = 10  # value_six 模式只需10根K线
        if len(data) < min_len:
            return 0
        current_price = data.iloc[-1]
        return self._get_signal_from_data(data, current_price)

    # ================================================================
    # 碗型形态识别
    # ================================================================

    def _detect_bowl_pattern(self, data: pd.Series) -> Optional[Dict[str, Any]]:
        """检测碗型形态

        碗型特征：
        - 左侧下跌：价格从高点回落，跌幅5%-25%
        - 碗底：价格在底部横盘，成交量极度萎缩
        - 右侧上涨：价格回升，成交量温和放大
        - 冰线：左侧高点连线，突破即买入信号

        Returns:
            dict or None: {ice_line, bowl_bottom, bowl_depth, quality_score}
        """
        if len(data) < self.bowl_period + 5:
            return None

        prices = data.values
        window = min(self.bowl_period, len(prices))

        # 找局部极值
        mid = len(prices) - window // 2
        left_half = prices[-window:mid]
        right_half = prices[mid:]

        if len(left_half) < 3 or len(right_half) < 3:
            return None

        # 左侧高点
        left_high = np.max(left_half)
        left_high_idx = np.argmax(left_half)

        # 碗底最低点
        bowl_bottom = np.min(prices[-window:])
        bowl_bottom_idx = np.argmin(prices[-window:])

        # 右侧当前价格
        right_price = right_half[-1]

        # 碗型深度
        bowl_depth = (left_high - bowl_bottom) / left_high

        # 深度检查
        if not (self.bowl_depth_min <= bowl_depth <= self.bowl_depth_max):
            return None

        # 形态检查：碗底必须在左高点和右价格之间
        actual_bowl_idx = len(prices) - window + bowl_bottom_idx
        actual_left_idx = len(prices) - window + left_high_idx
        if not (actual_left_idx < actual_bowl_idx < len(prices) - 1):
            return None

        # 右侧回升幅度（至少回升碗深的40%）
        recovery = (right_price - bowl_bottom) / (left_high - bowl_bottom) if left_high > bowl_bottom else 0
        if recovery < 0.4:
            return None

        # 冰线 = 左侧高点
        ice_line = left_high

        # 质量评分（0-100）
        quality = 0
        # 深度适中（8%-15%最佳）
        if 0.08 <= bowl_depth <= 0.15:
            quality += 30
        elif 0.05 <= bowl_depth <= 0.20:
            quality += 20
        else:
            quality += 10
        # 回升幅度（60%-80%最佳，说明有蓄力）
        if 0.6 <= recovery <= 0.8:
            quality += 30
        elif 0.4 <= recovery <= 0.9:
            quality += 20
        else:
            quality += 10
        # 碗型周期（10日碗型 > 5日碗型）
        if window >= 10:
            quality += 20
        else:
            quality += 10

        return {
            "ice_line": ice_line,
            "bowl_bottom": bowl_bottom,
            "bowl_depth": bowl_depth,
            "recovery": recovery,
            "quality_score": quality,
            "window": window,
        }

    def _check_volume_profile(self, data: pd.Series, bowl_info: Dict) -> bool:
        """检查碗型量价配合

        底部量能：碗底成交量必须极度萎缩（地量）
        右侧量能：随着股价回升，成交量温和放大
        突破量能：突破冰线当天成交量必须是近5日均量的1.5倍以上
        """
        if len(self.volume_history) < 10:
            return True  # 量能数据不足，不做过滤

        window = bowl_info.get("window", self.bowl_period)
        recent_vol = self.volume_history[-window:]

        if len(recent_vol) < 5:
            return True

        avg_vol = np.mean(recent_vol)
        current_vol = recent_vol[-1]

        # 当前量能放大（突破放量）
        if current_vol < avg_vol * self.BOWL_CONFIG["volume_expansion"]:
            return False

        # 碗底量能萎缩
        mid = len(recent_vol) // 2
        bottom_vol = np.mean(recent_vol[mid - 2:mid + 2])
        if bottom_vol > avg_vol * self.BOWL_CONFIG["volume_contraction"]:
            return False

        return True

    # ================================================================
    # 冰线突破检测（增强版：多K线确认 + 放量 + 均线 + 无背离）
    # ================================================================

    def _check_ice_line_breakout(self, current_price: float, data: pd.Series,
                                 bowl_info: Dict) -> bool:
        """冰线突破初步检测（单K线级别）

        条件：
        1. 收盘价站上冰线
        2. 突破幅度 > 1%（避免毛刺）
        """
        ice_line = bowl_info["ice_line"]
        cfg = self.BREAKOUT_CONFIRM_CONFIG

        # 价格突破 + 幅度确认
        if current_price <= ice_line:
            return False
        if (current_price - ice_line) / ice_line < cfg["breakout_pct_min"]:
            return False

        return True

    def _confirm_breakout_real(self, current_price: float, data: pd.Series,
                               bowl_info: Dict) -> bool:
        """冰线真突破综合确认（多K线 + 量能 + 均线 + 背离）

        技术栈：
        1. 多K线确认：连续N根K线收盘站上冰线（避免假突破）
        2. 放量确认：突破日量能 > 1.5倍 20日均量（主力资金介入）
        3. 均线多头排列：5MA > 10MA > 20MA（趋势向上）
        4. RSI背离检测：RSI > 70时检查顶背离（避免诱多）

        Returns:
            True: 真突破确认 | False: 假突破/未确认
        """
        cfg = self.BREAKOUT_CONFIRM_CONFIG
        ice_line = bowl_info["ice_line"]

        # ---- 1. 多K线确认：连续N根K线收盘站上冰线 ----
        if current_price > ice_line:
            self._breakout_confirm_count += 1
        else:
            self._breakout_confirm_count = 0

        if self._breakout_confirm_count < cfg["confirmation_bars"]:
            return False

        # ---- 2. 放量确认：突破日量能 > 1.5倍 20日均量 ----
        if len(self.volume_history) >= cfg["volume_ma_period"]:
            recent_vol = self.volume_history[-cfg["volume_ma_period"]:]
            avg_vol_20 = np.mean(recent_vol)
            current_vol = self.volume_history[-1]
            if current_vol < avg_vol_20 * cfg["volume_surge_ratio"]:
                self.signal_history.append({
                    "type": "fake_breakout_no_volume",
                    "price": current_price,
                    "ice_line": ice_line,
                    "current_vol": current_vol,
                    "avg_vol_20": avg_vol_20,
                })
                return False
        # 量能数据不足时放行（回测场景无真实量能数据）

        # ---- 3. 均线多头排列：5MA > 10MA > 20MA ----
        if cfg["require_ma_bullish"] and len(data) >= cfg["ma_bullish_long"]:
            ma5 = np.mean(data[-cfg["ma_bullish_short"]:])
            ma10 = np.mean(data[-cfg["ma_bullish_mid"]:])
            ma20 = np.mean(data[-cfg["ma_bullish_long"]:])
            if not (ma5 > ma10 > ma20):
                self.signal_history.append({
                    "type": "fake_breakout_ma_bearish",
                    "price": current_price,
                    "ice_line": ice_line,
                    "ma5": ma5, "ma10": ma10, "ma20": ma20,
                })
                return False

        # ---- 4. RSI背离检测：RSI > 70时检查顶背离 ----
        if len(data) >= cfg["rsi_period"] + 5:
            rsi = self._calc_rsi(data, cfg["rsi_period"])
            if rsi > cfg["rsi_divergence_threshold"]:
                price_high_recent = max(data[-5:])
                if price_high_recent > max(data[-10:-5]) and rsi < self._calc_rsi(data[:-5], cfg["rsi_period"]):
                    self.signal_history.append({
                        "type": "fake_breakout_rsi_divergence",
                        "price": current_price,
                        "rsi": rsi,
                    })
                    return False

        # 全部通过 → 真突破
        self.signal_history.append({
            "type": "breakout_confirmed",
            "price": current_price,
            "ice_line": ice_line,
            "confirm_bars": self._breakout_confirm_count,
        })
        return True

    def _calc_rsi(self, data: pd.Series, period: int = 14) -> float:
        """计算RSI"""
        if len(data) < period + 1:
            return 50.0
        diffs = np.diff(data[-period - 1:])
        gains = np.sum(diffs[diffs > 0])
        losses = -np.sum(diffs[diffs < 0])
        if losses == 0:
            return 100.0
        rs = gains / losses
        return 100.0 - (100.0 / (1.0 + rs))

    # ================================================================
    # 六大条件检查
    # ================================================================

    def _check_six_conditions(self, current_price: float, data: pd.Series) -> Dict[str, Any]:
        """检查六大条件

        返回每个条件的通过状态和详情
        """
        prices = data.values
        result = {"all_pass": True, "details": {}}

        # 条件1：量比 4-10
        if len(self.volume_history) >= 5:
            vol_5day_avg = np.mean(self.volume_history[-6:-1]) if len(self.volume_history) >= 6 else np.mean(self.volume_history[-5:])
            current_vol = self.volume_history[-1] if self.volume_history else 0
            volume_ratio = current_vol / vol_5day_avg if vol_5day_avg > 0 else 0
            cond1 = self.volume_ratio_min < volume_ratio < self.volume_ratio_max
        else:
            volume_ratio = 1.0
            cond1 = True  # 数据不足时不做限制
        result["details"]["volume_ratio"] = {"value": round(volume_ratio, 2), "pass": cond1}

        # 条件2：涨幅 3%-8%
        if len(prices) >= 2:
            change_pct = (prices[-1] - prices[-2]) / prices[-2] if prices[-2] > 0 else 0
            cond2 = self.change_pct_min < change_pct < self.change_pct_max
        else:
            change_pct = 0
            cond2 = True
        result["details"]["change_pct"] = {"value": round(change_pct * 100, 2), "pass": cond2}

        # 条件3：价格 > 4元
        cond3 = current_price > self.price_min
        result["details"]["price"] = {"value": round(current_price, 2), "pass": cond3}

        # 条件4：换手率 2%-20%
        if len(self.volume_history) >= 5:
            # 估算换手率（成交量/流通股本，简化处理）
            avg_vol = np.mean(self.volume_history[-5:])
            estimated_turnover = avg_vol / 1e8  # 粗略估算
            cond4 = self.turnover_min < estimated_turnover < self.turnover_max
        else:
            estimated_turnover = 0.05
            cond4 = True
        result["details"]["turnover"] = {"value": round(estimated_turnover, 4), "pass": cond4}

        # 条件5：成交额 0.5亿-20亿（volume单位：手，1手=100股）
        if len(self.volume_history) >= 1:
            current_vol = self.volume_history[-1]
            estimated_amount = current_vol * 100 * current_price  # 手→股
            cond5 = self.amount_min < estimated_amount < self.amount_max
        else:
            estimated_amount = 5e8
            cond5 = True
        result["details"]["amount"] = {"value": round(estimated_amount / 1e8, 2), "pass": cond5}

        # 条件6：涨速 > -0.5%（日线适配，允许微跌，过滤大跌）
        if len(prices) >= 3:
            speed = (prices[-1] - prices[-3]) / prices[-3] / 3 if prices[-3] > 0 else 0
            cond6 = speed > -0.001  # 允许微跌，只要不是持续下跌
        else:
            speed = 0
            cond6 = True
        result["details"]["speed"] = {"value": round(speed * 100, 4), "pass": cond6}

        # 日线适配：至少5/6条件通过（放宽，日线数据难以6/6全满足）
        passed_count = sum([cond1, cond2, cond3, cond4, cond5, cond6])
        result["all_pass"] = passed_count >= 5
        return result

    def _check_external_data_available(self) -> bool:
        """检查外部数据是否可用（量比/换手率/成交额/涨速需volume_history）"""
        return len(self.volume_history) >= 5

    def _get_offline_fallback_signal(self, data: pd.Series, current_price: float) -> int:
        """离线回退信号 — 仅用价格+成交量数据

        量比→5日均量/20日均量>2.0 | 换手率→volume/1e9 | 成交额→volume*price>50M | 涨速→(close-open)/open>0.01
        """
        prices = data.values
        if len(prices) < 20:
            return 0

        vol_ok = True
        if len(self.volume_history) >= 20:
            vol_5 = np.mean(self.volume_history[-5:])
            vol_20 = np.mean(self.volume_history[-20:])
            vol_ok = vol_20 > 0 and vol_5 / vol_20 > 1.0

        turnover_ok = True
        if len(self.volume_history) >= 1:
            est_turnover = self.volume_history[-1] / 1e9
            turnover_ok = 0.005 < est_turnover < 0.20

        amount_ok = True
        if len(self.volume_history) >= 1:
            amount_ok = self.volume_history[-1] * 100 * current_price > 1e7

        speed_ok = True
        if len(prices) >= 2:
            open_p = prices[-2]
            speed_ok = (current_price - open_p) / open_p > 0.01 if open_p > 0 else False

        price_ok = current_price > self.price_min

        change_ok = True
        if len(prices) >= 2:
            chg = (prices[-1] - prices[-2]) / prices[-2] if prices[-2] > 0 else 0
            change_ok = 0.005 < chg < self.change_pct_max

        return 1 if all([vol_ok, turnover_ok, amount_ok, speed_ok, price_ok, change_ok]) else 0

    # ================================================================
    # 信号生成
    # ================================================================

    def _get_signal_from_data(self, data, current_price: float) -> int:
        """综合信号生成 — 根据模式分支执行

        value_six:      六大条件连续N根K线满足 → 买入
        value_bowl:     碗型识别 → 冰线突破 → 真突破确认 → 买入
        value_six_bowl: 碗型 → 冰线 → 真突破确认 → 六大条件 → 买入
        """
        # 兼容 DataFrame 输入（signal_adapter传入）→ 转为 pd.Series
        if isinstance(data, pd.DataFrame):
            if 'close' in data.columns:
                data = data['close']
            else:
                data = data.iloc[:, 0]
        mode = self.mode
        confirm_bars = self.ENTRY_CONFIRM_CONFIG["confirmation_bars"]

        # ================================================================
        # 分支1: value_six — 六大条件 + 多K线确认
        # ================================================================
        if mode == "value_six":
            # 外部数据不可用时使用离线回退信号
            if not self._check_external_data_available():
                offline_signal = self._get_offline_fallback_signal(data, current_price)
                if offline_signal == 1:
                    self._six_confirm_count += 1
                else:
                    self._six_confirm_count = 0
                if self._six_confirm_count >= confirm_bars:
                    self.signal_history.append({
                        "type": "buy_signal",
                        "mode": "value_six",
                        "price": current_price,
                        "confirm_bars": self._six_confirm_count,
                        "source": "offline_fallback",
                    })
                    return 1
                return 0

            conditions = self._check_six_conditions(current_price, data)

            # 多K线确认：连续N根K线满足六大条件才买入
            if conditions["all_pass"]:
                self._six_confirm_count += 1
            else:
                self._six_confirm_count = 0

            if self._six_confirm_count >= confirm_bars:
                self.signal_history.append({
                    "type": "buy_signal",
                    "mode": "value_six",
                    "price": current_price,
                    "confirm_bars": self._six_confirm_count,
                    "conditions": conditions["details"],
                })
                return 1
            return 0

        # ================================================================
        # 分支2 & 3: value_bowl / value_six_bowl — 碗型 + 冰线 + 真突破确认
        # ================================================================
        # 1. 碗型形态识别
        bowl_info = self._detect_bowl_pattern(data)
        if bowl_info is None:
            return 0

        self.bowl_patterns.append(bowl_info)

        # 2. 冰线突破初步检测（单K线）
        if not self._check_ice_line_breakout(current_price, data, bowl_info):
            if current_price > bowl_info["ice_line"] * 0.97:
                self.signal_history.append({
                    "type": "near_breakout",
                    "mode": mode,
                    "price": current_price,
                    "ice_line": bowl_info["ice_line"],
                    "quality": bowl_info["quality_score"],
                })
            return 0

        # 3. 冰线真突破综合确认（多K线 + 放量 + 均线 + 无背离）
        if not self._confirm_breakout_real(current_price, data, bowl_info):
            return 0

        # 4. 量价配合检查（碗型内部量价关系）
        if not self._check_volume_profile(data, bowl_info):
            self.signal_history.append({
                "type": "volume_fail",
                "mode": mode,
                "price": current_price,
                "ice_line": bowl_info["ice_line"],
            })
            return 0

        # 5. value_bowl 模式到此为止 → 买入
        if mode == "value_bowl":
            self.signal_history.append({
                "type": "buy_signal",
                "mode": "value_bowl",
                "price": current_price,
                "ice_line": bowl_info["ice_line"],
                "quality": bowl_info["quality_score"],
            })
            return 1

        # 6. value_six_bowl 模式：额外检查六大条件（多K线确认）
        # 外部数据不可用时使用离线回退信号
        if not self._check_external_data_available():
            offline_signal = self._get_offline_fallback_signal(data, current_price)
            if offline_signal == 1:
                self._six_confirm_count += 1
            else:
                self._six_confirm_count = 0
            if self._six_confirm_count < confirm_bars:
                self.signal_history.append({
                    "type": "conditions_fail",
                    "mode": mode,
                    "price": current_price,
                    "confirm_bars": self._six_confirm_count,
                    "source": "offline_fallback",
                })
                return 0
            self.signal_history.append({
                "type": "buy_signal",
                "mode": "value_six_bowl",
                "price": current_price,
                "ice_line": bowl_info["ice_line"],
                "quality": bowl_info["quality_score"],
                "source": "offline_fallback",
            })
            return 1

        conditions = self._check_six_conditions(current_price, data)
        if conditions["all_pass"]:
            self._six_confirm_count += 1
        else:
            self._six_confirm_count = 0

        if self._six_confirm_count < confirm_bars:
            self.signal_history.append({
                "type": "conditions_fail",
                "mode": mode,
                "price": current_price,
                "confirm_bars": self._six_confirm_count,
                "details": conditions["details"],
            })
            return 0

        # 全部通过 → 买入信号
        self.signal_history.append({
            "type": "buy_signal",
            "mode": "value_six_bowl",
            "price": current_price,
            "ice_line": bowl_info["ice_line"],
            "quality": bowl_info["quality_score"],
            "conditions": conditions["details"],
        })
        return 1

    # ================================================================
    # 交易执行
    # ================================================================

    def _execute_buy(self, current_price: float, data: pd.Series) -> Dict:
        """执行买入"""
        pos_size = self.current_balance * self.RISK_CONFIG["max_position_pct"] / current_price
        self.position = pos_size
        self.entry_price = current_price
        self.current_balance -= pos_size * current_price
        self.ice_line_price = self._get_ice_line_from_data(data)
        self.below_ice_line_days = 0

        # 记录冷却期和交易计数
        self._last_buy_bar = self._bar_index
        self._trade_count += 1
        self._six_confirm_count = 0
        self._breakout_confirm_count = 0

        self.trades.append({
            'type': 'BUY',
            'price': current_price,
            'size': pos_size,
            'ice_line': self.ice_line_price,
        })
        return {"action": "buy", "balance": self.current_balance, "position": self.position}

    def _execute_sell(self, current_price: float, reason: str = "manual") -> Dict:
        """执行卖出"""
        if self.position <= 0:
            return {"action": "hold", "balance": self.current_balance, "position": self.position}

        profit = self.position * (current_price - self.entry_price)
        self.current_balance += self.position * current_price
        self.trades.append({
            'type': 'SELL',
            'price': current_price,
            'profit': profit,
            'reason': reason,
        })
        self.position = 0
        self.entry_price = 0
        self.ice_line_price = 0
        self.below_ice_line_days = 0
        return {"action": "sell", "balance": self.current_balance, "position": self.position, "profit": profit}

    def _manage_position(self, current_price: float, data: pd.Series) -> Optional[Dict]:
        """持仓管理：止损止盈"""
        # 兼容DataFrame输入
        if isinstance(data, pd.DataFrame):
            if 'close' in data.columns:
                price_series = data['close']
            else:
                price_series = data.iloc[:, 0]
        else:
            price_series = data

        # 阶梯止盈：第一阶梯减仓一半
        profit_pct = (current_price - self.entry_price) / self.entry_price
        if profit_pct >= self.take_profit_tier2:
            return self._execute_sell(current_price, "take_profit_tier2")
        elif profit_pct >= self.take_profit_tier1:
            # 减仓一半
            sell_size = self.position * 0.5
            profit = sell_size * (current_price - self.entry_price)
            self.current_balance += sell_size * current_price
            self.position -= sell_size
            self.trades.append({
                'type': 'SELL',
                'price': current_price,
                'profit': profit,
                'reason': 'take_profit_tier1',
            })
            return {"action": "partial_sell", "balance": self.current_balance, "position": self.position}

        # 冰线止损：跌破冰线N天收不回
        if self.ice_line_price > 0 and current_price < self.ice_line_price * (1 + self.ice_line_stop_pct):
            self.below_ice_line_days += 1
            if self.below_ice_line_days >= self.RISK_CONFIG["ice_line_stop_days"]:
                return self._execute_sell(current_price, "ice_line_stop")
        else:
            self.below_ice_line_days = 0

        # 趋势跟踪止盈：收盘跌破10日均线
        if len(price_series) >= self.RISK_CONFIG["trailing_stop_ma"]:
            ma_trail = pd.Series(price_series).rolling(self.RISK_CONFIG["trailing_stop_ma"]).mean().iloc[-1]
            if current_price < ma_trail:
                return self._execute_sell(current_price, "trailing_stop")

        return None

    def _get_ice_line_from_data(self, data: pd.Series) -> float:
        """从数据中提取当前冰线价格"""
        bowl_info = self._detect_bowl_pattern(data)
        if bowl_info:
            return bowl_info["ice_line"]
        return 0

    # ================================================================
    # 基本面评估（外部调用）
    # ================================================================

    def evaluate_fundamentals(self, fundamentals: Dict[str, float]) -> Dict[str, Any]:
        """评估基本面，计算安全评分

        Args:
            fundamentals: {
                roe, pe, gross_margin, profit_growth, peg,
                debt_ratio, market_cap
            }

        Returns:
            {score, checks, passed}
        """
        checks = {}
        score = 0

        cfg = self.FUNDAMENTAL_CONFIG

        # ROE
        checks["roe"] = fundamentals.get("roe", 0) >= cfg["roe_min"]
        score += 15 if checks["roe"] else 0

        # PE
        checks["pe"] = 0 < fundamentals.get("pe", 999) <= cfg["pe_max"]
        score += 15 if checks["pe"] else 0

        # 毛利率
        checks["gross_margin"] = fundamentals.get("gross_margin", 0) >= cfg["gross_margin_min"]
        score += 10 if checks["gross_margin"] else 0

        # 净利润增长率
        checks["profit_growth"] = fundamentals.get("profit_growth", 0) >= cfg["profit_growth_min"]
        score += 15 if checks["profit_growth"] else 0

        # PEG
        checks["peg"] = 0 < fundamentals.get("peg", 999) <= cfg["peg_max"]
        score += 15 if checks["peg"] else 0

        # 资产负债率
        checks["debt_ratio"] = fundamentals.get("debt_ratio", 1) <= cfg["debt_ratio_max"]
        score += 10 if checks["debt_ratio"] else 0

        # 市值
        checks["market_cap"] = fundamentals.get("market_cap", 0) >= cfg["market_cap_min"]
        score += 10 if checks["market_cap"] else 0

        # 行业赛道加分（可选）
        sector = fundamentals.get("sector", "")
        good_sectors = ["新能源", "高端制造", "医药生物", "大消费", "科技", "半导体"]
        if any(s in sector for s in good_sectors):
            score += 10

        self.fundamental_score = score
        self.fundamental_checks = checks

        return {
            "score": score,
            "checks": checks,
            "passed": score >= 50,  # 50分及格
            "grade": "A" if score >= 80 else "B" if score >= 60 else "C" if score >= 50 else "D",
        }

    def get_fundamental_score(self) -> float:
        """获取基本面评分"""
        return self.fundamental_score

    # ================================================================
    # 状态查询
    # ================================================================

    def get_status(self) -> Dict[str, Any]:
        """获取策略当前状态"""
        return {
            "mode": self.mode,
            "mode_label": self.mode_info["label"],
            "position": self.position,
            "entry_price": self.entry_price,
            "current_balance": self.current_balance,
            "initial_balance": self.initial_balance,
            "ice_line_price": self.ice_line_price,
            "fundamental_score": self.fundamental_score,
            "bowl_patterns_count": len(self.bowl_patterns),
            "last_signal": self.signal_history[-1] if self.signal_history else None,
            "total_trades": len([t for t in self.trades if t['type'] == 'BUY']),
        }

    def get_risk_metrics(self) -> Dict[str, float]:
        """获取风控指标"""
        perf = self.get_performance()
        return {
            "max_drawdown": perf.get("max_drawdown", 0),
            "sharpe_ratio": perf.get("sharpe_ratio", 0),
            "win_rate": perf.get("win_rate", 0),
            "profit_factor": perf.get("profit_factor", 0),
            "total_return": perf.get("total_return", 0),
        }

    # ================================================================
    # 参数持久化接口（优化参数永久继承）
    # ================================================================

    def get_optimizable_params(self) -> Dict[str, Any]:
        """返回所有可优化参数及其当前值

        供韬定律优化器读取，自动生成参数搜索空间。

        Returns:
            {param_name: current_value}
        """
        return {
            # 模式参数
            "mode": self.mode,
            # 六大条件参数
            "volume_ratio_min": self.volume_ratio_min,
            "volume_ratio_max": self.volume_ratio_max,
            "change_pct_min": self.change_pct_min,
            "change_pct_max": self.change_pct_max,
            "price_min": self.price_min,
            "turnover_min": self.turnover_min,
            "turnover_max": self.turnover_max,
            "amount_min": self.amount_min,
            "amount_max": self.amount_max,
            "speed_min": self.speed_min,
            # 碗型参数
            "bowl_period": self.bowl_period,
            "bowl_depth_min": self.bowl_depth_min,
            "bowl_depth_max": self.bowl_depth_max,
            "ice_line_ma": self.ice_line_ma,
            # 风控参数
            "take_profit_tier1": self.take_profit_tier1,
            "take_profit_tier2": self.take_profit_tier2,
            "ice_line_stop_pct": self.ice_line_stop_pct,
            "max_position_pct": self.RISK_CONFIG["max_position_pct"],
            "trailing_stop_ma": self.RISK_CONFIG["trailing_stop_ma"],
            "ice_line_stop_days": self.RISK_CONFIG["ice_line_stop_days"],
            # 确认参数
            "confirmation_bars": self.ENTRY_CONFIRM_CONFIG["confirmation_bars"],
            "cooldown_bars": self.ENTRY_CONFIRM_CONFIG["cooldown_bars"],
            "max_signals_per_period": self.ENTRY_CONFIRM_CONFIG["max_signals_per_period"],
            # 突破确认参数
            "breakout_confirmation_bars": self.BREAKOUT_CONFIRM_CONFIG["confirmation_bars"],
            "breakout_volume_surge": self.BREAKOUT_CONFIRM_CONFIG["volume_surge_ratio"],
            "require_ma_bullish": self.BREAKOUT_CONFIRM_CONFIG["require_ma_bullish"],
        }

    def get_param_space(self) -> Dict[str, list]:
        """返回参数搜索空间（供网格搜索/贝叶斯优化使用）
        
        每个参数对应一个候选值列表，优化器遍历所有组合找到最优参数。
        """
        return {
            "mode": ["value_six", "value_bowl", "value_six_bowl"],
            "volume_ratio_min": [1.0, 1.5, 2.0, 3.0],
            "volume_ratio_max": [8.0, 10.0, 12.0, 15.0],
            "change_pct_min": [0.003, 0.005, 0.01, 0.015],
            "change_pct_max": [0.06, 0.08, 0.10],
            "turnover_min": [0.003, 0.005, 0.01],
            "turnover_max": [0.15, 0.20, 0.25],
            "take_profit_tier1": [0.08, 0.10, 0.12, 0.15],
            "take_profit_tier2": [0.15, 0.20, 0.25, 0.30],
            "ice_line_stop_pct": [-0.01, -0.02, -0.03, -0.05],
            "cooldown_bars": [3, 5, 7, 10],
            "max_signals_per_period": [2, 3, 5],
            "max_position_pct": [0.80, 0.90, 0.95],
            "trailing_stop_ma": [5, 10, 15, 20],
            "ice_line_stop_days": [2, 3, 5],
            "bowl_period": [8, 10, 15, 20],
            "bowl_depth_min": [0.03, 0.05, 0.08],
            "bowl_depth_max": [0.20, 0.25, 0.30],
        }

    def get_adaptive_params(self, data: pd.Series) -> Dict[str, float]:
        """根据市场数据计算动态自适应参数
        
        核心思想：参数不应固定，而应根据市场波动率、趋势强度等动态调整。
        - ATR大 → 止盈止损放宽，避免被噪音扫出
        - ATR小 → 收紧止盈止损，锁定利润
        - 趋势强 → 放宽冷却期，允许更多交易
        - 震荡市 → 收紧冷却期，避免频繁交易
        """
        if len(data) < 20:
            return {}

        prices = data.values
        returns = np.diff(prices) / prices[:-1]
        
        # ATR计算（14周期，简化版）
        atr = np.std(returns[-14:]) if len(returns) >= 14 else np.std(returns)
        atr_pct = float(atr)
        
        # 趋势强度（20日价格变化率）
        trend = (prices[-1] - prices[-20]) / prices[-20] if len(prices) >= 20 else 0
        trend_strength = abs(trend)
        
        # 波动率分位数
        vol_percentile = min(atr_pct / 0.03, 1.0)  # 相对于3%日波动的比例
        
        # 动态止盈：ATR越大，止盈越宽
        tp1 = max(0.06, min(0.18, 0.10 + vol_percentile * 0.04))
        tp2 = max(0.12, min(0.30, 0.20 + vol_percentile * 0.06))
        
        # 动态止损：ATR越大，止损越宽
        sl_pct = max(-0.05, min(-0.01, -0.02 - vol_percentile * 0.01))
        
        # 动态冷却期：趋势强→短冷却，震荡→长冷却
        cooldown = max(3, min(10, int(5 - trend_strength * 10)))
        
        return {
            "take_profit_tier1": round(tp1, 3),
            "take_profit_tier2": round(tp2, 3),
            "ice_line_stop_pct": round(sl_pct, 3),
            "cooldown_bars": cooldown,
            "atr_pct": round(atr_pct, 4),
            "trend_strength": round(trend_strength, 4),
        }

    def apply_adaptive_params(self, data: pd.Series):
        """应用动态自适应参数到当前实例
        
        在 update_price 中每次调用前先计算动态参数。
        """
        adaptive = self.get_adaptive_params(data)
        if adaptive:
            self.take_profit_tier1 = adaptive["take_profit_tier1"]
            self.take_profit_tier2 = adaptive["take_profit_tier2"]
            self.ice_line_stop_pct = adaptive["ice_line_stop_pct"]
            self.ENTRY_CONFIRM_CONFIG["cooldown_bars"] = adaptive["cooldown_bars"]

    def apply_optimized_params(self, params: Dict[str, Any]) -> bool:
        """应用优化参数（永久继承）

        由策略管理器在优化完成后调用，将最优参数写入策略实例。

        Args:
            params: 优化后的参数字典

        Returns:
            是否成功应用
        """
        try:
            # 模式参数
            if "mode" in params and params["mode"] in self.MODE_CONFIG:
                self.mode = params["mode"]
                self.mode_info = self.MODE_CONFIG[self.mode]

            # 六大条件参数
            self.volume_ratio_min = float(params.get("volume_ratio_min", self.volume_ratio_min))
            self.volume_ratio_max = float(params.get("volume_ratio_max", self.volume_ratio_max))
            self.change_pct_min = float(params.get("change_pct_min", self.change_pct_min))
            self.change_pct_max = float(params.get("change_pct_max", self.change_pct_max))
            self.price_min = float(params.get("price_min", self.price_min))
            self.turnover_min = float(params.get("turnover_min", self.turnover_min))
            self.turnover_max = float(params.get("turnover_max", self.turnover_max))
            self.amount_min = float(params.get("amount_min", self.amount_min))
            self.amount_max = float(params.get("amount_max", self.amount_max))
            self.speed_min = float(params.get("speed_min", self.speed_min))

            # 碗型参数
            self.bowl_period = int(params.get("bowl_period", self.bowl_period))
            self.bowl_depth_min = float(params.get("bowl_depth_min", self.bowl_depth_min))
            self.bowl_depth_max = float(params.get("bowl_depth_max", self.bowl_depth_max))
            self.ice_line_ma = int(params.get("ice_line_ma", self.ice_line_ma))

            # 风控参数
            self.take_profit_tier1 = float(params.get("take_profit_tier1", self.take_profit_tier1))
            self.take_profit_tier2 = float(params.get("take_profit_tier2", self.take_profit_tier2))
            self.ice_line_stop_pct = float(params.get("ice_line_stop_pct", self.ice_line_stop_pct))
            self.RISK_CONFIG["max_position_pct"] = float(params.get("max_position_pct", self.RISK_CONFIG["max_position_pct"]))
            self.RISK_CONFIG["trailing_stop_ma"] = int(params.get("trailing_stop_ma", self.RISK_CONFIG["trailing_stop_ma"]))
            self.RISK_CONFIG["ice_line_stop_days"] = int(params.get("ice_line_stop_days", self.RISK_CONFIG["ice_line_stop_days"]))

            # 确认参数
            self.ENTRY_CONFIRM_CONFIG["confirmation_bars"] = int(params.get("confirmation_bars", self.ENTRY_CONFIRM_CONFIG["confirmation_bars"]))
            self.ENTRY_CONFIRM_CONFIG["cooldown_bars"] = int(params.get("cooldown_bars", self.ENTRY_CONFIRM_CONFIG["cooldown_bars"]))
            self.ENTRY_CONFIRM_CONFIG["max_signals_per_period"] = int(params.get("max_signals_per_period", self.ENTRY_CONFIRM_CONFIG["max_signals_per_period"]))

            # 突破确认参数
            self.BREAKOUT_CONFIRM_CONFIG["confirmation_bars"] = int(params.get("breakout_confirmation_bars", self.BREAKOUT_CONFIRM_CONFIG["confirmation_bars"]))
            self.BREAKOUT_CONFIRM_CONFIG["volume_surge_ratio"] = float(params.get("breakout_volume_surge", self.BREAKOUT_CONFIRM_CONFIG["volume_surge_ratio"]))
            self.BREAKOUT_CONFIRM_CONFIG["require_ma_bullish"] = bool(params.get("require_ma_bullish", self.BREAKOUT_CONFIRM_CONFIG["require_ma_bullish"]))

            return True
        except Exception as e:
            import traceback
            traceback.print_exc()
            return False