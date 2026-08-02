#!/usr/bin/env python3
"""
Vibe Visualization Protocol (VVP) - 统一可视化数据协议
===========================================================

定义后端模块到前端可视化的统一数据格式。
后端只负责产出 VVP 格式数据，前端根据 chart_type 自动选择渲染方式。

协议版本: 1.0
"""

from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from datetime import datetime
import json


# ============================================================
# VVP Schema 定义
# ============================================================

VVP_VALID_CHART_TYPES = {
    'line', 'bar', 'scatter', 'radar', 'sankey', 'heatmap',
    'pie', 'candlestick', 'gauge', 'treemap', 'funnel', 'table'
}

VVP_VALID_DRILL_DOWN_TYPES = {
    'stock_detail', 'factor_detail', 'trade_detail', 'sector_detail',
    'agent_detail', 'params_detail', 'trace_detail'
}


@dataclass
class VVPDataset:
    """VVP 数据集"""
    label: str
    data: List[Union[float, int, str]]
    color: str = ''
    type: str = ''  # 可选覆盖 chart_type


@dataclass
class VVPChart:
    """VVP 图表定义
    
    后端模块产出此结构，前端渲染器自动解析。
    """
    chart_type: str                       # line|bar|scatter|radar|sankey|heatmap|pie|table
    title: str                            # 图表标题
    data: Dict[str, Any] = field(default_factory=dict)
    # data 结构示例:
    # {
    #     "labels": ["2024-01", "2024-02", ...],
    #     "datasets": [{"label": "收益", "data": [...], "color": "#4ade80"}],
    #     "x_axis": "时间",
    #     "y_axis": "收益率(%)",
    # }
    options: Dict[str, Any] = field(default_factory=dict)
    # options 示例:
    # {
    #     "x_axis": "日期",
    #     "y_axis": "评分",
    #     "unit": "%",
    #     "height": 400,
    #     "show_legend": True,
    # }
    drill_down: Optional[Dict[str, Any]] = None
    # drill_down 示例:
    # {
    #     "type": "stock_detail",
    #     "params": {"symbol": "600519", "date": "2024-01-15"},
    #     "endpoint": "/api/vibe/stock-detail",
    # }
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为前端可消费的 JSON"""
        return {
            "chart_type": self.chart_type,
            "title": self.title,
            "data": self.data,
            "options": self.options,
            "drill_down": self.drill_down,
            "metadata": self.metadata,
        }
    
    def validate(self) -> Dict[str, Any]:
        """校验 VVP 图表的合法性"""
        errors = []
        if self.chart_type not in VVP_VALID_CHART_TYPES:
            errors.append(f"无效的 chart_type: {self.chart_type}，允许: {VVP_VALID_CHART_TYPES}")
        if not self.title:
            errors.append("title 不能为空")
        if self.drill_down:
            dt = self.drill_down.get('type', '')
            if dt and dt not in VVP_VALID_DRILL_DOWN_TYPES:
                errors.append(f"无效的 drill_down type: {dt}，允许: {VVP_VALID_DRILL_DOWN_TYPES}")
        return {"valid": len(errors) == 0, "errors": errors}


# ============================================================
# VVP 工厂方法 - 便捷创建各类图表
# ============================================================

class VVPFactory:
    """VVP 图表工厂"""
    
    @staticmethod
    def line(title: str, labels: List[str], datasets: List[Dict],
             x_axis: str = "", y_axis: str = "", unit: str = "",
             drill_down: Dict = None) -> VVPChart:
        return VVPChart(
            chart_type='line',
            title=title,
            data={'labels': labels, 'datasets': datasets},
            options={'x_axis': x_axis, 'y_axis': y_axis, 'unit': unit},
            drill_down=drill_down,
        )
    
    @staticmethod
    def bar(title: str, labels: List[str], datasets: List[Dict],
            x_axis: str = "", y_axis: str = "", unit: str = "",
            drill_down: Dict = None) -> VVPChart:
        return VVPChart(
            chart_type='bar',
            title=title,
            data={'labels': labels, 'datasets': datasets},
            options={'x_axis': x_axis, 'y_axis': y_axis, 'unit': unit},
            drill_down=drill_down,
        )
    
    @staticmethod
    def scatter(title: str, data: List[Dict],
                x_axis: str = "", y_axis: str = "",
                drill_down: Dict = None) -> VVPChart:
        return VVPChart(
            chart_type='scatter',
            title=title,
            data={'points': data},
            options={'x_axis': x_axis, 'y_axis': y_axis},
            drill_down=drill_down,
        )
    
    @staticmethod
    def radar(title: str, indicators: List[Dict], datasets: List[Dict],
              drill_down: Dict = None) -> VVPChart:
        return VVPChart(
            chart_type='radar',
            title=title,
            data={'indicators': indicators, 'datasets': datasets},
            options={},
            drill_down=drill_down,
        )
    
    @staticmethod
    def sankey(title: str, nodes: List[Dict], links: List[Dict]) -> VVPChart:
        return VVPChart(
            chart_type='sankey',
            title=title,
            data={'nodes': nodes, 'links': links},
            options={},
        )
    
    @staticmethod
    def heatmap(title: str, x_labels: List[str], y_labels: List[str],
                data: List[List[float]], unit: str = "") -> VVPChart:
        return VVPChart(
            chart_type='heatmap',
            title=title,
            data={'x_labels': x_labels, 'y_labels': y_labels, 'values': data},
            options={'unit': unit},
        )
    
    @staticmethod
    def table(title: str, columns: List[str], rows: List[List[Any]],
              drill_down: Dict = None) -> VVPChart:
        return VVPChart(
            chart_type='table',
            title=title,
            data={'columns': columns, 'rows': rows},
            options={},
            drill_down=drill_down,
        )


# ============================================================
# VVP 响应包装器
# ============================================================

@dataclass
class VVPResponse:
    """VVP API 响应格式"""
    success: bool = True
    title: str = ""
    description: str = ""
    charts: List[VVPChart] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "title": self.title,
            "description": self.description,
            "charts": [c.to_dict() for c in self.charts],
            "timestamp": self.timestamp,
        }
    
    def validate(self) -> Dict[str, Any]:
        """校验所有图表"""
        all_errors = []
        for i, chart in enumerate(self.charts):
            result = chart.validate()
            if not result['valid']:
                for err in result['errors']:
                    all_errors.append(f"图表[{i}] {chart.title}: {err}")
        return {"valid": len(all_errors) == 0, "errors": all_errors}


# ============================================================
# 便捷导出的工具函数
# ============================================================

def vvp_response_to_json(vvp: VVPResponse) -> str:
    """将 VVP 响应序列化为 JSON 字符串"""
    return json.dumps(vvp.to_dict(), ensure_ascii=False, indent=2)


def make_convergence_trace_chart(trace_history: List[Dict],
                                  strategy_name: str) -> VVPChart:
    """从收敛轨迹创建折线图"""
    if not trace_history:
        return VVPChart(
            chart_type='line', title=f'{strategy_name} 收敛轨迹',
            data={'labels': [], 'datasets': []},
            options={'x_axis': '迭代', 'y_axis': '最佳评分', 'unit': '分'},
        )
    
    iterations = [t['iteration'] for t in trace_history]
    scores = [t['best_score'] for t in trace_history]
    phases = [t['phase'] for t in trace_history]
    
    return VVPChart(
        chart_type='line',
        title=f'{strategy_name} 收敛轨迹',
        data={
            'labels': iterations,
            'datasets': [
                {'label': '最佳评分', 'data': scores, 'color': '#4ade80'},
                {'label': '阶段', 'data': [{'coarse': 0, 'refined': 1, 'validation': 2}.get(p, 0) for p in phases],
                 'color': '#818cf8', 'type': 'scatter'},
            ],
        },
        options={'x_axis': '迭代次数', 'y_axis': '最佳评分', 'unit': '分'},
    )


def make_agent_vote_chart(agent_votes: List[Dict]) -> VVPChart:
    """从智能体投票创建雷达图"""
    # 按组汇总
    groups = {}
    for v in agent_votes:
        g = v.get('group', 'Unknown')
        if g not in groups:
            groups[g] = {'buy': 0, 'sell': 0, 'hold': 0, 'total': 0}
        groups[g]['total'] += 1
        if '买入' in str(v.get('vote', '')):
            groups[g]['buy'] += 1
        elif '卖出' in str(v.get('vote', '')):
            groups[g]['sell'] += 1
        else:
            groups[g]['hold'] += 1
    
    indicators = [{'name': g, 'max': max(d['total'], 1)} for g, d in groups.items()]
    datasets = [{
        'label': '买入比例',
        'data': [d['buy'] / max(d['total'], 1) * 100 for d in groups.values()],
        'color': '#4ade80',
    }]
    
    return VVPChart(
        chart_type='radar',
        title='智能体投票分布',
        data={'indicators': indicators, 'datasets': datasets},
        options={},
    )