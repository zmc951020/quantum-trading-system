
import logging
import time
from prometheus_client import Counter, Gauge, Histogram, Summary
from typing import Optional

logger = logging.getLogger(__name__)


class AuthMetrics:
    """权限系统监控指标"""
    
    def __init__(self):
        # 计数器
        self.auth_success_counter = Counter(
            'auth_success_total',
            'Total successful authentication attempts',
            ['method', 'user_type']
        )
        
        self.auth_failure_counter = Counter(
            'auth_failure_total',
            'Total failed authentication attempts',
            ['method', 'reason']
        )
        
        self.permission_check_counter = Counter(
            'permission_check_total',
            'Total permission check attempts',
            ['permission', 'result']
        )
        
        self.approval_request_counter = Counter(
            'approval_request_total',
            'Total approval requests',
            ['status']
        )
        
        # 仪表盘
        self.active_users_gauge = Gauge(
            'active_users',
            'Number of active users'
        )
        
        self.pending_approvals_gauge = Gauge(
            'pending_approvals',
            'Number of pending approval requests'
        )
        
        self.risk_score_gauge = Gauge(
            'risk_score',
            'Current risk score',
            ['user_id']
        )
        
        # 直方图
        self.auth_duration_histogram = Histogram(
            'auth_duration_seconds',
            'Authentication duration in seconds',
            ['method']
        )
        
        self.permission_check_duration_histogram = Histogram(
            'permission_check_duration_seconds',
            'Permission check duration in seconds',
            ['permission']
        )
        
        # 摘要
        self.api_request_summary = Summary(
            'api_request_duration_seconds',
            'API request duration in seconds',
            ['endpoint']
        )
    
    def record_auth_success(self, method: str, user_type: str):
        """记录认证成功"""
        self.auth_success_counter.labels(method=method, user_type=user_type).inc()
    
    def record_auth_failure(self, method: str, reason: str):
        """记录认证失败"""
        self.auth_failure_counter.labels(method=method, reason=reason).inc()
    
    def record_permission_check(self, permission: str, result: bool):
        """记录权限检查"""
        result_str = "success" if result else "failure"
        self.permission_check_counter.labels(permission=permission, result=result_str).inc()
    
    def record_approval_request(self, status: str):
        """记录审批请求"""
        self.approval_request_counter.labels(status=status).inc()
    
    def set_active_users(self, count: int):
        """设置活跃用户数"""
        self.active_users_gauge.set(count)
    
    def set_pending_approvals(self, count: int):
        """设置待审批请求数"""
        self.pending_approvals_gauge.set(count)
    
    def set_risk_score(self, user_id: str, score: float):
        """设置用户风险分数"""
        self.risk_score_gauge.labels(user_id=user_id).set(score)
    
    def time_auth(self, method: str):
        """认证时间装饰器"""
        return self.auth_duration_histogram.labels(method=method).time()
    
    def time_permission_check(self, permission: str):
        """权限检查时间装饰器"""
        return self.permission_check_duration_histogram.labels(permission=permission).time()
    
    def time_api_request(self, endpoint: str):
        """API请求时间装饰器"""
        return self.api_request_summary.labels(endpoint=endpoint).time()


# 全局指标实例
_auth_metrics: Optional[AuthMetrics] = None


def get_auth_metrics() -> AuthMetrics:
    """获取指标实例"""
    global _auth_metrics
    if _auth_metrics is None:
        _auth_metrics = AuthMetrics()
    return _auth_metrics


def setup_metrics():
    """设置指标服务"""
    try:
        from prometheus_client import start_http_server
        start_http_server(8001)
        logger.info("Prometheus metrics server started on port 8001")
    except Exception as e:
        logger.warning(f"Failed to start metrics server: {e}")

