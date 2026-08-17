# -*- coding: utf-8 -*-
"""输入验证器"""


class InputValidator:
    """输入验证器"""
    @staticmethod
    def sanitize_stock_code(code: str) -> str:
        if not code:
            return ""
        return str(code).strip().replace(" ", "").upper()[:10]

    @staticmethod
    def validate_number(value, min_val: float = None, max_val: float = None) -> float:
        try:
            val = float(value)
            if min_val is not None and val < min_val:
                return min_val
            if max_val is not None and val > max_val:
                return max_val
            return val
        except (ValueError, TypeError):
            return min_val or 0.0


def get_input_validator() -> InputValidator:
    return InputValidator()
