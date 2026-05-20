#!/usr/bin/env python3
"""
数据库模块（增量模块集成版）
实现 BaseModule 标准接口，包装 DatabaseManager 提供集成功能

功能：
1. 包装现有 DatabaseManager
2. 提供查询和统计接口
3. 数据库健康检查
4. 系统日志查询
5. 交易记录查询
6. 备份与维护API
7. 与 SystemSwitcher 和 ModuleRegistry 联动
"""

import json
import os
import sqlite3
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class BaseModule:
    """增量模块基类（本地定义，避免循环导入）"""
    
    def __init__(self, app=None):
        self.app = app
        self.enabled = False
        self.module_name = self.__class__.__name__
    
    def register_routes(self, app):
        pass
    
    def register_hooks(self, app):
        pass
    
    def start(self):
        self.enabled = True
        logger.info(f"[{self.module_name}] 已启动")
    
    def stop(self):
        self.enabled = False
        logger.info(f"[{self.module_name}] 已停止")
    
    def get_status(self) -> Dict[str, Any]:
        return {
            'name': self.module_name,
            'enabled': self.enabled,
        }


class DatabaseModule(BaseModule):
    """
    数据库模块（集成版）
    
    包装 DatabaseManager，提供查询、统计和维护接口
    """
    
    def __init__(self, app=None, db_manager=None):
        super().__init__(app)
        self.module_name = 'DatabaseModule'
        
        # 使用传入或全局数据库管理器
        if db_manager:
            self._db = db_manager
        else:
            from utils.database_manager import get_database_manager
            self._db = get_database_manager()
        
        # 最后已知状态
        self._last_stats: Dict = {}
        self._last_stats_time: Optional[datetime] = None
        
        logger.info("[DatabaseModule] 数据库模块已初始化")
    
    def _execute_query(self, sql: str, params: tuple = None) -> List[Dict]:
        """
        执行查询并返回结果列表
        
        Args:
            sql: SQL查询语句
            params: 查询参数
        
        Returns:
            结果行列表
        """
        results = []
        try:
            self._db.connect()
            cursor = self._db.conn.cursor()
            cursor.execute(sql, params or ())
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            for row in cursor.fetchall():
                row_dict = {columns[i]: row[i] for i in range(len(columns))}
                results.append(row_dict)
        except Exception as e:
            logger.error(f"[DatabaseModule] 查询失败: {e}, SQL: {sql}")
        finally:
            self._db.close()
        
        return results
    
    def get_system_logs(self, level: str = None, module: str = None,
                        limit: int = 100, offset: int = 0,
                        start_time: str = None, end_time: str = None) -> List[Dict]:
        """
        查询系统日志
        
        Args:
            level: 日志级别过滤 (INFO, WARNING, ERROR)
            module: 模块名过滤
            limit: 返回数量
            offset: 偏移量
            start_time: 开始时间
            end_time: 结束时间
        
        Returns:
            日志列表
        """
        sql = 'SELECT * FROM system_logs WHERE 1=1'
        params = []
        
        if level:
            sql += ' AND level = ?'
            params.append(level)
        if module:
            sql += ' AND module = ?'
            params.append(module)
        if start_time:
            sql += ' AND timestamp >= ?'
            params.append(start_time)
        if end_time:
            sql += ' AND timestamp <= ?'
            params.append(end_time)
        
        sql += ' ORDER BY id DESC LIMIT ? OFFSET ?'
        params.extend([limit, offset])
        
        return self._execute_query(sql, tuple(params))
    
    def get_trade_records(self, strategy_name: str = None, symbol: str = None,
                          status: str = None, limit: int = 100, offset: int = 0,
                          start_time: str = None, end_time: str = None) -> List[Dict]:
        """
        查询交易记录
        
        Args:
            strategy_name: 策略名过滤
            symbol: 标的过滤
            status: 状态过滤
            limit: 返回数量
            offset: 偏移量
            start_time: 开始时间
            end_time: 结束时间
        
        Returns:
            交易记录列表
        """
        sql = 'SELECT * FROM trade_records WHERE 1=1'
        params = []
        
        if strategy_name:
            sql += ' AND strategy_name = ?'
            params.append(strategy_name)
        if symbol:
            sql += ' AND symbol = ?'
            params.append(symbol)
        if status:
            sql += ' AND status = ?'
            params.append(status)
        if start_time:
            sql += ' AND timestamp >= ?'
            params.append(start_time)
        if end_time:
            sql += ' AND timestamp <= ?'
            params.append(end_time)
        
        sql += ' ORDER BY id DESC LIMIT ? OFFSET ?'
        params.extend([limit, offset])
        
        return self._execute_query(sql, tuple(params))
    
    def get_health_checks(self, component: str = None, status: str = None,
                          limit: int = 100) -> List[Dict]:
        """
        查询健康检查记录
        
        Args:
            component: 组件名过滤
            status: 状态过滤
            limit: 返回数量
        
        Returns:
            健康检查记录列表
        """
        sql = 'SELECT * FROM health_checks WHERE 1=1'
        params = []
        
        if component:
            sql += ' AND component = ?'
            params.append(component)
        if status:
            sql += ' AND status = ?'
            params.append(status)
        
        sql += ' ORDER BY id DESC LIMIT ?'
        params.append(limit)
        
        return self._execute_query(sql, tuple(params))
    
    def get_security_events(self, event_type: str = None,
                            limit: int = 100) -> List[Dict]:
        """
        查询安全事件
        
        Args:
            event_type: 事件类型过滤
            limit: 返回数量
        
        Returns:
            安全事件列表
        """
        sql = 'SELECT * FROM security_events WHERE 1=1'
        params = []
        
        if event_type:
            sql += ' AND event_type = ?'
            params.append(event_type)
        
        sql += ' ORDER BY id DESC LIMIT ?'
        params.append(limit)
        
        return self._execute_query(sql, tuple(params))
    
    def get_all_configs(self) -> Dict[str, str]:
        """获取所有配置"""
        try:
            self._db.connect()
            cursor = self._db.conn.cursor()
            cursor.execute('SELECT key, value FROM system_config ORDER BY key')
            rows = cursor.fetchall()
            return {row[0]: row[1] for row in rows}
        except Exception as e:
            logger.error(f"[DatabaseModule] 获取所有配置失败: {e}")
            return {}
        finally:
            self._db.close()
    
    def get_trade_summary(self, days: int = 30) -> Dict[str, Any]:
        """
        获取交易摘要统计
        
        Args:
            days: 统计天数
        
        Returns:
            交易统计
        """
        start_date = (datetime.now() - timedelta(days=days)).isoformat()
        
        try:
            self._db.connect()
            cursor = self._db.conn.cursor()
            
            # 总交易数
            cursor.execute(
                'SELECT COUNT(*) FROM trade_records WHERE timestamp >= ?',
                (start_date,)
            )
            total_trades = cursor.fetchone()[0]
            
            # 已平仓交易
            cursor.execute(
                'SELECT COUNT(*), SUM(profit) FROM trade_records WHERE timestamp >= ? AND status = "closed"',
                (start_date,)
            )
            row = cursor.fetchone()
            closed_trades = row[0] or 0
            total_profit = row[1] or 0.0
            
            # 按策略分组
            cursor.execute(
                '''SELECT strategy_name, COUNT(*) as count, SUM(profit) as total_profit
                   FROM trade_records WHERE timestamp >= ? AND status = "closed"
                   GROUP BY strategy_name ORDER BY count DESC LIMIT 10''',
                (start_date,)
            )
            by_strategy = []
            for row in cursor.fetchall():
                by_strategy.append({
                    'strategy': row[0],
                    'count': row[1],
                    'total_profit': round(row[2], 2) if row[2] else 0,
                })
            
            return {
                'period_days': days,
                'total_trades': total_trades,
                'closed_trades': closed_trades,
                'total_profit': round(total_profit, 2),
                'avg_profit': round(total_profit / closed_trades, 2) if closed_trades > 0 else 0,
                'by_strategy': by_strategy,
            }
        except Exception as e:
            logger.error(f"[DatabaseModule] 获取交易摘要失败: {e}")
            return {}
        finally:
            self._db.close()
    
    def get_database_size(self) -> Dict[str, Any]:
        """获取数据库文件大小"""
        result = {
            'path': self._db.db_path,
            'exists': False,
            'size_bytes': 0,
            'size_mb': 0,
        }
        
        if os.path.exists(self._db.db_path):
            size_bytes = os.path.getsize(self._db.db_path)
            result.update({
                'exists': True,
                'size_bytes': size_bytes,
                'size_mb': round(size_bytes / (1024 * 1024), 2),
            })
        
        return result
    
    def vacuum_database(self) -> bool:
        """数据库清理和优化"""
        try:
            self._db.connect()
            self._db.conn.execute('VACUUM')
            self._db.close()
            logger.info("[DatabaseModule] 数据库VACUUM完成")
            return True
        except Exception as e:
            logger.error(f"[DatabaseModule] 数据库VACUUM失败: {e}")
            return False
    
    def backup_database(self, backup_path: str = None) -> Optional[str]:
        """
        备份数据库
        
        Args:
            backup_path: 备份路径（默认使用时间戳命名）
        
        Returns:
            备份文件路径
        """
        if backup_path is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_dir = os.path.join(os.path.dirname(self._db.db_path), 'backups')
            os.makedirs(backup_dir, exist_ok=True)
            backup_path = os.path.join(backup_dir, f'trading_system_backup_{timestamp}.db')
        
        try:
            source = sqlite3.connect(self._db.db_path)
            dest = sqlite3.connect(backup_path)
            source.backup(dest)
            source.close()
            dest.close()
            logger.info(f"[DatabaseModule] 数据库备份完成: {backup_path}")
            return backup_path
        except Exception as e:
            logger.error(f"[DatabaseModule] 数据库备份失败: {e}")
            return None
    
    def get_database_stats(self) -> Dict[str, Any]:
        """获取数据库统计信息"""
        stats = {
            'database': self.get_database_size(),
            'tables': {},
            'checked_at': datetime.now().isoformat(),
        }
        
        tables = ['system_logs', 'trade_records', 'health_checks', 'security_events', 'system_config']
        
        try:
            self._db.connect()
            for table in tables:
                cursor = self._db.conn.cursor()
                cursor.execute(f'SELECT COUNT(*) FROM {table}')
                count = cursor.fetchone()[0]
                stats['tables'][table] = count
        except Exception as e:
            logger.error(f"[DatabaseModule] 统计查询失败: {e}")
        finally:
            self._db.close()
        
        self._last_stats = stats
        self._last_stats_time = datetime.now()
        
        return stats
    
    def check_health(self) -> tuple:
        """
        数据库健康检查
        
        Returns:
            (status, message)，其中 status 为 'healthy'/'warning'/'critical'
        """
        try:
            # 检查数据库文件存在性
            if not os.path.exists(self._db.db_path):
                return 'critical', '数据库文件不存在'
            
            # 检查连接
            self._db.connect()
            cursor = self._db.conn.cursor()
            cursor.execute('SELECT 1')
            self._db.close()
            
            # 检查大小
            size = os.path.getsize(self._db.db_path)
            if size > 500 * 1024 * 1024:  # 500MB
                return 'warning', f'数据库文件较大 ({size / (1024*1024):.1f}MB)'
            
            return 'healthy', '数据库正常运行'
        except Exception as e:
            return 'critical', f'数据库检查失败: {e}'
    
    def register_routes(self, app):
        """注册数据库模块路由"""
        
        @app.route('/api/database/stats')
        def database_stats():
            """获取数据库统计"""
            try:
                stats = self.get_database_stats()
                return json.dumps({
                    'success': True,
                    'data': stats,
                }), 200, {'Content-Type': 'application/json'}
            except Exception as e:
                return json.dumps({
                    'success': False,
                    'message': f'获取数据库统计失败: {str(e)}',
                }), 500, {'Content-Type': 'application/json'}
        
        @app.route('/api/database/logs')
        def database_logs():
            """查询系统日志"""
            try:
                level = request.args.get('level')
                module = request.args.get('module')
                limit = int(request.args.get('limit', 100))
                offset = int(request.args.get('offset', 0))
                start_time = request.args.get('start_time')
                end_time = request.args.get('end_time')
                
                logs = self.get_system_logs(
                    level=level, module=module,
                    limit=limit, offset=offset,
                    start_time=start_time, end_time=end_time
                )
                
                return json.dumps({
                    'success': True,
                    'data': logs,
                    'total': len(logs),
                }), 200, {'Content-Type': 'application/json'}
            except Exception as e:
                return json.dumps({
                    'success': False,
                    'message': f'查询日志失败: {str(e)}',
                }), 500, {'Content-Type': 'application/json'}
        
        @app.route('/api/database/trades')
        def database_trades():
            """查询交易记录"""
            try:
                strategy = request.args.get('strategy')
                symbol = request.args.get('symbol')
                status = request.args.get('status')
                limit = int(request.args.get('limit', 100))
                offset = int(request.args.get('offset', 0))
                start_time = request.args.get('start_time')
                end_time = request.args.get('end_time')
                
                trades = self.get_trade_records(
                    strategy_name=strategy, symbol=symbol,
                    status=status, limit=limit, offset=offset,
                    start_time=start_time, end_time=end_time
                )
                
                return json.dumps({
                    'success': True,
                    'data': trades,
                    'total': len(trades),
                }), 200, {'Content-Type': 'application/json'}
            except Exception as e:
                return json.dumps({
                    'success': False,
                    'message': f'查询交易记录失败: {str(e)}',
                }), 500, {'Content-Type': 'application/json'}
        
        @app.route('/api/database/trades/summary')
        def database_trade_summary():
            """获取交易摘要"""
            try:
                days = int(request.args.get('days', 30))
                summary = self.get_trade_summary(days=days)
                return json.dumps({
                    'success': True,
                    'data': summary,
                }), 200, {'Content-Type': 'application/json'}
            except Exception as e:
                return json.dumps({
                    'success': False,
                    'message': f'获取交易摘要失败: {str(e)}',
                }), 500, {'Content-Type': 'application/json'}
        
        @app.route('/api/database/health-checks')
        def database_health_checks():
            """查询健康检查记录"""
            try:
                component = request.args.get('component')
                status = request.args.get('status')
                limit = int(request.args.get('limit', 100))
                
                checks = self.get_health_checks(
                    component=component, status=status, limit=limit
                )
                
                return json.dumps({
                    'success': True,
                    'data': checks,
                }), 200, {'Content-Type': 'application/json'}
            except Exception as e:
                return json.dumps({
                    'success': False,
                    'message': f'查询健康检查失败: {str(e)}',
                }), 500, {'Content-Type': 'application/json'}
        
        @app.route('/api/database/security-events')
        def database_security_events():
            """查询安全事件"""
            try:
                event_type = request.args.get('type')
                limit = int(request.args.get('limit', 100))
                
                events = self.get_security_events(
                    event_type=event_type, limit=limit
                )
                
                return json.dumps({
                    'success': True,
                    'data': events,
                }), 200, {'Content-Type': 'application/json'}
            except Exception as e:
                return json.dumps({
                    'success': False,
                    'message': f'查询安全事件失败: {str(e)}',
                }), 500, {'Content-Type': 'application/json'}
        
        @app.route('/api/database/config')
        def database_config():
            """获取/设置配置"""
            try:
                if request.method == 'GET':
                    key = request.args.get('key')
                    if key:
                        value = self._db.get_config(key)
                        return json.dumps({
                            'success': True,
                            'data': {key: value},
                        }), 200, {'Content-Type': 'application/json'}
                    else:
                        configs = self.get_all_configs()
                        return json.dumps({
                            'success': True,
                            'data': configs,
                        }), 200, {'Content-Type': 'application/json'}
            except Exception as e:
                return json.dumps({
                    'success': False,
                    'message': f'获取配置失败: {str(e)}',
                }), 500, {'Content-Type': 'application/json'}
        
        @app.route('/api/database/config', methods=['POST'])
        def database_set_config():
            """设置配置"""
            try:
                data = request.get_json() if request.is_json else {}
                key = data.get('key', '')
                value = data.get('value', '')
                description = data.get('description', '')
                
                if not key:
                    return json.dumps({
                        'success': False,
                        'message': '缺少配置key',
                    }), 400, {'Content-Type': 'application/json'}
                
                self._db.set_config(key, str(value), description)
                return json.dumps({
                    'success': True,
                    'message': f'配置 {key} 已更新',
                }), 200, {'Content-Type': 'application/json'}
            except Exception as e:
                return json.dumps({
                    'success': False,
                    'message': f'设置配置失败: {str(e)}',
                }), 500, {'Content-Type': 'application/json'}
        
        @app.route('/api/database/backup', methods=['POST'])
        def database_backup():
            """备份数据库"""
            try:
                backup_path = self.backup_database()
                if backup_path:
                    return json.dumps({
                        'success': True,
                        'message': '数据库备份完成',
                        'data': {'backup_path': backup_path},
                    }), 200, {'Content-Type': 'application/json'}
                else:
                    return json.dumps({
                        'success': False,
                        'message': '备份失败',
                    }), 500, {'Content-Type': 'application/json'}
            except Exception as e:
                return json.dumps({
                    'success': False,
                    'message': f'备份失败: {str(e)}',
                }), 500, {'Content-Type': 'application/json'}
        
        @app.route('/api/database/vacuum', methods=['POST'])
        def database_vacuum():
            """优化数据库"""
            try:
                result = self.vacuum_database()
                return json.dumps({
                    'success': result,
                    'message': '数据库优化完成' if result else '优化失败',
                }), 200, {'Content-Type': 'application/json'}
            except Exception as e:
                return json.dumps({
                    'success': False,
                    'message': f'优化失败: {str(e)}',
                }), 500, {'Content-Type': 'application/json'}
        
        logger.info("[DatabaseModule] 数据库路由已注册")
    
    def get_status(self) -> Dict[str, Any]:
        """获取模块状态"""
        base = super().get_status()
        try:
            stats = self.get_database_stats()
            base.update(stats)
        except Exception:
            pass
        return base


# 全局实例
_global_database_module: Optional[DatabaseModule] = None


def get_database_module() -> DatabaseModule:
    """获取全局数据库模块实例"""
    global _global_database_module
    if _global_database_module is None:
        _global_database_module = DatabaseModule()
    return _global_database_module