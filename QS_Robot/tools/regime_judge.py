"""大盘环境判断器：6指标加权 + 情绪极值信号"""
import os, sys, json, math
from dataclasses import dataclass, field

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


@dataclass
class RegimeResult:
    score: float
    label: str
    position_limit: float
    stop_loss: float
    signals: list[str] = field(default_factory=list)


def load_index_data(index_code="000300"):
    """加载大盘指数数据"""
    cache_dir = os.path.join(PROJECT_ROOT, "data", "bus_cache")
    for fname in os.listdir(cache_dir):
        if not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(cache_dir, fname), encoding="utf-8") as f:
                d = json.load(f)
            data = d.get("data", {})
            if data.get("symbol") == index_code:
                n = len(data["dates"])
                return [{"date": data["dates"][i], "open": float(data["opens"][i]),
                         "high": float(data["highs"][i]), "low": float(data["lows"][i]),
                         "close": float(data["closes"][i]), "volume": float(data["volumes"][i])}
                        for i in range(n)]
        except Exception:
            pass
    return []


def _calc_trend_score(bars, i):
    """20日涨跌幅趋势分 (30%)"""
    if i < 20:
        return 50
    pct = (bars[i]["close"] - bars[i - 20]["close"]) / bars[i - 20]["close"] * 100
    if pct > 5:
        return 85
    if pct > 0:
        return 65
    if pct > -5:
        return 40
    return 15


def _calc_adr_score(bars, i):
    """涨跌家数比模拟: 用当日涨跌幅度替代 (20%)"""
    if i < 5:
        return 50
    up_days = sum(1 for j in range(i - 4, i + 1) if bars[j]["close"] > bars[j]["open"])
    ratio = up_days / 5
    if ratio >= 0.8:
        return 90
    if ratio >= 0.6:
        return 70
    if ratio >= 0.4:
        return 50
    return 30


def _calc_volume_score(bars, i):
    """成交额趋势分 (15%)"""
    if i < 20:
        return 50
    vol_ma20 = sum(bars[j]["volume"] for j in range(i - 19, i + 1)) / 20
    vol_ma60 = sum(bars[j]["volume"] for j in range(max(0, i - 59), i + 1)) / min(i + 1, 60)
    if vol_ma20 > vol_ma60 * 1.2:
        return 80
    if vol_ma20 > vol_ma60 * 0.8:
        return 60
    return 30


def _calc_ma_score(bars, i):
    """均线形态分 (20%): 替代融资情绪，用MA20/MA60多头排列"""
    if i < 60:
        return 50
    ma20 = sum(bars[j]["close"] for j in range(i - 19, i + 1)) / 20
    ma60 = sum(bars[j]["close"] for j in range(i - 59, i + 1)) / 60
    if bars[i]["close"] > ma20 > ma60:
        return 90
    if bars[i]["close"] > ma60:
        return 60
    if bars[i]["close"] > ma20:
        return 45
    return 20


def _calc_cross_market_score(bars, i):
    """跨市场联动分 (15%): 用波动率替代"""
    if i < 20:
        return 50
    returns = [(bars[j]["close"] - bars[j - 1]["close"]) / bars[j - 1]["close"]
               for j in range(i - 19, i + 1)]
    mean_r = sum(returns) / len(returns)
    var = sum((r - mean_r) ** 2 for r in returns) / len(returns)
    vol = math.sqrt(var) * 100
    if vol < 1.5:
        return 70
    if vol < 3:
        return 50
    return 30


def judge_regime(bars, i):
    """大盘环境综合判断"""
    if i < 60:
        return RegimeResult(50, "shake", 0.5, -0.03, ["数据不足"])

    trend = _calc_trend_score(bars, i)
    adr = _calc_adr_score(bars, i)
    volume = _calc_volume_score(bars, i)
    ma = _calc_ma_score(bars, i)
    cross = _calc_cross_market_score(bars, i)

    score = trend * 0.30 + adr * 0.20 + volume * 0.15 + ma * 0.20 + cross * 0.15

    signals = []
    if adr < 30:
        signals.append("冰点")
    if adr < 15:
        signals.append("极致冰点")
    if adr >= 90:
        signals.append("沸点")

    if score >= 70:
        return RegimeResult(score, "bull", 0.80, -0.05, signals)
    if score >= 40:
        return RegimeResult(score, "shake", 0.50, -0.04, signals)
    return RegimeResult(score, "bear", 0.20, -0.03, signals)


def get_regime_series(index_bars):
    """返回按日期的全系列大盘环境"""
    regimes = []
    for i in range(len(index_bars)):
        r = judge_regime(index_bars, i)
        regimes.append({
            "date": index_bars[i]["date"],
            "score": round(r.score, 1),
            "label": r.label,
            "position_limit": r.position_limit,
            "signals": r.signals,
        })
    return regimes


def get_regime_for_date(regimes, date):
    """按日期匹配大盘环境"""
    for r in regimes:
        if r["date"] == date:
            return r
    return {"score": 50, "label": "shake", "position_limit": 0.5, "signals": []}


if __name__ == "__main__":
    index_bars = load_index_data("000300")
    regimes = get_regime_series(index_bars)

    labels = {"bull": 0, "shake": 0, "bear": 0}
    ice = 0
    for r in regimes:
        labels[r["label"]] += 1
        if "冰点" in r["signals"]:
            ice += 1

    print(f"沪深300 大盘环境统计 ({len(regimes)}天):")
    print(f"  牛市: {labels['bull']}天 ({labels['bull']/len(regimes)*100:.0f}%)")
    print(f"  震荡: {labels['shake']}天 ({labels['shake']/len(regimes)*100:.0f}%)")
    print(f"  熊市: {labels['bear']}天 ({labels['bear']/len(regimes)*100:.0f}%)")
    print(f"  冰点: {ice}天")
    print(f"  当前: {regimes[-1]['label']} score={regimes[-1]['score']}")