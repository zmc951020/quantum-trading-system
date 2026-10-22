"""
策略回测模块 - 为策略参数优化提供真实回测目标函数
====================================================
修复 strategy_optimizer_v2.py 的 TODO：
原 strategy_objective 调用 _multi_stock_objective（优化V15.36引擎参数），
现改为调用本模块的真实策略回测函数。
"""
import json
import os
import sys
import time

import numpy as np

# P0-3: 导入多目标函数模块
try:
    from multi_objective import (
        compute_15dim_metrics,
        compute_composite_entropy,
        weighted_objective_score,
    )
    _MULTI_OBJECTIVE_AVAILABLE = True
except Exception:
    _MULTI_OBJECTIVE_AVAILABLE = False
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

# 添加路径
sys.path.insert(0, r'D:\Gupiao\升级vscode\QS_Robot\export_package')
sys.path.insert(0, r'D:\Gupiao\升级vscode\QS_Robot\core')
sys.path.insert(0, r'C:\Users\PT\AppData\Roaming\TRAE SOLO CN\ModularData\ai-agent\work-mode-projects\6a8b8c0485c5b5d81de83afc')

DATA_DIR = Path(r'D:\Gupiao\升级vscode\QS_Robot\export_package\data\minute_data_ext')

# 数据切分（修复 holdout 泄漏 C1/C2）：优化窗口默认只喂 train 段
try:
    from data_split import mask_period as _mask_period
    _DATA_SPLIT_AVAILABLE = True
except Exception:
    _DATA_SPLIT_AVAILABLE = False

# ============ 性能优化：全局缓存 ============
_DATA_CACHE: Dict[str, pd.DataFrame] = {}  # 股票代码_max_bars -> DataFrame


def load_minute_data(stock_code: str, max_bars: int = 2000) -> Optional[pd.DataFrame]:
    """加载5分钟K线数据（带缓存，避免重复读CSV）"""
    cache_key = f"{stock_code}_{max_bars}"
    if cache_key in _DATA_CACHE:
        return _DATA_CACHE[cache_key]

    # 尝试多种文件名格式
    candidates = [
        DATA_DIR / f'{stock_code}_5min.csv',
        DATA_DIR / f'{stock_code}.csv',
        DATA_DIR / f'{stock_code}_minute.csv',
    ]
    for f in candidates:
        if f.exists():
            try:
                df = pd.read_csv(f)
                if len(df) > 50:
                    # 统一列名
                    col_map = {}
                    for c in df.columns:
                        cl = c.lower()
                        if 'close' in cl or cl == 'c': col_map[c] = 'close'
                        elif 'open' in cl or cl == 'o': col_map[c] = 'open'
                        elif 'high' in cl or cl == 'h': col_map[c] = 'high'
                        elif 'low' in cl or cl == 'l': col_map[c] = 'low'
                        elif 'vol' in cl or cl == 'v': col_map[c] = 'volume'
                    df = df.rename(columns=col_map)
                    if 'close' not in df.columns:
                        continue
                    # 确保有OHLCV
                    for col in ['open', 'high', 'low']:
                        if col not in df.columns:
                            df[col] = df['close']
                    if 'volume' not in df.columns:
                        df['volume'] = 1000000
                    # 取最近max_bars根
                    if len(df) > max_bars:
                        df = df.iloc[-max_bars:].reset_index(drop=True)
                    _DATA_CACHE[cache_key] = df
                    return df
            except Exception:
                continue
    return None


# BUG-3 修复：大盘风控层接线默认值。
# 背景：基线脚本从不传 market_env，原逻辑在 market_env=None 时调用 filter_one 不带大盘参数，
# check_market_environment 命中"三参全空→静默放行"分支（_market_env_state=MISSING, fail-open），
# 导致第四层大盘风控整个空跑、形同不存在。
# 这里给一个中性固定大盘环境（regime=normal 非熊市 / 沪深300平盘 0.0 不触发 -1.5% 拦截 / 板块微涨 +0.1%），
# 使该层真实执行三条风控规则且不误杀现有回测；后续调用方传入真实 market_env 时走真实风控。
DEFAULT_MARKET_ENV: Dict = {'index_change': 0.0, 'sector_change': 0.001, 'regime_label': 'normal'}


def backtest_strategy(strategy_name: str,
                      params: Dict,
                      stock_code: str,
                      initial_capital: float = 100000.0,
                      commission_rate: float = 0.0003,
                      max_bars: int = 2000,
                      use_v4_filter: bool = True,
                      low_stars_min: int = 2,
                      hot_score_min: int = 1,
                      auto_base_config: bool = False,
                      market_env: Optional[Dict] = None,
                      data: Optional[pd.DataFrame] = None,
                      period: str = 'train') -> Dict:
    """
    真实策略回测（V4.0三层架构集成版）

    Args:
        strategy_name: 策略名称（V14_FACTORIES中的key）
        params: 策略参数字典
        stock_code: 股票代码
        initial_capital: 初始资金
        commission_rate: 手续费率
        max_bars: 最大K线数
        use_v4_filter: 是否启用V4.0三层过滤（底座+热启动+通用信号）
        low_stars_min: 底座低位星级阈值（默认2）
        hot_score_min: 热启动分数阈值（默认1）
        auto_base_config: 是否自动使用分策略底座严格度配置（True时覆盖use_v4_filter/low_stars_min/hot_score_min）
        market_env: 大盘环境数据 {'index_change': float, 'sector_change': float, 'regime_label': str}
                    提供时大盘层真实执行 fail-close 检查；未提供时显式标记 MISSING（禁止伪装生效）
        data: 预加载 DataFrame（滚动评估切片用）。传入时跳过内部 load_minute_data。

    Returns:
        回测结果字典
    """
    from deep_optimizer_v16 import V14_FACTORIES
    # P0-3b: 底座过滤切换为 UnifiedBaseFilter 完整版（6条热启动+大盘+涨跌停+评分）
    # B4d: 过滤实现收敛——UnifiedBaseFilter 为唯一生产实现
    # 旧版 deep_optimizer_v16.apply_base_filter（3 条热启动，历史 passed≈23.6%）
    # 仅作 import 失败的降级兜底，标记 DEPRECATED，禁止作为新评估的过滤实现
    try:
        from tools.unified_base_filter import UnifiedBaseFilter
        _USE_UNIFIED_BF = True
    except Exception:
        from deep_optimizer_v16 import apply_base_filter
        _USE_UNIFIED_BF = False

    # 分策略底座严格度自动配置
    if auto_base_config:
        try:
            from strategy_base_filter_config import get_strategy_base_filter_config
            cfg = get_strategy_base_filter_config(strategy_name)
            use_v4_filter = cfg.get('use_v4_filter', use_v4_filter)
            low_stars_min = cfg.get('low_stars_min', low_stars_min)
            hot_score_min = cfg.get('hot_score_min', hot_score_min)
            # P0-A 接线修复：hot_strictness 由分策略档位显式指定（默认中档 0.5），
            # 不再硬编码 0.3 —— 此前 0.3 只要求 4/6 条热启动，是"底座无效果"根因之一
            hot_strictness = cfg.get('hot_strictness', 0.5)
        except Exception:
            pass  # 配置加载失败时使用默认参数

    result = {
        'score': -100, 'total_return': 0, 'sharpe_ratio': 0,
        'max_drawdown': 0, 'win_rate': 0, 'total_trades': 0,
        'equity_curve': [], 'trades': [], 'error': None
    }

    try:
        # 1. 加载数据（C1: 传入 data 则用切片，否则内部加载）
        df = data if data is not None else load_minute_data(stock_code, max_bars)
        if df is None or len(df) < 100:
            result['error'] = f'数据不足: {stock_code}'
            return result

        # C1/C2 修复：内部加载的 CSV 必须按 period 掩码，优化打分只喂 train；
        # 外部传入的 data 切片由调用方负责周期归属，不重复掩码。
        if data is None and _DATA_SPLIT_AVAILABLE:
            try:
                df = _mask_period(df, period=period)
                if len(df) < 100:
                    result['error'] = f'{period} 段数据不足: {stock_code} (rows={len(df)})'
                    return result
            except Exception as _e:
                result['error'] = f'split mask failed: {str(_e)[:120]}'
                return result

        closes = df['close'].values.astype(float)
        n = len(closes)
        volumes = df['volume'].values.astype(float) if 'volume' in df.columns else np.full(n, 1000000.0)
        highs = df['high'].values.astype(float) if 'high' in df.columns else closes
        lows = df['low'].values.astype(float) if 'low' in df.columns else closes
        opens = df['open'].values.astype(float) if 'open' in df.columns else closes

        # V4.0三层过滤：底座（低位星级）+ 热启动（P0-3b: 完整版 UnifiedBaseFilter 6条热启动）
        v4_passed_set = None
        v4_filter_stats = {}
        if use_v4_filter:
            try:
                if _USE_UNIFIED_BF:
                    # P0-A 接线修复：hot_strictness 由上方配置传入（auto_base_config 或默认 0.5）
                    _bf = UnifiedBaseFilter(low_stars_min=low_stars_min,
                                            hot_strictness=hot_strictness,
                                            n_stocks=20)
                    _pd = []
                    # BUG-3：未传 market_env 时接入中性固定大盘环境，使大盘风控层真实执行而非空跑放行。
                    _env = market_env if market_env is not None else DEFAULT_MARKET_ENV
                    _market_env_state = 'ACTIVE' if market_env is not None else 'ACTIVE(default)'
                    for _i in range(60, n):
                        # B4a: 真实执行 fail-close 大盘检查（熊市/沪深300暴跌/板块下跌 三条规则）
                        _r = _bf.filter_one(opens, highs, lows, closes, volumes, _i,
                                            index_change=_env.get('index_change'),
                                            sector_change=_env.get('sector_change'),
                                            regime_label=_env.get('regime_label', ''))
                        if _r.passed:
                            _pd.append(_i)
                    passed_days = _pd
                    v4_filter_stats = {'unified_base_filter': True, 'passed': len(_pd),
                                       'market_env': _market_env_state}
                else:
                    stock_data = {'closes': closes, 'highs': highs, 'lows': lows}
                    passed_days, v4_filter_stats = apply_base_filter(
                        stock_data, low_stars_min=low_stars_min, hot_score_min=hot_score_min
                    )
                v4_passed_set = set(passed_days)
            except Exception as e:
                v4_passed_set = None  # 过滤失败时不过滤
                v4_filter_stats = {'error': str(e)[:100]}

        # 2. 实例化策略（传入参数）
        try:
            factory = V14_FACTORIES[strategy_name]
            strategy = factory()
            # B4c: 传入优化参数（修复 **params 展开 bug：GSA/集群 set_params 签名是 dict）
            params_applied = True
            if hasattr(strategy, 'set_params') and callable(getattr(strategy, 'set_params')):
                try:
                    _r = strategy.set_params(params)   # dict 参数（GSA/集群/包装器签名）
                    if _r is False:
                        params_applied = False
                except TypeError:
                    # 兼容 **kwargs 签名策略
                    try:
                        strategy.set_params(**params)
                    except Exception as e:
                        params_applied = False
                        result['param_apply_error'] = f'set_params(**): {str(e)[:80]}'
                except Exception as e:
                    params_applied = False
                    result['param_apply_error'] = f'set_params: {str(e)[:80]}'
            # GSA适配器：_custom_kwargs 兜底（未生效时更新并触发重建）
            if hasattr(strategy, '_custom_kwargs') and not params_applied:
                strategy._custom_kwargs.update(params)
                if hasattr(strategy, '_prices') and len(getattr(strategy, '_prices', [])) == 0:
                    try:
                        _r2 = strategy.set_params(params)
                        if _r2 is False:
                            params_applied = False
                        else:
                            params_applied = True
                    except Exception as e:
                        result['param_apply_error'] = f'rebuild: {str(e)[:80]}'
            if not params_applied:
                # B4c: 参数未生效 → 显式标记（优化器必须跳过该评估）
                result['param_apply_failed'] = True
                result['param_apply_error'] = result.get('param_apply_error', 'params not applied')
        except Exception as e:
            result['error'] = f'策略实例化失败: {e}'
            return result

        # 3. 构建 minute_bars（v15 引擎格式：open/high/low/close/volume/day_idx）
        minute_bars = []
        for i in range(n):
            minute_bars.append({
                'open': float(opens[i]),
                'high': float(highs[i]),
                'low': float(lows[i]),
                'close': float(closes[i]),
                'volume': float(volumes[i]),
                'day_idx': i // 48,
            })

        # v4_passed_set（分钟bar索引）→ day_idx 集合（base_filtered_days 口径）
        base_filtered_days = None
        if v4_passed_set is not None:
            try:
                base_filtered_days = {i // 48 for i in v4_passed_set}
                v4_filter_stats = dict(v4_filter_stats)
                v4_filter_stats['engine_switched_mapped'] = True
            except Exception as e:
                base_filtered_days = None
                v4_filter_stats = {'note': 'engine_switched_filter_not_mapped',
                                   'error': str(e)[:100]}

        # 4. 调用 backtest_v15（E模式：T+1 + 信号延迟 + 动态滑点 + 涨跌停拦截）
        #    v15 内部通过 inspect.signature 探测 update_price 并自动透传 OHLC
        from deep_optimizer_v16 import backtest_v15
        bt = backtest_v15(
            strategy_obj=strategy,
            minute_bars=minute_bars,
            capital=initial_capital,
            experiment='E',
            stock_code=stock_code,
            base_filtered_days=base_filtered_days,
        )

        # 5. 映射返回指标（v15 返回百分数 → 旧口径小数）
        total_return = float(bt.get('total_return', 0)) / 100.0
        sharpe = float(bt.get('sharpe', 0))
        max_dd = float(bt.get('max_drawdown', 0)) / 100.0
        win_rate = float(bt.get('win_rate', 0)) / 100.0
        total_trades = int(bt.get('total_trades', 0))

        # 复合评分（沿用旧口径：收益40% + 夏普25% + 胜率15% - 回撤10%；v15无逐笔明细，省略盈亏比项）
        score = (total_return * 100 * 0.4 +
                 sharpe * 0.25 +
                 win_rate * 15 * 0.15 -
                 max_dd * 100 * 0.10)

        # 交易次数约束（B2 对齐优化器评分器硬约束：<2次视为无效样本）
        if total_trades < 3:
            score -= 10  # 交易太少惩罚
        valid = total_trades >= 2
        if not valid:
            score = -100.0

        result.update({
            'score': score,                # 选优口径：复合评分（v15引擎）
            'score_legacy': score,
            'valid': valid,                # B2: 交易次数硬约束标记
            'total_return': total_return,
            'sharpe_ratio': sharpe,
            'max_drawdown': max_dd,
            'win_rate': win_rate,
            'total_trades': total_trades,
            'trades': bt.get('trades', []),          # v15 已导出逐笔明细
            'equity_curve': bt.get('equity_curve', []),  # v15 已导出逐bar权益曲线
            'final_equity': bt.get('equity_curve', [None])[-1] if bt.get('equity_curve') else None,
            'v4_filter_enabled': use_v4_filter,
            'v4_filter_stats': v4_filter_stats,
            'v4_passed_bars': len(v4_passed_set) if v4_passed_set else 0,
            'engine': 'backtest_v15_E',
            'calmar': bt.get('calmar'),
            'exit_reasons': bt.get('exit_reasons'),
            'limit_stats': bt.get('limit_stats'),
        })

    except Exception as e:
        result['error'] = str(e)[:200]

    return result


def multi_stock_strategy_objective(strategy_name: str,
                                    params: Dict,
                                    stock_codes: List[str],
                                    use_v4_filter: bool = True,
                                    low_stars_min: int = 2,
                                    hot_score_min: int = 1) -> Dict:
    """
    多股票策略回测目标函数（用于优化器，V4.0三层架构集成版）

    Args:
        strategy_name: 策略名称
        params: 策略参数
        stock_codes: 股票列表
        use_v4_filter: 是否启用V4.0三层过滤
        low_stars_min: 底座低位星级阈值
        hot_score_min: 热启动分数阈值

    Returns:
        综合评分
    """
    returns = []
    sharpes = []
    drawdowns = []
    win_rates = []
    total_trades = 0
    errors = []
    v4_passed_total = 0

    for code in stock_codes:
        r = backtest_strategy(strategy_name, params, code,
                             use_v4_filter=use_v4_filter,
                             low_stars_min=low_stars_min,
                             hot_score_min=hot_score_min)
        if r.get('error'):
            errors.append(f"{code}: {r['error']}")
            continue
        returns.append(r.get('total_return', 0))
        sharpes.append(r.get('sharpe_ratio', 0))
        drawdowns.append(r.get('max_drawdown', 0))
        win_rates.append(r.get('win_rate', 0))
        total_trades += r.get('total_trades', 0)
        v4_passed_total += r.get('v4_passed_bars', 0)

    if not returns:
        return {'score': -100, 'total_return': 0, 'sharpe_ratio': 0,
                'max_drawdown': 0, 'win_rate': 0, 'total_trades': 0,
                'errors': errors}

    avg_return = np.mean(returns)
    avg_sharpe = np.mean(sharpes)
    avg_drawdown = np.mean(drawdowns)
    avg_winrate = np.mean(win_rates)

    # 综合评分
    score = avg_return * 100 + avg_sharpe * 2 - avg_drawdown * 50
    if total_trades < 3:
        score -= 5

    return {
        'score': score,
        'total_return': avg_return,
        'sharpe_ratio': avg_sharpe,
        'max_drawdown': avg_drawdown,
        'win_rate': avg_winrate,
        'total_trades': total_trades,
        'per_stock_returns': dict(zip(stock_codes, returns)),
        'errors': errors,
        'v4_filter_enabled': use_v4_filter,
        'v4_passed_bars_total': v4_passed_total,
    }


# ============================================================
# V2 完整版回测引擎（使用 backtest_v15，含T+1/信号延迟/动态滑点）
# ============================================================

def backtest_strategy_v2(
    strategy_name: str,
    params: Dict,
    stock_code: str,
    initial_capital: float = 100000.0,
    max_bars: int = 2000,
    data: Optional[pd.DataFrame] = None,
) -> Dict:
    """
    V2 完整版回测：使用 backtest_v15 引擎
    
    特性：
    - T+1约束（当日买入次日才能卖出）
    - 信号延迟（信号触发后下根bar入场）
    - 动态滑点（按市值分档）
    - 涨跌停拦截
    - 交易成本（手续费+印花税+滑点）
    
    Args:
        strategy_name: 策略名称
        params: 策略参数字典
        stock_code: 股票代码
        initial_capital: 初始资金
        max_bars: 最大K线数
        data: 预加载DataFrame（可选）
    
    Returns:
        回测结果字典
    """
    result = {
        'score': -100,
        'total_return': 0,
        'sharpe_ratio': 0,
        'max_drawdown': 0,
        'win_rate': 0,
        'total_trades': 0,
        'equity_curve': [],
        'trades': [],
        'error': None,
    }
    
    try:
        from deep_optimizer_v16 import V14_FACTORIES, backtest_v15
        
        # 1. 加载数据
        df = data if data is not None else load_minute_data(stock_code, max_bars)
        if df is None or len(df) < 100:
            result['error'] = f'数据不足: {stock_code}'
            return result
        
        # 2. 转换为 minute_bars 格式
        minute_bars = []
        for i, row in df.iterrows():
            close = float(row.get('close', row.get('Close', 0)))
            minute_bars.append({
                'open': float(row.get('open', row.get('Open', close))),
                'high': float(row.get('high', row.get('High', close))),
                'low': float(row.get('low', row.get('Low', close))),
                'close': close,
                'volume': float(row.get('volume', row.get('Volume', 1000000))),
                'day_idx': i // 48,
            })
        
        # 3. 创建策略实例
        factory = V14_FACTORIES.get(strategy_name)
        if factory is None:
            result['error'] = f'未找到策略: {strategy_name}'
            return result
        
        strategy = factory()
        
        # 4. 应用参数
        if params and hasattr(strategy, 'set_params'):
            try:
                strategy.set_params(**params)
            except Exception:
                pass
        
        # 5. 运行完整版回测
        bt_result = backtest_v15(
            strategy_obj=strategy,
            minute_bars=minute_bars,
            capital=initial_capital,
            experiment='E',  # 完整模式：T+1+信号延迟+动态滑点
            stock_code=stock_code,
        )
        
        # 6. 转换返回格式
        result['total_return'] = bt_result.get('total_return', 0) / 100.0  # 百分比转小数
        result['sharpe_ratio'] = bt_result.get('sharpe', 0)
        result['max_drawdown'] = bt_result.get('max_drawdown', 0) / 100.0
        result['win_rate'] = bt_result.get('win_rate', 0) / 100.0
        result['total_trades'] = bt_result.get('total_trades', 0)
        
        # 计算score（与原函数保持一致）
        result['score'] = result['total_return'] * 100 + result['sharpe_ratio'] * 2 - result['max_drawdown'] * 50
        
        return result
        
    except Exception as e:
        result['error'] = str(e)[:200]
        return result


if __name__ == '__main__':
    # 测试：回测高收益网格策略
    print("测试策略回测模块...")
    r = backtest_strategy('high_return_grid', {}, '000001', max_bars=500)
    print("高收益网格 000001:")
    print(f"  收益: {r['total_return']*100:.2f}%")
    print(f"  夏普: {r['sharpe_ratio']:.2f}")
    print(f"  回撤: {r['max_drawdown']*100:.2f}%")
    print(f"  胜率: {r['win_rate']*100:.1f}%")
    print(f"  交易: {r['total_trades']}次")
    if r.get('error'):
        print(f"  错误: {r['error']}")
    
    print("\n" + "=" * 60)
    print("测试 V2 完整版回测...")
    r2 = backtest_strategy_v2('final_market_adaptive', {}, '000001', max_bars=500)
    print("final_market_adaptive 000001 (V2完整版):")
    print(f"  收益: {r2['total_return']*100:.2f}%")
    print(f"  夏普: {r2['sharpe_ratio']:.2f}")
    print(f"  回撤: {r2['max_drawdown']*100:.2f}%")
    print(f"  胜率: {r2['win_rate']*100:.1f}%")
    print(f"  交易: {r2['total_trades']}次")
    if r2.get('error'):
        print(f"  错误: {r2['error']}")
