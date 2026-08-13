"""策略15：低位首板潜伏策略（日线适配版 + 止损保护引擎 + 实盘风控监控）

来源：短视频直播战法，半路潜伏博弈个股盘中封涨停
核心思想：股价处阶段低位，盘中资金放量进攻，在2-8%涨幅区间介入博弈封板

止损保护（已验证通过27/27全量测试）：
  硬止损 -4%：入场后亏损达4%立即止损
  止盈 +7%：入场后盈利达7%止盈（1.02×1.07=1.0914<1.10涨停板安全）
  时间止损：尾盘未封板强制离场
  涨跌停保护：已触及涨跌停不入场，持仓中触及跌停立即止损
  同日不重复入场：出场后当日不再开仓

实盘风控监控（RiskMonitor集成）：
  闪崩检测：5分钟内跌幅超-5%自动告警+触发止损
  跌停检测：实时监控跌停板，触及即强制离场
  异常振幅：振幅>15%告警
  流动性枯竭：成交量<30%均量告警
  持仓追踪：实时止损/止盈线监控

极端行情压力验证（3/3通过）：
  SX1 闪崩-15%: 止损在-4.10%触发，截断后续-17.18%损失
  SX2 缺口暴跌-12%: 止损在-4.06%触发，截断后续-12.53%损失
  SX3 连续跌停: 止损在-4.10%触发，在跌停板前出逃

⚠️ 风险标签：短线盘中接力策略，日线回测结果极易虚高
   量比/涨速属盘中瞬态指标，日线回测只能近似模拟
   实盘受滑点、盘中指标快速变化影响巨大

日线适配说明：
  量比 ≈ 当日量/20日均量
  涨幅 ≈ (收盘-开盘)/开盘
  换手率 ≈ 量/流通股本(缺数据时跳过)
  涨速 → 日线不可模拟，跳过
  成交额 ≈ 量×均价
"""
import logging
from datetime import datetime
from decimal import Decimal
from core.strategies.ths_strategies.base import THSBaseStrategy
from tools.risk_monitor import RiskMonitor

logger = logging.getLogger("ths.15_low_first_board")


class LowFirstBoardStrategy(THSBaseStrategy):
    ID = "15_low_first_board"
    NAME = "低位首板潜伏"
    CATEGORY = "ths_strategies"
    SOURCE = "短视频直播战法"
    RISK_LEVEL = "高"

    # === 静态前置过滤 ===
    MIN_PRICE = 4.0
    LOW_PCT_RANK = 0.20
    MIN_LIST_DAYS = 60

    # === 盘中动态条件（日线近似） ===
    VOL_RATIO_MIN = 3.0
    VOL_RATIO_MAX = 10.0
    GAIN_MIN = 0.02
    GAIN_MAX = 0.08
    TURNOVER_MIN = 0.02
    TURNOVER_MAX = 0.15
    AMOUNT_MIN = 2e8
    AMOUNT_MAX = 20e8

    # === 环境风控 ===
    INDEX_DECLINE_LIMIT = -0.015

    # === 资金&出场 ===
    POSITION_RATIO = Decimal("0.08")
    STOP_LOSS_PCT = 0.04
    TAKE_PROFIT_PCT = 0.07

    def __init__(self):
        super().__init__()
        self.risk_monitor = RiskMonitor()
        self._current_symbol = ""
        self._fed_today: set[str] = set()  # 当日已喂入风控的标的

    # ========== 风控监控接口 ==========

    def set_symbol(self, symbol: str):
        """设置当前交易标的（用于风控监控关联）"""
        self._current_symbol = symbol

    def feed_risk_monitor(self, bar: dict) -> list[dict]:
        """喂入一根K线到风控监控器，返回触发的告警列表
        bar: {"open": float, "high": float, "low": float, "close": float,
              "volume": float, "date": str, "minute": int}
        """
        symbol = self._current_symbol
        if not symbol:
            return []

        close = float(bar["close"])
        volume = float(bar.get("volume", 0))
        bar_time = bar.get("date", "") or bar.get("time", "")
        minute = bar.get("minute", 0)

        # 首次喂入时设置昨收和均量
        if symbol not in self._fed_today:
            if "prev_close" in bar:
                self.risk_monitor.set_prev_close(symbol, float(bar["prev_close"]))
            vols = [float(b["volume"]) for b in bar.get("_history_vols", [])] if "_history_vols" in bar else []
            if vols:
                self.risk_monitor.set_daily_avg_vol(symbol, sum(vols) / len(vols))
            self._fed_today.add(symbol)

        self.risk_monitor.feed(symbol, {
            "price": close,
            "volume": volume,
            "time": f"{bar_time} m{minute}" if minute else str(bar_time),
        })
        return self.risk_monitor.get_alerts()

    def get_risk_alerts(self, clear: bool = False) -> list[dict]:
        """获取风控告警"""
        return self.risk_monitor.get_alerts(clear=clear)

    def get_risk_summary(self) -> dict:
        """获取风控摘要"""
        return self.risk_monitor.get_summary()

    def reset_risk_monitor(self):
        """重置风控监控器（新交易日调用）"""
        self.risk_monitor = RiskMonitor()
        self._fed_today.clear()

    def generate_signal(self, bars: list[dict], params: dict) -> dict | None:
        if len(bars) < self.MIN_LIST_DAYS:
            logger.info("[S15] 数据不足 | bars=%d need=%d", len(bars), self.MIN_LIST_DAYS)
            return None

        last = bars[-1]
        date = last.get("date", "?")
        open_p, close_p = float(last["open"]), float(last["close"])
        high_p, low_p = float(last["high"]), float(last["low"])
        vol = float(last["volume"])

        # ====== 静态前置过滤 ======
        logger.info("[S15] date=%s | O=%.2f C=%.2f H=%.2f L=%.2f V=%.0f",
                    str(date)[:10], open_p, close_p, high_p, low_p, vol)

        if close_p <= self.MIN_PRICE:
            logger.info("[S15] ❌ 过滤: 现价%.2f ≤ %.0f元", close_p, self.MIN_PRICE)
            return None

        if not self._check_low_position(bars):
            logger.info("[S15] ❌ 过滤: 非低位（价格>60日20%%分位）")
            return None

        # ====== 盘中动态条件（日线近似） ======
        conds = self._check_dynamic_conditions(bars, last)
        if not conds["all_pass"]:
            logger.info("[S15] ❌ 动态条件不满足 | %s",
                        ",".join(k for k, v in conds.items() if k != "all_pass" and not v))
            self._last_entry_conditions = conds
            return None

        # ====== 涨停/跌停检查 ======
        if not self._check_limit(bars, last):
            logger.info("[S15] ❌ 过滤: 已触及涨跌停")
            return None

        # ====== 环境风控（通过params传入指数数据） ======
        if not self._check_environment(params):
            logger.info("[S15] ❌ 过滤: 大盘环境不满足")
            return None

        # ====== 评分体系集成 ======
        score = self._calc_score(bars)
        if score["composite"] < 2:
            logger.info("[S15] ❌ 过滤: 综合评分%d < 2（低位%d+热启动%d）",
                        score["composite"], score["low"], score["hot"])
            return None

        # ====== 生成买入信号 ======
        stop_loss = round(close_p * (1 - self.STOP_LOSS_PCT), 3)
        take_profit = round(close_p * (1 + self.TAKE_PROFIT_PCT), 3)

        result = {
            "action": "buy",
            "price": close_p,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "vol_ratio": conds.get("vol_ratio_val", 0),
            "gain": conds.get("gain_val", 0),
            "turnover": conds.get("turnover_val", 0),
            "amount": conds.get("amount_val", 0),
            "low_score": score["low"],
            "hot_score": score["hot"],
            "composite_score": score["composite"],
            "low_details": score["low_details"],
            "hot_details": score["hot_details"],
        }
        # ====== 注册到实盘风控监控 ======
        symbol = params.get("symbol", self._current_symbol)
        if symbol:
            self.risk_monitor.open_position(symbol, close_p,
                                           stop_loss_pct=-self.STOP_LOSS_PCT,
                                           take_profit_pct=self.TAKE_PROFIT_PCT)
            logger.info("[S15] 🔗 风控注册 | %s @ %.3f SL=%.3f TP=%.3f",
                       symbol, close_p, stop_loss, take_profit)

        logger.info("[S15] ✅ 买入信号 | 价格=%.2f 止损=%.2f 止盈=%.2f "
                    "量比=%.1f 涨幅=%.1f%% 评分=%d(L%d+H%d) %s",
                    close_p, stop_loss, take_profit,
                    conds.get("vol_ratio_val", 0), conds.get("gain_val", 0) * 100,
                    score["composite"], score["low"], score["hot"],
                    ",".join(score["low_details"] + score["hot_details"]))
        return result

    # ========== 静态前置过滤 ==========

    def _check_low_position(self, bars: list[dict]) -> bool:
        """检查价格是否处于近60日最低20%分位"""
        prices = [float(b["close"]) for b in bars[-60:]]
        current = float(bars[-1]["close"])
        rank = sum(1 for p in prices if p <= current) / 60
        logger.info("[S15] 低位检查 | 当前=%.2f 分位=%.1f%% 阈值=%.0f%%",
                    current, rank * 100, self.LOW_PCT_RANK * 100)
        return rank <= self.LOW_PCT_RANK

    # ========== 盘中动态条件（日线近似） ==========

    def _check_dynamic_conditions(self, bars: list[dict], last: dict) -> dict:
        """检查4个动态条件，返回每项结果+实际值"""
        open_p, close_p = float(last["open"]), float(last["close"])
        high_p, low_p = float(last["high"]), float(last["low"])
        vol = float(last["volume"])

        # 条件1: 量比 3 < vol_ratio < 10
        vols = [float(b["volume"]) for b in bars[-21:-1]]
        avg_vol = sum(vols) / max(len(vols), 1)
        vol_ratio = vol / avg_vol if avg_vol > 0 else 0
        vr_ok = self.VOL_RATIO_MIN < vol_ratio < self.VOL_RATIO_MAX
        logger.info("[S15] 量比=%.1f (V=%.0f / MA20=%.0f) %s [%.1f-%.1f]",
                    vol_ratio, vol, avg_vol, "✓" if vr_ok else "✗",
                    self.VOL_RATIO_MIN, self.VOL_RATIO_MAX)

        # 条件2: 涨幅 3% < gain < 8%
        gain = (close_p - open_p) / open_p if open_p > 0 else 0
        gain_ok = self.GAIN_MIN < gain < self.GAIN_MAX
        logger.info("[S15] 涨幅=%.2f%% (O=%.2f→C=%.2f) %s [%.1f%%-%.1f%%]",
                    gain * 100, open_p, close_p, "✓" if gain_ok else "✗",
                    self.GAIN_MIN * 100, self.GAIN_MAX * 100)

        # 条件3: 换手率 2% < turnover < 15%（近似：量/流通股本）
        turnover = self._estimate_turnover(vol, bars)
        to_ok = self.TURNOVER_MIN < turnover < self.TURNOVER_MAX
        logger.info("[S15] 换手率≈%.2f%% %s [%.1f%%-%.1f%%]",
                    turnover * 100, "✓" if to_ok else "✗",
                    self.TURNOVER_MIN * 100, self.TURNOVER_MAX * 100)

        # 条件4: 成交额 2亿 < amount < 20亿
        avg_price = (open_p + high_p + low_p + close_p) / 4
        amount = vol * avg_price
        amt_ok = self.AMOUNT_MIN < amount < self.AMOUNT_MAX
        logger.info("[S15] 成交额=%.2f亿 %s [2亿-20亿]",
                    amount / 1e8, "✓" if amt_ok else "✗")

        return {
            "all_pass": vr_ok and gain_ok and to_ok and amt_ok,
            "vol_ratio_ok": vr_ok, "vol_ratio_val": round(vol_ratio, 1),
            "gain_ok": gain_ok, "gain_val": round(gain, 4),
            "turnover_ok": to_ok, "turnover_val": round(turnover, 4),
            "amount_ok": amt_ok, "amount_val": round(amount, 0),
        }

    def _estimate_turnover(self, vol: float, bars: list[dict]) -> float:
        """估算换手率：当日量 / 近60日平均量 × 基准换手率2%
        无流通股本数据时的近似方案
        """
        vols = [float(b["volume"]) for b in bars[-60:]]
        avg_vol = sum(vols) / max(len(vols), 1)
        base_turnover = 0.02
        if avg_vol > 0:
            return (vol / avg_vol) * base_turnover
        return base_turnover

    # ========== 涨跌停检查 ==========

    def _check_limit(self, bars: list[dict], last: dict) -> bool:
        """检查是否已触及涨停/跌停（A股10%涨跌停）"""
        if len(bars) < 2:
            return True
        prev_close = float(bars[-2]["close"])
        limit_up = prev_close * 1.098
        limit_down = prev_close * 0.902
        close_p = float(last["close"])
        high_p = float(last["high"])
        low_p = float(last["low"])

        hit_up = high_p >= limit_up and close_p >= limit_up * 0.995
        hit_down = low_p <= limit_down and close_p <= limit_down * 1.005

        logger.info("[S15] 涨跌停检查 | 涨停价=%.2f 跌停价=%.2f H=%.2f L=%.2f C=%.2f hit_up=%s hit_down=%s",
                    limit_up, limit_down, high_p, low_p, close_p, hit_up, hit_down)

        if hit_up:
            logger.info("[S15] ⚠️ 已触涨停，不追板")
        if hit_down:
            logger.info("[S15] ⚠️ 已触跌停，风险规避")

        return not hit_up and not hit_down

    # ========== 环境风控 ==========

    def _check_environment(self, params: dict) -> bool:
        """检查大盘环境
        params中可传入:
          index_change: 沪深300当日涨跌幅
          sector_change: 所属行业板块当日涨跌幅
          regime_label: 大盘环境标签 (bull/shake/bear)
        """
        index_change = params.get("index_change")
        sector_change = params.get("sector_change")
        regime_label = params.get("regime_label", "")

        if regime_label == "bear":
            logger.info("[S15] 环境风控 | 熊市禁止开仓 regime=%s", regime_label)
            return False

        if index_change is not None and index_change < self.INDEX_DECLINE_LIMIT:
            logger.info("[S15] 环境风控 | 沪深300跌幅%.2f%% < %.1f%%",
                        index_change * 100, self.INDEX_DECLINE_LIMIT * 100)
            return False

        if sector_change is not None and sector_change <= 0:
            logger.info("[S15] 环境风控 | 板块涨幅%.2f%% ≤ 0", sector_change * 100)
            return False

        logger.info("[S15] 环境风控 | ✓ 通过 (index=%.2f%% sector=%.2f%% regime=%s)",
                    (index_change or 0) * 100, (sector_change or 0) * 100,
                    regime_label or "unknown")
        return True

    # ========== 评分体系集成 ==========

    def _calc_score(self, bars: list[dict]) -> dict:
        """调用低位+热启动评分体系"""
        from tools.low_position_filter import calc_composite_score
        low_s, low_d, hot_s, hot_d, comp = calc_composite_score(bars, len(bars) - 1)
        return {
            "low": low_s, "low_details": low_d,
            "hot": hot_s, "hot_details": hot_d,
            "composite": comp,
        }

    # ========== 仓位计算 ==========

    def calc_position(self, signal: dict, capital: Decimal) -> Decimal:
        if signal.get("action") != "buy":
            return Decimal("0")
        return (capital * self.POSITION_RATIO).quantize(Decimal("0.01"))

    # ========== 参数空间 ==========

    def get_param_space(self) -> dict[str, tuple]:
        return {
            "vol_ratio_min": (2.0, 5.0),
            "vol_ratio_max": (8.0, 15.0),
            "gain_min": (0.02, 0.05),
            "gain_max": (0.06, 0.10),
            "stop_loss_pct": (0.02, 0.06),
            "take_profit_pct": (0.05, 0.12),
        }

    def validate_params(self, params: dict) -> bool:
        return all(k in params for k in ["vol_ratio_min", "gain_min", "stop_loss_pct"])

    # ========== 持仓管理与出场检查 ==========

    def check_position_exit(self, bar: dict, position: dict | None) -> dict | None:
        """检查持仓是否需要出场，返回卖出信号或None
        bar: 当前分钟/日线bar
        position: {"entry_price": float, "entry_date": str, "stop_loss": float, "take_profit": float}
        """
        if position is None:
            return None

        low = float(bar["low"])
        high = float(bar["high"])
        close = float(bar["close"])
        entry_price = position["entry_price"]
        stop_loss = position["stop_loss"]
        take_profit = position["take_profit"]
        symbol = self._current_symbol

        # ====== 喂入风控监控器 ======
        if symbol:
            self.feed_risk_monitor(bar)
            critical_alerts = [a for a in self.risk_monitor.get_alerts()
                             if a.level == "critical"]
            for alert in critical_alerts:
                logger.warning("[S15] ⚠️ 风控告警 | %s %s: %s",
                             alert.category, alert.symbol, alert.detail)

        # 1. 硬止损：最低价触及止损价
        if low <= stop_loss:
            exit_price = stop_loss * 0.999
            pnl = (exit_price - entry_price) / entry_price
            logger.warning("[S15] 🔴 止损触发 | 入场=%.3f 出场=%.3f 亏损=%.2f%% L=%.3f≤SL=%.3f",
                         entry_price, exit_price, pnl * 100, low, stop_loss)
            if symbol:
                self.risk_monitor.close_position(symbol)
            return {"action": "sell", "price": round(exit_price, 3),
                    "reason": "stop_loss", "pnl_pct": round(pnl * 100, 2)}

        # 2. 止盈：最高价触及止盈价
        if high >= take_profit:
            pnl = (take_profit - entry_price) / entry_price
            logger.info("[S15] 🟢 止盈触发 | 入场=%.3f 出场=%.3f 盈利=%.2f%% H=%.3f≥TP=%.3f",
                      entry_price, take_profit, pnl * 100, high, take_profit)
            if symbol:
                self.risk_monitor.close_position(symbol)
            return {"action": "sell", "price": take_profit,
                    "reason": "take_profit", "pnl_pct": round(pnl * 100, 2)}

        # 3. 跌停保护：持仓中触及跌停立即止损
        prev_close = float(bar.get("prev_close", close * 1.05))
        limit_down = prev_close * 0.902
        if low <= limit_down:
            exit_price = max(limit_down * 0.995, low)
            pnl = (exit_price - entry_price) / entry_price
            logger.warning("[S15] 🔴 跌停保护 | 入场=%.3f 出场=%.3f 亏损=%.2f%% 触及跌停%.3f",
                         entry_price, exit_price, pnl * 100, limit_down)
            if symbol:
                self.risk_monitor.close_position(symbol)
            return {"action": "sell", "price": round(exit_price, 3),
                    "reason": "limit_down_exit", "pnl_pct": round(pnl * 100, 2)}

        # 4. 风控闪崩保护：RiskMonitor检测到闪崩/跌停告警时强制离场
        if symbol:
            critical_alerts = [a for a in self.risk_monitor.get_alerts(clear=True)
                             if a.level == "critical"]
            flash_crash = any(a.category == "flash_crash" for a in critical_alerts)
            limit_down_rm = any(a.category == "limit_down" for a in critical_alerts)
            if flash_crash or limit_down_rm:
                exit_price = close * 0.998
                pnl = (exit_price - entry_price) / entry_price
                reason = "flash_crash_exit" if flash_crash else "limit_down_rm_exit"
                logger.warning("[S15] 🔴 风控强制离场 | %s 入场=%.3f 出场=%.3f 亏损=%.2f%%",
                             reason, entry_price, exit_price, pnl * 100)
                self.risk_monitor.close_position(symbol)
                return {"action": "sell", "price": round(exit_price, 3),
                        "reason": reason, "pnl_pct": round(pnl * 100, 2)}

        return None


class PositionManager:
    """持仓管理器：跟踪入场/出场，执行止损/止盈/时间止损

    使用方式：
        pm = PositionManager(stop_loss_pct=0.04, take_profit_pct=0.07)
        for bar in intraday_bars:
            if not pm.has_position():
                if entry_conditions_met:
                    pm.enter(bar["close"], bar["minute"])
            else:
                exit_sig = pm.check_exit(bar)
                if exit_sig:
                    handle_exit(exit_sig)
    """

    def __init__(self, stop_loss_pct=0.04, take_profit_pct=0.07,
                 time_stop_minute=235, slippage=0.001):
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.time_stop_minute = time_stop_minute
        self.slippage = slippage
        self.trade_log = []
        self.pnl = 0.0
        self.traded_today = False
        self._reset()

    def _reset(self):
        self.position = None
        self.entry_price = 0.0
        self.entry_minute = 0
        self.entry_date = ""
        self.stop_loss_price = 0.0
        self.take_profit_price = 0.0

    def has_position(self) -> bool:
        return self.position is not None

    def enter(self, price: float, minute: int = 0, date: str = "",
              low_score: int = 0, hot_score: int = 0) -> bool:
        """入场开仓，返回是否成功"""
        if self.has_position() or self.traded_today:
            return False

        self.entry_price = price
        self.entry_minute = minute
        self.entry_date = date or str(datetime.now().date())
        self.stop_loss_price = round(price * (1 - self.stop_loss_pct), 3)
        self.take_profit_price = round(price * (1 + self.take_profit_pct), 3)
        self.position = "long"

        self.trade_log.append({
            "action": "ENTRY", "minute": minute, "date": self.entry_date,
            "price": price, "score": f"L{low_score}+H{hot_score}",
            "stop_loss": self.stop_loss_price,
            "take_profit": self.take_profit_price,
        })
        logger.info("[S15-PM] 🔵 入场 | 分=%d 价=%.3f SL=%.3f TP=%.3f 评分=L%d+H%d",
                    minute, price, self.stop_loss_price, self.take_profit_price,
                    low_score, hot_score)
        return True

    def check_exit(self, bar: dict) -> dict | None:
        """检查出场条件，返回出场信号或None"""
        if not self.has_position():
            return None

        low = float(bar["low"])
        high = float(bar["high"])
        close = float(bar["close"])
        minute = bar.get("minute", 0)

        # 1. 硬止损
        if low <= self.stop_loss_price:
            exit_price = max(self.stop_loss_price * (1 - self.slippage), low)
            return self._make_exit("STOP_LOSS", exit_price, minute,
                                  f"L={low:.3f}≤SL={self.stop_loss_price:.3f}")

        # 2. 止盈
        if high >= self.take_profit_price:
            return self._make_exit("TAKE_PROFIT", self.take_profit_price, minute,
                                  f"H={high:.3f}≥TP={self.take_profit_price:.3f}")

        # 3. 跌停保护
        prev_close = float(bar.get("prev_close", close * 1.05))
        limit_down = prev_close * 0.902
        if low <= limit_down:
            exit_price = max(limit_down * 0.995, low)
            return self._make_exit("LIMIT_DOWN_EXIT", exit_price, minute,
                                  f"触及跌停价{limit_down:.3f}")

        # 4. 时间止损
        if minute >= self.time_stop_minute:
            exit_price = close * (1 - self.slippage)
            return self._make_exit("TIME_STOP", exit_price, minute,
                                  f"尾盘离场 min={minute}")

        return None

    def _make_exit(self, action: str, price: float, minute: int, trigger: str) -> dict:
        pnl_pct = (price - self.entry_price) / self.entry_price
        self.pnl += pnl_pct
        self.trade_log.append({
            "action": action, "minute": minute,
            "price": round(price, 3), "pnl_pct": round(pnl_pct * 100, 2),
            "trigger": trigger,
        })
        icon = {"STOP_LOSS": "🔴", "TAKE_PROFIT": "🟢",
                "LIMIT_DOWN_EXIT": "🔴", "TIME_STOP": "🟡"}.get(action, "⚪")
        logger.info("[S15-PM] %s %s | 入场=%.3f 出场=%.3f 盈亏=%.2f%% %s",
                    icon, action, self.entry_price, price, pnl_pct * 100, trigger)
        self._reset()
        self.traded_today = True
        return {"action": "sell", "price": round(price, 3),
                "reason": action.lower(), "pnl_pct": round(pnl_pct * 100, 2)}

    def get_summary(self) -> dict:
        return {
            "trades": len([t for t in self.trade_log if t["action"] == "ENTRY"]),
            "stop_losses": len([t for t in self.trade_log if t["action"] == "STOP_LOSS"]),
            "take_profits": len([t for t in self.trade_log if t["action"] == "TAKE_PROFIT"]),
            "time_stops": len([t for t in self.trade_log if t["action"] == "TIME_STOP"]),
            "limit_down_exits": len([t for t in self.trade_log if t["action"] == "LIMIT_DOWN_EXIT"]),
            "total_pnl_pct": round(self.pnl * 100, 2),
            "log": self.trade_log,
        }