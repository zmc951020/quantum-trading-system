"""
分策略底座严格度配置
根据V4.0过滤对比验证结果，为不同策略适配不同的底座严格度
策略分类：
- 紧底座（low_stars_min=3, hot_score_min=2）：负收益策略，V4.0过滤改善显著
- 中底座（low_stars_min=2, hot_score_min=1）：默认配置
- 松底座（low_stars_min=1, hot_score_min=0）：正收益策略，V4.0过滤导致收益下降
- 无底座（use_v4_filter=False）：高频策略，底座过滤会过滤掉大部分盈利交易

【P0-A 接线修复 2026-10-22】：
- hot_score_min 是旧版（deep_optimizer_v16 3条热启动）参数名，UnifiedBaseFilter（6条热启动）
  不识别该参数；统一底座实际只认 hot_strictness（0.9=6条/0.5=5条/0.3=4条）。
- 此前 strategy_backtest.py 硬编码 hot_strictness=0.3（4条松档），导致分策略 strictness 档位
  无法传导、6条热启动门槛被压死 —— 这是"底座引擎无效果"的根因之一。
- 本修复：为各策略新增 hot_strictness 显式字段（按 strictness 档位映射），
  hot_score_min 保留仅供旧版兼容层使用，不再作为 UnifiedBaseFilter 生效参数。
"""

# 档位 → hot_strictness 映射（统一底座 6 条热启动需满足条数）
STRICTNESS_HOT_MAP = {
    'tight': 0.9,        # 6/6 条
    'medium_tight': 0.7,  # 5/6 条（0.5≤s<0.8 区间取紧端）
    'medium': 0.5,        # 5/6 条
    'loose': 0.3,         # 4/6 条
    'very_loose': 0.1,    # 4/6 条（最低门槛，接近不过滤）
    'none': -1,           # 禁用（配合 use_v4_filter=False）
}

# 分策略底座严格度配置
STRATEGY_BASE_FILTER_CONFIG = {
    # === 紧底座：负收益策略，V4.0过滤改善显著 ===
    'high_return_grid': {
        'use_v4_filter': True,
        'low_stars_min': 3,
        'hot_score_min': 2,
        'hot_strictness': STRICTNESS_HOT_MAP['tight'],
        'strictness': 'tight',
        'reason': 'V4.0过滤收益改善+2.66%，交易减少80.3%',
    },
    'multi_factor_resonance': {
        'use_v4_filter': True,
        'low_stars_min': 3,
        'hot_score_min': 2,
        'hot_strictness': STRICTNESS_HOT_MAP['tight'],
        'strictness': 'tight',
        'reason': 'V4.0过滤收益改善+11.45%，交易减少89.8%',
    },
    'golden_bowl_ice_break': {
        'use_v4_filter': True,
        'low_stars_min': 3,
        'hot_score_min': 2,
        'hot_strictness': STRICTNESS_HOT_MAP['tight'],
        'strictness': 'tight',
        'reason': 'V4.0过滤收益改善+3.50%，交易减少80.4%',
    },
    'shepherd_rotation_strategy': {
        'use_v4_filter': True,
        'low_stars_min': 3,
        'hot_score_min': 2,
        'hot_strictness': STRICTNESS_HOT_MAP['tight'],
        'strictness': 'tight',
        'reason': 'V4.0过滤收益改善+5.00%，交易减少84.3%',
    },
    'vibe_chanlun': {
        'use_v4_filter': True,
        'low_stars_min': 2,
        'hot_score_min': 1,
        'hot_strictness': STRICTNESS_HOT_MAP['medium_tight'],
        'strictness': 'medium_tight',
        'reason': 'V4.0过滤收益改善+4.96%，交易减少69.7%',
    },

    # === 松底座：正收益策略，V4.0过滤导致收益下降 ===
    'adaptive_range_grid': {
        'use_v4_filter': True,
        'low_stars_min': 1,
        'hot_score_min': 0,
        'hot_strictness': STRICTNESS_HOT_MAP['loose'],
        'strictness': 'loose',
        'reason': 'V4.0过滤收益下降-3.77%，原正收益7.13%，用松底座保留盈利交易',
    },
    'bernoulli_coanda_strategy': {
        'use_v4_filter': True,
        'low_stars_min': 1,
        'hot_score_min': 0,
        'hot_strictness': STRICTNESS_HOT_MAP['loose'],
        'strictness': 'loose',
        'reason': 'V4.0过滤收益下降-2.99%，原正收益2.05%，用松底座',
    },
    'special_forces_strategy': {
        'use_v4_filter': True,
        'low_stars_min': 1,
        'hot_score_min': 0,
        'hot_strictness': STRICTNESS_HOT_MAP['loose'],
        'strictness': 'loose',
        'reason': 'V4.0过滤收益下降-2.35%，原正收益0.40%，用松底座',
    },

    # === 高频网格策略：无底座或极松底座 ===
    'ml_range_grid': {
        'use_v4_filter': True,
        'low_stars_min': 1,
        'hot_score_min': 0,
        'hot_strictness': STRICTNESS_HOT_MAP['very_loose'],
        'strictness': 'very_loose',
        'reason': '高频网格策略，底座过滤会过滤掉大部分交易',
    },
    'final_grid_executor': {
        'use_v4_filter': False,
        'low_stars_min': 0,
        'hot_score_min': 0,
        'hot_strictness': STRICTNESS_HOT_MAP['none'],
        'strictness': 'none',
        'reason': '网格执行器，不需要底座过滤',
    },
}

# 默认配置（中底座）
DEFAULT_BASE_FILTER_CONFIG = {
    'use_v4_filter': True,
    'low_stars_min': 2,
    'hot_score_min': 1,
    'hot_strictness': STRICTNESS_HOT_MAP['medium'],
    'strictness': 'medium',
    'reason': '默认中底座配置',
}


def get_strategy_base_filter_config(strategy_name: str) -> dict:
    """获取策略的底座过滤配置"""
    return STRATEGY_BASE_FILTER_CONFIG.get(strategy_name, DEFAULT_BASE_FILTER_CONFIG).copy()


def list_all_configs() -> dict:
    """列出所有策略的底座过滤配置"""
    return {
        'tight': [k for k, v in STRATEGY_BASE_FILTER_CONFIG.items() if v['strictness'] == 'tight'],
        'medium_tight': [k for k, v in STRATEGY_BASE_FILTER_CONFIG.items() if v['strictness'] == 'medium_tight'],
        'medium': ['默认配置'],
        'loose': [k for k, v in STRATEGY_BASE_FILTER_CONFIG.items() if v['strictness'] == 'loose'],
        'very_loose': [k for k, v in STRATEGY_BASE_FILTER_CONFIG.items() if v['strictness'] == 'very_loose'],
        'none': [k for k, v in STRATEGY_BASE_FILTER_CONFIG.items() if v['strictness'] == 'none'],
    }


if __name__ == '__main__':
    print("=" * 70)
    print("分策略底座严格度配置")
    print("=" * 70)

    configs = list_all_configs()
    for strictness, strategies in configs.items():
        print(f"\n【{strictness}】({len(strategies)}个策略)")
        for s in strategies:
            if s == '默认配置':
                print(f"  - {s}: low_stars_min=2, hot_score_min=1")
            else:
                cfg = STRATEGY_BASE_FILTER_CONFIG[s]
                print(f"  - {s}: use_v4_filter={cfg['use_v4_filter']}, "
                      f"low_stars_min={cfg['low_stars_min']}, hot_score_min={cfg['hot_score_min']}")
                print(f"    原因: {cfg['reason']}")
