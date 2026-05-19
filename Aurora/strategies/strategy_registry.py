#!/usr/bin/env python3
"""
策略注册表 - 策略分类、属性界定与统一管理
============================================
提供所有策略的元数据注册、分类查询和实例化工厂。

策略分类体系：
  1. 通用型核心策略 (Core) - 全能型主力策略，适用于多种市场环境
  2. 市场类型策略 (MarketRegime) - 针对特定市场状态优化
  3. 专项策略 (Specialized) - 特定交易逻辑或资金管理

市场状态适配：
  - BULL: 上涨趋势市场
  - RANGE: 横盘震荡市场
  - BEAR: 下跌趋势市场
  - ADAPTIVE: 自适应全市场
"""

from typing import Dict, List, Optional, Any, Type
from enum import Enum


class StrategyCategory(str, Enum):
    """策略大类"""
    CORE = "core"              # 通用型核心策略
    MARKET_REGIME = "regime"   # 市场类型策略
    SPECIALIZED = "specialized" # 专项策略


class MarketRegime(str, Enum):
    """市场状态适配"""
    BULL = "bull"              # 上涨趋势
    RANGE = "range"            # 横盘震荡
    BEAR = "bear"              # 下跌趋势
    ADAPTIVE = "adaptive"      # 自适应全市场


class TradingLogic(str, Enum):
    """交易逻辑类型"""
    GRID = "grid"              # 网格交易
    TREND = "trend"            # 趋势跟踪
    RL = "reinforcement"       # 强化学习
    ML = "machine_learning"    # 机器学习
    VALUE = "value"            # 价值投资
    DCA = "dca"                # 定投策略
    MOMENTUM = "momentum"      # 动量策略
    RESONANCE = "resonance"    # 多因子共振
    HYBRID = "hybrid"          # 混合策略


# ============================================================
# 策略注册记录
# ============================================================
STRATEGY_REGISTRY: Dict[str, Dict[str, Any]] = {
    # ==================== 通用型核心策略 (Core) ====================
    "FourierRLStrategy": {
        "name": "FourierRLStrategy",
        "label": "傅里叶强化学习策略",
        "category": StrategyCategory.CORE,
        "regime": MarketRegime.ADAPTIVE,
        "logic": TradingLogic.RL,
        "module": "strategies.fourier_rl_strategy",
        "class_name": "FourierRLStrategy",
        "description": "傅里叶变换+PPO强化学习，全市场自适应，高夏普比率",
        "params": {
            "base_price": {"type": "float", "default": 100.0, "desc": "基准价格"},
            "initial_balance": {"type": "float", "default": 100000, "desc": "初始资金"}
        },
        "status": "active",  # active | beta | archived
        "priority": 1,       # 优先级，数字越小越优先
        "tags": ["RL", "傅里叶", "自适应", "高频"],
        "strengths": ["全市场自适应", "高夏普比率", "强化学习持续优化"],
        "weaknesses": ["计算资源消耗大", "需要较长历史数据训练"],
        "recommended_regime": ["bull", "range", "bear"],
        "performance_rating": 4.5
    },
    "FinalMarketAdaptiveGrid": {
        "name": "FinalMarketAdaptiveGrid",
        "label": "市场自适应网格策略",
        "category": StrategyCategory.CORE,
        "regime": MarketRegime.ADAPTIVE,
        "logic": TradingLogic.HYBRID,
        "module": "strategies.final_market_adaptive",
        "class_name": "FinalMarketAdaptiveGrid",
        "description": "随机森林市场分类+自适应网格，全市场覆盖，稳健收益",
        "params": {
            "base_price": {"type": "float", "default": 100.0, "desc": "基准价格"},
            "initial_balance": {"type": "float", "default": 100000, "desc": "初始资金"}
        },
        "status": "active",
        "priority": 2,
        "tags": ["网格", "随机森林", "自适应", "稳健"],
        "strengths": ["全市场覆盖", "机器学习市场分类", "网格稳健收益"],
        "weaknesses": ["横盘表现最优", "单边趋势可能滞后"],
        "recommended_regime": ["bull", "range", "bear"],
        "performance_rating": 4.3
    },
    "MLRangeGridTrading": {
        "name": "MLRangeGridTrading",
        "label": "机器学习网格交易策略",
        "category": StrategyCategory.CORE,
        "regime": MarketRegime.RANGE,
        "logic": TradingLogic.ML,
        "module": "strategies.ml_range_grid",
        "class_name": "MLRangeGridTrading",
        "description": "随机森林优化网格步长，横盘市场高胜率",
        "params": {
            "base_price": {"type": "float", "default": 100.0, "desc": "基准价格"},
            "initial_balance": {"type": "float", "default": 100000, "desc": "初始资金"}
        },
        "status": "active",
        "priority": 3,
        "tags": ["网格", "机器学习", "横盘", "高频"],
        "strengths": ["横盘市场高胜率", "ML自动优化网格", "交易频率高"],
        "weaknesses": ["单边趋势表现差", "网格参数敏感"],
        "recommended_regime": ["range"],
        "performance_rating": 4.0
    },
    "HuijinValueStrategy": {
        "name": "HuijinValueStrategy",
        "label": "汇金价值AI轮动策略",
        "category": StrategyCategory.CORE,
        "regime": MarketRegime.ADAPTIVE,
        "logic": TradingLogic.VALUE,
        "module": "strategies.huijin_value_strategy",
        "class_name": "HuijinValueStrategy",
        "description": "价值投资+AI轮动，基本面驱动，长期稳健",
        "params": {
            "initial_balance": {"type": "float", "default": 100000, "desc": "初始资金"}
        },
        "status": "active",
        "priority": 4,
        "tags": ["价值投资", "AI轮动", "基本面", "长期"],
        "strengths": ["基本面驱动", "长期稳健", "AI轮动选股"],
        "weaknesses": ["依赖外部数据源", "短期波动较大"],
        "recommended_regime": ["bull", "range"],
        "performance_rating": 4.2
    },

    # ==================== 市场类型策略 (Market Regime) ====================
    "AdaptiveMLStrategy": {
        "name": "AdaptiveMLStrategy",
        "label": "机构终极自适应ML策略",
        "category": StrategyCategory.MARKET_REGIME,
        "regime": MarketRegime.ADAPTIVE,
        "logic": TradingLogic.HYBRID,
        "module": "strategies.adaptive_ml_strategy",
        "class_name": "AdaptiveMLStrategy",
        "description": "横盘赚大钱|上涨赚趋势|下跌防御反转，永不丢失学习成果",
        "params": {
            "initial_balance": {"type": "float", "default": 100000, "desc": "初始资金"}
        },
        "status": "beta",
        "priority": 5,
        "tags": ["自适应", "ML", "机构级", "全市场"],
        "strengths": ["三种市场自动切换", "ML永久记忆", "目标收益明确"],
        "weaknesses": ["复杂度高", "需要大量历史数据"],
        "recommended_regime": ["bull", "range", "bear"],
        "performance_rating": 4.6
    },
    "AdaptiveRangeGridTrading": {
        "name": "AdaptiveRangeGridTrading",
        "label": "自适应横盘网格策略",
        "category": StrategyCategory.MARKET_REGIME,
        "regime": MarketRegime.RANGE,
        "logic": TradingLogic.GRID,
        "module": "strategies.adaptive_range_grid",
        "class_name": "AdaptiveRangeGridTrading",
        "description": "专门针对横盘市场优化，ML动态网格调整",
        "params": {
            "base_price": {"type": "float", "default": 100.0, "desc": "基准价格"},
            "initial_balance": {"type": "float", "default": 100000, "desc": "初始资金"}
        },
        "status": "beta",
        "priority": 6,
        "tags": ["网格", "横盘", "自适应", "ML"],
        "strengths": ["横盘市场优化", "动态网格调整", "50层网格"],
        "weaknesses": ["仅适用于横盘", "趋势市场表现差"],
        "recommended_regime": ["range"],
        "performance_rating": 3.8
    },
    "DownMarketStrategy": {
        "name": "DownMarketStrategy",
        "label": "下跌市场优化策略",
        "category": StrategyCategory.MARKET_REGIME,
        "regime": MarketRegime.BEAR,
        "logic": TradingLogic.MOMENTUM,
        "module": "strategies.downtrend_optimized",
        "class_name": "DownMarketStrategy",
        "description": "超跌反弹+支撑位承接+金字塔仓位控制，五层风控",
        "params": {
            "initial_capital": {"type": "float", "default": 100000, "desc": "初始资金"},
            "max_position_pct": {"type": "float", "default": 0.3, "desc": "最大仓位比例"}
        },
        "status": "beta",
        "priority": 7,
        "tags": ["下跌", "防御", "超跌反弹", "风控"],
        "strengths": ["下跌市场防御", "五层风控", "金字塔加仓"],
        "weaknesses": ["仅适用于下跌", "上涨市场踏空"],
        "recommended_regime": ["bear"],
        "performance_rating": 3.5
    },
    "MultiFactorResonanceStrategy": {
        "name": "MultiFactorResonanceStrategy",
        "label": "多因子共振趋势策略",
        "category": StrategyCategory.MARKET_REGIME,
        "regime": MarketRegime.BULL,
        "logic": TradingLogic.RESONANCE,
        "module": "strategies.multi_factor_resonance",
        "class_name": "MultiFactorResonanceStrategy",
        "description": "趋势跟踪+动量择时+波动率风控+资金管理",
        "params": {
            "initial_balance": {"type": "float", "default": 100000, "desc": "初始资金"},
            "risk_per_trade": {"type": "float", "default": 0.02, "desc": "单笔风险比例"}
        },
        "status": "beta",
        "priority": 8,
        "tags": ["趋势", "动量", "多因子", "共振"],
        "strengths": ["趋势跟踪强", "多因子确认", "资金管理完善"],
        "weaknesses": ["横盘市场频繁假信号", "参数较多"],
        "recommended_regime": ["bull"],
        "performance_rating": 3.7
    },
    "MovingAveragesStrategy": {
        "name": "MovingAveragesStrategy",
        "label": "移动平均线趋势策略",
        "category": StrategyCategory.MARKET_REGIME,
        "regime": MarketRegime.BULL,
        "logic": TradingLogic.TREND,
        "module": "strategies.trend_trading",
        "class_name": "MovingAveragesStrategy",
        "description": "多周期均线交叉，趋势跟踪，经典稳健",
        "params": {
            "short_window": {"type": "int", "default": 10, "desc": "短期均线窗口"},
            "medium_window": {"type": "int", "default": 20, "desc": "中期均线窗口"},
            "long_window": {"type": "int", "default": 30, "desc": "长期均线窗口"}
        },
        "status": "beta",
        "priority": 9,
        "tags": ["均线", "趋势", "经典", "稳健"],
        "strengths": ["简单可靠", "趋势跟踪有效", "参数少"],
        "weaknesses": ["滞后性", "横盘市场表现差"],
        "recommended_regime": ["bull"],
        "performance_rating": 3.3
    },

    # ==================== 专项策略 (Specialized) ====================
    "HighReturnGridTrading": {
        "name": "HighReturnGridTrading",
        "label": "高收益网格交易策略",
        "category": StrategyCategory.SPECIALIZED,
        "regime": MarketRegime.RANGE,
        "logic": TradingLogic.GRID,
        "module": "strategies.high_return_grid",
        "class_name": "HighReturnGridTrading",
        "description": "目标8%收益率+2.0-3.0夏普，分钟级高频交易",
        "params": {
            "initial_balance": {"type": "float", "default": 100000, "desc": "初始资金"},
            "base_price": {"type": "float", "default": 100.0, "desc": "基准价格"}
        },
        "status": "beta",
        "priority": 10,
        "tags": ["网格", "高频", "高收益", "分钟级"],
        "strengths": ["高频交易", "目标收益明确", "网格精细"],
        "weaknesses": ["手续费敏感", "极端行情风险大"],
        "recommended_regime": ["range"],
        "performance_rating": 3.6
    },
    "GridTrading": {
        "name": "GridTrading",
        "label": "经典网格交易策略",
        "category": StrategyCategory.SPECIALIZED,
        "regime": MarketRegime.RANGE,
        "logic": TradingLogic.GRID,
        "module": "strategies.grid_trading",
        "class_name": "GridTrading",
        "description": "经典网格化交易，可配置间距和层数，适合震荡市",
        "params": {
            "base_price": {"type": "float", "default": 100.0, "desc": "基准价格"},
            "grid_spacing": {"type": "float", "default": 0.005, "desc": "网格间距"},
            "grid_levels": {"type": "int", "default": 10, "desc": "网格层数"},
            "initial_balance": {"type": "float", "default": 100000, "desc": "初始资金"}
        },
        "status": "beta",
        "priority": 11,
        "tags": ["网格", "经典", "可配置", "震荡"],
        "strengths": ["简单易懂", "参数可配置", "震荡市有效"],
        "weaknesses": ["趋势市场亏损", "参数需手动优化"],
        "recommended_regime": ["range"],
        "performance_rating": 3.2
    },
    "DCAStrategy": {
        "name": "DCAStrategy",
        "label": "定投(DCA)资金配置策略",
        "category": StrategyCategory.SPECIALIZED,
        "regime": MarketRegime.ADAPTIVE,
        "logic": TradingLogic.DCA,
        "module": "strategies.fund_allocation",
        "class_name": "DCAStrategy",
        "description": "美元成本平均法，定期定额投资，长期稳健增值",
        "params": {
            "initial_balance": {"type": "float", "default": 100000, "desc": "初始资金"},
            "fixed_amount": {"type": "float", "default": 1000, "desc": "固定投资金额"},
            "interval": {"type": "int", "default": 1, "desc": "投资间隔(天)"},
            "adaptive": {"type": "bool", "default": True, "desc": "自适应投资金额"}
        },
        "status": "beta",
        "priority": 12,
        "tags": ["定投", "DCA", "长期", "稳健"],
        "strengths": ["长期稳健", "无需择时", "风险分散"],
        "weaknesses": ["短期收益低", "牛市收益不如其他策略"],
        "recommended_regime": ["bull", "range", "bear"],
        "performance_rating": 3.0
    },
    "PPOTradingAgent": {
        "name": "PPOTradingAgent",
        "label": "PPO深度强化学习策略",
        "category": StrategyCategory.SPECIALIZED,
        "regime": MarketRegime.ADAPTIVE,
        "logic": TradingLogic.RL,
        "module": "strategies.ppo_trading_agent",
        "class_name": "PPOTradingAgent",
        "description": "PPO算法+连续状态空间，20维特征向量，深度学习驱动",
        "params": {
            "initial_capital": {"type": "float", "default": 100000, "desc": "初始资金"}
        },
        "status": "beta",
        "priority": 13,
        "tags": ["PPO", "强化学习", "深度学习", "连续动作"],
        "strengths": ["连续状态空间", "深度学习", "自适应优化"],
        "weaknesses": ["训练时间长", "计算资源需求高"],
        "recommended_regime": ["bull", "range", "bear"],
        "performance_rating": 3.8
    },
    "FinalOptimizedStrategy": {
        "name": "FinalOptimizedStrategy",
        "label": "最终优化综合策略",
        "category": StrategyCategory.SPECIALIZED,
        "regime": MarketRegime.ADAPTIVE,
        "logic": TradingLogic.HYBRID,
        "module": "strategies.final_optimized_strategy",
        "class_name": "FinalOptimizedStrategy",
        "description": "市场分类器+多策略切换，综合优化版",
        "params": {
            "initial_balance": {"type": "float", "default": 100000, "desc": "初始资金"}
        },
        "status": "beta",
        "priority": 14,
        "tags": ["综合", "市场分类", "多策略", "优化"],
        "strengths": ["市场分类准确", "多策略切换", "综合优化"],
        "weaknesses": ["复杂度高", "依赖分类器准确性"],
        "recommended_regime": ["bull", "range", "bear"],
        "performance_rating": 4.0
    },
}


# ============================================================
# 分类索引
# ============================================================
def get_strategies_by_category(category: StrategyCategory) -> List[Dict]:
    """按大类获取策略列表"""
    return [info for info in STRATEGY_REGISTRY.values()
            if info["category"] == category and info["status"] != "archived"]


def get_strategies_by_regime(regime: MarketRegime) -> List[Dict]:
    """按市场状态获取推荐策略"""
    return [info for info in STRATEGY_REGISTRY.values()
            if regime in info["recommended_regime"] and info["status"] != "archived"]


def get_strategies_by_logic(logic: TradingLogic) -> List[Dict]:
    """按交易逻辑获取策略列表"""
    return [info for info in STRATEGY_REGISTRY.values()
            if info["logic"] == logic and info["status"] != "archived"]


def get_active_strategies() -> List[Dict]:
    """获取所有活跃策略"""
    return [info for info in STRATEGY_REGISTRY.values()
            if info["status"] == "active"]


def get_beta_strategies() -> List[Dict]:
    """获取所有Beta策略"""
    return [info for info in STRATEGY_REGISTRY.values()
            if info["status"] == "beta"]


def get_all_strategies() -> List[Dict]:
    """获取所有策略（含beta）"""
    return [info for info in STRATEGY_REGISTRY.values()
            if info["status"] != "archived"]


def get_strategy_info(name: str) -> Optional[Dict]:
    """获取单个策略信息"""
    return STRATEGY_REGISTRY.get(name)


def get_strategy_class(name: str):
    """动态导入并返回策略类"""
    info = STRATEGY_REGISTRY.get(name)
    if not info:
        raise ValueError(f"未知策略: {name}")

    import importlib
    module = importlib.import_module(info["module"])
    return getattr(module, info["class_name"])


def create_strategy(name: str, **kwargs):
    """工厂方法：创建策略实例"""
    cls = get_strategy_class(name)
    info = STRATEGY_REGISTRY.get(name)

    # 填充默认参数
    for param_name, param_info in info["params"].items():
        if param_name not in kwargs:
            kwargs[param_name] = param_info["default"]

    return cls(**kwargs)


def get_strategy_list_api() -> List[Dict]:
    """获取前端API所需的策略列表（含分类分组）"""
    categories = {
        "core": {
            "label": "⭐ 通用型核心策略",
            "description": "全能型主力策略，适用于多种市场环境",
            "strategies": []
        },
        "regime": {
            "label": "📊 市场类型策略",
            "description": "针对特定市场状态（上涨/横盘/下跌）优化",
            "strategies": []
        },
        "specialized": {
            "label": "🔧 专项策略",
            "description": "特定交易逻辑或资金管理策略",
            "strategies": []
        }
    }

    for info in get_all_strategies():
        cat = info["category"].value
        categories[cat]["strategies"].append({
            "name": info["name"],
            "label": info["label"],
            "description": info["description"],
            "regime": info["regime"].value,
            "logic": info["logic"].value,
            "status": info["status"],
            "tags": info["tags"],
            "strengths": info["strengths"],
            "recommended_regime": info["recommended_regime"],
            "performance_rating": info["performance_rating"]
        })

    return {
        "categories": categories,
        "total_count": len(get_all_strategies()),
        "active_count": len(get_active_strategies()),
        "beta_count": len(get_beta_strategies())
    }


# ============================================================
# 市场状态推荐策略
# ============================================================
REGIME_RECOMMENDATIONS = {
    MarketRegime.BULL: {
        "primary": ["MultiFactorResonanceStrategy", "MovingAveragesStrategy"],
        "secondary": ["FourierRLStrategy", "FinalMarketAdaptiveGrid", "HuijinValueStrategy"],
        "avoid": ["DownMarketStrategy", "AdaptiveRangeGridTrading"]
    },
    MarketRegime.RANGE: {
        "primary": ["MLRangeGridTrading", "AdaptiveRangeGridTrading", "HighReturnGridTrading"],
        "secondary": ["GridTrading", "FourierRLStrategy", "FinalMarketAdaptiveGrid"],
        "avoid": ["MovingAveragesStrategy", "MultiFactorResonanceStrategy"]
    },
    MarketRegime.BEAR: {
        "primary": ["DownMarketStrategy"],
        "secondary": ["FourierRLStrategy", "FinalMarketAdaptiveGrid", "DCAStrategy"],
        "avoid": ["HighReturnGridTrading", "MultiFactorResonanceStrategy"]
    },
    MarketRegime.ADAPTIVE: {
        "primary": ["FourierRLStrategy", "FinalMarketAdaptiveGrid", "AdaptiveMLStrategy"],
        "secondary": ["HuijinValueStrategy", "FinalOptimizedStrategy", "PPOTradingAgent"],
        "avoid": []
    }
}


def get_recommended_strategies(regime: MarketRegime) -> Dict[str, List[Dict]]:
    """获取特定市场状态的推荐策略"""
    recs = REGIME_RECOMMENDATIONS.get(regime, REGIME_RECOMMENDATIONS[MarketRegime.ADAPTIVE])
    result = {}
    for key, names in recs.items():
        result[key] = [STRATEGY_REGISTRY[n] for n in names if n in STRATEGY_REGISTRY]
    return result


# ============================================================
# 快速测试
# ============================================================
if __name__ == "__main__":
    import json
    print("=" * 60)
    print("Aurora 策略注册表 - 分类概览")
    print("=" * 60)

    api_data = get_strategy_list_api()
    for cat_key, cat_data in api_data["categories"].items():
        print(f"\n{'─' * 50}")
        print(f"{cat_data['label']} ({len(cat_data['strategies'])}个)")
        print(f"  {cat_data['description']}")
        for s in cat_data["strategies"]:
            status_icon = "✅" if s["status"] == "active" else "🧪"
            print(f"  {status_icon} {s['label']} [{s['name']}]")
            print(f"     市场适配: {s['recommended_regime']} | 评分: {s['performance_rating']}")
            print(f"     标签: {', '.join(s['tags'])}")

    print(f"\n{'=' * 60}")
    print(f"总计: {api_data['total_count']} 个策略")
    print(f"  活跃: {api_data['active_count']} 个")
    print(f"  Beta: {api_data['beta_count']} 个")
    print(f"{'=' * 60}")
