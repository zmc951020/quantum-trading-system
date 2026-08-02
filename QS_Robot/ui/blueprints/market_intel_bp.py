#!/usr/bin/env python3
"""
市场情报看板蓝图（单页Tab模式）

Aurora UI 内嵌模块 - 不做独立子站
  /market_intel/         - 单页面，5维度通过Tab切换
  /market_intel/api/all  - JSON API: 一键获取全部情报
  /market_intel/api/<dimension> - JSON API: 按维度获取情报
"""

import logging
from datetime import datetime
from flask import Blueprint, render_template, jsonify

from api.ths_bridge.market_intel import get_market_intel_collector

logger = logging.getLogger(__name__)

bp = Blueprint("market_intel", __name__, url_prefix="/market_intel",
               template_folder="templates/market_intel")


@bp.route("/")
def index():
    """单页Tab模式 - 5维度通过Tab切换"""
    collector = get_market_intel_collector()
    data = collector.fetch_all()
    return render_template("market_intel/index.html", data=data)


@bp.route("/api/all")
def api_all():
    """JSON API：一键获取全部情报"""
    collector = get_market_intel_collector()
    return jsonify(collector.fetch_all())


@bp.route("/api/<dimension>")
def api_dimension(dimension: str):
    """JSON API：按维度获取情报（供前端Tab异步刷新）"""
    collector = get_market_intel_collector()
    dim_map = {
        "hot_stocks": collector.fetch_hot_stocks,
        "market_overview": collector.fetch_market_overview,
        "capital_flow": collector.fetch_capital_flow,
        "sector_rotation": collector.fetch_sector_rotation,
        "market_emotion": collector.fetch_market_emotion,
    }
    if dimension not in dim_map:
        return jsonify({"error": f"未知维度: {dimension}",
                        "available": list(dim_map.keys())}), 404
    return jsonify(dim_map[dimension]())


@bp.route("/api/seed_pool")
def api_seed_pool():
    """种子池看板数据API：金融大师股票池 + 专家评点池 + 升级流转"""
    try:
        from core.stock_pool import get_stock_pool_manager
        pool = get_stock_pool_manager()
        overview = pool.get_seed_pool_overview()
        return jsonify({"success": True, "data": overview,
                        "fetched_at": datetime.now().isoformat()})
    except Exception as e:
        logger.error("种子池看板API失败: %s", e)
        return jsonify({"success": False, "error": str(e), "data": {
            "master_pool": {"total": 0, "promoted": 0, "pending": 0, "stocks": []},
            "expert": {"total": 0, "promoted": 0, "pending": 0, "stocks": []},
            "promoted_to_iwencai": 0,
        }})
