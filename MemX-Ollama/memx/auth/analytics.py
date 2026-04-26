
import logging
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from collections import defaultdict, Counter

logger = logging.getLogger(__name__)


class PermissionAnalytics:
    """权限分析和异常检测"""
    
    def __init__(self, data_dir: str = "./data/auth"):
        self.data_dir = data_dir
        self.analytics_dir = os.path.join(data_dir, "analytics")
        os.makedirs(self.analytics_dir, exist_ok=True)
    
    def generate_permission_report(self, tenant_id: Optional[str] = None, days: int = 7) -> Dict[str, Any]:
        """生成权限分析报告"""
        from .storage import AuthStorage
        storage = AuthStorage()
        
        # 获取审计日志
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=days)
        
        logs = storage.get_audit_logs(
            tenant_id=tenant_id,
            start_time=start_time,
            end_time=end_time,
            limit=10000
        )
        
        # 分析数据
        analysis = {
            "report_time": end_time.isoformat(),
            "time_range": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat()
            },
            "tenant_id": tenant_id,
            "total_events": len(logs),
            "by_action": defaultdict(int),
            "by_permission": defaultdict(int),
            "by_user": defaultdict(int),
            "success_rate": 0,
            "failure_reasons": defaultdict(int),
            "risk_score_distribution": defaultdict(int),
            "approval_stats": {
                "total": 0,
                "pending": 0,
                "approved": 0,
                "rejected": 0
            }
        }
        
        success_count = 0
        
        for log in logs:
            analysis["by_action"][log.action] += 1
            analysis["by_user"][log.user_id] += 1
            
            if log.success:
                success_count += 1
            else:
                reason = log.details.get("reason", "unknown")
                analysis["failure_reasons"][reason] += 1
            
            # 分析权限相关日志
            if log.action.startswith("permission:check:"):
                permission = log.action.replace("permission:check:", "")
                analysis["by_permission"][permission] += 1
                
                risk_score = log.details.get("risk_score", 0)
                risk_level = self._get_risk_level(risk_score)
                analysis["risk_score_distribution"][risk_level] += 1
            
            # 分析审批相关日志
            if "approval_request_id" in log.details:
                analysis["approval_stats"]["total"] += 1
        
        # 计算成功率
        if logs:
            analysis["success_rate"] = round(success_count / len(logs) * 100, 2)
        
        # 获取审批状态统计
        from .tenant import get_tenant_manager
        tenant_manager = get_tenant_manager()
        approvals = tenant_manager.list_approval_requests(tenant_id=tenant_id)
        
        for approval in approvals:
            analysis["approval_stats"][approval.status] += 1
        
        # 保存报告
        report_file = os.path.join(self.analytics_dir, f"permission_report_{end_time.strftime('%Y%m%d_%H%M%S')}.json")
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(analysis, f, ensure_ascii=False, indent=2)
        
        logger.info(f"权限分析报告生成成功: {report_file}")
        return analysis
    
    def detect_anomalies(self, tenant_id: Optional[str] = None, days: int = 3) -> List[Dict[str, Any]]:
        """检测异常行为"""
        from .storage import AuthStorage
        storage = AuthStorage()
        
        # 获取审计日志
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=days)
        
        logs = storage.get_audit_logs(
            tenant_id=tenant_id,
            start_time=start_time,
            end_time=end_time,
            limit=5000
        )
        
        # 异常检测规则
        anomalies = []
        
        # 1. 频繁失败检测
        failure_counts = Counter()
        for log in logs:
            if not log.success:
                failure_counts[log.user_id] += 1
        
        for user_id, count in failure_counts.items():
            if count > 10:  # 阈值：10次以上失败
                anomalies.append({
                    "type": "frequent_failures",
                    "severity": "high",
                    "user_id": user_id,
                    "count": count,
                    "description": f"用户 {user_id} 在过去 {days} 天内有 {count} 次操作失败"
                })
        
        # 2. 高风险操作检测
        high_risk_operations = []
        for log in logs:
            risk_score = log.details.get("risk_score", 0)
            if risk_score > 0.8:
                high_risk_operations.append({
                    "user_id": log.user_id,
                    "action": log.action,
                    "risk_score": risk_score,
                    "timestamp": log.timestamp
                })
        
        if len(high_risk_operations) > 5:
            anomalies.append({
                "type": "high_risk_operations",
                "severity": "critical",
                "count": len(high_risk_operations),
                "description": f"过去 {days} 天内检测到 {len(high_risk_operations)} 次高风险操作"
            })
        
        # 3. 异常时间检测（非工作时间操作）
        off_hours_operations = []
        for log in logs:
            hour = log.timestamp.hour
            if hour < 6 or hour > 22:
                off_hours_operations.append({
                    "user_id": log.user_id,
                    "action": log.action,
                    "timestamp": log.timestamp
                })
        
        if len(off_hours_operations) > 20:
            anomalies.append({
                "type": "off_hours_operations",
                "severity": "medium",
                "count": len(off_hours_operations),
                "description": f"过去 {days} 天内检测到 {len(off_hours_operations)} 次非工作时间操作"
            })
        
        # 4. 权限升级检测
        permission_escalations = []
        user_permissions = defaultdict(set)
        
        for log in sorted(logs, key=lambda x: x.timestamp):
            if log.action.startswith("permission:check:"):
                permission = log.action.replace("permission:check:", "")
                user_permissions[log.user_id].add(permission)
                
                # 检测权限升级
                if permission in ["SYSTEM_ADMIN", "TENANT_ADMIN"]:
                    permission_escalations.append({
                        "user_id": log.user_id,
                        "permission": permission,
                        "timestamp": log.timestamp
                    })
        
        if permission_escalations:
            anomalies.append({
                "type": "permission_escalation",
                "severity": "high",
                "count": len(permission_escalations),
                "description": f"检测到 {len(permission_escalations)} 次权限升级操作"
            })
        
        # 保存异常检测结果
        if anomalies:
            anomaly_file = os.path.join(self.analytics_dir, f"anomalies_{end_time.strftime('%Y%m%d_%H%M%S')}.json")
            with open(anomaly_file, 'w', encoding='utf-8') as f:
                json.dump(anomalies, f, ensure_ascii=False, indent=2)
            logger.info(f"异常检测完成，发现 {len(anomalies)} 个异常: {anomaly_file}")
        
        return anomalies
    
    def generate_user_behavior_profile(self, user_id: str, days: int = 30) -> Dict[str, Any]:
        """生成用户行为画像"""
        from .storage import AuthStorage
        storage = AuthStorage()
        
        # 获取用户审计日志
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=days)
        
        logs = storage.get_audit_logs(
            user_id=user_id,
            start_time=start_time,
            end_time=end_time,
            limit=5000
        )
        
        profile = {
            "user_id": user_id,
            "report_time": end_time.isoformat(),
            "time_range": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat()
            },
            "total_operations": len(logs),
            "success_rate": 0,
            "most_frequent_actions": [],
            "permission_usage": defaultdict(int),
            "time_distribution": defaultdict(int),
            "risk_score_average": 0,
            "anomalies": []
        }
        
        if not logs:
            return profile
        
        # 分析数据
        success_count = 0
        action_counter = Counter()
        risk_scores = []
        
        for log in logs:
            if log.success:
                success_count += 1
            
            action_counter[log.action] += 1
            
            if log.action.startswith("permission:check:"):
                permission = log.action.replace("permission:check:", "")
                profile["permission_usage"][permission] += 1
                
                risk_score = log.details.get("risk_score", 0)
                risk_scores.append(risk_score)
            
            hour = log.timestamp.hour
            profile["time_distribution"][hour] += 1
        
        # 计算统计数据
        profile["success_rate"] = round(success_count / len(logs) * 100, 2)
        profile["most_frequent_actions"] = action_counter.most_common(5)
        
        if risk_scores:
            profile["risk_score_average"] = round(sum(risk_scores) / len(risk_scores), 2)
        
        # 检测用户异常行为
        user_anomalies = []
        
        # 检测失败率
        failure_rate = 100 - profile["success_rate"]
        if failure_rate > 30:
            user_anomalies.append({
                "type": "high_failure_rate",
                "severity": "medium",
                "description": f"失败率较高: {failure_rate:.2f}%"
            })
        
        # 检测风险分数
        if profile["risk_score_average"] > 0.6:
            user_anomalies.append({
                "type": "high_average_risk",
                "severity": "high",
                "description": f"平均风险分数较高: {profile['risk_score_average']}"
            })
        
        profile["anomalies"] = user_anomalies
        
        # 保存用户画像
        profile_file = os.path.join(self.analytics_dir, f"user_profile_{user_id}_{end_time.strftime('%Y%m%d_%H%M%S')}.json")
        with open(profile_file, 'w', encoding='utf-8') as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)
        
        logger.info(f"用户行为画像生成成功: {profile_file}")
        return profile
    
    def _get_risk_level(self, risk_score: float) -> str:
        """根据风险分数获取风险等级"""
        if risk_score >= 0.8:
            return "critical"
        elif risk_score >= 0.6:
            return "high"
        elif risk_score >= 0.4:
            return "medium"
        else:
            return "low"


# 全局分析实例
_analytics: Optional[PermissionAnalytics] = None


def get_analytics() -> PermissionAnalytics:
    """获取分析实例"""
    global _analytics
    if _analytics is None:
        _analytics = PermissionAnalytics()
    return _analytics

