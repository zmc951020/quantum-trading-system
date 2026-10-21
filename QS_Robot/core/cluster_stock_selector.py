"""金融大师32策略集群选股器

批量海选 + 低位筛选 + 热启动 + 优良度排名。
与 TauClusterEngine 互补：本模块做批量选股，TauClusterEngine 做单股深度决策。
"""
import importlib
import inspect
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

logger = logging.getLogger("cluster_stock_selector")


@dataclass
class StockScore:
    """单只股票的集群评分"""
    code: str
    name: str = ""
    goodness: float = 0.0
    low_score: int = 0
    hot_score: int = 0
    signal_count: int = 0
    strategy_names: list[str] = field(default_factory=list)
    avg_signal_strength: float = 0.0
    market_regime: str = "unknown"
    details: dict = field(default_factory=dict)


@dataclass
class ScanResult:
    """扫描结果"""
    stocks: list[StockScore] = field(default_factory=list)
    total_scanned: int = 0
    passed: int = 0
    avg_score: float = 0.0
    params: dict = field(default_factory=dict)
    elapsed_seconds: float = 0.0


class ClusterStockSelector:
    """32策略集群选股器

    用法:
        selector = ClusterStockSelector()
        result = selector.scan(pool_codes, u=0.5, n=10)
    """

    def __init__(self):
        self._strategies: list[tuple[str, Any]] = []
        self._regime_detector = None
        self._strategy_win_rates: dict[str, float] = {}
        self._load_strategies()

    def _load_strategies(self):
        """加载全部 14基础 + 18高级 策略"""
        base = os.path.join(PROJECT_ROOT, "core", "strategies", "ths_strategies")
        dirs = [
            os.path.join(base, "14_strategies"),
            os.path.join(base, "18_advanced"),
        ]

        for d in dirs:
            if not os.path.exists(d):
                continue
            for fname in sorted(os.listdir(d)):
                if not fname.endswith(".py") or fname.startswith("_") or fname.startswith("test_"):
                    continue
                mod_name = fname.replace(".py", "")
                rel_dir = os.path.relpath(d, PROJECT_ROOT).replace(os.sep, ".")
                full_mod = f"{rel_dir}.{mod_name}"
                try:
                    mod = importlib.import_module(full_mod)
                    found = False
                    for _n, obj in inspect.getmembers(mod, inspect.isclass):
                        if not hasattr(obj, "ID") or not hasattr(obj, "generate_signal"):
                            continue
                        try:
                            inst = obj()
                            if hasattr(inst, "ID") and inst.ID:
                                self._strategies.append((inst.ID, inst))
                                found = True
                                break
                        except Exception:
                            continue
                    if not found:
                        logger.debug("跳过无策略类: %s", mod_name)
                except Exception as e:
                    logger.warning("加载失败 %s: %s", mod_name, e)

        logger.info("已加载 %d 个策略", len(self._strategies))

    def scan(self, pool_codes: list[str], u: float = 0.5, n: int = 10,
             index_bars: list[dict] | None = None) -> ScanResult:
        """执行批量选股扫描"""
        t0 = time.time()

        hot_required = _hot_threshold(u)
        logger.info("[集群选股] ===== 开始扫描 u=%.2f (热启动需≥%d/3条件) n=%d =====",
                    u, hot_required, n)

        regime = self._detect_regime(index_bars)
        logger.info("[集群选股] 大盘状态: %s, 策略数: %d", regime, len(self._strategies))

        stock_data = self._load_stock_data(pool_codes)
        total = len(stock_data)
        logger.info("[集群选股] 股票池: %d 条K线数据就绪", total)

        scores: list[StockScore] = []
        for code, bars in stock_data.items():
            if len(bars) < 60:
                continue
            s = self._evaluate_stock(code, bars, hot_required, regime)
            if s and s.signal_count > 0:
                scores.append(s)

        scores.sort(key=lambda x: x.goodness, reverse=True)
        top_n = scores[:n]
        rejected = scores[n:] if len(scores) > n else []
        avg = sum(s.goodness for s in top_n) / max(len(top_n), 1)

        logger.info("[集群选股] 通过: %d/%d 只 (%.1f%%), 入选: %d 只",
                    len(scores), total, len(scores) / max(total, 1) * 100, len(top_n))
        if rejected:
            logger.info("[集群选股] n=%d 淘汰: %d 只 (优良度 %.4f ~ %.4f)",
                        n, len(rejected),
                        rejected[0].goodness if rejected else 0,
                        rejected[-1].goodness if rejected else 0)

        return ScanResult(
            stocks=top_n,
            total_scanned=total,
            passed=len(scores),
            avg_score=round(avg, 4),
            params={"u": u, "n": n, "regime": regime},
            elapsed_seconds=round(time.time() - t0, 2),
        )

    def _evaluate_stock(self, code: str, bars: list[dict], hot_required: int,
                        regime: str) -> StockScore | None:
        """对单只股票评估：低位 + 热启动 + 32策略信号"""
        from tools.low_position_filter import check_hot_start, check_low_position

        i = len(bars) - 1

        # 低位筛选（必须 ≥2 星）
        low_score, low_details, low_stars = check_low_position(bars, i)
        if low_stars == 0:
            logger.debug("[集群选股] %s 低位☆=0 跳过: %s", code, low_details)
            return None

        # 热启动（受 u 控制）
        hot_score, hot_details = check_hot_start(bars, i)
        if hot_score < hot_required:
            logger.info("[集群选股] %s 热启动不满足: score=%d/3 < required=%d 详情=%s",
                        code, hot_score, hot_required, hot_details)
            return None

        # 熊市过滤
        if regime == "bear":
            logger.info("[集群选股] %s 熊市过滤跳过", code)
            return None

        # 运行全部策略
        triggered: list[dict] = []
        for sid, strategy in self._strategies:
            try:
                sig = strategy.generate_signal(bars, {})
                if sig and sig.get("action") == "buy":
                    triggered.append({
                        "id": sid,
                        "name": getattr(strategy, "NAME", sid),
                        "strength": _calc_signal_strength(sig, bars[i]),
                    })
            except Exception:
                pass

        if not triggered:
            logger.info("[集群选股] %s 无信号触发 (低位=%d/5☆=%d 热启=%d/3)",
                        code, low_score, low_stars, hot_score)
            return None

        signal_count = len(triggered)
        avg_strength = sum(t["strength"] for t in triggered) / signal_count
        consensus = min(1.0, signal_count / len(self._strategies))

        goodness = (
            0.25 * (low_score / 5.0) +
            0.20 * (hot_score / 3.0) +
            0.25 * consensus +
            0.15 * avg_strength +
            0.15 * 0.5
        )

        logger.info(
            "[集群选股] %s 评估通过: 优良度=%.4f | "
            "低位=%d/5(☆%d) 热启=%d/3 共识=%.2f(%d/%d策略) 强度=%.2f",
            code, goodness,
            low_score, low_stars, hot_score,
            consensus, signal_count, len(self._strategies),
            avg_strength,
        )

        return StockScore(
            code=code,
            goodness=round(goodness, 4),
            low_score=low_score,
            hot_score=hot_score,
            signal_count=signal_count,
            strategy_names=[t["name"] for t in triggered],
            avg_signal_strength=round(avg_strength, 4),
            market_regime=regime,
            details={
                "low_details": low_details,
                "hot_details": hot_details,
                "low_stars": low_stars,
                "triggered": triggered,
            },
        )

    def _detect_regime(self, index_bars: list[dict] | None) -> str:
        if not index_bars or len(index_bars) < 20:
            return "unknown"
        from core.tau_cluster_engine import MarketRegimeDetector
        if self._regime_detector is None:
            self._regime_detector = MarketRegimeDetector()
        for b in index_bars:
            self._regime_detector.feed(b["close"])
        return self._regime_detector.detect()

    def _load_stock_data(self, codes: list[str]) -> dict[str, list[dict]]:
        """从 bus_cache 加载股票K线"""
        cache_dir = os.path.join(PROJECT_ROOT, "data", "bus_cache")
        result: dict[str, list[dict]] = {}
        if not os.path.exists(cache_dir):
            return result

        code_set = set(codes)
        for fname in os.listdir(cache_dir):
            if not fname.endswith(".json"):
                continue
            try:
                with open(os.path.join(cache_dir, fname), encoding="utf-8") as f:
                    d = json.load(f)
                data = d.get("data", {})
                sym = data.get("symbol", "")
                if sym not in code_set:
                    continue
                n = len(data.get("dates", []))
                bars = [{
                    "date": data["dates"][j],
                    "open": float(data["opens"][j]),
                    "high": float(data["highs"][j]),
                    "low": float(data["lows"][j]),
                    "close": float(data["closes"][j]),
                    "volume": float(data["volumes"][j]),
                } for j in range(n)]
                result[sym] = bars
            except Exception:
                pass
        return result

    def auto_tune(self, pool_codes: list[str],
                  u_range: tuple[float, float, float] = (0.0, 1.0, 0.1),
                  n_range: tuple[int, int, int] = (5, 30, 5),
                  index_bars: list[dict] | None = None) -> dict:
        """u × n 网格搜索"""
        u_start, u_end, u_step = u_range
        n_start, n_end, n_step = n_range

        u_vals = [round(u_start + i * u_step, 2)
                  for i in range(int((u_end - u_start) / u_step) + 1)]
        n_vals = list(range(n_start, n_end + 1, n_step))

        grid: list[dict] = []
        best = {"u": 0.5, "n": 10, "score": -1.0}

        for u_val in u_vals:
            for n_val in n_vals:
                result = self.scan(pool_codes, u=u_val, n=max(n_val, 50),
                                   index_bars=index_bars)
                top = result.stocks[:n_val]
                avg = (sum(s.goodness for s in top) / max(len(top), 1)) if top else 0
                grid.append({
                    "u": u_val, "n": n_val,
                    "count": len(top), "avg_score": round(avg, 4),
                })
                if avg > best["score"]:
                    best = {"u": u_val, "n": n_val, "score": avg}

        return {"grid": grid, "best": best}


def _hot_threshold(u: float) -> int:
    """u → 热启动最少需满足条件数"""
    if u >= 1.0:
        logger.debug("[集群选股] _hot_threshold: u=%.2f → 不强制热启 (0/3)", u)
        return 0
    if u >= 0.67:
        logger.debug("[集群选股] _hot_threshold: u=%.2f → 需≥1/3条件", u)
        return 1
    if u >= 0.33:
        logger.debug("[集群选股] _hot_threshold: u=%.2f → 需≥2/3条件", u)
        return 2
    logger.info("[集群选股] _hot_threshold: u=%.2f → 需3/3条件(最严格)", u)
    return 3


def _calc_signal_strength(sig: dict, bar: dict) -> float:
    """计算信号强度 [0, 1]"""
    price = sig.get("price", bar["close"])
    close = bar["close"]
    if close > 0:
        return min(1.0, abs(price - close) / close * 10 + 0.5)
    return 0.5