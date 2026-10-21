"""基本面因子 Mixin（15个）"""
import numpy as np

from ._registry import register_factor


class FundamentalFactorsMixin:
    """基本面因子：PE、PB、ROE、ROA、毛利率、净利率、负债率、现金流等"""

    @staticmethod
    @register_factor("pe_factor", "fundamental", "PE因子", "市盈率，越低越好",
                     higher_is_better=False)
    def pe_factor(pe: float) -> np.ndarray:
        if pe <= 0:
            return np.array([20.0])
        if pe < 10:
            return np.array([90.0])
        elif pe < 20:
            return np.array([70.0])
        elif pe < 30:
            return np.array([50.0])
        elif pe < 50:
            return np.array([30.0])
        else:
            return np.array([10.0])

    @staticmethod
    @register_factor("pb_factor", "fundamental", "PB因子", "市净率，越低越好",
                     higher_is_better=False)
    def pb_factor(pb: float) -> np.ndarray:
        if pb <= 0:
            return np.array([20.0])
        if pb < 1:
            return np.array([85.0])
        elif pb < 2:
            return np.array([65.0])
        elif pb < 3:
            return np.array([45.0])
        elif pb < 5:
            return np.array([25.0])
        else:
            return np.array([10.0])

    @staticmethod
    @register_factor("roe_factor", "fundamental", "ROE因子", "净资产收益率")
    def roe_factor(roe: float) -> np.ndarray:
        if roe > 20:
            return np.array([90.0])
        elif roe > 15:
            return np.array([75.0])
        elif roe > 10:
            return np.array([55.0])
        elif roe > 5:
            return np.array([35.0])
        elif roe > 0:
            return np.array([15.0])
        else:
            return np.array([5.0])

    @staticmethod
    @register_factor("roa_factor", "fundamental", "ROA因子", "总资产收益率")
    def roa_factor(roa: float) -> np.ndarray:
        if roa > 10:
            return np.array([90.0])
        elif roa > 5:
            return np.array([70.0])
        elif roa > 2:
            return np.array([50.0])
        elif roa > 0:
            return np.array([30.0])
        else:
            return np.array([10.0])

    @staticmethod
    @register_factor("gross_margin", "fundamental", "毛利率", "销售毛利率")
    def gross_margin(margin: float) -> np.ndarray:
        if margin > 60:
            return np.array([90.0])
        elif margin > 40:
            return np.array([70.0])
        elif margin > 20:
            return np.array([50.0])
        elif margin > 10:
            return np.array([30.0])
        else:
            return np.array([10.0])

    @staticmethod
    @register_factor("net_margin", "fundamental", "净利率", "销售净利率")
    def net_margin(margin: float) -> np.ndarray:
        if margin > 20:
            return np.array([90.0])
        elif margin > 10:
            return np.array([70.0])
        elif margin > 5:
            return np.array([50.0])
        elif margin > 0:
            return np.array([30.0])
        else:
            return np.array([10.0])

    @staticmethod
    @register_factor("debt_ratio", "fundamental", "负债率", "资产负债率，越低越好",
                     higher_is_better=False)
    def debt_ratio(ratio: float) -> np.ndarray:
        if ratio < 30:
            return np.array([85.0])
        elif ratio < 50:
            return np.array([65.0])
        elif ratio < 70:
            return np.array([40.0])
        elif ratio < 85:
            return np.array([20.0])
        else:
            return np.array([5.0])

    @staticmethod
    @register_factor("cash_flow_ratio", "fundamental", "现金流比率", "经营现金流/营业收入")
    def cash_flow_ratio(ratio: float) -> np.ndarray:
        if ratio > 30:
            return np.array([90.0])
        elif ratio > 20:
            return np.array([75.0])
        elif ratio > 10:
            return np.array([55.0])
        elif ratio > 5:
            return np.array([35.0])
        elif ratio > 0:
            return np.array([15.0])
        else:
            return np.array([5.0])

    @staticmethod
    @register_factor("eps_growth", "fundamental", "EPS增长率", "每股收益同比增长率")
    def eps_growth(growth: float) -> np.ndarray:
        if growth > 50:
            return np.array([90.0])
        elif growth > 30:
            return np.array([75.0])
        elif growth > 10:
            return np.array([55.0])
        elif growth > 0:
            return np.array([35.0])
        else:
            return np.array([10.0])

    @staticmethod
    @register_factor("revenue_growth", "fundamental", "营收增长率", "营业收入同比增长率")
    def revenue_growth(growth: float) -> np.ndarray:
        if growth > 30:
            return np.array([90.0])
        elif growth > 20:
            return np.array([75.0])
        elif growth > 10:
            return np.array([55.0])
        elif growth > 0:
            return np.array([35.0])
        else:
            return np.array([10.0])

    @staticmethod
    @register_factor("dividend_yield", "fundamental", "股息率", "股息率")
    def dividend_yield(yld: float) -> np.ndarray:
        if yld > 5:
            return np.array([90.0])
        elif yld > 3:
            return np.array([70.0])
        elif yld > 2:
            return np.array([50.0])
        elif yld > 1:
            return np.array([30.0])
        else:
            return np.array([10.0])

    @staticmethod
    @register_factor("current_ratio", "fundamental", "流动比率", "流动资产/流动负债")
    def current_ratio(cr: float) -> np.ndarray:
        if cr > 2.5:
            return np.array([85.0])
        elif cr > 2.0:
            return np.array([70.0])
        elif cr > 1.5:
            return np.array([55.0])
        elif cr > 1.0:
            return np.array([40.0])
        else:
            return np.array([15.0])

    @staticmethod
    @register_factor("inventory_turnover", "fundamental", "存货周转率", "存货周转率")
    def inventory_turnover(turnover: float) -> np.ndarray:
        if turnover > 10:
            return np.array([90.0])
        elif turnover > 5:
            return np.array([70.0])
        elif turnover > 2:
            return np.array([50.0])
        elif turnover > 1:
            return np.array([30.0])
        else:
            return np.array([10.0])

    @staticmethod
    @register_factor("peg_factor", "fundamental", "PEG因子", "市盈率/增长率，越低越好",
                     higher_is_better=False)
    def peg_factor(peg: float) -> np.ndarray:
        if peg <= 0:
            return np.array([20.0])
        if peg < 0.5:
            return np.array([90.0])
        elif peg < 1.0:
            return np.array([75.0])
        elif peg < 1.5:
            return np.array([50.0])
        elif peg < 2.0:
            return np.array([30.0])
        else:
            return np.array([10.0])

    @staticmethod
    @register_factor("ev_ebitda", "fundamental", "EV/EBITDA", "企业价值/EBITDA，越低越好",
                     higher_is_better=False)
    def ev_ebitda(ratio: float) -> np.ndarray:
        if ratio <= 0:
            return np.array([20.0])
        if ratio < 5:
            return np.array([90.0])
        elif ratio < 10:
            return np.array([70.0])
        elif ratio < 15:
            return np.array([50.0])
        elif ratio < 20:
            return np.array([30.0])
        else:
            return np.array([10.0])