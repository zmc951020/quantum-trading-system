# -*- coding: utf-8 -*-
"""股票池管理 API 路由"""
from flask import request, jsonify


def register_routes(app):
    stock_pool_system = app.config.get('stock_pool_system')

    @app.route('/api/stock_pool/generate_stocks', methods=['POST'])
    def generate_stocks():
        """生成示例股票数据"""
        try:
            data = request.get_json()
            count = data.get('count', 10)
            stocks = stock_pool_system.generate_sample_stocks(count)

            result = []
            for stock in stocks:
                result.append({
                    'code': stock.code,
                    'name': stock.name,
                    'market': stock.market,
                    'price': stock.price,
                    'pe': stock.pe,
                    'pb': stock.pb,
                    'roe': stock.roe,
                    'volume': stock.volume,
                    'volatility': stock.volatility,
                    'trend_strength': stock.trend_strength,
                    'quality_score': stock.quality_score,
                    'sector': stock.sector,
                    'industry': stock.industry
                })

            return jsonify({"success": True, "data": result})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route('/api/stock_pool/run_pipeline', methods=['POST'])
    def run_pipeline():
        """运行股票筛选评估流程"""
        try:
            data = request.get_json()
            count = data.get('count', 10)

            stocks = stock_pool_system.generate_sample_stocks(count)
            results = stock_pool_system.run_full_pipeline(stocks)

            formatted_results = {
                'filtered': [],
                'simulated': [],
                'final': [],
                'pool_summary': stock_pool_system.pool_manager.get_pool_summary()
            }

            for f in results['filtered']:
                formatted_results['filtered'].append({
                    'code': f['stock'].code,
                    'name': f['stock'].name,
                    'scores': f['scores'],
                    'passed': f['passed']
                })

            for s in results['simulated']:
                formatted_results['simulated'].append({
                    'code': s['stock'].code,
                    'name': s['stock'].name,
                    'strategy': s['strategy'].name,
                    'strategy_type': s['strategy'].type,
                    'total_return': s['simulation'].total_return,
                    'sharpe_ratio': s['simulation'].sharpe_ratio,
                    'max_drawdown': s['simulation'].max_drawdown,
                    'win_rate': s['simulation'].win_rate,
                    'trades': s['simulation'].trades,
                    'sim_score': s['simulation'].score
                })

            for f in results['final']:
                formatted_results['final'].append({
                    'code': f['stock'].code,
                    'name': f['stock'].name,
                    'strategy': f['strategy'].name,
                    'score': f['score'],
                    'grade': f['grade']
                })

            return jsonify({"success": True, "data": formatted_results})
        except Exception as e:
            import traceback
            return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500

    @app.route('/api/stock_pool/pool_summary', methods=['GET'])
    def pool_summary():
        """获取股票池摘要 - 从 core/stock_pool.py 持久化数据读取"""
        try:
            from core.stock_pool import get_stock_pool_manager
            mgr = get_stock_pool_manager()
            raw = mgr.get_pool_summary()
            summary = {
                "candidate": raw.get("candidate", 0),
                "classified": raw.get("testing", 0),
                "watchlist": raw.get("watchlist", 0),
                "adaptive": raw.get("prelive", 0),
                "trading": raw.get("live", 0),
            }
            return jsonify({"success": True, "data": summary})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route('/api/stock_pool/get_pool/<pool_type>', methods=['GET'])
    def get_pool(pool_type):
        """获取指定股票池的股票 - 从 core/stock_pool.py 持久化数据读取"""
        try:
            from core.stock_pool import get_stock_pool_manager, PoolLevel
            mgr = get_stock_pool_manager()
            level_map = {
                "candidate": PoolLevel.CANDIDATE,
                "classified": PoolLevel.TESTING,
                "watchlist": PoolLevel.WATCHLIST,
                "adaptive": PoolLevel.PRELIVE,
                "trading": PoolLevel.LIVE,
            }
            level = level_map.get(pool_type)
            if not level:
                return jsonify({"success": False, "error": f"未知池类型: {pool_type}"}), 400

            stocks = mgr.get_pool(level)
            result = []
            for r in stocks:
                result.append({
                    "code": r.symbol,
                    "name": r.name,
                    "level": r.level.value if hasattr(r.level, 'value') else str(r.level),
                    "source": r.source.value if hasattr(r.source, 'value') else str(r.source),
                    "strategy_name": r.strategy_name,
                    "goodness": r.metadata.get("goodness", 0),
                    "low_score": r.metadata.get("low_score", 0),
                    "hot_score": r.metadata.get("hot_score", 0),
                    "signal_count": r.metadata.get("signal_count", 0),
                    "added_at": r.added_at,
                })
            return jsonify({"success": True, "data": result})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route('/api/stock_pool/strategies', methods=['GET'])
    def get_strategies():
        """获取策略列表"""
        try:
            strategies = stock_pool_system.matcher.strategy_profiles
            result = []
            for s in strategies:
                result.append({
                    'name': s.name,
                    'type': s.type,
                    'volatility_profile': s.volatility_profile,
                    'min_liquidity': s.min_liquidity,
                    'ideal_trend': s.ideal_trend,
                    'min_return': s.min_return
                })
            return jsonify({"success": True, "data": result})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    # ============================================================
    # 人工审批API
    # ============================================================

    @app.route('/api/stock_pool/pending_approvals', methods=['GET'])
    def get_pending_approvals():
        """获取待审批股票列表"""
        try:
            from core.stock_pool import get_stock_pool_manager
            mgr = get_stock_pool_manager()
            mgr.reload()
            pending = mgr.get_pending_approvals()
            return jsonify({"success": True, "data": pending, "count": len(pending)})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route('/api/stock_pool/approve', methods=['POST'])
    def approve_stock():
        """审批通过股票"""
        data = request.get_json() or {}
        symbol = data.get('symbol', '')
        target_level = data.get('target_level', 'candidate')
        try:
            from core.stock_pool import get_stock_pool_manager, PoolLevel
            mgr = get_stock_pool_manager()
            level_map = {'candidate': PoolLevel.CANDIDATE, 'testing': PoolLevel.TESTING,
                         'prelive': PoolLevel.PRELIVE, 'live': PoolLevel.LIVE}
            level = level_map.get(target_level, PoolLevel.CANDIDATE)
            result = mgr.approve_stock(symbol, target_level=level)
            return jsonify(result)
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route('/api/stock_pool/reject', methods=['POST'])
    def reject_stock():
        """审批拒绝股票"""
        data = request.get_json() or {}
        symbol = data.get('symbol', '')
        reason = data.get('reason', '人工拒绝')
        try:
            from core.stock_pool import get_stock_pool_manager
            mgr = get_stock_pool_manager()
            result = mgr.reject_stock(symbol, reason)
            return jsonify(result)
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route('/api/stock_pool/batch_approve', methods=['POST'])
    def batch_approve_stocks():
        """批量审批通过"""
        data = request.get_json() or {}
        symbols = data.get('symbols', [])
        try:
            from core.stock_pool import get_stock_pool_manager
            mgr = get_stock_pool_manager()
            result = mgr.batch_approve(symbols)
            return jsonify(result)
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route('/api/stock_pool/batch_reject', methods=['POST'])
    def batch_reject_stocks():
        """批量审批拒绝"""
        data = request.get_json() or {}
        symbols = data.get('symbols', [])
        reason = data.get('reason', '人工拒绝')
        try:
            from core.stock_pool import get_stock_pool_manager
            mgr = get_stock_pool_manager()
            result = mgr.batch_reject(symbols, reason)
            return jsonify(result)
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500