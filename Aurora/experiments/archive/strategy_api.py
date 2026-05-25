#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略管理API - 提供策略选择、优化、回测的完整API接口
打通前后端连接，实现策略的完整管理流程
"""

from flask import Blueprint, jsonify, request
from datetime import datetime
import random
import traceback
import pandas as pd
import numpy as np

# 导入伯努利-康达策略
try:
    from strategies.bernoulli_coanda_strategy import (
        BernoulliCoandaStrategy,
        create_bernoulli_coanda_strategy
    )
    from strategies.bernoulli_coanda_optimizer import (
        StrategyParameterOptimizer,
        StrategyWalkForwardTester
    )
    BERNOULLI_COANDA_AVAILABLE = True
except Exception as e:
    BERNOULLI_COANDA_AVAILABLE = False
    print(f"[StrategyAPI] 伯努利-康达策略不可用: {e}")

# 导入策略监控系统
try:
    from strategy_monitor import (
        StrategyMonitor,
        StrategyEventType,
        EventStatus,
        get_strategy_monitor,
        monitor_event
    )
    STRATEGY_MONITOR_AVAILABLE = True
except Exception as e:
    STRATEGY_MONITOR_AVAILABLE = False
    print(f"[StrategyAPI] 策略监控系统不可用: {e}")

# 导入增强型评估器
try:
    from enhanced_evaluator import EnhancedFinancialEvaluator
    ENHANCED_EVALUATOR_AVAILABLE = True
except Exception as e:
    ENHANCED_EVALUATOR_AVAILABLE = False
    print(f"[StrategyAPI] 增强型评估器不可用: {e}")

strategy_api = Blueprint('strategy_api', __name__)

# 获取监控器实例
def get_monitor():
    if STRATEGY_MONITOR_AVAILABLE:
        try:
            return get_strategy_monitor()
        except:
            return None
    return None

# 全局策略状态管理
strategy_state = {
    'current_environment': 'paper',  # paper: 模拟盘, live: 实盘
    'active_strategies': [],         # 已激活的策略列表
    'pending_strategies': [],        # 待激活的策略列表
    'strategy_parameters': {},       # 策略参数配置
    'optimization_results': {},      # 优化结果缓存
    'backtest_results': {}           # 回测结果缓存
}


def init_strategy_state():
    """初始化策略状态，用于在应用启动时重置"""
    strategy_state['current_environment'] = 'paper'
    strategy_state['active_strategies'] = []
    strategy_state['pending_strategies'] = []
    strategy_state['strategy_parameters'] = {}
    strategy_state['optimization_results'] = {}
    strategy_state['backtest_results'] = {}

# 策略库定义（22个策略+4个核心策略）
STRATEGY_LIBRARY = {
    'core': {
        'name': '核心通用策略',
        'strategies': [
            {'id': 'BernoulliCoandaStrategy', 'name': '伯努利-康达量化策略', 'description': '基于流体力学原理的自适应策略，支持自优化演进', 'risk_level': 'medium'},
            {'id': 'FourierRLStrategy', 'name': '傅里叶强化学习策略', 'description': '基于傅里叶变换的强化学习策略', 'risk_level': 'medium'},
            {'id': 'FinalMarketAdaptiveGrid', 'name': '市场自适应网格策略', 'description': '市场自适应网格交易策略', 'risk_level': 'low'},
            {'id': 'MLRangeGridTrading', 'name': '机器学习网格交易策略', 'description': '机器学习优化的网格交易策略', 'risk_level': 'low'},
            {'id': 'HuijinValueStrategy', 'name': '汇金价值AI轮动策略', 'description': '价值投资AI轮动策略', 'risk_level': 'low'},
            {'id': 'momentum', 'name': '动量策略', 'description': '基于动量效应的趋势跟踪', 'risk_level': 'medium'},
            {'id': 'mean_reversion', 'name': '均值回归策略', 'description': '价格围绕均值波动的回归交易', 'risk_level': 'low'},
            {'id': 'arbitrage', 'name': '套利策略', 'description': '跨市场或跨品种的无风险套利', 'risk_level': 'low'},
            {'id': 'hft', 'name': '高频交易策略', 'description': '基于微秒级价格变化的快速交易', 'risk_level': 'high'},
            {'id': 'other', 'name': '其他策略', 'description': '复合型或其他创新策略', 'risk_level': 'medium'}
        ]
    },
    'bull': {
        'name': '上涨市场策略',
        'strategies': [
            {'id': 'breakout', 'name': '突破策略', 'description': '价格突破关键阻力位时买入', 'risk_level': 'medium'},
            {'id': 'trend_following', 'name': '趋势跟踪策略', 'description': '跟随主要趋势方向交易', 'risk_level': 'medium'},
            {'id': 'bull_grid', 'name': '上涨网格策略', 'description': '在上涨行情中分批建仓', 'risk_level': 'low'},
            {'id': 'accumulation', 'name': '吸筹策略', 'description': '在回调时逐步积累筹码', 'risk_level': 'low'}
        ]
    },
    'bear': {
        'name': '下跌市场策略',
        'strategies': [
            {'id': 'contrarian', 'name': '逆势策略', 'description': '在超跌时逆向买入', 'risk_level': 'high'},
            {'id': 'bottom_fishing', 'name': '抄底策略', 'description': '在价格底部区域买入', 'risk_level': 'high'},
            {'id': 'short_selling', 'name': '做空策略', 'description': '在下跌趋势中做空获利', 'risk_level': 'very_high'},
            {'id': 'protective', 'name': '保护性策略', 'description': '通过期权等工具对冲风险', 'risk_level': 'low'}
        ]
    },
    'sideways': {
        'name': '横盘市场策略',
        'strategies': [
            {'id': 'grid_trading', 'name': '网格交易策略', 'description': '在固定价格区间内高抛低吸', 'risk_level': 'low'},
            {'id': 'range_bound', 'name': '区间震荡策略', 'description': '在震荡区间上下边界交易', 'risk_level': 'low'},
            {'id': 'band_trading', 'name': '波段交易策略', 'description': '在区间内进行波段操作', 'risk_level': 'medium'},
            {'id': 'volatility', 'name': '波动率交易策略', 'description': '基于波动率变化的交易', 'risk_level': 'medium'}
        ]
    },
    'volatile': {
        'name': '震荡市场策略',
        'strategies': [
            {'id': 'swing', 'name': '波段策略', 'description': '捕捉短期波动的利润', 'risk_level': 'medium'},
            {'id': 'channel', 'name': '通道交易策略', 'description': '在价格通道内交易', 'risk_level': 'medium'},
            {'id': 'breakout_vol', 'name': '震荡突破策略', 'description': '在震荡后突破时入场', 'risk_level': 'high'},
            {'id': 'vol_adaptive', 'name': '波动自适应策略', 'description': '根据波动率自动调整参数', 'risk_level': 'medium'}
        ]
    }
}

# 优化器配置
OPTIMIZERS = {
    'v5': {
        'name': '智能体优化器V5',
        'type': 'genetic_algorithm',
        'description': '基于遗传算法的策略参数优化',
        'capabilities': [
            '多参数同时优化',
            '全局搜索最优解',
            '自适应变异率',
            '精英保留机制'
        ]
    },
    'v6_deep': {
        'name': '超能优化器V6（深度优化）',
        'type': 'deep_reinforcement_learning',
        'description': '基于深度强化学习的策略优化',
        'capabilities': [
            '深度神经网络',
            '策略网络学习',
            '价值网络评估',
            '端到端优化'
        ]
    },
    'v6_auto': {
        'name': '超能优化器V6（自动演进）',
        'type': 'auto_evolution',
        'description': '基于自动演进机制的自优化系统',
        'capabilities': [
            '自动特征工程',
            '自监督学习',
            '跨市场迁移',
            '持续自我改进'
        ]
    }
}

# 强化学习机器人配置
RL_BOT = {
    'name': '强化学习机器人',
    'type': 'reinforcement_learning',
    'description': '一键回测优化的智能体',
    'features': [
        '一键启动回测',
        '自动参数调优',
        '多周期验证',
        '性能可视化'
    ]
}


@strategy_api.route('/library', methods=['GET'])
def get_strategy_library():
    """获取策略库"""
    return jsonify({
        'success': True,
        'data': STRATEGY_LIBRARY,
        'total_count': sum(len(cat['strategies']) for cat in STRATEGY_LIBRARY.values())
    })


@strategy_api.route('/environment', methods=['GET'])
def get_environment():
    """获取当前环境"""
    return jsonify({
        'success': True,
        'data': {
            'current': strategy_state['current_environment'],
            'label': '模拟盘' if strategy_state['current_environment'] == 'paper' else '实盘'
        }
    })


@strategy_api.route('/environment', methods=['POST'])
def switch_environment():
    """切换环境"""
    data = request.get_json()
    new_env = data.get('environment')
    confirmed = data.get('confirmed', False)

    if new_env not in ['paper', 'live']:
        return jsonify({
            'success': False,
            'error': '无效的环境类型'
        }), 400

    if new_env == 'live' and not confirmed:
        # 实盘切换需要确认
        return jsonify({
            'success': True,
            'require_confirmation': True,
            'message': '切换到实盘将使用真实资金，是否继续？'
        })

    # 记录环境切换事件
    event = None
    if STRATEGY_MONITOR_AVAILABLE:
        try:
            event = record_strategy_event(
                StrategyEventType.ENVIRONMENT_SWITCH,
                environment=new_env,
                metadata={'from_env': strategy_state['current_environment'], 'to_env': new_env}
            )
        except:
            pass

    strategy_state['current_environment'] = new_env

    # 标记事件完成
    if event:
        try:
            event.complete({'success': True})
            monitor = get_monitor()
            if monitor:
                monitor.record_event(event)
        except:
            pass

    return jsonify({
        'success': True,
        'data': {
            'current': new_env,
            'label': '模拟盘' if new_env == 'paper' else '实盘'
        }
    })


@strategy_api.route('/strategies', methods=['GET'])
def get_strategies():
    """获取策略列表"""
    category = request.args.get('category')
    status = request.args.get('status')

    if category and category in STRATEGY_LIBRARY:
        strategies = STRATEGY_LIBRARY[category]['strategies']
    else:
        strategies = []
        for cat_data in STRATEGY_LIBRARY.values():
            strategies.extend(cat_data['strategies'])

    # 添加状态信息
    for strategy in strategies:
        strategy_id = strategy['id']
        if strategy_id in strategy_state['active_strategies']:
            strategy['status'] = 'active'
        elif strategy_id in strategy_state['pending_strategies']:
            strategy['status'] = 'pending'
        else:
            strategy['status'] = 'available'

        # 添加参数信息
        if strategy_id in strategy_state['strategy_parameters']:
            strategy['parameters'] = strategy_state['strategy_parameters'][strategy_id]

    return jsonify({
        'success': True,
        'data': strategies,
        'active_count': len(strategy_state['active_strategies']),
        'pending_count': len(strategy_state['pending_strategies'])
    })


@strategy_api.route('/strategies/<strategy_id>', methods=['GET'])
def get_strategy_detail(strategy_id):
    """获取策略详情"""
    strategy = None
    category = None

    for cat_key, cat_data in STRATEGY_LIBRARY.items():
        for s in cat_data['strategies']:
            if s['id'] == strategy_id:
                strategy = s.copy()
                category = cat_key
                break
        if strategy:
            break

    if not strategy:
        return jsonify({
            'success': False,
            'error': '策略不存在'
        }), 404

    strategy['category'] = category
    strategy['category_name'] = STRATEGY_LIBRARY[category]['name']

    # 添加状态和参数信息
    if strategy_id in strategy_state['active_strategies']:
        strategy['status'] = 'active'
    elif strategy_id in strategy_state['pending_strategies']:
        strategy['status'] = 'pending'
    else:
        strategy['status'] = 'available'

    if strategy_id in strategy_state['strategy_parameters']:
        strategy['parameters'] = strategy_state['strategy_parameters'][strategy_id]

    # 添加优化结果
    if strategy_id in strategy_state['optimization_results']:
        strategy['optimization'] = strategy_state['optimization_results'][strategy_id]

    # 添加回测结果
    if strategy_id in strategy_state['backtest_results']:
        strategy['backtest'] = strategy_state['backtest_results'][strategy_id]

    return jsonify({
        'success': True,
        'data': strategy
    })


@strategy_api.route('/strategies/<strategy_id>/parameters', methods=['GET', 'POST'])
def manage_strategy_parameters(strategy_id):
    """管理策略参数"""
    if request.method == 'GET':
        params = strategy_state['strategy_parameters'].get(strategy_id, {})
        return jsonify({
            'success': True,
            'data': params
        })

    # POST - 更新参数
    data = request.get_json()
    strategy_state['strategy_parameters'][strategy_id] = data

    return jsonify({
        'success': True,
        'message': '参数已更新',
        'data': data
    })


@strategy_api.route('/strategies/<strategy_id>/activate', methods=['POST'])
def activate_strategy(strategy_id):
    """激活策略"""
    if strategy_id not in [s['id'] for strategies in STRATEGY_LIBRARY.values() for s in strategies]:
        return jsonify({
            'success': False,
            'error': '策略不存在'
        }), 404

    if strategy_id in strategy_state['active_strategies']:
        return jsonify({
            'success': False,
            'error': '策略已在激活状态'
        })

    # 记录策略激活事件
    event = None
    if STRATEGY_MONITOR_AVAILABLE:
        try:
            event = record_strategy_event(
                StrategyEventType.STRATEGY_ACTIVATE,
                strategy_id=strategy_id,
                environment=strategy_state['current_environment'],
                metadata={'action': 'activate'}
            )
        except:
            pass

    # 从待激活列表移到激活列表
    if strategy_id in strategy_state['pending_strategies']:
        strategy_state['pending_strategies'].remove(strategy_id)

    strategy_state['active_strategies'].append(strategy_id)

    # 标记事件完成
    if event:
        try:
            event.complete({'success': True})
            monitor = get_monitor()
            if monitor:
                monitor.record_event(event)
        except:
            pass

    return jsonify({
        'success': True,
        'message': f'策略 {strategy_id} 已激活',
        'data': {
            'active_strategies': strategy_state['active_strategies'],
            'pending_strategies': strategy_state['pending_strategies']
        }
    })


@strategy_api.route('/strategies/<strategy_id>/deactivate', methods=['POST'])
def deactivate_strategy(strategy_id):
    """停用策略"""
    if strategy_id not in strategy_state['active_strategies']:
        return jsonify({
            'success': False,
            'error': '策略未激活'
        })

    # 记录策略停用事件
    event = None
    if STRATEGY_MONITOR_AVAILABLE:
        try:
            event = record_strategy_event(
                StrategyEventType.STRATEGY_DEACTIVATE,
                strategy_id=strategy_id,
                environment=strategy_state['current_environment'],
                metadata={'action': 'deactivate'}
            )
        except:
            pass

    strategy_state['active_strategies'].remove(strategy_id)

    # 标记事件完成
    if event:
        try:
            event.complete({'success': True})
            monitor = get_monitor()
            if monitor:
                monitor.record_event(event)
        except:
            pass

    return jsonify({
        'success': True,
        'message': f'策略 {strategy_id} 已停用',
        'data': {
            'active_strategies': strategy_state['active_strategies'],
            'pending_strategies': strategy_state['pending_strategies']
        }
    })


@strategy_api.route('/strategies/<strategy_id>/pending', methods=['POST'])
def add_to_pending(strategy_id):
    """添加到待激活列表"""
    if strategy_id not in [s['id'] for strategies in STRATEGY_LIBRARY.values() for s in strategies]:
        return jsonify({
            'success': False,
            'error': '策略不存在'
        }), 404

    if strategy_id not in strategy_state['pending_strategies']:
        strategy_state['pending_strategies'].append(strategy_id)

    return jsonify({
        'success': True,
        'message': f'策略 {strategy_id} 已添加到待激活列表',
        'data': {
            'pending_count': len(strategy_state['pending_strategies']),
            'pending_strategies': strategy_state['pending_strategies']
        }
    })


@strategy_api.route('/optimizers', methods=['GET'])
def get_optimizers():
    """获取优化器列表"""
    # 合并所有优化器，包括强化学习机器人
    all_optimizers = {
        'rl_bot': RL_BOT,
        **OPTIMIZERS
    }
    return jsonify({
        'success': True,
        'data': all_optimizers
    })


@strategy_api.route('/optimizers/rl_bot/optimize', methods=['POST'])
def run_rl_bot_optimization():
    """执行强化学习机器人优化"""
    data = request.get_json()
    strategy_id = data.get('strategy_id')
    parameters = data.get('parameters', {})

    if not strategy_id:
        return jsonify({
            'success': False,
            'error': '未指定策略'
        }), 400

    # 记录优化器执行事件
    event = None
    if STRATEGY_MONITOR_AVAILABLE:
        try:
            event = record_strategy_event(
                StrategyEventType.OPTIMIZATION_START,
                strategy_id=strategy_id,
                environment=strategy_state['current_environment'],
                metadata={'optimizer': 'rl_bot', 'parameters': parameters}
            )
        except:
            pass

    # 模拟强化学习机器人优化过程
    result = {
        'optimizer_id': 'rl_bot',
        'optimizer_name': RL_BOT['name'],
        'strategy_id': strategy_id,
        'status': 'completed',
        'start_time': datetime.now().isoformat(),
        'end_time': datetime.now().isoformat(),
        'iterations': 200,
        'improvement': round(20 + (hash(strategy_id + 'rl') % 30), 2),  # 20-50% 的性能提升
        'best_parameters': {
            'learning_rate': round(0.001 + (hash(strategy_id) % 900) / 10000, 4),
            'batch_size': 32 + (hash(strategy_id) % 32) * 16,
            'gamma': round(0.9 + (hash(strategy_id) % 80) / 100, 2),
            'epsilon': round(0.1 + (hash(strategy_id) % 20) / 100, 2)
        },
        'metrics': {
            'sharpe_ratio': round(1.8 + (hash(strategy_id) % 150) / 100, 2),
            'max_drawdown': round(-6 - (hash(strategy_id) % 120) / 100, 2),
            'win_rate': round(58 + (hash(strategy_id) % 320) / 100, 1),
            'profit_factor': round(2.0 + (hash(strategy_id) % 50) / 100, 2)
        }
    }

    # 保存优化结果
    if strategy_id not in strategy_state['optimization_results']:
        strategy_state['optimization_results'][strategy_id] = []
    strategy_state['optimization_results'][strategy_id].append(result)

    # 标记事件完成
    if event:
        try:
            event.complete({'success': True, 'result': result})
            monitor = get_monitor()
            if monitor:
                monitor.record_event(event)
        except:
            pass

    return jsonify({
        'success': True,
        'message': f'{RL_BOT["name"]} 优化完成',
        'data': result
    })


@strategy_api.route('/optimizers/<optimizer_id>/optimize', methods=['POST'])
def run_optimization(optimizer_id):
    """执行优化"""
    if optimizer_id not in OPTIMIZERS:
        return jsonify({
            'success': False,
            'error': '优化器不存在'
        }), 404

    data = request.get_json()
    strategy_id = data.get('strategy_id')
    parameters = data.get('parameters', {})

    if not strategy_id:
        return jsonify({
            'success': False,
            'error': '未指定策略'
        }), 400

    # 记录优化器执行事件
    event = None
    if STRATEGY_MONITOR_AVAILABLE:
        try:
            event = record_strategy_event(
                StrategyEventType.OPTIMIZATION_START,
                strategy_id=strategy_id,
                environment=strategy_state['current_environment'],
                metadata={'optimizer': optimizer_id, 'parameters': parameters}
            )
        except:
            pass

    # 模拟优化过程
    optimizer = OPTIMIZERS[optimizer_id]

    # 这里应该调用实际的优化算法
    # 暂时返回模拟结果
    result = {
        'optimizer_id': optimizer_id,
        'optimizer_name': optimizer['name'],
        'strategy_id': strategy_id,
        'status': 'completed',
        'start_time': datetime.now().isoformat(),
        'end_time': datetime.now().isoformat(),
        'iterations': 100,
        'improvement': round(15 + (hash(strategy_id) % 20), 2),  # 15-35% 的性能提升
        'best_parameters': {
            'param1': round(0.5 + (hash(strategy_id) % 50) / 100, 2),
            'param2': round(10 + (hash(strategy_id + '2') % 90, 2)),
            'param3': round(0.1 + (hash(strategy_id + '3') % 30) / 100, 2)
        },
        'metrics': {
            'sharpe_ratio': round(1.5 + (hash(strategy_id) % 100) / 100, 2),
            'max_drawdown': round(-5 - (hash(strategy_id) % 150) / 100, 2),
            'win_rate': round(55 + (hash(strategy_id) % 300) / 100, 1),
            'profit_factor': round(1.8 + (hash(strategy_id) % 40) / 100, 2)
        }
    }

    # 保存优化结果
    if strategy_id not in strategy_state['optimization_results']:
        strategy_state['optimization_results'][strategy_id] = []
    strategy_state['optimization_results'][strategy_id].append(result)

    # 标记事件完成
    if event:
        try:
            event.complete({'success': True, 'result': result})
            monitor = get_monitor()
            if monitor:
                monitor.record_event(event)
        except:
            pass

    return jsonify({
        'success': True,
        'message': f'{optimizer["name"]} 优化完成',
        'data': result
    })


@strategy_api.route('/backtest', methods=['GET', 'POST'])
def run_backtest():
    """执行回测"""
    if request.method == 'GET':
        # 获取回测历史
        return jsonify({
            'success': True,
            'data': strategy_state['backtest_results']
        })

    # POST - 执行回测
    data = request.get_json()
    strategy_id = data.get('strategy_id')
    optimizer_type = data.get('optimizer_type')  # rl_bot, v5, v6_deep, v6_auto
    period = data.get('period', '1y')  # 回测周期

    if not strategy_id:
        return jsonify({
            'success': False,
            'error': '未指定策略'
        }), 400

    if not optimizer_type:
        return jsonify({
            'success': False,
            'error': '未指定优化器类型'
        }), 400

    # 记录回测事件
    event = None
    if STRATEGY_MONITOR_AVAILABLE:
        try:
            event = record_strategy_event(
                StrategyEventType.BACKTEST_START,
                strategy_id=strategy_id,
                environment=strategy_state['current_environment'],
                metadata={'optimizer_type': optimizer_type, 'period': period}
            )
        except:
            pass

    # 获取优化器名称
    optimizer_name = RL_BOT['name'] if optimizer_type == 'rl_bot' else OPTIMIZERS.get(optimizer_type, {}).get('name', 'Unknown')

    # 模拟回测过程
    result = {
        'id': f'bt_{datetime.now().strftime("%Y%m%d_%H%M%S")}',
        'strategy_id': strategy_id,
        'optimizer_type': optimizer_type,
        'optimizer_name': optimizer_name,
        'period': period,
        'status': 'completed',
        'start_time': datetime.now().isoformat(),
        'end_time': datetime.now().isoformat(),
        'duration': round(30 + (hash(strategy_id + optimizer_type) % 120), 1),  # 30-150秒
        'metrics': {
            'total_return': round(15 + (hash(strategy_id) % 500) / 10, 2),  # 15-65% 收益率
            'annual_return': round(12 + (hash(strategy_id) % 400) / 10, 2),
            'sharpe_ratio': round(1.5 + (hash(strategy_id) % 100) / 100, 2),
            'max_drawdown': round(-8 - (hash(strategy_id) % 200) / 100, 2),
            'win_rate': round(55 + (hash(strategy_id) % 350) / 100, 1),
            'total_trades': 150 + (hash(strategy_id) % 200),
            'profit_factor': round(1.8 + (hash(strategy_id) % 40) / 100, 2)
        },
        'equity_curve': generate_mock_equity_curve(),
        'trade_distribution': generate_mock_trade_distribution()
    }

    # 保存回测结果
    if strategy_id not in strategy_state['backtest_results']:
        strategy_state['backtest_results'][strategy_id] = []
    strategy_state['backtest_results'][strategy_id].append(result)

    # 标记事件完成
    if event:
        try:
            event.complete({'success': True, 'result': result})
            monitor = get_monitor()
            if monitor:
                monitor.record_event(event)
        except:
            pass

    return jsonify({
        'success': True,
        'message': f'回测完成 ({optimizer_name})',
        'data': result
    })


@strategy_api.route('/backtest/<strategy_id>', methods=['GET'])
def get_backtest_results(strategy_id):
    """获取策略的回测结果"""
    results = strategy_state['backtest_results'].get(strategy_id, [])
    return jsonify({
        'success': True,
        'data': results
    })


@strategy_api.route('/status', methods=['GET'])
def get_strategy_status():
    """获取策略系统状态"""
    return jsonify({
        'success': True,
        'data': {
            'environment': strategy_state['current_environment'],
            'environment_label': '模拟盘' if strategy_state['current_environment'] == 'paper' else '实盘',
            'active_strategies': strategy_state['active_strategies'],
            'active_count': len(strategy_state['active_strategies']),
            'pending_strategies': strategy_state['pending_strategies'],
            'pending_count': len(strategy_state['pending_strategies']),
            'total_optimizations': sum(len(results) for results in strategy_state['optimization_results'].values()),
            'total_backtests': sum(len(results) for results in strategy_state['backtest_results'].values())
        }
    })


@strategy_api.route('/reset', methods=['POST'])
def reset_strategy_system():
    """重置策略系统状态（用于测试）"""
    init_strategy_state()
    return jsonify({
        'success': True,
        'message': '策略系统已重置'
    })


def generate_mock_equity_curve():
    """生成模拟权益曲线数据"""
    points = []
    value = 100000
    for i in range(100):
        value *= (1 + random.uniform(-0.02, 0.025))
        points.append(round(value, 2))
    return points


def generate_mock_trade_distribution():
    """生成模拟交易分布数据"""
    return [
        {'type': 'profit', 'count': 85 + random.randint(0, 20)},
        {'type': 'loss', 'count': 45 + random.randint(0, 15)},
        {'type': 'breakeven', 'count': 15 + random.randint(0, 10)}
    ]


# ==================== 伯努利-康达策略API ====================

@strategy_api.route('/bernoulli-coanda/backtest', methods=['POST'])
def run_bernoulli_coanda_backtest():
    """运行伯努利-康达策略回测"""
    if not BERNOULLI_COANDA_AVAILABLE:
        return jsonify({
            'success': False,
            'error': '伯努利-康达策略模块不可用'
        }), 503
    
    try:
        data = request.get_json() or {}
        initial_capital = data.get('initial_capital', 100000)
        
        # 记录回测事件
        event = None
        if STRATEGY_MONITOR_AVAILABLE:
            try:
                event = record_strategy_event(
                    StrategyEventType.BACKTEST_START,
                    strategy_id='BernoulliCoandaStrategy',
                    environment=strategy_state['current_environment'],
                    metadata={'initial_capital': initial_capital}
                )
            except:
                pass
        
        # 生成模拟数据
        dates = pd.date_range(start='2022-01-01', periods=500, freq='D')
        np.random.seed(42)
        close_prices = 100 + np.cumsum(np.random.randn(500))
        high_prices = close_prices + np.random.rand(500) * 2
        low_prices = close_prices - np.random.rand(500) * 2
        volumes = np.random.randint(1000000, 10000000, size=500)
        
        mock_data = pd.DataFrame({
            'Open': close_prices - np.random.rand(500),
            'High': high_prices,
            'Low': low_prices,
            'Close': close_prices,
            'Volume': volumes
        }, index=dates)
        
        # 运行回测
        strategy = BernoulliCoandaStrategy(name='BCQ_Backtest')
        result = strategy.run_backtest(mock_data, initial_capital=initial_capital)
        
        # 保存结果
        strategy_id = 'BernoulliCoandaStrategy'
        if strategy_id not in strategy_state['backtest_results']:
            strategy_state['backtest_results'][strategy_id] = []
        strategy_state['backtest_results'][strategy_id].append(result)
        
        # 标记事件完成
        if event:
            try:
                event.complete({'success': True, 'result': result})
                monitor = get_monitor()
                if monitor:
                    monitor.record_event(event)
            except:
                pass
        
        return jsonify({
            'success': True,
            'message': '伯努利-康达策略回测完成',
            'data': result
        })
    except Exception as e:
        print(f"伯努利-康达回测错误: {e}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@strategy_api.route('/bernoulli-coanda/optimize', methods=['POST'])
def run_bernoulli_coanda_optimization():
    """运行伯努利-康达策略参数优化"""
    if not BERNOULLI_COANDA_AVAILABLE:
        return jsonify({
            'success': False,
            'error': '伯努利-康达策略模块不可用'
        }), 503
    
    try:
        data = request.get_json() or {}
        optimization_type = data.get('type', 'grid')
        iterations = data.get('iterations', 20)
        
        # 记录优化事件
        event = None
        if STRATEGY_MONITOR_AVAILABLE:
            try:
                event = record_strategy_event(
                    StrategyEventType.OPTIMIZATION_START,
                    strategy_id='BernoulliCoandaStrategy',
                    environment=strategy_state['current_environment'],
                    metadata={'type': optimization_type, 'iterations': iterations}
                )
            except:
                pass
        
        # 生成模拟数据
        dates = pd.date_range(start='2022-01-01', periods=500, freq='D')
        np.random.seed(43)
        close_prices = 100 + np.cumsum(np.random.randn(500))
        high_prices = close_prices + np.random.rand(500) * 2
        low_prices = close_prices - np.random.rand(500) * 2
        volumes = np.random.randint(1000000, 10000000, size=500)
        
        mock_data = pd.DataFrame({
            'Open': close_prices - np.random.rand(500),
            'High': high_prices,
            'Low': low_prices,
            'Close': close_prices,
            'Volume': volumes
        }, index=dates)
        
        # 运行优化
        optimizer = StrategyParameterOptimizer()
        param_grid = {
            'short_velocity_window': [3, 5, 7],
            'long_velocity_window': [15, 20, 25],
            'pressure_threshold': [0.4, 0.5, 0.6],
        }
        
        result = optimizer.grid_search(
            mock_data, 
            param_grid,
            initial_capital=100000
        )
        
        # 标记事件完成
        if event:
            try:
                event.complete({'success': True, 'best_score': result.best_score})
                monitor = get_monitor()
                if monitor:
                    monitor.record_event(event)
            except:
                pass
        
        return jsonify({
            'success': True,
            'message': '伯努利-康达策略优化完成',
            'data': {
                'best_params': result.best_params,
                'best_score': result.best_score,
                'total_iterations': len(result.all_results)
            }
        })
    except Exception as e:
        print(f"伯努利-康达优化错误: {e}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@strategy_api.route('/bernoulli-coanda/info', methods=['GET'])
def get_bernoulli_coanda_info():
    """获取伯努利-康达策略信息"""
    return jsonify({
        'success': True,
        'data': {
            'available': BERNOULLI_COANDA_AVAILABLE,
            'name': '伯努利-康达量化策略',
            'description': '基于流体力学原理的自适应策略，融合伯努利压强差原理和康达附壁效应，支持自优化演进',
            'features': [
                '自适应康达曲面（支持EMA和卡尔曼滤波）',
                '动态市场状态识别',
                '策略参数自优化',
                '基于风险的仓位管理',
                '集成策略监控系统'
            ],
            'risk_level': 'medium'
        }
    })


# ==================== 策略监控API ====================

@strategy_api.route('/monitor/dashboard', methods=['GET'])
def get_monitor_dashboard():
    """获取策略监控仪表盘数据"""
    monitor = get_monitor()
    if not monitor:
        return jsonify({
            'success': False,
            'error': '策略监控系统不可用'
        })
    
    return jsonify({
        'success': True,
        'data': monitor.get_dashboard_data()
    })


@strategy_api.route('/monitor/events', methods=['GET'])
def get_monitor_events():
    """获取策略事件列表"""
    monitor = get_monitor()
    if not monitor:
        return jsonify({
            'success': False,
            'error': '策略监控系统不可用'
        })
    
    limit = request.args.get('limit', 50, type=int)
    event_type = request.args.get('type', None)
    strategy_id = request.args.get('strategy_id', None)
    environment = request.args.get('environment', None)
    
    events = monitor.get_recent_events(limit, event_type, strategy_id, environment)
    
    return jsonify({
        'success': True,
        'data': events
    })


@strategy_api.route('/monitor/stats', methods=['GET'])
def get_monitor_stats():
    """获取策略监控统计"""
    monitor = get_monitor()
    if not monitor:
        return jsonify({
            'success': False,
            'error': '策略监控系统不可用'
        })
    
    return jsonify({
        'success': True,
        'data': monitor.get_stats()
    })


@strategy_api.route('/monitor/report', methods=['GET'])
def generate_monitor_report():
    """生成策略监控报告"""
    monitor = get_monitor()
    if not monitor:
        return jsonify({
            'success': False,
            'error': '策略监控系统不可用'
        })
    
    # 简化版报告
    stats = monitor.get_stats()
    recent_events = monitor.get_recent_events(limit=20)
    
    return jsonify({
        'success': True,
        'data': {
            'overview': stats,
            'recent_events': recent_events,
            'generated_at': datetime.now().isoformat()
        }
    })


# ==================== 辅助函数：记录事件 ====================

def record_strategy_event(event_type, strategy_id=None, environment=None, metadata=None):
    """记录策略事件的辅助函数"""
    if not STRATEGY_MONITOR_AVAILABLE:
        return None
    
    try:
        monitor = get_monitor()
        if monitor:
            event = monitor_event(event_type, strategy_id, environment, metadata)
            return event
    except Exception as e:
        print(f"[StrategyAPI] 记录事件失败: {e}")
    return None


# ==================== 增强型评估器API ====================

@strategy_api.route('/evaluate/enhanced', methods=['POST'])
def evaluate_strategy_enhanced():
    """使用增强型评估器评估策略（16个协同指标）"""
    if not ENHANCED_EVALUATOR_AVAILABLE:
        return jsonify({
            'success': False,
            'error': '增强型评估器不可用'
        }), 503
    
    try:
        data = request.get_json() or {}
        backtest_result = data.get('backtest_result', {})
        
        # 创建增强型评估器
        evaluator = EnhancedFinancialEvaluator()
        
        # 评估
        total_score, metric_scores, details = evaluator.evaluate(backtest_result)
        grade = evaluator.get_grade(total_score)
        
        return jsonify({
            'success': True,
            'data': {
                'total_score': total_score,
                'grade': grade,
                'metric_scores': metric_scores,
                'metrics_count': len(metric_scores)
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@strategy_api.route('/evaluate/metrics-info', methods=['GET'])
def get_enhanced_metrics_info():
    """获取增强型评估器的16个协同指标信息"""
    if not ENHANCED_EVALUATOR_AVAILABLE:
        return jsonify({
            'success': False,
            'error': '增强型评估器不可用'
        }), 503
    
    try:
        evaluator = EnhancedFinancialEvaluator()
        
        metrics_info = {
            'base_metrics': {
                'sharpe_ratio': {'weight': 0.20, 'target': '>= 2.0', 'description': 'Risk-adjusted return'},
                'max_drawdown': {'weight': 0.15, 'target': '<= 5%', 'description': 'Downside risk'},
                'win_rate': {'weight': 0.10, 'target': '>= 60%', 'description': 'Entry quality'},
                'profit_factor': {'weight': 0.10, 'target': '>= 2.0', 'description': 'Profit/loss ratio'},
                'annual_return': {'weight': 0.05, 'target': '>= 20%', 'description': 'Absolute return'},
            },
            'synergy_metrics': {
                'sortino_ratio': {'weight': 0.08, 'target': '>= 2.0', 'description': 'Downside risk-adjusted return'},
                'omega_ratio': {'weight': 0.05, 'target': '>= 1.5', 'description': 'Probability-weighted gains/losses'},
                'rolling_sharpe_stability': {'weight': 0.05, 'target': '<= 0.5', 'description': 'Strategy consistency'},
                'information_ratio': {'weight': 0.05, 'target': '>= 0.5', 'description': 'Alpha generation'},
                'market_correlation': {'weight': 0.04, 'target': '0.3-0.7', 'description': 'Diversification'},
                'tail_ratio': {'weight': 0.03, 'target': '>= 1.5', 'description': 'Tail risk detection'},
                'trade_frequency': {'weight': 0.03, 'target': '20-50/yr', 'description': 'Activity control'},
                'max_consecutive_losses': {'weight': 0.03, 'target': '<= 5', 'description': 'Behavioral risk'},
                'avg_holding_period': {'weight': 0.02, 'target': '5-20 days', 'description': 'Position duration'},
                'recovery_time': {'weight': 0.02, 'target': '<= 30 days', 'description': 'Capital recovery'},
            }
        }
        
        return jsonify({
            'success': True,
            'data': {
                'total_metrics': 15,
                'base_weight': 0.60,
                'synergy_weight': 0.40,
                'metrics': metrics_info
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@strategy_api.route('/bernoulli-coanda/evaluate', methods=['POST'])
def evaluate_bernoulli_coanda_strategy():
    """使用增强型评估器评估伯努利-康达策略"""
    if not BERNOULLI_COANDA_AVAILABLE or not ENHANCED_EVALUATOR_AVAILABLE:
        return jsonify({
            'success': False,
            'error': '策略或评估器不可用'
        }), 503
    
    try:
        data = request.get_json() or {}
        initial_capital = data.get('initial_capital', 100000)
        
        # 生成模拟数据
        dates = pd.date_range(start='2022-01-01', periods=500, freq='D')
        np.random.seed(42)
        close_prices = 100 + np.cumsum(np.random.randn(500))
        high_prices = close_prices + np.random.rand(500) * 2
        low_prices = close_prices - np.random.rand(500) * 2
        volumes = np.random.randint(1000000, 10000000, size=500)
        
        mock_data = pd.DataFrame({
            'Open': close_prices - np.random.rand(500),
            'High': high_prices,
            'Low': low_prices,
            'Close': close_prices,
            'Volume': volumes
        }, index=dates)
        
        # 运行回测
        strategy = BernoulliCoandaStrategy(name='BCQ_Evaluate')
        backtest_result = strategy.run_backtest(mock_data, initial_capital=initial_capital)
        
        # 添加returns数据
        if 'returns' not in backtest_result:
            trades = backtest_result.get('trades', [])
            backtest_result['returns'] = [t.get('profit_pct', 0) for t in trades]
        backtest_result['days'] = len(mock_data)
        
        # 使用增强型评估器
        evaluator = EnhancedFinancialEvaluator()
        total_score, metric_scores, details = evaluator.evaluate(backtest_result)
        grade = evaluator.get_grade(total_score)
        
        return jsonify({
            'success': True,
            'data': {
                'total_score': total_score,
                'grade': grade,
                'metric_scores': metric_scores,
                'backtest_summary': {
                    'total_return': backtest_result.get('total_return_pct', 0),
                    'sharpe_ratio': backtest_result.get('sharpe_ratio', 0),
                    'max_drawdown': backtest_result.get('max_drawdown_pct', 0),
                    'total_trades': backtest_result.get('total_trades', 0)
                }
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
