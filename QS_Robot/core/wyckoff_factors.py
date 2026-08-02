#!/usr/bin/env python3
"""
威科夫68维因子计算引擎 (Wyckoff Factor Engine)
================================================
为「特种兵・威科夫量价自适应策略」提供68维技术因子计算。

六组因子：
  1. 威科夫结构因子 (12维) — 吸筹/拉升/派发/下跌阶段识别
  2. 量价健康度因子 (12维) — 量价关系、供需平衡
  3. 箱体震荡因子 (12维) — 区间识别、突破概率
  4. 突破真假判别因子 (10维) — 真假突破辨别
  5. 盘口分时因子 (12维) — 分钟级攻击波、冲击波等
  6. 市场情绪强度因子 (10维) — 大盘环境、板块动量

计算策略：
  - 1-4组：基于日线数据计算，数值映射到15分钟级别
  - 5组：基于15分钟数据实时计算
  - 6组：基于外部市场数据

所有因子值归一化到 [0, 1] 或 [-1, 1] 范围。
"""

import os
import sys
import math
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field

import numpy as np

# 路径设置
current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)


# ============================================================
# 因子名称常量
# ============================================================

# 第1组：威科夫结构因子
WYCKOFF_STRUCTURE_FACTORS = [
    "wyckoff_phase",        # 0: 阶段（0吸筹/1拉升/2派发/3下跌）
    "spring_score",         # 1: 震仓强度
    "sos_score",            # 2: 强势信号
    "lps_score",            # 3: 回踩有效性
    "joc_score",            # 4: 突破强度(JOC)
    "ut_ad_score",          # 5: 诱多强度
    "sow_score",            # 6: 弱势信号
    "supply_exhausted",     # 7: 供应耗尽
    "demand_exhausted",     # 8: 需求枯竭
    "absorption_signal",    # 9: 主力吸收
    "stop_grab",            # 10: 扫止损
    "distribution_head",    # 11: 顶部盘头
]

# 第2组：量价健康度因子
VOLUME_HEALTH_FACTORS = [
    "volume_trend_health",  # 12: 量价健康度
    "up_vol_ratio",         # 13: 上涨放量比
    "down_vol_ratio",       # 14: 下跌缩量比
    "effort_result",        # 15: 努力vs结果
    "volume_ma5_dev",       # 16: 5日均量偏离
    "volume_ma20_dev",      # 17: 20日均量偏离
    "large_volume_signal",  # 18: 巨量信号
    "no_demand",            # 19: 无需求
    "no_supply",            # 20: 无供应
    "volume_trend_angle",   # 21: 量能趋势角度
    "vol_price_corr",       # 22: 量价相关系数
    "vol_spike",            # 23: 量峰强度
]

# 第3组：箱体震荡因子
RANGE_FACTORS = [
    "range_width",          # 24: 箱体幅度
    "range_duration",       # 25: 箱体时长
    "range_upper_valid",    # 26: 上轨有效性
    "range_lower_valid",    # 27: 下轨有效性
    "price_to_upper",       # 28: 价格到上轨距离
    "price_to_lower",       # 29: 价格到下轨距离
    "ma_flat_score",        # 30: 均线走平度
    "ma_cluster_score",     # 31: 均线粘合度
    "range_vol_shrink",     # 32: 量能萎缩比例
    "range_vol_at_top",     # 33: 上轨放量
    "range_vol_at_bottom",  # 34: 下轨缩量
    "range_break_prob",     # 35: 突破概率
]

# 第4组：突破真假判别因子
BREAKOUT_FACTORS = [
    "breakout_strength",    # 36: 突破强度
    "breakout_vol_ratio",   # 37: 突破量比
    "breakout_retest_vol",  # 38: 回踩缩量
    "breakout_retest_hold", # 39: 回踩守住
    "false_breakout_score", # 40: 假突破概率
    "breakout_support_loss",# 41: 支撑失效
    "breakout_ma_confirm",  # 42: 均线确认
    "breakout_trend_confirm",#43: 趋势确认
    "breakout_depth",       # 44: 突破深度
    "breakout_rebound_speed",#45: 反弹速度
]

# 第5组：盘口分时因子
ORDER_BOOK_FACTORS = [
    "attack_wave",          # 46: 攻击波
    "shock_wave",           # 47: 冲击波
    "test_wave",            # 48: 试盘波
    "turn_back_wave",       # 49: 回头波
    "fake_rise_wave",       # 50: 假升波
    "avg_line_strength",    # 51: 均价线支撑
    "time_share_vol_peak",  # 52: 分时量峰
    "time_share_trend",     # 53: 分时趋势
    "open_position_power",  # 54: 开盘力量
    "close_position_power", # 55: 尾盘力量
    "vol_per_min",          # 56: 分钟量能分布
    "depth_vol_imbalance",  # 57: 盘口失衡
]

# 第6组：市场情绪强度因子
MARKET_SENTIMENT_FACTORS = [
    "market_trend",         # 58: 大盘趋势
    "market_volatility",    # 59: 市场波动率
    "adv_dec_ratio",        # 60: 涨跌家数比
    "limit_up_count",       # 61: 涨停数
    "sector_momentum",      # 62: 板块动量
    "sector_leader_strength",#63: 龙头强度
    "market_risk_level",    # 64: 市场风险等级
    "capm_beta",            # 65: 贝塔
    "liquidity_score",      # 66: 流动性评分
    "turnover_rate_z",      # 67: 换手率Z分数
]

# 全部68维因子名称列表
ALL_FACTOR_NAMES = (
    WYCKOFF_STRUCTURE_FACTORS +
    VOLUME_HEALTH_FACTORS +
    RANGE_FACTORS +
    BREAKOUT_FACTORS +
    ORDER_BOOK_FACTORS +
    MARKET_SENTIMENT_FACTORS
)

assert len(ALL_FACTOR_NAMES) == 68, f"因子数量应为68，实际为{len(ALL_FACTOR_NAMES)}"


# ============================================================
# 工具函数
# ============================================================

def _rolling_window(arr: np.ndarray, window: int) -> np.ndarray:
    """创建滚动窗口视图（不复制数据）"""
    if len(arr) < window:
        return np.array([])
    shape = (len(arr) - window + 1, window)
    strides = (arr.strides[0], arr.strides[0])
    return np.lib.stride_tricks.as_strided(arr, shape=shape, strides=strides)


def _sma(arr: np.ndarray, window: int) -> np.ndarray:
    """简单移动平均"""
    if len(arr) < window:
        return np.full_like(arr, np.nan)
    result = np.full_like(arr, np.nan)
    cumsum = np.cumsum(np.insert(arr, 0, 0))
    result[window-1:] = (cumsum[window:] - cumsum[:-window]) / window
    return result


def _ema(arr: np.ndarray, window: int) -> np.ndarray:
    """指数移动平均"""
    if len(arr) < 2:
        return arr.copy()
    alpha = 2.0 / (window + 1)
    result = np.zeros_like(arr)
    result[0] = arr[0]
    for i in range(1, len(arr)):
        result[i] = alpha * arr[i] + (1 - alpha) * result[i-1]
    return result


def _std(arr: np.ndarray, window: int) -> np.ndarray:
    """滚动标准差"""
    if len(arr) < window:
        return np.full_like(arr, np.nan)
    result = np.full_like(arr, np.nan)
    for i in range(window - 1, len(arr)):
        result[i] = np.std(arr[i-window+1:i+1])
    return result


def _min_max_norm(arr: np.ndarray, window: int = 60) -> np.ndarray:
    """滚动Min-Max归一化到[0,1]"""
    if len(arr) < window:
        return np.zeros_like(arr)
    result = np.zeros_like(arr)
    for i in range(window - 1, len(arr)):
        seg = arr[i-window+1:i+1]
        mn, mx = np.nanmin(seg), np.nanmax(seg)
        if mx > mn:
            result[i] = (arr[i] - mn) / (mx - mn)
        else:
            result[i] = 0.5
    result[:window-1] = result[window-1]  # 前段用第一个有效值填充
    return np.clip(result, 0, 1)


def _zscore(arr: np.ndarray, window: int = 60) -> np.ndarray:
    """滚动Z-Score"""
    ma = _sma(arr, window)
    sd = _std(arr, window)
    sd[sd < 1e-10] = 1e-10
    return (arr - ma) / sd


def _slope(arr: np.ndarray, window: int = 5) -> np.ndarray:
    """线性回归斜率（滚动）"""
    if len(arr) < window:
        return np.zeros_like(arr)
    x = np.arange(window)
    x_mean = x.mean()
    x_diff = x - x_mean
    denom = np.sum(x_diff ** 2)
    if denom == 0:
        return np.zeros_like(arr)
    result = np.zeros_like(arr)
    for i in range(window - 1, len(arr)):
        y = arr[i-window+1:i+1]
        y_mean = y.mean()
        result[i] = np.sum(x_diff * (y - y_mean)) / denom
    result[:window-1] = result[window-1]
    return result


def _correlation(x: np.ndarray, y: np.ndarray, window: int = 20) -> np.ndarray:
    """滚动相关系数"""
    if len(x) < window:
        return np.zeros_like(x)
    result = np.zeros_like(x)
    for i in range(window - 1, len(x)):
        x_seg = x[i-window+1:i+1]
        y_seg = y[i-window+1:i+1]
        std_x, std_y = np.std(x_seg), np.std(y_seg)
        if std_x > 1e-10 and std_y > 1e-10:
            result[i] = np.corrcoef(x_seg, y_seg)[0, 1]
    result[:window-1] = result[window-1]
    return np.clip(result, -1, 1)


# ============================================================
# 第1组：威科夫结构因子 (12维)
# ============================================================

def compute_wyckoff_structure(opens: np.ndarray, highs: np.ndarray,
                               lows: np.ndarray, closes: np.ndarray,
                               volumes: np.ndarray) -> Dict[str, np.ndarray]:
    """
    计算威科夫结构因子

    基于日线OHLCV数据，通过量价关系识别市场阶段和主力行为。
    """
    n = len(closes)
    factors = {}

    # 价格变化
    returns = np.diff(closes, prepend=closes[0]) / np.where(closes > 0, closes, 1)
    price_change = closes - closes[0] if n > 0 else np.zeros(n)

    # 均线
    ma20 = _sma(closes, 20)
    ma50 = _sma(closes, 50)
    vol_ma20 = _sma(volumes, 20)

    # 振幅
    amplitude = (highs - lows) / np.where(closes > 0, closes, 1)

    # ---- 1. spring_score: 震仓强度 ----
    # 特征：价格创新低后快速收回，下影线长，成交量放大
    low_20 = np.array([np.min(lows[max(0, i-19):i+1]) for i in range(n)])
    spring = np.zeros(n)
    for i in range(5, n):
        is_new_low = lows[i] <= low_20[i-1] * 0.99
        lower_shadow = (min(opens[i], closes[i]) - lows[i]) / np.where(closes[i] > 0, closes[i], 1)
        recovery = closes[i] > (opens[i] + lows[i]) / 2
        vol_surge = volumes[i] > vol_ma20[i] * 1.3 if i < len(vol_ma20) and not np.isnan(vol_ma20[i]) else False
        if is_new_low and lower_shadow > 0.02 and recovery:
            spring[i] = min(1.0, lower_shadow * 20 + (0.2 if vol_surge else 0))
    factors["spring_score"] = spring

    # ---- 2. sos_score: 强势信号 (Sign of Strength) ----
    # 特征：放量大阳线突破均线，收盘在最高点附近
    sos = np.zeros(n)
    for i in range(5, n):
        is_bullish = closes[i] > opens[i] * 1.02
        close_near_high = closes[i] >= highs[i] * 0.99
        above_ma = closes[i] > ma20[i] if i < len(ma20) and not np.isnan(ma20[i]) else True
        vol_above = volumes[i] > vol_ma20[i] * 1.5 if i < len(vol_ma20) and not np.isnan(vol_ma20[i]) else False
        if is_bullish and close_near_high and above_ma:
            sos[i] = min(1.0, (closes[i]/opens[i] - 1) * 20 + (0.3 if vol_above else 0))
    factors["sos_score"] = sos

    # ---- 3. lps_score: 回踩有效性 (Last Point of Support) ----
    # 特征：回踩均线不破，缩量，小实体
    lps = np.zeros(n)
    for i in range(10, n):
        near_ma20 = abs(closes[i] - ma20[i]) / closes[i] < 0.02 if not np.isnan(ma20[i]) else False
        low_above_ma = lows[i] > ma20[i] * 0.99 if not np.isnan(ma20[i]) else False
        small_body = abs(closes[i] - opens[i]) / closes[i] < 0.01
        low_vol = volumes[i] < vol_ma20[i] * 0.7 if i < len(vol_ma20) and not np.isnan(vol_ma20[i]) else False
        if near_ma20 and low_above_ma and small_body:
            lps[i] = min(1.0, 0.4 + (0.3 if low_vol else 0) + (0.3 if low_above_ma else 0))
    factors["lps_score"] = lps

    # ---- 4. joc_score: 突破强度 (Jump Across Creek) ----
    # 特征：突破前期阻力位，放量，大阳线
    joc = np.zeros(n)
    high_50 = np.array([np.max(highs[max(0, i-49):i+1]) for i in range(n)])
    for i in range(20, n):
        breakout = highs[i] > high_50[i-1] * 1.005
        is_bullish = closes[i] > opens[i] * 1.01
        vol_above = volumes[i] > vol_ma20[i] * 1.2 if i < len(vol_ma20) and not np.isnan(vol_ma20[i]) else False
        if breakout and is_bullish:
            joc[i] = min(1.0, (highs[i]/high_50[i-1] - 1) * 100 + (0.3 if vol_above else 0))
    factors["joc_score"] = joc

    # ---- 5. ut_ad_score: 诱多强度 (Upthrust / Upthrust After Distribution) ----
    # 特征：上冲后回落，长上影线，放量，收盘在底部
    ut_ad = np.zeros(n)
    for i in range(5, n):
        upper_shadow = (highs[i] - max(opens[i], closes[i])) / np.where(closes[i] > 0, closes[i], 1)
        close_near_low = closes[i] <= lows[i] * 1.005
        is_bearish = closes[i] < opens[i]
        if upper_shadow > 0.02 and close_near_low and is_bearish:
            vol_factor = min(1.0, volumes[i] / (vol_ma20[i] + 1)) if i < len(vol_ma20) and not np.isnan(vol_ma20[i]) else 0.5
            ut_ad[i] = min(1.0, upper_shadow * 30 + vol_factor * 0.3)
    factors["ut_ad_score"] = ut_ad

    # ---- 6. sow_score: 弱势信号 (Sign of Weakness) ----
    # 特征：放量大阴线跌破均线，收盘在最低点附近
    sow = np.zeros(n)
    for i in range(5, n):
        is_bearish = closes[i] < opens[i] * 0.98
        close_near_low = closes[i] <= lows[i] * 1.005
        below_ma = closes[i] < ma20[i] * 0.98 if i < len(ma20) and not np.isnan(ma20[i]) else True
        if is_bearish and close_near_low and below_ma:
            vol_factor = min(1.0, volumes[i] / (vol_ma20[i] + 1)) if i < len(vol_ma20) and not np.isnan(vol_ma20[i]) else 0.5
            sow[i] = min(1.0, (opens[i]/closes[i] - 1) * 20 + vol_factor * 0.3)
    factors["sow_score"] = sow

    # ---- 7. supply_exhausted: 供应耗尽 ----
    # 特征：连续下跌后缩量，振幅缩小，出现spring
    supply_ex = np.zeros(n)
    for i in range(20, n):
        down_5 = np.sum(returns[max(0,i-4):i+1] < 0) >= 4
        vol_shrink = volumes[i] < vol_ma20[i] * 0.6 if i < len(vol_ma20) and not np.isnan(vol_ma20[i]) else False
        range_shrink = amplitude[i] < np.mean(amplitude[max(0,i-19):i+1]) * 0.7
        if down_5 and (vol_shrink or range_shrink):
            supply_ex[i] = min(1.0, 0.4 + (0.3 if vol_shrink else 0) + (0.3 if range_shrink else 0))
    factors["supply_exhausted"] = supply_ex

    # ---- 8. demand_exhausted: 需求枯竭 ----
    # 特征：连续上涨后缩量，振幅缩小，出现ut_ad
    demand_ex = np.zeros(n)
    for i in range(20, n):
        up_5 = np.sum(returns[max(0,i-4):i+1] > 0) >= 4
        vol_shrink = volumes[i] < vol_ma20[i] * 0.6 if i < len(vol_ma20) and not np.isnan(vol_ma20[i]) else False
        range_shrink = amplitude[i] < np.mean(amplitude[max(0,i-19):i+1]) * 0.7
        if up_5 and (vol_shrink or range_shrink):
            demand_ex[i] = min(1.0, 0.4 + (0.3 if vol_shrink else 0) + (0.3 if range_shrink else 0))
    factors["demand_exhausted"] = demand_ex

    # ---- 9. absorption_signal: 主力吸收 ----
    # 特征：窄幅震荡但成交量不萎缩（主力在暗中吸筹/派发）
    absorption = np.zeros(n)
    for i in range(20, n):
        range_10 = np.std(closes[max(0,i-9):i+1]) / np.mean(closes[max(0,i-9):i+1])
        range_small = range_10 < 0.02
        vol_normal = volumes[i] > vol_ma20[i] * 0.9 if i < len(vol_ma20) and not np.isnan(vol_ma20[i]) else False
        if range_small and vol_normal:
            absorption[i] = min(1.0, 0.5 + 0.5 * (1 - range_10 / 0.02))
    factors["absorption_signal"] = absorption

    # ---- 10. stop_grab: 扫止损 ----
    # 特征：短暂跌破支撑位后迅速收回
    stop_grab = np.zeros(n)
    for i in range(10, n):
        low_10 = np.min(lows[max(0,i-9):i])
        broke_low = lows[i] < low_10 * 0.995
        recovered = closes[i] > low_10 * 1.005
        if broke_low and recovered:
            v_recovery = volumes[i] / (vol_ma20[i] + 1) if i < len(vol_ma20) and not np.isnan(vol_ma20[i]) else 1
            stop_grab[i] = min(1.0, 0.5 + 0.5 * min(v_recovery, 2) / 2)
    factors["stop_grab"] = stop_grab

    # ---- 11. distribution_head: 顶部盘头 ----
    # 特征：高位震荡，成交量放大但价格不涨，频繁出现ut_ad
    dist_head = np.zeros(n)
    for i in range(30, n):
        high_30 = np.max(highs[max(0,i-29):i+1])
        near_high = closes[i] > high_30 * 0.95
        vol_above_avg = volumes[i] > vol_ma20[i] * 1.3 if i < len(vol_ma20) and not np.isnan(vol_ma20[i]) else False
        no_progress = closes[i] < closes[max(0,i-20)] * 1.02
        if near_high and vol_above_avg and no_progress:
            ut_count = np.sum(ut_ad[max(0,i-9):i+1] > 0.3)
            dist_head[i] = min(1.0, 0.3 + 0.3 * min(ut_count/3, 1) + 0.4 * min(volumes[i]/(vol_ma20[i]+1), 2)/2)
    factors["distribution_head"] = dist_head

    # ---- 12. wyckoff_phase: 阶段判定 (0吸筹/1拉升/2派发/3下跌) ----
    # 综合各信号判定阶段
    phase = np.zeros(n)
    for i in range(30, n):
        # 累积信号强度
        spring_recent = np.mean(spring[max(0,i-9):i+1])
        sos_recent = np.mean(sos[max(0,i-9):i+1])
        ut_recent = np.mean(ut_ad[max(0,i-9):i+1])
        sow_recent = np.mean(sow[max(0,i-9):i+1])
        supply_ex_recent = np.mean(supply_ex[max(0,i-9):i+1])
        demand_ex_recent = np.mean(demand_ex[max(0,i-9):i+1])
        joc_recent = np.mean(joc[max(0,i-9):i+1])
        dist_recent = np.mean(dist_head[max(0,i-9):i+1])

        # 趋势判断
        trend_up = closes[i] > ma50[i] * 1.02 if not np.isnan(ma50[i]) else False
        trend_down = closes[i] < ma50[i] * 0.98 if not np.isnan(ma50[i]) else False

        if spring_recent > 0.3 or supply_ex_recent > 0.5:
            phase_val = 0  # 吸筹
        elif joc_recent > 0.3 or (sos_recent > 0.3 and trend_up):
            phase_val = 1  # 拉升
        elif ut_recent > 0.3 or dist_recent > 0.3 or demand_ex_recent > 0.5:
            phase_val = 2  # 派发
        elif sow_recent > 0.3 or trend_down:
            phase_val = 3  # 下跌
        else:
            # 默认：价格在均线上方=拉升倾向，下方=下跌倾向
            phase_val = 1 if trend_up else (3 if trend_down else 1)

        phase[i] = phase_val

    factors["wyckoff_phase"] = phase

    return factors


# ============================================================
# 第2组：量价健康度因子 (12维)
# ============================================================

def compute_volume_health(opens: np.ndarray, highs: np.ndarray,
                           lows: np.ndarray, closes: np.ndarray,
                           volumes: np.ndarray) -> Dict[str, np.ndarray]:
    """计算量价健康度因子"""
    n = len(closes)
    factors = {}

    returns = np.diff(closes, prepend=closes[0]) / np.where(closes > 0, closes, 1)
    vol_ma5 = _sma(volumes, 5)
    vol_ma20 = _sma(volumes, 20)

    # ---- 12. volume_trend_health: 量价健康度 ----
    # 综合评估：上涨放量+下跌缩量=健康
    health = np.zeros(n)
    for i in range(20, n):
        up_days = 0
        up_vol = 0.0
        down_days = 0
        down_vol = 0.0
        for j in range(max(0, i-19), i+1):
            if returns[j] > 0:
                up_days += 1
                up_vol += volumes[j]
            else:
                down_days += 1
                down_vol += volumes[j]
        if up_days > 0 and down_days > 0:
            avg_up_vol = up_vol / up_days
            avg_down_vol = down_vol / down_days
            health[i] = min(1.0, max(0.0, (avg_up_vol / max(avg_down_vol, 1) - 1) * 2))
        else:
            health[i] = 0.5
    factors["volume_trend_health"] = health

    # ---- 13. up_vol_ratio: 上涨放量比 ----
    up_vol_ratio = np.zeros(n)
    for i in range(20, n):
        up_vols = [volumes[j] for j in range(max(0,i-19), i+1) if returns[j] > 0]
        if up_vols:
            up_vol_ratio[i] = np.mean(up_vols) / max(np.mean(volumes[max(0,i-19):i+1]), 1)
    factors["up_vol_ratio"] = np.clip(up_vol_ratio, 0, 2)

    # ---- 14. down_vol_ratio: 下跌缩量比 ----
    down_vol_ratio = np.zeros(n)
    for i in range(20, n):
        down_vols = [volumes[j] for j in range(max(0,i-19), i+1) if returns[j] < 0]
        if down_vols:
            down_vol_ratio[i] = np.mean(down_vols) / max(np.mean(volumes[max(0,i-19):i+1]), 1)
    factors["down_vol_ratio"] = np.clip(down_vol_ratio, 0, 2)

    # ---- 15. effort_result: 努力vs结果 ----
    # 威科夫核心概念：成交量(努力)与价格变动(结果)的关系
    effort = np.zeros(n)
    for i in range(5, n):
        vol_change = volumes[i] / max(vol_ma20[i], 1) if i < len(vol_ma20) and not np.isnan(vol_ma20[i]) else 1
        price_range = (highs[i] - lows[i]) / closes[i] if closes[i] > 0 else 0
        # 大量但小振幅 = 努力无结果（吸收/派发）
        if vol_change > 1.5 and price_range < 0.015:
            effort[i] = -1.0  # 负面：努力无结果
        elif vol_change > 1.5 and price_range > 0.03:
            effort[i] = 1.0   # 正面：努力有结果
        elif vol_change < 0.5 and price_range < 0.01:
            effort[i] = 0.5   # 低量低振幅：正常
        else:
            effort[i] = 0.0
    factors["effort_result"] = effort

    # ---- 16. volume_ma5_dev: 5日均量偏离 ----
    vol_ma5_arr = _sma(volumes, 5)
    factors["volume_ma5_dev"] = np.clip(
        (volumes - vol_ma5_arr) / np.where(vol_ma5_arr > 0, vol_ma5_arr, 1), -2, 2)

    # ---- 17. volume_ma20_dev: 20日均量偏离 ----
    factors["volume_ma20_dev"] = np.clip(
        (volumes - vol_ma20) / np.where(vol_ma20 > 0, vol_ma20, 1), -2, 2)

    # ---- 18. large_volume_signal: 巨量信号 ----
    large_vol = np.zeros(n)
    for i in range(20, n):
        vol_z = (volumes[i] - np.mean(volumes[max(0,i-19):i+1])) / max(np.std(volumes[max(0,i-19):i+1]), 1)
        large_vol[i] = min(1.0, max(0.0, vol_z / 3))
    factors["large_volume_signal"] = large_vol

    # ---- 19. no_demand: 无需求 ----
    # 特征：价格上涨但成交量萎缩（上涨乏力）
    no_demand = np.zeros(n)
    for i in range(5, n):
        price_up = closes[i] > closes[i-1] * 1.005
        vol_down = volumes[i] < vol_ma5[i] * 0.7 if i < len(vol_ma5) and not np.isnan(vol_ma5[i]) else False
        if price_up and vol_down:
            no_demand[i] = min(1.0, 0.5 + 0.5 * (1 - volumes[i]/max(vol_ma5[i], 1)))
    factors["no_demand"] = no_demand

    # ---- 20. no_supply: 无供应 ----
    # 特征：价格下跌但成交量萎缩（抛压枯竭）
    no_supply = np.zeros(n)
    for i in range(5, n):
        price_down = closes[i] < closes[i-1] * 0.995
        vol_down = volumes[i] < vol_ma5[i] * 0.7 if i < len(vol_ma5) and not np.isnan(vol_ma5[i]) else False
        if price_down and vol_down:
            no_supply[i] = min(1.0, 0.5 + 0.5 * (1 - volumes[i]/max(vol_ma5[i], 1)))
    factors["no_supply"] = no_supply

    # ---- 21. volume_trend_angle: 量能趋势角度 ----
    vol_slope = _slope(volumes, 10)
    vol_mean = _sma(volumes, 10)
    factors["volume_trend_angle"] = np.clip(
        vol_slope / np.where(vol_mean > 0, vol_mean, 1) * 10, -1, 1)

    # ---- 22. vol_price_corr: 量价相关系数 ----
    factors["vol_price_corr"] = _correlation(closes, volumes, 20)

    # ---- 23. vol_spike: 量峰强度 ----
    vol_spike = np.zeros(n)
    for i in range(60, n):
        vol_history = volumes[max(0,i-59):i+1]
        vol_mean_60 = np.mean(vol_history)
        vol_std_60 = np.std(vol_history)
        if vol_std_60 > 0:
            vol_spike[i] = min(1.0, max(0.0, (volumes[i] - vol_mean_60) / (vol_std_60 * 3)))
    factors["vol_spike"] = vol_spike

    return factors


# ============================================================
# 第3组：箱体震荡因子 (12维)
# ============================================================

def compute_range_factors(opens: np.ndarray, highs: np.ndarray,
                           lows: np.ndarray, closes: np.ndarray,
                           volumes: np.ndarray) -> Dict[str, np.ndarray]:
    """计算箱体震荡因子"""
    n = len(closes)
    factors = {}

    vol_ma20 = _sma(volumes, 20)
    ma5 = _sma(closes, 5)
    ma10 = _sma(closes, 10)
    ma20 = _sma(closes, 20)
    ma60 = _sma(closes, 60)

    # 动态识别箱体：用最近N根K线的高低点
    range_high = np.zeros(n)
    range_low = np.zeros(n)
    range_width_arr = np.zeros(n)
    range_duration_arr = np.zeros(n)

    for i in range(60, n):
        lookback = min(60, i)
        seg_highs = highs[i-lookback:i+1]
        seg_lows = lows[i-lookback:i+1]
        range_high[i] = np.max(seg_highs)
        range_low[i] = np.min(seg_lows)
        range_width_arr[i] = (range_high[i] - range_low[i]) / range_low[i] if range_low[i] > 0 else 0

        # 箱体时长：价格在区间内持续的天数
        in_range = (closes[i-lookback:i+1] >= range_low[i] * 0.995) & \
                   (closes[i-lookback:i+1] <= range_high[i] * 1.005)
        range_duration_arr[i] = np.sum(in_range)

    # ---- 24. range_width: 箱体幅度 ----
    factors["range_width"] = np.clip(range_width_arr / 0.2, 0, 1)  # 20%振幅=满分

    # ---- 25. range_duration: 箱体时长 ----
    factors["range_duration"] = np.clip(range_duration_arr / 60, 0, 1)

    # ---- 26. range_upper_valid: 上轨有效性 ----
    # 上轨被触及次数越多越有效
    upper_valid = np.zeros(n)
    for i in range(60, n):
        touches = np.sum(highs[max(0,i-59):i+1] >= range_high[i] * 0.995)
        upper_valid[i] = min(1.0, touches / 3)
    factors["range_upper_valid"] = upper_valid

    # ---- 27. range_lower_valid: 下轨有效性 ----
    lower_valid = np.zeros(n)
    for i in range(60, n):
        touches = np.sum(lows[max(0,i-59):i+1] <= range_low[i] * 1.005)
        lower_valid[i] = min(1.0, touches / 3)
    factors["range_lower_valid"] = lower_valid

    # ---- 28. price_to_upper: 价格到上轨距离 ----
    factors["price_to_upper"] = np.clip(
        (range_high - closes) / np.where(range_high > 0, range_high - range_low, 1), 0, 1)

    # ---- 29. price_to_lower: 价格到下轨距离 ----
    factors["price_to_lower"] = np.clip(
        (closes - range_low) / np.where(range_high > 0, range_high - range_low, 1), 0, 1)

    # ---- 30. ma_flat_score: 均线走平度 ----
    # 多条均线斜率接近0
    ma_slopes = np.zeros((n, 4))
    for idx, ma in enumerate([ma5, ma10, ma20, ma60]):
        ma_slopes[:, idx] = np.abs(_slope(ma, 10) / np.where(ma > 0, ma, 1))
    factors["ma_flat_score"] = 1 - np.clip(np.mean(ma_slopes, axis=1) * 50, 0, 1)

    # ---- 31. ma_cluster_score: 均线粘合度 ----
    # 多条均线间距小
    ma_arrays = np.column_stack([ma5, ma10, ma20, ma60])
    ma_spread = np.std(ma_arrays, axis=1) / np.where(np.mean(ma_arrays, axis=1) > 0,
                                                       np.mean(ma_arrays, axis=1), 1)
    factors["ma_cluster_score"] = 1 - np.clip(ma_spread * 20, 0, 1)

    # ---- 32. range_vol_shrink: 量能萎缩比例 ----
    vol_shrink = np.zeros(n)
    for i in range(60, n):
        recent_vol = np.mean(volumes[max(0,i-19):i+1])
        early_vol = np.mean(volumes[max(0,i-59):max(0,i-20)])
        if early_vol > 0:
            vol_shrink[i] = max(0.0, 1 - recent_vol / early_vol)
    factors["range_vol_shrink"] = np.clip(vol_shrink, 0, 1)

    # ---- 33. range_vol_at_top: 上轨放量 ----
    vol_at_top = np.zeros(n)
    for i in range(60, n):
        near_top = closes[i] >= range_high[i] * 0.98
        if near_top and i < len(vol_ma20) and not np.isnan(vol_ma20[i]):
            vol_at_top[i] = min(1.0, volumes[i] / (vol_ma20[i] + 1))
    factors["range_vol_at_top"] = vol_at_top

    # ---- 34. range_vol_at_bottom: 下轨缩量 ----
    vol_at_bottom = np.zeros(n)
    for i in range(60, n):
        near_bottom = closes[i] <= range_low[i] * 1.02
        if near_bottom and i < len(vol_ma20) and not np.isnan(vol_ma20[i]):
            vol_at_bottom[i] = min(1.0, (vol_ma20[i] + 1) / (volumes[i] + 1) * 0.5)
    factors["range_vol_at_bottom"] = vol_at_bottom

    # ---- 35. range_break_prob: 突破概率 ----
    # 综合评估：箱体持续时间越长、量能萎缩越明显，突破概率越大
    break_prob = np.zeros(n)
    for i in range(60, n):
        duration_factor = min(1.0, range_duration_arr[i] / 40)
        shrink_factor = vol_shrink[i]
        cluster_factor = factors["ma_cluster_score"][i]
        break_prob[i] = duration_factor * 0.3 + shrink_factor * 0.4 + cluster_factor * 0.3
    factors["range_break_prob"] = break_prob

    return factors


# ============================================================
# 第4组：突破真假判别因子 (10维)
# ============================================================

def compute_breakout_factors(opens: np.ndarray, highs: np.ndarray,
                              lows: np.ndarray, closes: np.ndarray,
                              volumes: np.ndarray) -> Dict[str, np.ndarray]:
    """计算突破真假判别因子"""
    n = len(closes)
    factors = {}

    vol_ma20 = _sma(volumes, 20)
    ma20 = _sma(closes, 20)
    ma60 = _sma(closes, 60)

    # 识别突破点：价格突破N日高点
    high_20 = np.array([np.max(highs[max(0,i-19):i+1]) if i > 0 else highs[0] for i in range(n)])
    high_50 = np.array([np.max(highs[max(0,i-49):i+1]) if i > 0 else highs[0] for i in range(n)])

    # ---- 36. breakout_strength: 突破强度 ----
    # 突破幅度相对于前期波动
    break_strength = np.zeros(n)
    for i in range(20, n):
        if highs[i] > high_20[i] * 1.001:
            break_strength[i] = min(1.0, (highs[i] / high_20[i] - 1) * 50)
    factors["breakout_strength"] = break_strength

    # ---- 37. breakout_vol_ratio: 突破量比 ----
    break_vol = np.zeros(n)
    for i in range(20, n):
        if break_strength[i] > 0 and i < len(vol_ma20) and not np.isnan(vol_ma20[i]):
            break_vol[i] = min(1.0, volumes[i] / (vol_ma20[i] * 2 + 1))
    factors["breakout_vol_ratio"] = break_vol

    # ---- 38. breakout_retest_vol: 回踩缩量 ----
    retest_vol = np.zeros(n)
    for i in range(25, n):
        # 突破后3-5天回踩时缩量
        recent_break = any(break_strength[max(0,i-5):i] > 0.1)
        if recent_break:
            price_near_break = abs(closes[i] - high_20[i]) / high_20[i] < 0.02
            if price_near_break and i < len(vol_ma20) and not np.isnan(vol_ma20[i]):
                retest_vol[i] = min(1.0, max(0, 1 - volumes[i] / (vol_ma20[i] + 1)))
    factors["breakout_retest_vol"] = retest_vol

    # ---- 39. breakout_retest_hold: 回踩守住 ----
    retest_hold = np.zeros(n)
    for i in range(25, n):
        recent_break = any(break_strength[max(0,i-5):i] > 0.1)
        if recent_break:
            hold = lows[i] > high_20[i] * 0.995
            retest_hold[i] = 1.0 if hold else 0.0
    factors["breakout_retest_hold"] = retest_hold

    # ---- 40. false_breakout_score: 假突破概率 ----
    # 突破后快速回落=假突破
    false_break = np.zeros(n)
    for i in range(25, n):
        if break_strength[i-3] > 0.1:
            fall_back = closes[i] < high_20[i-3] * 0.99
            if fall_back:
                false_break[i] = min(1.0, 0.5 + 0.5 * (1 - closes[i] / high_20[i-3]))
    factors["false_breakout_score"] = false_break

    # ---- 41. breakout_support_loss: 支撑失效 ----
    # 跌破突破前的支撑位
    support_loss = np.zeros(n)
    for i in range(30, n):
        if break_strength[max(0,i-10)] > 0.1:
            lost = closes[i] < ma20[i] * 0.98 if not np.isnan(ma20[i]) else False
            if lost:
                support_loss[i] = 1.0
    factors["breakout_support_loss"] = support_loss

    # ---- 42. breakout_ma_confirm: 均线确认 ----
    # 突破时均线多头排列
    ma_confirm = np.zeros(n)
    for i in range(20, n):
        if break_strength[i] > 0:
            ma_bullish = ma20[i] > ma60[i] * 1.01 if not np.isnan(ma20[i]) and not np.isnan(ma60[i]) else False
            ma_confirm[i] = 1.0 if ma_bullish else 0.3
    factors["breakout_ma_confirm"] = ma_confirm

    # ---- 43. breakout_trend_confirm: 趋势确认 ----
    # 周线或日线级别趋势方向
    trend_confirm = np.zeros(n)
    for i in range(20, n):
        ma20_slope = (ma20[i] - ma20[max(0,i-10)]) / ma20[max(0,i-10)] if not np.isnan(ma20[i]) and not np.isnan(ma20[max(0,i-10)]) and ma20[max(0,i-10)] > 0 else 0
        trend_confirm[i] = min(1.0, max(0.0, ma20_slope * 20 + 0.5))
    factors["breakout_trend_confirm"] = trend_confirm

    # ---- 44. breakout_depth: 突破深度 ----
    # 突破了多少个前期高点
    depth = np.zeros(n)
    for i in range(20, n):
        if break_strength[i] > 0:
            break_price = highs[i]
            levels_broken = 0
            for j in range(max(0,i-50), i):
                if highs[j] > high_20[i] and highs[j] < break_price:
                    levels_broken += 1
            depth[i] = min(1.0, levels_broken / 5)
    factors["breakout_depth"] = depth

    # ---- 45. breakout_rebound_speed: 反弹速度 ----
    # 突破后回踩反弹的速度
    rebound_speed = np.zeros(n)
    for i in range(30, n):
        recent_break_idx = -1
        for j in range(i-5, i-20, -1):
            if j >= 0 and break_strength[j] > 0.1:
                recent_break_idx = j
                break
        if recent_break_idx > 0:
            low_since = np.min(lows[recent_break_idx:i+1])
            if low_since < closes[i]:
                rebound_speed[i] = min(1.0, (closes[i] / low_since - 1) * 20)
    factors["breakout_rebound_speed"] = rebound_speed

    return factors


# ============================================================
# 第5组：盘口分时因子 (12维)
# ============================================================

def compute_order_book_factors(m15_opens: np.ndarray, m15_highs: np.ndarray,
                                m15_lows: np.ndarray, m15_closes: np.ndarray,
                                m15_volumes: np.ndarray,
                                m15_to_daily: List[int]) -> Dict[str, np.ndarray]:
    """
    计算盘口分时因子（基于15分钟K线）

    攻击波/冲击波/试盘波等Wave形态，从15分钟K线中提取。
    每日独立计算，避免跨日干扰。
    """
    n = len(m15_closes)
    factors = {}
    factors.update({f: np.zeros(n) for f in ORDER_BOOK_FACTORS})

    # 按日分组
    daily_groups: Dict[int, List[int]] = {}
    for i, di in enumerate(m15_to_daily):
        if di >= 0:
            daily_groups.setdefault(di, []).append(i)

    for day_idx, bar_indices in daily_groups.items():
        if len(bar_indices) < 4:
            continue

        day_bars = np.array(bar_indices)
        day_open = m15_opens[day_bars[0]]
        day_high = np.max(m15_highs[day_bars])
        day_low = np.min(m15_lows[day_bars])
        day_vol = np.sum(m15_volumes[day_bars])

        if day_open <= 0:
            continue

        # 分时价格序列
        intraday_prices = m15_closes[day_bars]
        intraday_vols = m15_volumes[day_bars]

        # 均价线（VWAP近似）
        cum_vol = np.cumsum(intraday_vols)
        vwap = np.cumsum(intraday_prices * intraday_vols) / np.where(cum_vol > 0, cum_vol, 1)

        # 分时涨跌幅
        intraday_ret = (intraday_prices - day_open) / day_open

        # 价格变化率
        price_changes = np.diff(intraday_prices, prepend=intraday_prices[0])
        ret_changes = np.diff(intraday_ret, prepend=intraday_ret[0])

        for idx_in_day, bar_idx in enumerate(bar_indices):
            if idx_in_day < 2:
                continue

            # ---- 46. attack_wave: 攻击波 ----
            # 特征：连续放量上涨，价格斜率陡峭，每根bar创新高
            if idx_in_day >= 3:
                recent_3 = intraday_ret[max(0,idx_in_day-2):idx_in_day+1]
                recent_vols = intraday_vols[max(0,idx_in_day-2):idx_in_day+1]
                all_up = all(r > 0 for r in np.diff(recent_3))
                slope_steep = (recent_3[-1] - recent_3[0]) > 0.003
                vol_increasing = recent_vols[-1] > np.mean(recent_vols[:-1]) * 1.2 if len(recent_vols) > 1 else False
                if all_up and slope_steep:
                    factors["attack_wave"][bar_idx] = min(1.0, abs(recent_3[-1] - recent_3[0]) * 200 +
                                                         (0.3 if vol_increasing else 0))

            # ---- 47. shock_wave: 冲击波 ----
            # 特征：单根bar大幅波动，放巨量
            bar_range = (m15_highs[bar_idx] - m15_lows[bar_idx]) / m15_closes[bar_idx] if m15_closes[bar_idx] > 0 else 0
            avg_range = np.mean(np.abs(price_changes[max(0,idx_in_day-9):idx_in_day+1]))
            if bar_range > avg_range * 3 and bar_range > 0.005:
                vol_ratio = intraday_vols[idx_in_day] / max(np.mean(intraday_vols[max(0,idx_in_day-9):idx_in_day+1]), 1)
                factors["shock_wave"][bar_idx] = min(1.0, bar_range * 100 + min(vol_ratio/3, 0.5))

            # ---- 48. test_wave: 试盘波 ----
            # 特征：快速冲高后立即回落，上影线长
            upper_shadow = (m15_highs[bar_idx] - max(m15_opens[bar_idx], m15_closes[bar_idx])) / m15_closes[bar_idx] if m15_closes[bar_idx] > 0 else 0
            if upper_shadow > 0.005:
                prev_up = idx_in_day > 0 and intraday_ret[idx_in_day-1] > 0
                cur_down = intraday_ret[idx_in_day] < 0
                if prev_up and cur_down:
                    factors["test_wave"][bar_idx] = min(1.0, upper_shadow * 100)

            # ---- 49. turn_back_wave: 回头波 ----
            # 特征：连续下跌后突然反转，放量
            if idx_in_day >= 4:
                prev_down = all(intraday_ret[j] < 0 for j in range(idx_in_day-3, idx_in_day))
                cur_up = intraday_ret[idx_in_day] > 0
                if prev_down and cur_up:
                    reversal_pct = intraday_ret[idx_in_day] - intraday_ret[idx_in_day-1]
                    vol_ratio = intraday_vols[idx_in_day] / max(np.mean(intraday_vols[max(0,idx_in_day-4):idx_in_day]), 1)
                    factors["turn_back_wave"][bar_idx] = min(1.0, reversal_pct * 100 + min(vol_ratio/3, 0.5))

            # ---- 50. fake_rise_wave: 假升波 ----
            # 特征：价格上涨但量能萎缩（无量上涨）
            if idx_in_day >= 3:
                price_up = intraday_ret[idx_in_day] > intraday_ret[idx_in_day-1]
                vol_down = intraday_vols[idx_in_day] < intraday_vols[idx_in_day-1] * 0.7
                if price_up and vol_down:
                    factors["fake_rise_wave"][bar_idx] = min(1.0, 0.5 + 0.5 * (1 - intraday_vols[idx_in_day] / max(intraday_vols[idx_in_day-1], 1)))

            # ---- 51. avg_line_strength: 均价线支撑 ----
            # 价格在均价线上方运行
            if idx_in_day > 0:
                price_to_vwap = (intraday_prices[idx_in_day] - vwap[idx_in_day]) / day_open
                # 价格持续在均价线上方 = 强势
                above_vwap = [intraday_prices[j] > vwap[j] for j in range(max(0,idx_in_day-4), idx_in_day+1)]
                consistency = sum(above_vwap) / len(above_vwap)
                factors["avg_line_strength"][bar_idx] = min(1.0, max(0.0, consistency * 0.7 + price_to_vwap * 50))

            # ---- 52. time_share_vol_peak: 分时量峰 ----
            # 当前bar的成交量在当日所有bar中的相对位置
            if idx_in_day > 0:
                vol_rank = sum(1 for v in intraday_vols[:idx_in_day+1] if v <= intraday_vols[idx_in_day]) / (idx_in_day + 1)
                factors["time_share_vol_peak"][bar_idx] = vol_rank

            # ---- 53. time_share_trend: 分时趋势 ----
            # 日内趋势强度
            if idx_in_day > 0:
                x = np.arange(idx_in_day + 1)
                y = intraday_ret[:idx_in_day+1]
                if len(x) > 1:
                    slope = np.polyfit(x, y, 1)[0]
                    factors["time_share_trend"][bar_idx] = min(1.0, max(-1.0, slope * 2000))

            # ---- 54. open_position_power: 开盘力量 ----
            # 开盘30分钟（前2根15分钟bar）的方向和力度
            if idx_in_day < 2:
                first_bar_ret = intraday_ret[0] if len(intraday_ret) > 0 else 0
                first_bar_vol = intraday_vols[0] if len(intraday_vols) > 0 else 1
                avg_vol = np.mean(intraday_vols) if len(intraday_vols) > 0 else 1
                factors["open_position_power"][bar_idx] = min(1.0, abs(first_bar_ret) * 50 + min(first_bar_vol/avg_vol, 2) * 0.3)
            else:
                first_bar_ret = intraday_ret[0] if len(intraday_ret) > 0 else 0
                first_bar_vol = intraday_vols[0] if len(intraday_vols) > 0 else 1
                avg_vol = np.mean(intraday_vols) if len(intraday_vols) > 0 else 1
                factors["open_position_power"][bar_idx] = min(1.0, abs(first_bar_ret) * 50 + min(first_bar_vol/avg_vol, 2) * 0.3)

            # ---- 55. close_position_power: 尾盘力量 ----
            # 最后30分钟的力度
            is_last_two = idx_in_day >= len(bar_indices) - 2
            if is_last_two:
                last_bars_ret = intraday_ret[-min(2, len(intraday_ret)):]
                cum_ret = np.sum(last_bars_ret)
                factors["close_position_power"][bar_idx] = min(1.0, abs(cum_ret) * 50)

            # ---- 56. vol_per_min: 分钟量能分布 ----
            # 当前bar的成交量 / 当日平均每15分钟成交量
            avg_vol_per_bar = day_vol / len(bar_indices) if len(bar_indices) > 0 else 1
            factors["vol_per_min"][bar_idx] = min(1.0, intraday_vols[idx_in_day] / (avg_vol_per_bar * 3 + 1))

            # ---- 57. depth_vol_imbalance: 盘口失衡（近似） ----
            # 从15分钟K线近似：上影线/下影线不对称 + 量价背离
            if idx_in_day > 0:
                upper_shadow = (m15_highs[bar_idx] - max(m15_opens[bar_idx], m15_closes[bar_idx])) / m15_closes[bar_idx] if m15_closes[bar_idx] > 0 else 0
                lower_shadow = (min(m15_opens[bar_idx], m15_closes[bar_idx]) - m15_lows[bar_idx]) / m15_closes[bar_idx] if m15_closes[bar_idx] > 0 else 0
                # 上影线远大于下影线 = 卖压 > 买压（盘口失衡偏卖）
                if upper_shadow > lower_shadow * 2 and upper_shadow > 0.003:
                    factors["depth_vol_imbalance"][bar_idx] = -min(1.0, upper_shadow * 100)
                elif lower_shadow > upper_shadow * 2 and lower_shadow > 0.003:
                    factors["depth_vol_imbalance"][bar_idx] = min(1.0, lower_shadow * 100)
                else:
                    factors["depth_vol_imbalance"][bar_idx] = 0.0

    return factors


# ============================================================
# 第6组：市场情绪强度因子 (10维)
# ============================================================

def compute_market_sentiment(closes: np.ndarray, volumes: np.ndarray,
                              market_data: Optional[Dict] = None) -> Dict[str, np.ndarray]:
    """
    计算市场情绪强度因子

    部分因子需要外部市场数据（涨跌家数、板块动量等），
    无外部数据时使用标的自身数据近似。
    """
    n = len(closes)
    factors = {}

    returns = np.diff(closes, prepend=closes[0]) / np.where(closes > 0, closes, 1)
    ma20 = _sma(closes, 20)
    ma60 = _sma(closes, 60)

    # ---- 58. market_trend: 大盘趋势 ----
    # 用标的自身趋势近似（实盘时可替换为指数数据）
    trend = np.zeros(n)
    for i in range(20, n):
        above_ma20 = closes[i] > ma20[i] if not np.isnan(ma20[i]) else False
        above_ma60 = closes[i] > ma60[i] if not np.isnan(ma60[i]) else False
        ma20_slope = (ma20[i] - ma20[max(0,i-5)]) / ma20[max(0,i-5)] if not np.isnan(ma20[i]) and not np.isnan(ma20[max(0,i-5)]) and ma20[max(0,i-5)] > 0 else 0
        if above_ma20 and above_ma60 and ma20_slope > 0.005:
            trend[i] = 1.0   # 上升趋势
        elif above_ma20 and above_ma60:
            trend[i] = 0.7   # 偏多
        elif not above_ma20 and not above_ma60 and ma20_slope < -0.005:
            trend[i] = 0.0   # 下降趋势
        elif not above_ma20 and not above_ma60:
            trend[i] = 0.3   # 偏空
        else:
            trend[i] = 0.5   # 震荡
    factors["market_trend"] = trend

    # ---- 59. market_volatility: 市场波动率 ----
    # 20日年化波动率
    vol_20 = _std(returns, 20) * np.sqrt(252)
    factors["market_volatility"] = np.clip(vol_20 / 0.5, 0, 1)  # 50%年化波动率=满分

    # ---- 60. adv_dec_ratio: 涨跌家数比 ----
    # 用标的自身的涨跌比近似
    adv_ratio = np.zeros(n)
    for i in range(20, n):
        up = np.sum(returns[max(0,i-19):i+1] > 0)
        down = np.sum(returns[max(0,i-19):i+1] < 0)
        if down > 0:
            adv_ratio[i] = up / down
        else:
            adv_ratio[i] = 2.0 if up > 0 else 1.0
    factors["adv_dec_ratio"] = np.clip(adv_ratio / 3, 0, 1)

    # ---- 61. limit_up_count: 涨停数 ----
    # 用标的自身大幅上涨近似
    limit_up = np.zeros(n)
    for i in range(5, n):
        if returns[i] > 0.095:  # 接近涨停
            limit_up[i] = 1.0
        elif returns[i] > 0.05:
            limit_up[i] = 0.5
    factors["limit_up_count"] = limit_up

    # ---- 62. sector_momentum: 板块动量 ----
    # 用标的自身动量近似
    momentum = np.zeros(n)
    for i in range(20, n):
        ret_5 = (closes[i] - closes[max(0,i-5)]) / closes[max(0,i-5)] if closes[max(0,i-5)] > 0 else 0
        ret_20 = (closes[i] - closes[max(0,i-20)]) / closes[max(0,i-20)] if closes[max(0,i-20)] > 0 else 0
        momentum[i] = min(1.0, max(0.0, ret_5 * 5 + ret_20 * 2))
    factors["sector_momentum"] = momentum

    # ---- 63. sector_leader_strength: 龙头强度 ----
    # 用标的相对强度近似
    leader_str = np.zeros(n)
    for i in range(60, n):
        ret_60 = (closes[i] - closes[max(0,i-60)]) / closes[max(0,i-60)] if closes[max(0,i-60)] > 0 else 0
        leader_str[i] = min(1.0, max(0.0, ret_60 * 2 + 0.5))
    factors["sector_leader_strength"] = leader_str

    # ---- 64. market_risk_level: 市场风险等级 ----
    # 综合波动率+回撤
    risk = np.zeros(n)
    for i in range(60, n):
        dd = (np.max(closes[max(0,i-59):i+1]) - closes[i]) / np.max(closes[max(0,i-59):i+1])
        vol = vol_20[i] if not np.isnan(vol_20[i]) else 0.2
        risk[i] = min(1.0, dd * 2 + vol)
    factors["market_risk_level"] = risk

    # ---- 65. capm_beta: 贝塔 ----
    # 用标的自身波动与"市场"（自身均线）的关系近似
    beta = np.zeros(n)
    for i in range(60, n):
        stock_ret = np.array(returns[max(0,i-59):i+1], dtype=float)
        # market_ret: ma20的百分比变化
        ma_seg = np.array(ma20[max(0,i-59):i+1], dtype=float)
        market_ret = np.zeros(len(ma_seg))
        market_ret[0] = 0.0
        for j in range(1, len(ma_seg)):
            if ma_seg[j-1] > 0 and not np.isnan(ma_seg[j-1]) and not np.isnan(ma_seg[j]):
                market_ret[j] = (ma_seg[j] - ma_seg[j-1]) / ma_seg[j-1]
        if len(stock_ret) > 1 and np.std(market_ret) > 1e-10:
            cov_matrix = np.cov(stock_ret, market_ret)
            beta[i] = cov_matrix[0, 1] / max(np.var(market_ret), 1e-10)
            beta[i] = np.clip(abs(beta[i]), 0, 3) / 3
    factors["capm_beta"] = beta

    # ---- 66. liquidity_score: 流动性评分 ----
    # 用成交量稳定性评估
    liquidity = np.zeros(n)
    for i in range(60, n):
        vol_cv = np.std(volumes[max(0,i-59):i+1]) / max(np.mean(volumes[max(0,i-59):i+1]), 1)
        liquidity[i] = max(0.0, 1 - vol_cv)
    factors["liquidity_score"] = liquidity

    # ---- 67. turnover_rate_z: 换手率Z分数 ----
    # 用成交量Z分数近似
    factors["turnover_rate_z"] = np.clip(_zscore(volumes, 60) / 3, -1, 1)

    # 外部数据覆盖（如果有）
    if market_data:
        for key in ["market_trend", "market_volatility", "adv_dec_ratio",
                     "limit_up_count", "sector_momentum", "sector_leader_strength"]:
            if key in market_data:
                factors[key] = np.full(n, market_data[key])

    return factors


# ============================================================
# 因子引擎主类
# ============================================================

class WyckoffFactorEngine:
    """
    威科夫68维因子计算引擎

    用法:
        engine = WyckoffFactorEngine()
        factors = engine.compute_all(aligned_data)

    返回的 factor_matrix 形状为 (n_15min_bars, 68)，
    每个15分钟bar对应一个68维因子向量。
    """

    def __init__(self):
        self._daily_cache: Dict[str, Dict[str, np.ndarray]] = {}

    def compute_all(self, aligned) -> Dict[str, Any]:
        """
        计算全部68维因子

        Args:
            aligned: AlignedData 实例（来自 MultiTimeframePipeline）

        Returns:
            {
                "factor_names": List[str],           # 68个因子名
                "factor_matrix": np.ndarray,         # (n, 68) 因子矩阵
                "daily_factors": Dict[str, np.ndarray], # 日线级别的因子
                "m15_factors": Dict[str, np.ndarray],   # 15分钟级别的因子
                "timestamp": str,
            }
        """
        n = aligned.count
        if n == 0:
            return {"factor_names": ALL_FACTOR_NAMES, "factor_matrix": np.array([]).reshape(0, 68)}

        # 日线数据转numpy
        d_opens = np.array(aligned.daily_opens, dtype=float)
        d_highs = np.array(aligned.daily_highs, dtype=float)
        d_lows = np.array(aligned.daily_lows, dtype=float)
        d_closes = np.array(aligned.daily_closes, dtype=float)
        d_volumes = np.array(aligned.daily_volumes, dtype=float)

        # 15分钟数据转numpy
        m15_opens = np.array(aligned.m15_opens, dtype=float)
        m15_highs = np.array(aligned.m15_highs, dtype=float)
        m15_lows = np.array(aligned.m15_lows, dtype=float)
        m15_closes = np.array(aligned.m15_closes, dtype=float)
        m15_volumes = np.array(aligned.m15_volumes, dtype=float)

        # ---- 计算日线级别因子（1-4组，6组） ----
        print("[WyckoffFactorEngine] 计算日线级别因子...")
        wyckoff = compute_wyckoff_structure(d_opens, d_highs, d_lows, d_closes, d_volumes)
        vol_health = compute_volume_health(d_opens, d_highs, d_lows, d_closes, d_volumes)
        range_factors = compute_range_factors(d_opens, d_highs, d_lows, d_closes, d_volumes)
        breakout = compute_breakout_factors(d_opens, d_highs, d_lows, d_closes, d_volumes)
        sentiment = compute_market_sentiment(d_closes, d_volumes)

        daily_factors = {}
        daily_factors.update(wyckoff)
        daily_factors.update(vol_health)
        daily_factors.update(range_factors)
        daily_factors.update(breakout)
        daily_factors.update(sentiment)

        # ---- 计算15分钟级别因子（第5组） ----
        print("[WyckoffFactorEngine] 计算15分钟级别因子...")
        m15_factors = compute_order_book_factors(
            m15_opens, m15_highs, m15_lows, m15_closes, m15_volumes,
            aligned.m15_to_daily
        )

        # ---- 构建68维因子矩阵 ----
        # 日线因子映射到15分钟：每个15分钟bar取所属日线bar的因子值
        print("[WyckoffFactorEngine] 构建68维因子矩阵...")
        factor_matrix = np.zeros((n, 68))

        for col_idx, name in enumerate(ALL_FACTOR_NAMES):
            if name in ORDER_BOOK_FACTORS:
                # 第5组：15分钟因子，直接使用
                factor_matrix[:, col_idx] = m15_factors.get(name, np.zeros(n))
            else:
                # 第1-4组、第6组：日线因子，映射到15分钟
                daily_arr = daily_factors.get(name, np.zeros(len(d_closes)))
                for i in range(n):
                    daily_idx = aligned.m15_to_daily[i] if i < len(aligned.m15_to_daily) else -1
                    if 0 <= daily_idx < len(daily_arr):
                        factor_matrix[i, col_idx] = daily_arr[daily_idx]
                    else:
                        factor_matrix[i, col_idx] = 0.0

        # 处理NaN
        factor_matrix = np.nan_to_num(factor_matrix, nan=0.0)

        print(f"[WyckoffFactorEngine] 因子矩阵: {factor_matrix.shape}, "
              f"非零比例: {np.count_nonzero(factor_matrix)/factor_matrix.size:.1%}")

        return {
            "factor_names": ALL_FACTOR_NAMES,
            "factor_matrix": factor_matrix,
            "daily_factors": daily_factors,
            "m15_factors": m15_factors,
            "timestamp": aligned.fetch_time,
        }

    def compute_single_bar(self, aligned, m15_idx: int) -> np.ndarray:
        """
        计算单个15分钟bar的68维因子向量（用于实时信号生成）

        Args:
            aligned: AlignedData
            m15_idx: 15分钟bar索引

        Returns:
            np.ndarray: shape (68,) 的因子向量
        """
        # 对于实时使用，先计算全量再取单行
        result = self.compute_all(aligned)
        if m15_idx < result["factor_matrix"].shape[0]:
            return result["factor_matrix"][m15_idx]
        return np.zeros(68)


# ============================================================
# 单例
# ============================================================

_factor_engine_instance: Optional[WyckoffFactorEngine] = None


def get_factor_engine() -> WyckoffFactorEngine:
    global _factor_engine_instance
    if _factor_engine_instance is None:
        _factor_engine_instance = WyckoffFactorEngine()
    return _factor_engine_instance