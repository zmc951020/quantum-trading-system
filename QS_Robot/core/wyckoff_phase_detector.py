#!/usr/bin/env python3
"""
威科夫阶段判定器 + 信号生成器
================================
为「特种兵・威科夫量价自适应策略」提供：
  1. 四阶段自动判定（吸筹/拉升/派发/下跌）
  2. 买卖信号生成
  3. 多周期共振确认
  4. 动态止损止盈

判定逻辑：
  吸筹阶段：价格在区间下轨 + 成交量萎缩 + spring信号 + 无供应
  拉升阶段：价格突破区间上轨 + 放量 + SOS信号 + JOC确认
  派发阶段：价格在区间上轨 + UT/UTAD信号 + 需求枯竭
  下跌阶段：价格跌破区间下轨 + SOW信号 + 供应涌现

信号逻辑：
  买入：吸筹→拉升转换点 / 拉升阶段回踩LPS
  卖出：拉升→派发转换点 / 派发阶段UT反弹
"""

import os
import sys
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import IntEnum

# 路径设置
current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)


# ============================================================
# 枚举定义
# ============================================================

class WyckoffPhase(IntEnum):
    """威科夫四阶段"""
    ACCUMULATION = 0   # 吸筹
    MARKUP = 1         # 拉升
    DISTRIBUTION = 2   # 派发
    MARKDOWN = 3       # 下跌
    UNKNOWN = -1       # 不确定


class SignalType(IntEnum):
    """交易信号类型"""
    NO_SIGNAL = 0
    BUY = 1           # 做多
    SELL = 2          # 平多/做空
    STRONG_BUY = 3    # 强买（多周期共振）
    STRONG_SELL = 4   # 强卖（多周期共振）


# ============================================================
# 数据模型
# ============================================================

@dataclass
class PhaseResult:
    """阶段判定结果"""
    phase: WyckoffPhase
    confidence: float          # 判定置信度 0-1
    phase_strength: float      # 阶段强度 0-1
    transition_prob: float     # 阶段转换概率 0-1
    sub_phase: str = ""        # 子阶段描述
    supporting_factors: List[str] = field(default_factory=list)
    conflicting_factors: List[str] = field(default_factory=list)


@dataclass
class TradeSignal:
    """交易信号"""
    signal_type: SignalType
    confidence: float          # 信号置信度 0-1
    entry_price: float         # 建议入场价
    stop_loss: float           # 止损价
    take_profit: float         # 止盈价
    position_pct: float        # 建议仓位比例
    reason: str = ""           # 信号原因
    mtf_confirm: bool = False  # 多周期共振确认


# ============================================================
# 因子索引映射
# ============================================================

# 与 wyckoff_factors.py 中的 ALL_FACTOR_NAMES 保持一致
FACTOR_INDEX = {
    # 威科夫结构 (0-11)
    "wyckoff_phase": 0, "spring_score": 1, "sos_score": 2,
    "lps_score": 3, "joc_score": 4, "ut_ad_score": 5,
    "sow_score": 6, "supply_exhausted": 7, "demand_exhausted": 8,
    "absorption_signal": 9, "stop_grab": 10, "distribution_head": 11,
    # 量价健康度 (12-23)
    "volume_trend_health": 12, "up_vol_ratio": 13, "down_vol_ratio": 14,
    "effort_result": 15, "volume_ma5_dev": 16, "volume_ma20_dev": 17,
    "large_volume_signal": 18, "no_demand": 19, "no_supply": 20,
    "volume_trend_angle": 21, "vol_price_corr": 22, "vol_spike": 23,
    # 箱体震荡 (24-35)
    "range_width": 24, "range_duration": 25, "range_upper_valid": 26,
    "range_lower_valid": 27, "price_to_upper": 28, "price_to_lower": 29,
    "ma_flat_score": 30, "ma_cluster_score": 31, "range_vol_shrink": 32,
    "range_vol_at_top": 33, "range_vol_at_bottom": 34, "range_break_prob": 35,
    # 突破判别 (36-45)
    "breakout_strength": 36, "breakout_vol_ratio": 37, "breakout_retest_vol": 38,
    "breakout_retest_hold": 39, "false_breakout_score": 40,
    "breakout_support_loss": 41, "breakout_ma_confirm": 42,
    "breakout_trend_confirm": 43, "breakout_depth": 44,
    "breakout_rebound_speed": 45,
    # 盘口分时 (46-57)
    "attack_wave": 46, "shock_wave": 47, "test_wave": 48,
    "turn_back_wave": 49, "fake_rise_wave": 50, "avg_line_strength": 51,
    "time_share_vol_peak": 52, "time_share_trend": 53,
    "open_position_power": 54, "close_position_power": 55,
    "vol_per_min": 56, "depth_vol_imbalance": 57,
    # 市场情绪 (58-67)
    "market_trend": 58, "market_volatility": 59, "adv_dec_ratio": 60,
    "limit_up_count": 61, "sector_momentum": 62, "sector_leader_strength": 63,
    "market_risk_level": 64, "capm_beta": 65, "liquidity_score": 66,
    "turnover_rate_z": 67,
}


# ============================================================
# 威科夫阶段判定器
# ============================================================

class WyckoffPhaseDetector:
    """
    威科夫阶段自动判定器

    基于68维因子，用量化规则判定当前市场阶段。
    判定逻辑分两级：
      1. 一级判定：基于因子阈值的快速判定
      2. 二级判定：基于因子综合评分的精细判定
    """

    # 阶段判定阈值（可优化参数）
    THRESHOLDS = {
        # 吸筹判定
        "acc_spring": 0.25,          # spring信号阈值
        "acc_supply_ex": 0.35,       # 供应耗尽阈值
        "acc_no_supply": 0.25,       # 无供应阈值
        "acc_near_low": 0.25,        # 接近下轨阈值
        "acc_vol_shrink": 0.25,      # 量能萎缩阈值
        "acc_absorption": 0.25,      # 吸收信号阈值
        # 拉升判定
        "mup_joc": 0.20,             # JOC突破阈值
        "mup_sos": 0.20,             # SOS信号阈值
        "mup_breakout": 0.15,        # 突破强度阈值
        "mup_trend_up": 0.55,        # 趋势向上阈值
        "mup_vol_confirm": 0.20,     # 量能确认阈值
        "mup_lps": 0.20,             # LPS回踩阈值
        # 派发判定
        "dis_ut": 0.20,              # UT诱多阈值
        "dis_demand_ex": 0.35,       # 需求枯竭阈值
        "dis_no_demand": 0.25,       # 无需求阈值
        "dis_near_high": 0.75,       # 接近上轨阈值
        "dis_dist_head": 0.20,       # 顶部盘头阈值
        "dis_effort_neg": -0.30,     # 努力无结果阈值
        # 下跌判定
        "mdn_sow": 0.20,             # SOW弱势信号阈值
        "mdn_trend_down": 0.45,      # 趋势向下阈值
        "mdn_support_loss": 0.30,    # 支撑失效阈值
        "mdn_false_break": 0.25,     # 假突破阈值
    }

    def __init__(self, thresholds: Dict[str, float] = None):
        if thresholds:
            self.THRESHOLDS.update(thresholds)

    def detect(self, factor_vector: np.ndarray) -> PhaseResult:
        """
        判定单个bar的威科夫阶段

        Args:
            factor_vector: shape (68,) 的因子向量

        Returns:
            PhaseResult: 阶段判定结果
        """
        if len(factor_vector) < 68:
            return PhaseResult(phase=WyckoffPhase.UNKNOWN, confidence=0.0,
                               phase_strength=0.0, transition_prob=0.0)

        f = factor_vector
        t = self.THRESHOLDS

        # ---- 提取关键因子 ----
        wyckoff_phase = f[FACTOR_INDEX["wyckoff_phase"]]
        spring = f[FACTOR_INDEX["spring_score"]]
        sos = f[FACTOR_INDEX["sos_score"]]
        lps = f[FACTOR_INDEX["lps_score"]]
        joc = f[FACTOR_INDEX["joc_score"]]
        ut = f[FACTOR_INDEX["ut_ad_score"]]
        sow = f[FACTOR_INDEX["sow_score"]]
        supply_ex = f[FACTOR_INDEX["supply_exhausted"]]
        demand_ex = f[FACTOR_INDEX["demand_exhausted"]]
        absorption = f[FACTOR_INDEX["absorption_signal"]]
        stop_grab = f[FACTOR_INDEX["stop_grab"]]
        dist_head = f[FACTOR_INDEX["distribution_head"]]

        no_demand = f[FACTOR_INDEX["no_demand"]]
        no_supply = f[FACTOR_INDEX["no_supply"]]
        effort = f[FACTOR_INDEX["effort_result"]]
        vol_health = f[FACTOR_INDEX["volume_trend_health"]]

        price_to_upper = f[FACTOR_INDEX["price_to_upper"]]
        price_to_lower = f[FACTOR_INDEX["price_to_lower"]]
        range_break_prob = f[FACTOR_INDEX["range_break_prob"]]
        range_vol_shrink = f[FACTOR_INDEX["range_vol_shrink"]]

        break_strength = f[FACTOR_INDEX["breakout_strength"]]
        break_vol = f[FACTOR_INDEX["breakout_vol_ratio"]]
        retest_hold = f[FACTOR_INDEX["breakout_retest_hold"]]
        false_break = f[FACTOR_INDEX["false_breakout_score"]]
        support_loss = f[FACTOR_INDEX["breakout_support_loss"]]
        ma_confirm = f[FACTOR_INDEX["breakout_ma_confirm"]]
        trend_confirm = f[FACTOR_INDEX["breakout_trend_confirm"]]

        market_trend = f[FACTOR_INDEX["market_trend"]]
        market_risk = f[FACTOR_INDEX["market_risk_level"]]

        # ---- 一级判定：量化规则 ----
        phase_scores = {
            WyckoffPhase.ACCUMULATION: 0.0,
            WyckoffPhase.MARKUP: 0.0,
            WyckoffPhase.DISTRIBUTION: 0.0,
            WyckoffPhase.MARKDOWN: 0.0,
        }

        supporting = []
        conflicting = []

        # === 吸筹判定 ===
        acc_score = 0.0
        acc_count = 0

        if spring > t["acc_spring"]:
            acc_score += spring * 0.20; acc_count += 1
            supporting.append(f"spring={spring:.2f}")
        if supply_ex > t["acc_supply_ex"]:
            acc_score += supply_ex * 0.20; acc_count += 1
            supporting.append(f"supply_exhausted={supply_ex:.2f}")
        if no_supply > t["acc_no_supply"]:
            acc_score += no_supply * 0.15; acc_count += 1
            supporting.append(f"no_supply={no_supply:.2f}")
        if price_to_lower < t["acc_near_low"]:
            acc_score += (1 - price_to_lower) * 0.15; acc_count += 1
            supporting.append(f"near_low={price_to_lower:.2f}")
        if range_vol_shrink > t["acc_vol_shrink"]:
            acc_score += range_vol_shrink * 0.10; acc_count += 1
        if absorption > t["acc_absorption"]:
            acc_score += absorption * 0.10; acc_count += 1
            supporting.append(f"absorption={absorption:.2f}")
        if stop_grab > 0.3:
            acc_score += stop_grab * 0.10; acc_count += 1
            supporting.append(f"stop_grab={stop_grab:.2f}")

        phase_scores[WyckoffPhase.ACCUMULATION] = acc_score

        # 冲突检查：如果同时有很强的SOS或JOC，更可能是拉升
        if sos > t["mup_sos"] or joc > t["mup_joc"]:
            conflicting.append(f"SOS/JOC active (sos={sos:.2f}, joc={joc:.2f})")

        # === 拉升判定 ===
        mup_score = 0.0

        if joc > t["mup_joc"]:
            mup_score += joc * 0.20
            supporting.append(f"joc={joc:.2f}")
        if sos > t["mup_sos"]:
            mup_score += sos * 0.15
            supporting.append(f"sos={sos:.2f}")
        if break_strength > t["mup_breakout"]:
            mup_score += break_strength * 0.15
            supporting.append(f"breakout={break_strength:.2f}")
        if trend_confirm > t["mup_trend_up"]:
            mup_score += trend_confirm * 0.10
        if break_vol > t["mup_vol_confirm"]:
            mup_score += break_vol * 0.10
        if lps > t["mup_lps"]:
            mup_score += lps * 0.10
            supporting.append(f"lps={lps:.2f}")
        if ma_confirm > 0.5:
            mup_score += ma_confirm * 0.10
        if retest_hold > 0.5:
            mup_score += retest_hold * 0.10

        phase_scores[WyckoffPhase.MARKUP] = mup_score

        if ut > t["dis_ut"] or sow > t["mdn_sow"]:
            conflicting.append(f"UT/SOW active (ut={ut:.2f}, sow={sow:.2f})")

        # === 派发判定 ===
        dis_score = 0.0

        if ut > t["dis_ut"]:
            dis_score += ut * 0.20
            supporting.append(f"ut={ut:.2f}")
        if demand_ex > t["dis_demand_ex"]:
            dis_score += demand_ex * 0.20
            supporting.append(f"demand_exhausted={demand_ex:.2f}")
        if no_demand > t["dis_no_demand"]:
            dis_score += no_demand * 0.15
            supporting.append(f"no_demand={no_demand:.2f}")
        if price_to_upper < t["dis_near_high"]:
            dis_score += (1 - price_to_upper) * 0.10
            supporting.append(f"near_high={price_to_upper:.2f}")
        if dist_head > t["dis_dist_head"]:
            dis_score += dist_head * 0.15
            supporting.append(f"distribution_head={dist_head:.2f}")
        if effort < t["dis_effort_neg"]:
            dis_score += abs(effort) * 0.10
            supporting.append(f"effort_negative={effort:.2f}")
        if false_break > 0.3:
            dis_score += false_break * 0.10

        phase_scores[WyckoffPhase.DISTRIBUTION] = dis_score

        # === 下跌判定 ===
        mdn_score = 0.0

        if sow > t["mdn_sow"]:
            mdn_score += sow * 0.25
            supporting.append(f"sow={sow:.2f}")
        if trend_confirm < t["mdn_trend_down"]:
            mdn_score += (1 - trend_confirm) * 0.15
        if support_loss > t["mdn_support_loss"]:
            mdn_score += support_loss * 0.15
            supporting.append(f"support_loss={support_loss:.2f}")
        if false_break > t["mdn_false_break"]:
            mdn_score += false_break * 0.15
        if price_to_lower > 0.7:
            mdn_score += price_to_lower * 0.10
        if vol_health < 0.3:
            mdn_score += (1 - vol_health) * 0.10
        if market_risk > 0.6:
            mdn_score += market_risk * 0.10

        phase_scores[WyckoffPhase.MARKDOWN] = mdn_score

        # ---- 确定最终阶段 ----
        best_phase = max(phase_scores, key=phase_scores.get)
        best_score = phase_scores[best_phase]
        second_score = sorted(phase_scores.values(), reverse=True)[1] if len(phase_scores) > 1 else 0

        if best_score < 0.1:
            # 所有阶段得分都太低，使用因子引擎的阶段判定
            if wyckoff_phase == 0:
                best_phase = WyckoffPhase.ACCUMULATION
            elif wyckoff_phase == 1:
                best_phase = WyckoffPhase.MARKUP
            elif wyckoff_phase == 2:
                best_phase = WyckoffPhase.DISTRIBUTION
            elif wyckoff_phase == 3:
                best_phase = WyckoffPhase.MARKDOWN
            confidence = 0.3
        else:
            # 置信度 = 最佳得分 / (最佳得分 + 次佳得分)
            confidence = min(0.95, best_score / (best_score + second_score + 0.01))

        # 阶段强度
        phase_strength = min(1.0, best_score * 2)

        # 转换概率
        transition_prob = 1 - confidence if best_score > 0.1 else 0.5

        # 子阶段描述
        sub_phase = self._get_sub_phase(best_phase, factor_vector)

        return PhaseResult(
            phase=best_phase,
            confidence=confidence,
            phase_strength=phase_strength,
            transition_prob=transition_prob,
            sub_phase=sub_phase,
            supporting_factors=supporting[:5],
            conflicting_factors=conflicting[:3],
        )

    def _get_sub_phase(self, phase: WyckoffPhase, f: np.ndarray) -> str:
        """获取子阶段描述"""
        if phase == WyckoffPhase.ACCUMULATION:
            spring = f[FACTOR_INDEX["spring_score"]]
            supply_ex = f[FACTOR_INDEX["supply_exhausted"]]
            if spring > 0.5:
                return "Spring震仓"
            elif supply_ex > 0.5:
                return "供应耗尽"
            elif f[FACTOR_INDEX["absorption_signal"]] > 0.4:
                return "主力吸收"
            elif f[FACTOR_INDEX["stop_grab"]] > 0.3:
                return "扫止损"
            else:
                return "底部盘整"

        elif phase == WyckoffPhase.MARKUP:
            joc = f[FACTOR_INDEX["joc_score"]]
            sos = f[FACTOR_INDEX["sos_score"]]
            lps = f[FACTOR_INDEX["lps_score"]]
            if joc > 0.4:
                return "JOC突破"
            elif sos > 0.4:
                return "SOS强势拉升"
            elif lps > 0.3:
                return "LPS回踩确认"
            elif f[FACTOR_INDEX["breakout_strength"]] > 0.3:
                return "突破拉升"
            else:
                return "趋势延续"

        elif phase == WyckoffPhase.DISTRIBUTION:
            ut = f[FACTOR_INDEX["ut_ad_score"]]
            dist_head = f[FACTOR_INDEX["distribution_head"]]
            if ut > 0.4:
                return "UT诱多"
            elif dist_head > 0.4:
                return "顶部盘头"
            elif f[FACTOR_INDEX["demand_exhausted"]] > 0.5:
                return "需求枯竭"
            elif f[FACTOR_INDEX["no_demand"]] > 0.3:
                return "无需求上涨"
            else:
                return "高位震荡"

        elif phase == WyckoffPhase.MARKDOWN:
            sow = f[FACTOR_INDEX["sow_score"]]
            if sow > 0.4:
                return "SOW破位"
            elif f[FACTOR_INDEX["breakout_support_loss"]] > 0.5:
                return "支撑失效"
            elif f[FACTOR_INDEX["false_breakout_score"]] > 0.4:
                return "假突破回落"
            else:
                return "趋势下跌"

        return "未知"


# ============================================================
# 信号生成器
# ============================================================

class SignalGenerator:
    """
    威科夫交易信号生成器

    基于阶段判定 + 多周期共振，生成买卖信号。
    信号规则：
      - 强买：吸筹确认 + 日线SOS + 60分钟突破 + 15分钟攻击波
      - 买入：吸筹→拉升转换 / 拉升回踩LPS
      - 卖出：拉升→派发转换 / 派发UT反弹
      - 强卖：派发确认 + 日线SOW + 60分钟破位
    """

    def __init__(self,
                 stop_loss_atr_mult: float = 2.0,
                 take_profit_rr: float = 2.5,
                 base_position_pct: float = 0.2):
        """
        Args:
            stop_loss_atr_mult: 止损ATR倍数
            take_profit_rr: 止盈风险回报比
            base_position_pct: 基础仓位比例
        """
        self.stop_loss_atr_mult = stop_loss_atr_mult
        self.take_profit_rr = take_profit_rr
        self.base_position_pct = base_position_pct

        self._phase_detector = WyckoffPhaseDetector()
        self._prev_phase: Optional[WyckoffPhase] = None
        self._prev_signal: Optional[TradeSignal] = None

    def generate(self, factor_vector: np.ndarray,
                 price: float, atr: float = None,
                 m15_factor: np.ndarray = None,
                 h60_factor: np.ndarray = None,
                 daily_factor: np.ndarray = None) -> TradeSignal:
        """
        生成交易信号

        Args:
            factor_vector: 当前15分钟bar的68维因子向量
            price: 当前价格
            atr: ATR值（用于止损计算）
            m15_factor: 15分钟因子（就是factor_vector本身）
            h60_factor: 60分钟因子向量
            daily_factor: 日线因子向量

        Returns:
            TradeSignal: 交易信号
        """
        # 阶段判定
        phase_result = self._phase_detector.detect(factor_vector)
        phase = phase_result.phase
        confidence = phase_result.confidence

        # 多周期共振检查
        mtf_confirm = self._check_mtf_resonance(phase, factor_vector,
                                                  h60_factor, daily_factor)

        # 初始化信号
        signal = TradeSignal(
            signal_type=SignalType.NO_SIGNAL,
            confidence=0.0,
            entry_price=price,
            stop_loss=price * 0.95,
            take_profit=price * 1.05,
            position_pct=0.0,
            reason="",
            mtf_confirm=mtf_confirm,
        )

        # ---- 信号生成逻辑 ----
        f = factor_vector

        # 提取关键因子
        spring = f[FACTOR_INDEX["spring_score"]]
        sos = f[FACTOR_INDEX["sos_score"]]
        joc = f[FACTOR_INDEX["joc_score"]]
        lps = f[FACTOR_INDEX["lps_score"]]
        ut = f[FACTOR_INDEX["ut_ad_score"]]
        sow = f[FACTOR_INDEX["sow_score"]]
        supply_ex = f[FACTOR_INDEX["supply_exhausted"]]
        break_strength = f[FACTOR_INDEX["breakout_strength"]]
        break_vol = f[FACTOR_INDEX["breakout_vol_ratio"]]
        attack_wave = f[FACTOR_INDEX["attack_wave"]]
        test_wave = f[FACTOR_INDEX["test_wave"]]
        avg_line = f[FACTOR_INDEX["avg_line_strength"]]
        time_trend = f[FACTOR_INDEX["time_share_trend"]]
        market_risk = f[FACTOR_INDEX["market_risk_level"]]
        vol_health = f[FACTOR_INDEX["volume_trend_health"]]

        # === 买入信号 ===

        # 强买：吸筹确认 + 多周期共振
        if (phase == WyckoffPhase.ACCUMULATION and
                spring > 0.4 and supply_ex > 0.4 and
                mtf_confirm and market_risk < 0.5):
            signal.signal_type = SignalType.STRONG_BUY
            signal.confidence = min(0.95, confidence + 0.1)
            signal.reason = f"强买: 吸筹确认 + 多周期共振 (spring={spring:.2f}, supply_ex={supply_ex:.2f})"
            signal.position_pct = self.base_position_pct * 1.2

        # 吸筹→拉升转换
        elif (self._prev_phase == WyckoffPhase.ACCUMULATION and
              phase == WyckoffPhase.MARKUP and
              (sos > 0.2 or joc > 0.2 or break_strength > 0.2)):
            signal.signal_type = SignalType.BUY
            signal.confidence = min(0.85, confidence + 0.05)
            signal.reason = f"买入: 吸筹→拉升转换 (phase={phase_result.sub_phase})"
            signal.position_pct = self.base_position_pct

        # 拉升回踩LPS
        elif (phase == WyckoffPhase.MARKUP and
              lps > 0.25 and avg_line > 0.4 and
              time_trend > 0):
            signal.signal_type = SignalType.BUY
            signal.confidence = min(0.80, confidence + 0.05)
            signal.reason = f"买入: LPS回踩确认 (lps={lps:.2f})"
            signal.position_pct = self.base_position_pct * 0.9

        # 15分钟攻击波 + 日线趋势向上
        elif (attack_wave > 0.3 and break_vol > 0.2 and
              f[FACTOR_INDEX["breakout_trend_confirm"]] > 0.6 and
              market_risk < 0.5):
            signal.signal_type = SignalType.BUY
            signal.confidence = min(0.75, attack_wave * 0.8 + break_vol * 0.2)
            signal.reason = f"买入: 攻击波突破 (attack_wave={attack_wave:.2f})"
            signal.position_pct = self.base_position_pct * 0.7

        # === 卖出信号 ===

        # 强卖：派发确认 + 多周期共振
        elif (phase == WyckoffPhase.DISTRIBUTION and
              ut > 0.4 and f[FACTOR_INDEX["demand_exhausted"]] > 0.4 and
              mtf_confirm and vol_health < 0.3):
            signal.signal_type = SignalType.STRONG_SELL
            signal.confidence = min(0.95, confidence + 0.1)
            signal.reason = f"强卖: 派发确认 + 多周期共振 (ut={ut:.2f})"
            signal.position_pct = self.base_position_pct * 1.0

        # 拉升→派发转换
        elif (self._prev_phase == WyckoffPhase.MARKUP and
              phase == WyckoffPhase.DISTRIBUTION and
              (ut > 0.2 or f[FACTOR_INDEX["demand_exhausted"]] > 0.3)):
            signal.signal_type = SignalType.SELL
            signal.confidence = min(0.85, confidence + 0.05)
            signal.reason = f"卖出: 拉升→派发转换 (phase={phase_result.sub_phase})"
            signal.position_pct = self.base_position_pct * 0.8

        # 派发UT反弹
        elif (phase == WyckoffPhase.DISTRIBUTION and
              ut > 0.3 and f[FACTOR_INDEX["no_demand"]] > 0.2):
            signal.signal_type = SignalType.SELL
            signal.confidence = min(0.80, ut * 0.7 + 0.1)
            signal.reason = f"卖出: UT诱多反弹 (ut={ut:.2f})"
            signal.position_pct = self.base_position_pct * 0.7

        # SOW破位
        elif (phase == WyckoffPhase.MARKDOWN and
              sow > 0.3 and f[FACTOR_INDEX["breakout_support_loss"]] > 0.3):
            signal.signal_type = SignalType.SELL
            signal.confidence = min(0.85, sow * 0.8 + 0.1)
            signal.reason = f"卖出: SOW破位 (sow={sow:.2f})"
            signal.position_pct = self.base_position_pct * 0.9

        # 假突破回落
        elif (f[FACTOR_INDEX["false_breakout_score"]] > 0.4 and
              f[FACTOR_INDEX["fake_rise_wave"]] > 0.3):
            signal.signal_type = SignalType.SELL
            signal.confidence = f[FACTOR_INDEX["false_breakout_score"]] * 0.8
            signal.reason = "卖出: 假突破回落"
            signal.position_pct = self.base_position_pct * 0.6

        # ---- 计算止损止盈 ----
        if signal.signal_type in (SignalType.BUY, SignalType.STRONG_BUY):
            if atr and atr > 0:
                signal.stop_loss = price - atr * self.stop_loss_atr_mult
            else:
                signal.stop_loss = price * 0.97
            signal.take_profit = price + (price - signal.stop_loss) * self.take_profit_rr

        elif signal.signal_type in (SignalType.SELL, SignalType.STRONG_SELL):
            if atr and atr > 0:
                signal.stop_loss = price + atr * self.stop_loss_atr_mult
            else:
                signal.stop_loss = price * 1.03
            signal.take_profit = price - (signal.stop_loss - price) * self.take_profit_rr

        # 市场风险调整仓位
        if market_risk > 0.6:
            signal.position_pct *= 0.5
        elif market_risk > 0.4:
            signal.position_pct *= 0.75

        # 更新状态
        self._prev_phase = phase
        self._prev_signal = signal

        return signal

    def _check_mtf_resonance(self, phase: WyckoffPhase,
                              m15_factor: np.ndarray,
                              h60_factor: np.ndarray = None,
                              daily_factor: np.ndarray = None) -> bool:
        """
        多周期共振检查

        买点共振：日线趋势向上 + 60分钟突破 + 15分钟攻击波
        卖点共振：日线趋势向下 + 60分钟破位 + 15分钟假突破
        """
        confirm_count = 0

        # 15分钟级别确认
        if phase in (WyckoffPhase.ACCUMULATION, WyckoffPhase.MARKUP):
            if (m15_factor[FACTOR_INDEX["attack_wave"]] > 0.2 or
                m15_factor[FACTOR_INDEX["spring_score"]] > 0.3 or
                m15_factor[FACTOR_INDEX["sos_score"]] > 0.2):
                confirm_count += 1
        elif phase in (WyckoffPhase.DISTRIBUTION, WyckoffPhase.MARKDOWN):
            if (m15_factor[FACTOR_INDEX["ut_ad_score"]] > 0.2 or
                m15_factor[FACTOR_INDEX["sow_score"]] > 0.2 or
                m15_factor[FACTOR_INDEX["fake_rise_wave"]] > 0.2):
                confirm_count += 1

        # 60分钟级别确认
        if h60_factor is not None and len(h60_factor) >= 68:
            if phase in (WyckoffPhase.ACCUMULATION, WyckoffPhase.MARKUP):
                if (h60_factor[FACTOR_INDEX["breakout_strength"]] > 0.15 or
                    h60_factor[FACTOR_INDEX["breakout_trend_confirm"]] > 0.5):
                    confirm_count += 1
            else:
                if (h60_factor[FACTOR_INDEX["breakout_support_loss"]] > 0.2 or
                    h60_factor[FACTOR_INDEX["breakout_trend_confirm"]] < 0.4):
                    confirm_count += 1

        # 日线级别确认
        if daily_factor is not None and len(daily_factor) >= 68:
            if phase in (WyckoffPhase.ACCUMULATION, WyckoffPhase.MARKUP):
                if (daily_factor[FACTOR_INDEX["market_trend"]] > 0.5 or
                    daily_factor[FACTOR_INDEX["breakout_trend_confirm"]] > 0.5):
                    confirm_count += 1
            else:
                if (daily_factor[FACTOR_INDEX["market_trend"]] < 0.5 or
                    daily_factor[FACTOR_INDEX["breakout_trend_confirm"]] < 0.4):
                    confirm_count += 1

        # 至少2个周期确认
        return confirm_count >= 2

    def reset(self):
        """重置状态（切换标的后调用）"""
        self._prev_phase = None
        self._prev_signal = None


# ============================================================
# 单例
# ============================================================

_phase_detector_instance: Optional[WyckoffPhaseDetector] = None
_signal_generator_instance: Optional[SignalGenerator] = None


def get_phase_detector() -> WyckoffPhaseDetector:
    global _phase_detector_instance
    if _phase_detector_instance is None:
        _phase_detector_instance = WyckoffPhaseDetector()
    return _phase_detector_instance


def get_signal_generator() -> SignalGenerator:
    global _signal_generator_instance
    if _signal_generator_instance is None:
        _signal_generator_instance = SignalGenerator()
    return _signal_generator_instance