"""
Celery异步任务队列 - 修补项 P2-9
================================
修补项 P2-9：Celery异步任务 ✅

功能：
- 异步交易日历更新
- 异步回测任务
- 异步数据质量扫描
- 异步通知推送（企业微信/WEBHOOK）
- 定时任务调度（Celery Beat）
- 任务状态追踪
- 失败重试机制
- Redis/RabbitMQ后端

任务清单：
| 任务名                    | 队列     | 优先级 | 说明              |
|---------------------------|----------|--------|-------------------|
| update_trading_calendar   | beat     | 低     | 交易日历更新      |
| run_backtest_async        | backtest | 中     | 异步回测          |
| scan_data_quality         | data     | 低     | 数据质量扫描      |
| send_wechat_notification  | notify   | 高     | 企业微信通知      |
| sync_market_data          | data     | 中     | 市场数据同步      |
| clean_expired_sessions    | beat     | 低     | 清理过期会话      |
| monitor_risk_thresholds   | risk     | 高     | 风控阈值监控      |
"""

import os
import logging
from datetime import timedelta
from typing import Optional, Dict, Any

from celery import Celery
from celery.schedules import crontab
from celery.signals import task_failure, task_success, after_setup_logger

logger = logging.getLogger(__name__)


# ============================================================
# Celery应用实例
# ============================================================
def make_celery(flask_app=None):
    """
    创建Celery实例（兼容Flask应用上下文）
    
    用法:
    from flask import Flask
    from celery_app import make_celery
    
    app = Flask(__name__)
    app.config['CELERY_BROKER_URL'] = 'redis://localhost:6379/0'
    app.config['CELERY_RESULT_BACKEND'] = 'redis://localhost:6379/1'
    
    celery = make_celery(app)
    """
    
    # 从环境或配置获取Broker URL
    broker_url = os.environ.get(
        "CELERY_BROKER_URL",
        "redis://localhost:6379/0"
    )
    result_backend = os.environ.get(
        "CELERY_RESULT_BACKEND",
        "redis://localhost:6379/1"
    )
    
    celery = Celery(
        "aurora",
        broker=broker_url,
        backend=result_backend,
    )
    
    # 默认配置
    celery.conf.update(
        # 任务序列化
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        
        # 时区
        timezone="Asia/Shanghai",
        enable_utc=True,
        
        # 任务超时
        task_time_limit=30 * 60,       # 30分钟硬超时
        task_soft_time_limit=25 * 60,  # 25分钟软超时（抛出SoftTimeLimitExceeded异常）
        
        # 任务重试
        task_acks_late=True,           # 任务完成后才确认（防丢失）
        task_reject_on_worker_lost=True,
        task_default_retry_delay=60,   # 默认60秒后重试
        task_max_retries=3,            # 默认最多重试3次
        
        # Worker配置
        worker_prefetch_multiplier=1,  # 每次只预取1个任务（公平调度）
        worker_max_tasks_per_child=100, # 每100个任务重启worker（防内存泄漏）
        worker_concurrency=4,          # 默认4个并发worker
        
        # 结果过期
        result_expires=3600,           # 结果1小时后过期
        
        # 任务路由
        task_routes={
            "celery_app.update_trading_calendar": {"queue": "beat"},
            "celery_app.run_backtest_async": {"queue": "backtest"},
            "celery_app.scan_data_quality": {"queue": "data"},
            "celery_app.sync_market_data": {"queue": "data"},
            "celery_app.send_wechat_notification": {"queue": "notify"},
            "celery_app.clean_expired_sessions": {"queue": "beat"},
            "celery_app.monitor_risk_thresholds": {"queue": "risk"},
        },
        
        # 定时任务调度（Celery Beat）
        beat_schedule={
            # 每个工作日18:00更新交易日历
            "update-trading-calendar-daily": {
                "task": "celery_app.update_trading_calendar",
                "schedule": crontab(hour=18, minute=0, day_of_week="1-5"),
                "options": {"queue": "beat"},
            },
            # 每4小时同步市场数据
            "sync-market-data-hourly": {
                "task": "celery_app.sync_market_data",
                "schedule": crontab(minute=0, hour="9-15/4"),
                "options": {"queue": "data"},
            },
            # 每30分钟数据质量扫描
            "scan-data-quality": {
                "task": "celery_app.scan_data_quality",
                "schedule": crontab(minute="*/30"),
                "options": {"queue": "data"},
            },
            # 每10分钟风控检查
            "monitor-risk-thresholds": {
                "task": "celery_app.monitor_risk_thresholds",
                "schedule": crontab(minute="*/10"),
                "options": {"queue": "risk"},
            },
            # 每天凌晨3点清理过期会话
            "clean-expired-sessions": {
                "task": "celery_app.clean_expired_sessions",
                "schedule": crontab(hour=3, minute=0),
                "options": {"queue": "beat"},
            },
        },
    )
    
    # 如果传入了Flask应用，自动配置
    if flask_app:
        celery.conf.update(flask_app.config)
        
        # 包装Task类以支持Flask应用上下文
        TaskBase = celery.Task
        
        class ContextTask(TaskBase):
            abstract = True
            
            def __call__(self, *args, **kwargs):
                with flask_app.app_context():
                    return TaskBase.__call__(self, *args, **kwargs)
        
        celery.Task = ContextTask
    
    return celery


# 创建默认Celery实例（无Flask上下文）
celery = make_celery()


# ============================================================
# 信号处理
# ============================================================
@task_success.connect
def on_task_success(sender=None, result=None, **kwargs):
    """任务成功回调"""
    task_name = sender.name if sender else "unknown"
    logger.info(f"✅ 任务成功: {task_name}")


@task_failure.connect
def on_task_failure(sender=None, exception=None, traceback=None, **kwargs):
    """任务失败回调"""
    task_name = sender.name if sender else "unknown"
    logger.error(f"❌ 任务失败: {task_name}, 异常: {exception}")


# ============================================================
# 异步任务定义
# ============================================================
@celery.task(bind=True, max_retries=3, default_retry_delay=300)
def update_trading_calendar(self, year: Optional[int] = None):
    """
    异步更新A股交易日历
    
    Args:
        year: 年份（默认为当前年份）
    
    Returns:
        更新的年份
    """
    from datetime import datetime
    from utils.trading_calendar import TradingCalendar
    
    year = year or datetime.now().year
    
    try:
        logger.info(f"开始更新交易日历: {year}")
        calendar = TradingCalendar()
        result = calendar.update_calendar(year)
        logger.info(f"交易日历更新完成: {year}, 营业日: {result}")
        return {"status": "success", "year": year, "trading_days": result}
    
    except Exception as e:
        logger.error(f"交易日历更新失败: {e}")
        raise self.retry(exc=e)


@celery.task(bind=True, max_retries=2, default_retry_delay=120)
def run_backtest_async(self, strategy_name: str, start_date: str,
                       end_date: str, initial_capital: float = 1000000.0,
                       **kwargs):
    """
    异步回测任务
    
    Args:
        strategy_name: 策略名称
        start_date: 起始日期 (YYYY-MM-DD)
        end_date: 结束日期 (YYYY-MM-DD)
        initial_capital: 初始资金
        **kwargs: 策略参数
    
    Returns:
        回测结果字典
    Example:
        result = run_backtest_async.delay(
            "ma_cross", "2024-01-01", "2024-12-31",
            initial_capital=500000, fast_period=5, slow_period=20
        )
    """
    import json
    from datetime import datetime
    
    task_id = self.request.id
    logger.info(f"开始异步回测 [{task_id}]: {strategy_name} ({start_date} ~ {end_date})")
    
    try:
        # 动态导入回测模块（避免循环依赖）
        from strategies import get_strategy
        from backtest_enhancer import BacktestRunner
        
        # 获取策略
        strategy = get_strategy(strategy_name)
        if not strategy:
            raise ValueError(f"策略不存在: {strategy_name}")
        
        # 运行回测
        runner = BacktestRunner(
            strategy=strategy,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            **kwargs,
        )
        
        result = runner.run()
        
        # 序列化结果
        summary = {
            "task_id": task_id,
            "strategy": strategy_name,
            "start_date": start_date,
            "end_date": end_date,
            "initial_capital": initial_capital,
            "final_equity": result.get("final_equity", 0),
            "total_return": result.get("total_return", 0),
            "annual_return": result.get("annual_return", 0),
            "sharpe_ratio": result.get("sharpe_ratio", 0),
            "max_drawdown": result.get("max_drawdown", 0),
            "win_rate": result.get("win_rate", 0),
            "total_trades": result.get("total_trades", 0),
            "completed_at": datetime.now().isoformat(),
        }
        
        logger.info(f"回测完成 [{task_id}]: 年化收益={summary['annual_return']:.2%}, "
                    f"夏普={summary['sharpe_ratio']:.2f}")
        
        return {"status": "success", "data": summary}
    
    except Exception as e:
        logger.error(f"回测失败 [{task_id}]: {e}")
        raise self.retry(exc=e)


@celery.task(bind=True, max_retries=1)
def scan_data_quality(self, source: Optional[str] = None):
    """
    异步数据质量扫描
    
    检查4个数据源的数据质量：
    - Yahoo Finance
    - 东方财富
    - Tushare
    - AKShare
    
    Args:
        source: 指定数据源（None表示检查所有）
    
    Returns:
        质量报告
    """
    logger.info(f"开始数据质量扫描: source={source or 'all'}")
    
    try:
        from data_aggregator import DataAggregator
        
        aggregator = DataAggregator()
        
        if source:
            report = aggregator.check_source_quality(source)
        else:
            report = aggregator.check_all_sources_quality()
        
        logger.info(f"数据质量扫描完成: 检查了 {len(report)} 个数据源")
        
        return {
            "status": "success",
            "data": report,
            "timestamp": __import__("datetime").datetime.now().isoformat(),
        }
    
    except Exception as e:
        logger.error(f"数据质量扫描失败: {e}")
        raise self.retry(exc=e)


@celery.task(bind=True, max_retries=3, default_retry_delay=30)
def sync_market_data(self, symbols: Optional[list] = None,
                     source: str = "auto"):
    """
    异步市场数据同步
    
    Args:
        symbols: 股票代码列表（None表示同步自选股）
        source: 数据源（auto自动选择最佳源）
    
    Returns:
        同步结果
    """
    logger.info(f"开始市场数据同步: {len(symbols or [])} symbols")
    
    try:
        from data_aggregator import DataAggregator
        
        aggregator = DataAggregator()
        result = aggregator.sync_market_data(symbols=symbols, source=source)
        
        logger.info(f"市场数据同步完成: {result.get('synced', 0)} 个股票")
        
        return {
            "status": "success",
            "data": result,
        }
    
    except Exception as e:
        logger.error(f"市场数据同步失败: {e}")
        raise self.retry(exc=e)


@celery.task(bind=True, max_retries=2, default_retry_delay=10)
def send_wechat_notification(self, message: str, msg_type: str = "text",
                             webhook_url: Optional[str] = None,
                             mentioned_list: Optional[list] = None):
    """
    企业微信通知推送
    
    Args:
        message: 消息内容
        msg_type: 消息类型（text/markdown/news）
        webhook_url: Webhook地址（默认使用环境变量WECOM_WEBHOOK_URL）
        mentioned_list: @的用户列表
    
    Returns:
        推送结果
    """
    import requests
    
    webhook = webhook_url or os.environ.get("WECOM_WEBHOOK_URL", "")
    
    if not webhook:
        logger.warning("企业微信Webhook未配置，跳过推送")
        return {"status": "skipped", "reason": "webhook not configured"}
    
    try:
        payload = {
            "msgtype": msg_type,
        }
        
        if msg_type == "text":
            payload["text"] = {
                "content": message,
                "mentioned_list": mentioned_list or [],
            }
        elif msg_type == "markdown":
            payload["markdown"] = {"content": message}
        
        response = requests.post(
            webhook,
            json=payload,
            timeout=10,
        )
        response.raise_for_status()
        
        logger.info(f"企业微信通知发送成功: {msg_type}")
        return {"status": "success", "response": response.json()}
    
    except Exception as e:
        logger.error(f"企业微信通知发送失败: {e}")
        raise self.retry(exc=e)


@celery.task(bind=True)
def clean_expired_sessions(self):
    """清理过期会话和令牌"""
    import sqlite3
    from datetime import datetime, timedelta
    
    logger.info("开始清理过期会话...")
    
    try:
        db_path = os.environ.get("DATABASE_URL", "aurora.db").replace("sqlite:///", "")
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 清理7天前的会话
        cutoff = (datetime.now() - timedelta(days=7)).isoformat()
        cursor.execute("DELETE FROM sessions WHERE created_at < ?", (cutoff,))
        deleted_sessions = cursor.rowcount
        
        # 清理过期的refresh tokens
        cursor.execute("DELETE FROM refresh_tokens WHERE expires_at < datetime('now')")
        deleted_tokens = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        logger.info(f"会话清理完成: {deleted_sessions} 会话, {deleted_tokens} 令牌")
        
        return {
            "status": "success",
            "deleted_sessions": deleted_sessions,
            "deleted_tokens": deleted_tokens,
        }
    
    except Exception as e:
        logger.error(f"会话清理失败: {e}")
        return {"status": "error", "reason": str(e)}


@celery.task(bind=True, max_retries=2, default_retry_delay=30)
def monitor_risk_thresholds(self):
    """
    风控阈值监控
    
    检查项：
    - 单日亏损是否超过限额
    - 单笔订单金额是否超过上限
    - 总仓位是否超过限制
    - 熔断器是否触发
    """
    logger.info("开始风控阈值监控...")
    
    try:
        from risk_manager import RiskManager
        
        risk_mgr = RiskManager()
        alerts = risk_mgr.check_all_thresholds()
        
        if alerts:
            # 汇总告警信息
            alert_msg = "⚠️ 风控告警\n"
            for alert in alerts:
                alert_msg += f"- [{alert['severity']}] {alert['rule']}: {alert['message']}\n"
            
            logger.warning(f"风控告警: {len(alerts)} 条")
            
            # 发送企业微信通知
            send_wechat_notification.delay(
                message=alert_msg,
                msg_type="text",
                mentioned_list=["@all"] if any(a['severity'] == 'critical' for a in alerts) else [],
            )
        else:
            logger.info("风控阈值正常")
        
        return {
            "status": "success",
            "alerts_count": len(alerts),
            "timestamp": __import__("datetime").datetime.now().isoformat(),
        }
    
    except Exception as e:
        logger.error(f"风控监控失败: {e}")
        raise self.retry(exc=e)


@celery.task(bind=True, max_retries=1)
def run_daily_report(self, date: Optional[str] = None):
    """
    每日交易报告生成
    
    Args:
        date: 报告日期（默认为今天）
    """
    from datetime import datetime
    
    date = date or datetime.now().strftime("%Y-%m-%d")
    logger.info(f"开始生成每日报告: {date}")
    
    try:
        from reports import DailyReportGenerator
        
        generator = DailyReportGenerator()
        report_path = generator.generate(date=date)
        
        logger.info(f"每日报告已生成: {report_path}")
        
        # 发送企业微信通知
        send_wechat_notification.delay(
            message=f"📊 每日交易报告已生成\n日期: {date}\n路径: {report_path}",
            msg_type="text",
        )
        
        return {
            "status": "success",
            "date": date,
            "report_path": report_path,
        }
    
    except Exception as e:
        logger.error(f"每日报告生成失败: {e}")
        return {"status": "error", "reason": str(e)}


# ============================================================
# 工具函数
# ============================================================
def get_task_status(task_id: str) -> Dict[str, Any]:
    """
    查询异步任务状态
    
    Args:
        task_id: 任务ID
    
    Returns:
        任务状态信息
    """
    from celery.result import AsyncResult
    
    result = AsyncResult(task_id, app=celery)
    
    response = {
        "task_id": task_id,
        "status": result.state,
        "ready": result.ready(),
        "successful": result.successful() if result.ready() else None,
    }
    
    if result.ready():
        if result.successful():
            response["result"] = result.get()
        else:
            response["error"] = str(result.info)
    
    return response


def revoke_task(task_id: str, terminate: bool = False):
    """
    取消异步任务
    
    Args:
        task_id: 任务ID
        terminate: 是否强制终止（SIGTERM）
    """
    celery.control.revoke(task_id, terminate=terminate)
    logger.info(f"任务已取消: {task_id} (terminate={terminate})")