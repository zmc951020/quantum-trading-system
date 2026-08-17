# -*- coding: utf-8 -*-
"""数据脱敏器"""


class DataMasker:
    """数据脱敏器"""
    @staticmethod
    def mask_trade_data(data: dict) -> dict:
        if not isinstance(data, dict):
            return data
        masked = dict(data)
        if 'order_id' in masked and isinstance(masked['order_id'], str) and len(masked['order_id']) > 4:
            masked['order_id'] = "***" + masked['order_id'][-4:]
        return masked


def get_data_masker() -> DataMasker:
    return DataMasker()
