#!/usr/bin/env python3
"""
数据校验器

负责对从数据源获取的数据进行完整性和格式检查：
1. K线数据检查：日期去重、价格有效性、数量一致性
2. 财务数据检查：字段完整性、数值合理性
"""

from typing import Dict, List, Optional, Any


class DataValidator:
    """数据校验器"""

    def __init__(self):
        pass

    # --------------------------------------------------------
    # K线数据校验
    # --------------------------------------------------------

    def validate_kline(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """校验K线数据

        Returns:
            {"valid": bool, "errors": List[str], "warnings": List[str]}
        """
        errors = []
        warnings = []

        if not data:
            return {"valid": False, "errors": ["数据为空"], "warnings": []}

        # 1. 检查必需字段
        required_fields = ["symbol", "dates", "opens", "highs", "lows", "closes", "volumes"]
        for field in required_fields:
            if field not in data:
                errors.append(f"缺少必需字段: {field}")

        if errors:
            return {"valid": False, "errors": errors, "warnings": warnings}

        # 2. 检查数据长度一致性
        n = len(data["dates"])
        for field in ["opens", "highs", "lows", "closes", "volumes"]:
            if len(data[field]) != n:
                errors.append(f"{field} 长度({len(data[field])})与 dates 长度({n})不一致")

        if errors:
            return {"valid": False, "errors": errors, "warnings": warnings}

        # 3. 检查日期去重
        seen_dates = set()
        duplicate_dates = []
        for d in data["dates"]:
            if d in seen_dates:
                duplicate_dates.append(d)
            seen_dates.add(d)

        if duplicate_dates:
            warnings.append(f"发现重复日期: {len(duplicate_dates)}个")

        # 4. 检查价格有效性
        for i in range(n):
            try:
                o, h, l, c = (
                    float(data["opens"][i]),
                    float(data["highs"][i]),
                    float(data["lows"][i]),
                    float(data["closes"][i])
                )
                # 价格必须 > 0
                if o <= 0 or h <= 0 or l <= 0 or c <= 0:
                    errors.append(f"第{i}条数据价格为0或负数")
                    break
                # high >= 其他价格，low <= 其他价格
                if h < max(o, c) or l > min(o, c):
                    warnings.append(f"第{i}条数据价格关系异常 (H={h}, L={l}, O={o}, C={c})")
            except (ValueError, TypeError, IndexError):
                errors.append(f"第{i}条数据价格无法解析")
                break

        # 5. 检查数据量
        if n == 0:
            errors.append("数据条数为0")
        elif n < 30:
            warnings.append(f"数据条数较少({n})，可能影响分析")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }

    # --------------------------------------------------------
    # 财务数据校验
    # --------------------------------------------------------

    def validate_financial(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """校验财务数据"""
        errors = []
        warnings = []

        if not data:
            return {"valid": False, "errors": ["数据为空"], "warnings": []}

        # 检查必需字段
        if "symbol" not in data:
            errors.append("缺少必需字段: symbol")

        # 检查数值合理性（PE/PB/EPS/ROE 可能为None，但不应该是负数）
        for field in ["pe", "pb", "eps", "roe"]:
            if field in data and data[field] is not None:
                try:
                    val = float(data[field])
                    if val < 0:
                        warnings.append(f"{field} 为负数: {val}")
                except (ValueError, TypeError):
                    pass

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }

    # --------------------------------------------------------
    # 数据去重
    # --------------------------------------------------------

    def deduplicate_kline(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """K线数据按日期去重（保留最后一条）"""
        if not data or "dates" not in data:
            return data

        seen = {}
        n = len(data["dates"])

        for i in range(n):
            seen[data["dates"][i]] = i

        # 按原始顺序保留不重复的数据
        keep_indices = sorted(seen.values())

        new_dates = [data["dates"][i] for i in keep_indices]
        new_opens = [data["opens"][i] for i in keep_indices]
        new_highs = [data["highs"][i] for i in keep_indices]
        new_lows = [data["lows"][i] for i in keep_indices]
        new_closes = [data["closes"][i] for i in keep_indices]
        new_volumes = [data["volumes"][i] for i in keep_indices]

        data["dates"] = new_dates
        data["opens"] = new_opens
        data["highs"] = new_highs
        data["lows"] = new_lows
        data["closes"] = new_closes
        data["volumes"] = new_volumes
        data["count"] = len(new_dates)

        return data


# ============================================================
# 单例模式
# ============================================================

_global_validator: Optional[DataValidator] = None


def get_validator() -> DataValidator:
    """获取数据校验器单例"""
    global _global_validator
    if _global_validator is None:
        _global_validator = DataValidator()
    return _global_validator
