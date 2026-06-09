#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
优化器配置文件
包含所有优化器的详细信息，按重要性排序
"""

# 优化器配置列表，按优先级从高到低排序
OPTIMIZERS = [
    {
        "id": "shepherd_v6",
        "name": "牧羊人V6综合优化器",
        "short_name": "V6综合优化器",
        "description": "系统论金融级自演化框架，五层闭环架构，逻辑与参数完全解耦，五行安全门禁体系，多专家协同评审",
        "detailed_description": """
牧羊人V6综合优化器是系统最高级的优化器，具备以下特性：
- 五层闭环架构：感知层→诊断层→演化层→专家评审层→落地归档层
- 逻辑与参数完全解耦，支持独立演化
- 五行安全门禁体系，防止过拟合和风险失控
- 12专家协同评审机制，确保优化结果质量
- 支持多目标Pareto前沿优化
- 自带Walk-Forward过拟合检测
        """,
        "version": "6.0",
        "priority": 1,
        "recommended": True,
        "category": "综合优化器",
        "file": "shepherd_v6_comprehensive.py",
        "enabled": True,
        "tags": ["深度强化学习", "自演化", "金融级", "多专家", "Pareto优化"]
    },
    {
        "id": "enhanced",
        "name": "增强策略优化器",
        "short_name": "增强优化器",
        "description": "集成多种高级优化算法，包括遗传算法、贝叶斯优化、网格搜索、多目标Pareto优化",
        "detailed_description": """
增强策略优化器是一个全能型优化器：
- 遗传算法（GA）优化：全局搜索最优解
- 贝叶斯优化（BO）：高效参数探索
- 网格搜索 + 随机搜索：基础参数扫描
- 多目标优化（Pareto前沿）：同时优化多个目标
- 优化结果持久化与版本管理
- 实时进度追踪
- 过拟合检测（Walk-Forward分析）
        """,
        "version": "2.0",
        "priority": 2,
        "recommended": True,
        "category": "综合优化器",
        "file": "optimizer_enhanced.py",
        "enabled": True,
        "tags": ["遗传算法", "贝叶斯优化", "Pareto优化", "Walk-Forward"]
    },
    {
        "id": "shepherd_v5",
        "name": "牧羊人V5优化器",
        "short_name": "V5优化器",
        "description": "基于五行理论的策略参数优化器，兼顾收益与风险控制",
        "detailed_description": """
牧羊人V5优化器特性：
- 基于五行相生相克理论
- 多维度参数调优
- 风险门限控制
- 策略稳定性优化
- 参数敏感性分析
        """,
        "version": "5.0",
        "priority": 3,
        "recommended": True,
        "category": "专业优化器",
        "file": "shepherd_five_line_optimizer.py",
        "enabled": True,
        "tags": ["五行理论", "风险控制", "参数优化"]
    },
    {
        "id": "rl_robot",
        "name": "强化学习机器人",
        "short_name": "RL机器人",
        "description": "基于PPO算法的强化学习优化器，自动完成策略回测和参数优化",
        "detailed_description": """
强化学习机器人特性：
- 一键启动回测优化
- PPO深度强化学习算法
- 自动参数调优
- 多周期验证
- 性能可视化
- 策略自我进化
        """,
        "version": "1.5",
        "priority": 4,
        "recommended": True,
        "category": "智能优化器",
        "file": "rl_optimizer.py",
        "enabled": True,
        "tags": ["强化学习", "PPO", "自动优化", "智能体"]
    },
    {
        "id": "smart_param",
        "name": "贝叶斯智能参数优化器",
        "short_name": "贝叶斯优化",
        "description": "基于高斯过程回归的贝叶斯优化器，高效探索参数空间",
        "detailed_description": """
贝叶斯智能参数优化器特性：
- 高斯过程回归（GPR）建模
- 采集函数优化（EI/UCB/PI）
- 单例模式，全局唯一实例
- 默认关闭，按需启用
- 支持多目标Pareto优化
- 参数空间自动探索
        """,
        "version": "1.2",
        "priority": 5,
        "recommended": False,
        "category": "专业优化器",
        "file": "utils/smart_param_optimizer.py",
        "enabled": True,
        "tags": ["贝叶斯优化", "高斯过程", "参数探索"]
    },
    {
        "id": "gyro_v7",
        "name": "Gyro V7优化器",
        "short_name": "Gyro优化",
        "description": "基于陀螺仪原理的策略优化器，专门针对趋势跟踪策略",
        "detailed_description": """
Gyro V7优化器特性：
- 陀螺仪物理原理类比
- 趋势跟踪策略专用
- 进动效应参数优化
- 多时间周期适配
- 自适应参数调整
        """,
        "version": "7.0",
        "priority": 6,
        "recommended": False,
        "category": "专用优化器",
        "file": "experiments/archive/gyro_minute_strategy_v7_optimized.py",
        "enabled": True,
        "tags": ["趋势跟踪", "陀螺仪", "自适应"]
    },
    {
        "id": "genetic",
        "name": "遗传算法优化器",
        "short_name": "遗传优化",
        "description": "基于进化算法的参数优化器，全局搜索最优解",
        "detailed_description": """
遗传算法优化器特性：
- 达尔文进化理论
- 选择、交叉、变异操作
- 精英保留机制
- 自适应变异率
- 多参数同时优化
        """,
        "version": "1.0",
        "priority": 7,
        "recommended": False,
        "category": "基础优化器",
        "file": "genetic_optimizer.py",
        "enabled": False,
        "tags": ["遗传算法", "进化策略", "全局搜索"]
    },
    {
        "id": "grid_search",
        "name": "网格搜索优化器",
        "short_name": "网格搜索",
        "description": "暴力网格搜索优化器，遍历所有参数组合",
        "detailed_description": """
网格搜索优化器特性：
- 参数网格穷举
- 全面但计算量大
- 适合小范围参数搜索
- 可作为基准对比
        """,
        "version": "1.0",
        "priority": 8,
        "recommended": False,
        "category": "基础优化器",
        "file": "grid_search_optimizer.py",
        "enabled": False,
        "tags": ["网格搜索", "穷举法", "基准测试"]
    },
    {
        "id": "random_search",
        "name": "随机搜索优化器",
        "short_name": "随机搜索",
        "description": "随机参数采样优化器，比网格搜索更高效",
        "detailed_description": """
随机搜索优化器特性：
- 随机参数采样
- 比网格搜索计算量小
- 适合高维参数空间
- 可配合其他优化器使用
        """,
        "version": "1.0",
        "priority": 9,
        "recommended": False,
        "category": "基础优化器",
        "file": "random_search_optimizer.py",
        "enabled": False,
        "tags": ["随机搜索", "采样", "高维优化"]
    },
    {
        "id": "hmm_grid",
        "name": "HMM网格优化器",
        "short_name": "HMM优化",
        "description": "隐马尔可夫模型参数优化器，专门针对市场状态识别",
        "detailed_description": """
HMM网格优化器特性：
- 隐马尔可夫模型（HMM）
- 市场状态识别
- 状态转移矩阵优化
- 观测概率分布优化
        """,
        "version": "1.0",
        "priority": 10,
        "recommended": False,
        "category": "专用优化器",
        "file": "hmm_optimizer.py",
        "enabled": False,
        "tags": ["HMM", "市场状态", "概率模型"]
    },
    {
        "id": "quantum",
        "name": "量子优化器",
        "short_name": "量子优化",
        "description": "量子计算启发的优化器，用于复杂优化问题",
        "detailed_description": """
量子优化器特性：
- 量子退火原理
- 叠加态探索
- 隧穿效应逃离局部最优
- 适合组合优化问题
        """,
        "version": "0.5",
        "priority": 11,
        "recommended": False,
        "category": "实验优化器",
        "file": "quantum_optimizer.py",
        "enabled": False,
        "tags": ["量子计算", "量子退火", "实验性"]
    }
]


def get_optimizers(enabled_only: bool = False) -> list:
    """
    获取优化器列表
    
    Args:
        enabled_only: 是否只返回启用的优化器
    
    Returns:
        优化器列表
    """
    if enabled_only:
        return [opt for opt in OPTIMIZERS if opt["enabled"]]
    return OPTIMIZERS


def get_optimizer_by_id(opt_id: str) -> dict:
    """
    根据ID获取优化器
    
    Args:
        opt_id: 优化器ID
    
    Returns:
        优化器配置字典，未找到返回None
    """
    for opt in OPTIMIZERS:
        if opt["id"] == opt_id:
            return opt
    return None


def toggle_optimizer(opt_id: str, enabled: bool = None) -> bool:
    """
    切换或设置优化器启用状态
    
    Args:
        opt_id: 优化器ID
        enabled: 可选，指定启用状态，True启用，False禁用，None则切换当前状态
    
    Returns:
        是否成功切换
    """
    opt = get_optimizer_by_id(opt_id)
    if opt:
        if enabled is not None:
            opt["enabled"] = enabled
        else:
            opt["enabled"] = not opt["enabled"]
        return True
    return False


def add_optimizer(opt_config: dict) -> bool:
    """
    添加新优化器
    
    Args:
        opt_config: 优化器配置字典
    
    Returns:
        是否成功添加
    """
    # 检查ID是否已存在
    if get_optimizer_by_id(opt_config.get("id")):
        return False
    OPTIMIZERS.append(opt_config)
    # 重新按优先级排序
    OPTIMIZERS.sort(key=lambda x: x["priority"])
    return True


def delete_optimizer(opt_id: str) -> bool:
    """
    删除优化器
    
    Args:
        opt_id: 优化器ID
    
    Returns:
        是否成功删除
    """
    opt = get_optimizer_by_id(opt_id)
    if opt:
        OPTIMIZERS.remove(opt)
        return True
    return False
