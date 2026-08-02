"""同花顺金融大师学院 - Flask蓝图

提供：
  - 学院主页（核心思想/战法/热点板块）
  - 14策略+18战法列表与详情
  - 三类选股来源对比看板（Aurora自创 / Vibe Trading / 同花顺问财）
  - 策略JSON API
"""
import json
from pathlib import Path
from flask import Blueprint, render_template, jsonify, request

bp = Blueprint("ths_academy", __name__, url_prefix="/ths_academy",
               template_folder="templates/ths_academy")

DATA_DIR = Path(__file__).parents[2] / "data" / "ths_academy"


def _load_json(filename: str):
    try:
        with open(DATA_DIR / filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


@bp.route("/")
def index():
    """学院主页"""
    basics = _load_json("basics.json")
    s14 = _load_json("14_strategies.json")
    s18 = _load_json("18_advanced.json")
    return render_template("ths_academy/index.html",
                           basics=basics,
                           count_14=len(s14.get("strategies", [])),
                           count_18=len(s18.get("strategies", [])))


@bp.route("/strategies")
def strategy_list():
    """14策略+18战法列表"""
    s14 = _load_json("14_strategies.json").get("strategies", [])
    s18 = _load_json("18_advanced.json").get("strategies", [])
    return render_template("ths_academy/strategy_list.html",
                           strategies_14=s14, strategies_18=s18)


@bp.route("/strategy/<sid>")
def strategy_detail(sid: str):
    """单策略详情"""
    s14 = _load_json("14_strategies.json").get("strategies", [])
    s18 = _load_json("18_advanced.json").get("strategies", [])
    all_strategies = s14 + s18
    strat = next((s for s in all_strategies if s.get("id") == sid), None)
    if not strat:
        return render_template("ths_academy/strategy_detail.html", strat=None, sid=sid)
    return render_template("ths_academy/strategy_detail.html", strat=strat, sid=sid)


@bp.route("/source_compare")
def source_compare():
    """三类选股来源对比看板"""
    try:
        from core.stock_pool import get_stock_pool_manager, StockSource
        pool = get_stock_pool_manager()
        data = {
            "summary": pool.get_source_summary(),
            "matrix": pool.get_source_level_matrix(),
            "aurora_native": [{"symbol": r.symbol, "name": r.name, "strategy": r.strategy_name}
                              for r in pool.get_stocks_by_source(StockSource.AURORA_NATIVE)],
            "vibe_trading": [{"symbol": r.symbol, "name": r.name, "strategy": r.strategy_name}
                             for r in pool.get_stocks_by_source(StockSource.VIBE_TRADING)],
            "ths_iwencai": [{"symbol": r.symbol, "name": r.name, "strategy": r.strategy_name}
                            for r in pool.get_stocks_by_source(StockSource.THS_IWENCAI)],
        }
    except Exception as e:
        data = {"error": str(e), "summary": {}, "matrix": {}}
    return render_template("ths_academy/source_compare.html", data=data)


@bp.route("/api/strategies")
def api_strategies():
    """策略JSON API"""
    s14 = _load_json("14_strategies.json")
    s18 = _load_json("18_advanced.json")
    return jsonify({"strategies_14": s14, "strategies_18": s18})


@bp.route("/api/source_compare")
def api_source_compare():
    """三类对比数据API"""
    try:
        from core.integration_bus import get_integration_bus
        bus = get_integration_bus()
        return jsonify(bus.get_source_comparison())
    except Exception as e:
        return jsonify({"error": str(e)})
