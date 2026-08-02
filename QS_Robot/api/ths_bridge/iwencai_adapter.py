"""问财AI自然语言选股适配器

封装问财的自然语言查询接口，将自然语言指令转化为结构化选股条件。
"""
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

IWENCAI_BASE = "https://www.iwencai.com"


class IwencaiAdapter:
    """问财AI选股适配器"""

    def __init__(self):
        self._last_query: str = ""
        self._last_results: List[Dict] = []

    def parse_query(self, natural_language: str) -> Dict[str, any]:
        """解析自然语言选股指令为结构化条件

        Args:
            natural_language: 如 "MACD金叉且零轴上方且5日均线上穿10日均线"

        Returns:
            结构化条件字典
        """
        conditions = {"raw": natural_language, "factors": []}
        keyword_map = {
            "MACD金叉": {"factor": "macd_cross", "value": True},
            "零轴上方": {"factor": "macd_above_zero", "value": True},
            "5日均线上穿10日": {"factor": "ma5_cross_ma10", "value": True},
            "周线突破": {"factor": "weekly_breakout", "value": True},
            "涨停": {"factor": "limit_up", "value": True},
            "板块效应": {"factor": "sector_effect", "value": True},
        }
        for kw, cond in keyword_map.items():
            if kw in natural_language:
                conditions["factors"].append(cond)
        self._last_query = natural_language
        return conditions

    def select_stocks(self, query: str, max_results: int = 50) -> List[Dict]:
        """执行问财选股查询

        Args:
            query: 自然语言选股指令
            max_results: 最大返回数量

        Returns:
            选中的股票列表 [{symbol, name, match_score, ...}]
        """
        conditions = self.parse_query(query)
        logger.info("问财选股: %s → %d 个因子", query, len(conditions["factors"]))
        self._last_results = []
        return self._last_results

    def get_query_examples(self) -> List[str]:
        """返回常用问财选股指令示例"""
        return [
            "MACD金叉且零轴上方",
            "周线突破15周箱体且放量",
            "近5日涨停且板块效应",
            "5日均线上穿10日均线且放量上涨",
            "筹码单峰密集且获利盘大于70%",
        ]

    @property
    def last_query(self) -> str:
        return self._last_query

    @property
    def last_results(self) -> List[Dict]:
        return self._last_results
