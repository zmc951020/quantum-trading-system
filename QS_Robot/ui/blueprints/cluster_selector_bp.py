"""金融大师32策略集群选股器 - Flask蓝图"""
import os
import json
import logging
from datetime import datetime
from flask import Blueprint, render_template, jsonify, request

logger = logging.getLogger("ClusterSelector")

bp = Blueprint("cluster_selector", __name__,
               url_prefix="/cluster_selector",
               template_folder="../templates")

PROJECT_ROOT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))

PUSH_LOG_PATH = os.path.join(PROJECT_ROOT, "data", "push_log.json")


@bp.route("/")
def index():
    return render_template("cluster_selector.html")


@bp.route("/api/scan", methods=["POST"])
def api_scan():
    """执行选股扫描"""
    try:
        data = request.get_json() or {}
        pool_type = data.get("pool", "hs300")
        u = float(data.get("u", 0.5))
        n = int(data.get("n", 10))

        codes = _get_pool_codes(pool_type)
        if not codes:
            return jsonify({"error": f"股票池为空: {pool_type}"}), 400

        from core.cluster_stock_selector import ClusterStockSelector
        selector = ClusterStockSelector()
        result = selector.scan(codes, u=u, n=n)

        return jsonify({
            "stocks": [{
                "rank": i + 1,
                "code": s.code,
                "name": s.name,
                "goodness": s.goodness,
                "low_score": s.low_score,
                "hot_score": s.hot_score,
                "signal_count": s.signal_count,
                "strategies": s.strategy_names[:10],
                "avg_strength": s.avg_signal_strength,
            } for i, s in enumerate(result.stocks)],
            "summary": {
                "total_scanned": result.total_scanned,
                "passed": result.passed,
                "avg_score": result.avg_score,
                "params": result.params,
                "elapsed": result.elapsed_seconds,
            },
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/auto_tune", methods=["POST"])
def api_auto_tune():
    """自动调参 u × n 网格搜索"""
    try:
        data = request.get_json() or {}
        pool_type = data.get("pool", "hs300")
        u_range = tuple(data.get("u_range", [0.0, 1.0, 0.1]))
        n_range = tuple(data.get("n_range", [5, 30, 5]))

        codes = _get_pool_codes(pool_type)
        if not codes:
            return jsonify({"error": f"股票池为空: {pool_type}"}), 400

        from core.cluster_stock_selector import ClusterStockSelector
        selector = ClusterStockSelector()
        result = selector.auto_tune(codes, u_range=u_range, n_range=n_range)

        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/push_to_pool", methods=["POST"])
def api_push_to_pool():
    """将选中的股票推入候选池"""
    try:
        data = request.get_json() or {}
        stocks = data.get("stocks", [])
        target_level = data.get("level", "candidate")
        u_param = data.get("u", "?")
        n_param = data.get("n", "?")

        logger.info("[集群选股] ========== 推入操作开始 ==========")
        logger.info("[集群选股] 操作参数: u=%.2f, n=%d, 目标池=%s, 股票数=%d",
                    u_param, n_param, target_level, len(stocks))
        for i, s in enumerate(stocks):
            logger.info("[集群选股] 推入[%d/%d] %s 优良度=%.4f 低位=%d/5 热启=%d/3 信号=%d",
                        i+1, len(stocks), s.get("code","?"), s.get("goodness",0),
                        s.get("low_score",0), s.get("hot_score",0), s.get("signal_count",0))

        if not stocks:
            logger.warning("[集群选股] 推入失败: 未选择股票")
            return jsonify({"error": "未选择股票"}), 400

        from core.stock_pool import get_stock_pool_manager, PoolLevel, StockSource

        mgr = get_stock_pool_manager()
        level_map = {
            "candidate": PoolLevel.CANDIDATE,
            "testing": PoolLevel.TESTING,
            "watchlist": PoolLevel.WATCHLIST,
        }
        level = level_map.get(target_level, PoolLevel.CANDIDATE)

        pushed = 0
        skipped = 0
        errors = []
        pushed_codes = []
        for s in stocks:
            code = s.get("code", "")
            if not code:
                continue
            try:
                result = mgr.add_stock(
                    code,
                    name=s.get("name", code),
                    level=level,
                    source=StockSource.THS_IWENCAI,
                    strategy_name=f"集群选股(u={u_param},n={n_param})",
                    metadata={
                        "goodness": s.get("goodness", 0),
                        "low_score": s.get("low_score", 0),
                        "hot_score": s.get("hot_score", 0),
                        "signal_count": s.get("signal_count", 0),
                        "strategies": s.get("strategies", []),
                    },
                )
                if result.get("success"):
                    pushed += 1
                    pushed_codes.append(code)
                    logger.info("[集群选股] ✅ %s 推入成功 → %s池", code, target_level)
                else:
                    skipped += 1
                    logger.info("[集群选股] ⏭️ %s 跳过: %s", code, result.get("error","已存在"))
            except Exception as e:
                errors.append(f"{code}: {e}")
                logger.error("[集群选股] ❌ %s 推入异常: %s", code, e)

        # 写入推送日志
        _write_push_log({
            "timestamp": datetime.now().isoformat(),
            "source": "cluster_selector",
            "u": u_param,
            "n": n_param,
            "target_level": target_level,
            "total": len(stocks),
            "pushed": pushed,
            "skipped": skipped,
            "codes": pushed_codes,
            "errors": errors,
        })

        logger.info("[集群选股] 推入结果: 成功=%d, 跳过=%d, 失败=%d", pushed, skipped, len(errors))
        logger.info("[集群选股] ========== 推入操作结束 ==========")

        return jsonify({
            "success": True,
            "pushed": pushed,
            "skipped": skipped,
            "errors": errors,
            "message": f"已推入 {pushed} 只到{target_level}池{f'，{skipped}只已存在' if skipped else ''}",
        })
    except Exception as e:
        logger.error("[集群选股] 推入异常: %s", e, exc_info=True)
        return jsonify({"error": str(e)}), 500


@bp.route("/api/batch_backtest", methods=["POST"])
def api_batch_backtest():
    """对选中的股票启动批量回测"""
    try:
        data = request.get_json() or {}
        stocks = data.get("stocks", [])

        if not stocks:
            return jsonify({"error": "未选择股票"}), 400

        codes = [s.get("code", "") for s in stocks if s.get("code")]
        if not codes:
            return jsonify({"error": "无有效股票代码"}), 400

        # 先推入测试池
        from core.stock_pool import get_stock_pool_manager, PoolLevel, StockSource
        mgr = get_stock_pool_manager()
        for s in stocks:
            try:
                mgr.add_stock(
                    s.get("code", ""),
                    name=s.get("name", s.get("code", "")),
                    level=PoolLevel.TESTING,
                    source=StockSource.THS_IWENCAI,
                    metadata={
                        "goodness": s.get("goodness", 0),
                    },
                )
            except Exception:
                pass

        return jsonify({
            "success": True,
            "codes": codes,
            "message": f"已将 {len(codes)} 只股票推入测试池，请前往回测页面执行验证",
            "next_step": "前往 /backtest 或 /stock_pool 查看并执行回测",
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _write_push_log(entry: dict):
    """写入推送操作日志"""
    try:
        os.makedirs(os.path.dirname(PUSH_LOG_PATH), exist_ok=True)
        logs = []
        if os.path.exists(PUSH_LOG_PATH):
            with open(PUSH_LOG_PATH, "r", encoding="utf-8") as f:
                logs = json.load(f)
        logs.append(entry)
        # 保留最近100条
        if len(logs) > 100:
            logs = logs[-100:]
        with open(PUSH_LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(logs, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error("[集群选股] 写入推送日志失败: %s", e)


@bp.route("/api/push_log", methods=["GET"])
def api_push_log():
    """获取推送操作日志"""
    try:
        limit = int(request.args.get("limit", 20))
        logs = []
        if os.path.exists(PUSH_LOG_PATH):
            with open(PUSH_LOG_PATH, "r", encoding="utf-8") as f:
                logs = json.load(f)
        return jsonify({"success": True, "data": logs[-limit:]})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


def _get_pool_codes(pool_type: str) -> list[str]:
    """获取股票池代码列表"""
    if pool_type == "watchlist":
        try:
            from stock_pool.main import StockPoolSystem
            sps = StockPoolSystem()
            stocks = sps.generate_sample_stocks(20)
            return [s.code for s in stocks]
        except Exception:
            pass

    # 从 bus_cache 加载
    cache_dir = os.path.join(PROJECT_ROOT, "data", "bus_cache")
    codes = []
    if os.path.exists(cache_dir):
        for fname in os.listdir(cache_dir):
            if not fname.endswith(".json"):
                continue
            try:
                with open(os.path.join(cache_dir, fname), encoding="utf-8") as f:
                    d = json.load(f)
                sym = d.get("data", {}).get("symbol", "")
                if sym:
                    codes.append(sym)
            except Exception:
                pass
    if pool_type == "hs300":
        codes = codes[:300]
    return codes