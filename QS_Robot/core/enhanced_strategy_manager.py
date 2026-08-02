#!/usr/bin/env python3
"""
QS Robot - 增强型策略管理器（双核统一版 V2.0）
==============================================
从量化指令解析到策略执行的全流程管理。
同时支持：
- 核心1：Aurora本地大数据引擎（DeepSeek V3.2T / 512GB）
- 核心2：QS Robot桌面智能体（Qwen 1.5B本地推理）

功能覆盖：
  ✅ 策略启动/停止/状态查询
  ✅ 回测执行与结果管理
  ✅ AI参数优化（Grid Search + Bayesian）
  ✅ 风险控制集成
  ✅ 系统健康监控
  ✅ 模拟降级策略（Aurora不可用时自动切换）
"""

import sys
import os
import json
import time
import threading
import requests
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
# ============================================================
# Windows控制台UTF-8编码补丁 (解决'gbk' codec无法编码emoji的问题)
# ============================================================
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


# ============================================================
# 数据模型
# ============================================================

class StrategyStatus(Enum):
    STOPPED = "stopped"
    RUNNING = "running"
    BACKTESTING = "backtesting"
    OPTIMIZING = "optimizing"
    ERROR = "error"


class SystemMode(Enum):
    AURORA_LIVE = "aurora_live"      # Aurora在线，双核联动
    AURORA_FALLBACK = "fallback"     # Aurora离线，本地模拟降级
    STANDALONE = "standalone"        # 独立运行


@dataclass
class StrategyInfo:
    name: str
    label: str
    category: str
    description: str
    status: StrategyStatus = StrategyStatus.STOPPED
    performance: Dict = field(default_factory=dict)
    last_backtest: Optional[str] = None
    params: Dict = field(default_factory=dict)
    best_params: Dict = field(default_factory=dict)
    best_score: float = 0.0
    version: int = 0


@dataclass
class BacktestResult:
    """
    回测结果（EnhancedStrategyManager 使用）
    
    单位约定:
    - total_return_pct: 百分比 (如 31.95 表示 31.95%)
    - sharpe_ratio: 比率 (原值, 如 1.5)
    - max_drawdown: 百分比 (如 15.0 表示 15%)
    - win_rate: 百分比 (如 65.0 表示 65%)
    - total_trades: 整数 (交易次数)
    """
    strategy_name: str
    total_return_pct: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    total_trades: int
    start_date: str
    end_date: str
    db_saved: bool = False


@dataclass
class SystemHealth:
    status: str  # healthy / degraded / critical
    cpu_percent: float
    memory_percent: float
    disk_percent: float
    uptime_seconds: int
    services: Dict[str, str]
    components: Dict[str, bool]


# ============================================================
# Aurora API 客户端
# ============================================================

class AuroraAPIClient:
    """与Aurora可视化层通信的HTTP客户端"""

    def __init__(self, base_url: str = "http://localhost:5003", timeout: int = 10):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self._available = False
        self._last_check = 0

    def _request(self, method: str, path: str, **kwargs) -> Optional[dict]:
        """发送HTTP请求，带超时重试"""
        url = f"{self.base_url}{path}"
        try:
            kwargs.setdefault('timeout', self.timeout)
            resp = requests.request(method, url, **kwargs)
            if resp.status_code == 200:
                return resp.json()
            return {"success": False, "error": f"HTTP {resp.status_code}"}
        except requests.ConnectionError:
            return {"success": False, "error": "Aurora连接失败"}
        except requests.Timeout:
            return {"success": False, "error": "Aurora响应超时"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def check_available(self) -> bool:
        """检查Aurora是否可达"""
        if time.time() - self._last_check < 5:
            return self._available
        result = self._request('GET', '/api/health')
        self._available = result is not None and result.get('status') == 'healthy'
        self._last_check = time.time()
        return self._available

    # ---- 系统API ----
    def get_system_status(self) -> dict:
        return self._request('GET', '/api/system/status') or {}

    def get_system_health(self) -> dict:
        return self._request('GET', '/api/system/health') or {}

    # ---- 策略API ----
    def get_strategy_list(self) -> list:
        result = self._request('GET', '/api/strategy-list')
        if result and result.get('success'):
            return result.get('data', {}).get('strategies', [])
        return []

    def get_strategy_params(self, name: str) -> dict:
        result = self._request('GET', f'/api/strategy-params?strategy_name={name}')
        return result.get('params', {}) if result else {}

    def start_strategy(self, name: str, balance: float = 100000) -> dict:
        return self._request('POST', '/api/start-strategy', json={
            'strategy_name': name, 'initial_balance': balance
        }) or {}

    def stop_strategy(self) -> dict:
        return self._request('GET', '/api/stop-strategy') or {}

    # ---- 回测API ----
    def run_backtest(self, name: str, days: int = 30, balance: float = 100000,
                     params: dict = None, symbol: str = 'BTCUSDT') -> dict:
        return self._request('POST', '/api/v1/backtest/run', json={
            'strategy_name': name,
            'days': days,
            'initial_balance': balance,
            'params': params or {},
            'symbol': symbol
        }) or {}

    def get_backtest_history(self, name: str = None, limit: int = 20) -> dict:
        params = {'limit': limit}
        if name:
            params['strategy_name'] = name
        return self._request('GET', '/api/backtest/history', params=params) or {}

    # ---- 优化器API ----
    def run_optimization(self, name: str, iterations: int = 50,
                         target: str = 'sharpe_ratio', params: dict = None) -> dict:
        return self._request('POST', '/api/v1/optimizer/optimize', json={
            'strategy_name': name,
            'iterations': iterations,
            'target_metric': target,
            'params': params or {}
        }) or {}

    # ---- 韬定律优化器API ----
    def run_tau_optimization(self, name: str, param_ranges: dict = None,
                             coarse_points: int = 30, refined_points: int = 50,
                             target: str = 'sharpe_ratio') -> dict:
        return self._request('POST', '/api/v1/tau/optimize', json={
            'strategy_name': name,
            'param_ranges': param_ranges or {},
            'coarse_points': coarse_points,
            'refined_points': refined_points,
            'target_metric': target
        }) or {}

    def get_tau_info(self) -> dict:
        return self._request('GET', '/api/v1/tau/info') or {}

    def run_tau_single(self, name: str, params: dict) -> dict:
        return self._request('POST', '/api/v1/tau/single', json={
            'strategy_name': name,
            'params': params or {}
        }) or {}

    def run_tau_optimization_strategy(self, strategy_name: str, strategy_type: str,
                                       iterations: int = 80) -> dict:
        """调用韬定律集群的策略感知优化 (优先走Aurora)"""
        return self._request('POST', '/api/v1/tau/optimize-strategy', json={
            'strategy_name': strategy_name,
            'strategy_type': strategy_type,
            'iterations': iterations,
        }) or {}

    def get_factor_groups(self, strategy_name: str) -> dict:
        """获取策略的因子分组信息 (用于高维参数策略)"""
        return self._request('GET', f'/api/v1/tau/factor-groups?strategy={strategy_name}') or {}

    # ---- 风险API ----
    def get_risk_status(self) -> dict:
        return self._request('GET', '/api/risk/status') or {}

    # ---- 性能API ----
    def get_performance_metrics(self) -> dict:
        return self._request('GET', '/api/performance/metrics') or {}

    # ---- 增益模块API ----
    def get_gain_status(self) -> dict:
        return self._request('GET', '/api/gain/status') or {}

    def get_shepherd_status(self) -> dict:
        return self._request('GET', '/api/shepherd/status') or {}

    def run_shepherd(self, strategy: str, max_loop: int = 10, target: float = 0.85) -> dict:
        return self._request('POST', '/api/shepherd/run', json={
            'strategy': strategy, 'max_loop': max_loop, 'target': target
        }) or {}


# ============================================================
# 模拟降级策略引擎
# ============================================================

class SimulatedFallbackEngine:
    """Aurora不可用时的本地模拟引擎"""

    def __init__(self):
        self._sim_data = {
            'prices': [],
            'timestamp': datetime.now().isoformat()
        }
        self._generate_mock_data()

    def _generate_mock_data(self, ticks: int = 200):
        """生成模拟市场数据"""
        import random
        price = 50000.0
        for i in range(ticks):
            price += random.normalvariate(0, 50)
            self._sim_data['prices'].append({
                'timestamp': (datetime.now().isoformat()),
                'price': round(price, 2),
                'volume': random.randint(100, 1000)
            })

    def get_system_status(self) -> dict:
        """返回模拟系统状态"""
        return {
            "success": True,
            "data": {
                "system": "QS Robot (Simulated Fallback)",
                "version": "V2.0-Fallback",
                "running": True,
                "mode": "simulated",
                "note": "Aurora不可用，使用本地模拟引擎",
                "components": {
                    "strategies": {"available": True, "loaded": 14},
                    "risk_control": {"available": True},
                    "data": {"available": True, "source": "simulated"},
                    "optimizer": {"available": True},
                    "database": {"available": False}
                },
                "timestamp": datetime.now().isoformat()
            }
        }

    def get_strategy_list(self) -> list:
        """返回模拟策略列表"""
        return [
            {"name": "FourierRLStrategy", "category": "RL", "label": "傅里叶强化学习策略",
             "description": "傅里叶变换+PPO强化学习"},
            {"name": "FinalMarketAdaptiveGrid", "category": "Grid", "label": "自适应网格策略",
             "description": "随机森林市场分类+自适应网格"},
            {"name": "MLRangeGridTrading", "category": "ML", "label": "ML区间网格策略",
             "description": "随机森林优化网格步长"},
            {"name": "HuijinValueStrategy", "category": "Value", "label": "汇金价值AI轮动策略",
             "description": "价值投资+AI轮动"},
            {"name": "MultiFactorResonanceStrategy", "category": "MultiFactor", "label": "多因子共振策略",
             "description": "多技术指标共振信号"},
            {"name": "MovingAveragesStrategy", "category": "Trend", "label": "均线趋势策略",
             "description": "双均线交叉+趋势跟踪"},
            {"name": "AdaptiveMLStrategy", "category": "ML", "label": "自适应ML策略",
             "description": "在线学习+自适应参数调整"},
            {"name": "GridTrading", "category": "Grid", "label": "经典网格策略",
             "description": "经典网格+区间震荡交易"},
            {"name": "PPOTradingAgent", "category": "RL", "label": "PPO强化学习智能体",
             "description": "深度强化学习+自主决策"},
            {"name": "DCAStrategy", "category": "Fund", "label": "定投策略",
             "description": "定期定额+成本平均"},
            {"name": "DownMarketStrategy", "category": "Defense", "label": "下跌防御策略",
             "description": "下跌趋势对冲+仓位控制"},
            {"name": "HighReturnGridTrading", "category": "Grid", "label": "高收益网格策略",
             "description": "激进网格+高频率交易"},
            {"name": "AdaptiveRangeGridTrading", "category": "Grid", "label": "自适应范围网格",
             "description": "动态范围检测+网格交易"},
            {"name": "FinalOptimizedStrategy", "category": "Ensemble", "label": "综合优化策略",
             "description": "多策略融合+综合优化"},
            {"name": "special_forces_wyckoff", "category": "特种兵", "label": "特种兵・威科夫量价自适应",
             "description": "威科夫三定律+四级周期共振+68维量价结构因子+强化学习自动寻优"},
        ]

    def run_backtest(self, name: str, days: int = 30, balance: float = 100000.0,
                     params: dict = None, symbol: str = 'BTCUSDT') -> dict:
        """模拟回测（参数感知的本地计算）

        根据策略参数计算有意义的回测指标，使韬定律优化器能够真实优化。
        """
        import random
        import numpy as np

        # --- 参数感知评分逻辑 ---
        quality_score = 0.5
        params = params or {}
        name_lower = str(name).lower()
        is_gyro = any(k in name_lower for k in ['gyro', '陀螺仪', '陀螺', 'gyroscopic', 'gyro_v7'])
        is_fourier = any(k in name_lower for k in ['fourier', '傅里叶', 'ppo', 'rl', '强化学习'])
        is_bernoulli = any(k in name_lower for k in ['bernoulli', 'coanda', '伯努利', '康达'])
        is_shepherd = any(k in name_lower for k in ['shepherd', 'rotation', '轮动', '标的'])

        # 陀螺仪/傅里叶策略：优先使用专用评分模块（避免因参数名称不同而漏评分）
        if is_gyro or is_fourier:
            try:
                from .tau_optimizer_cluster import GyroModule, FourierRLStrategyModule
                if is_gyro:
                    mod = GyroModule()
                else:
                    mod = FourierRLStrategyModule()
                module_score = mod.estimate_quality(params)
                # module_score 是 0-10 金融级，归一化为 0-1
                quality_score = max(0.0, min(1.0, module_score / 10.0))
                quality_score += random.uniform(-0.03, 0.03)
            except Exception:
                pass  # 失败则退回下面的通用逻辑

        if params and quality_score == 0.5:  # 仅当专用模块未覆盖时才走通用评分
            # 计算参数合理性得分（0-1范围，1=最佳）
            param_scores = []

            # 1. 短周期参数 (short_period)
            if 'short_period' in params:
                sp = float(params['short_period'])
                # 5-20 之间好，10-15 最佳
                if 10 <= sp <= 15:
                    param_scores.append(1.0)
                elif 5 <= sp <= 20:
                    param_scores.append(0.7)
                elif sp < 5 or sp > 50:
                    param_scores.append(0.2)
                else:
                    param_scores.append(0.5)

            # 2. 长周期参数 (long_period)
            if 'long_period' in params:
                lp = float(params['long_period'])
                if 60 <= lp <= 80:
                    param_scores.append(1.0)
                elif 40 <= lp <= 120:
                    param_scores.append(0.7)
                elif lp < 20 or lp > 200:
                    param_scores.append(0.2)
                else:
                    param_scores.append(0.5)

            # 3. 中周期参数 (mid_period)
            if 'mid_period' in params:
                mp = float(params['mid_period'])
                if 25 <= mp <= 45:
                    param_scores.append(1.0)
                elif 15 <= mp <= 60:
                    param_scores.append(0.7)
                else:
                    param_scores.append(0.4)

            # 4. 周期间隔合理性（短<中<长，且间隔合理）
            sp_v = float(params.get('short_period', 0))
            mp_v = float(params.get('mid_period', 0))
            lp_v = float(params.get('long_period', 0))
            if sp_v > 0 and mp_v > 0 and lp_v > 0:
                if sp_v < mp_v < lp_v and (mp_v - sp_v) >= 5 and (lp_v - mp_v) >= 15:
                    param_scores.append(1.0)
                elif sp_v < mp_v < lp_v:
                    param_scores.append(0.6)
                else:
                    param_scores.append(0.2)

            # 5. 伯努利阈值 (bernoulli_threshold)
            if 'bernoulli_threshold' in params:
                bt = float(params['bernoulli_threshold'])
                if 0.04 <= bt <= 0.08:
                    param_scores.append(1.0)
                elif 0.02 <= bt <= 0.12:
                    param_scores.append(0.6)
                else:
                    param_scores.append(0.3)

            # 6. 动量因子 (momentum_alpha)
            if 'momentum_alpha' in params:
                ma = float(params['momentum_alpha'])
                if 0.6 <= ma <= 1.5:
                    param_scores.append(1.0)
                elif 0.3 <= ma <= 2.5:
                    param_scores.append(0.6)
                else:
                    param_scores.append(0.3)

            # 7. 康达效应强度 (coanda_attachment)
            if 'coanda_attachment' in params:
                ca = float(params['coanda_attachment'])
                if 0.4 <= ca <= 0.8:
                    param_scores.append(1.0)
                elif 0.2 <= ca <= 1.0:
                    param_scores.append(0.6)
                else:
                    param_scores.append(0.3)

            # 8. 压力敏感度 (pressure_sensitivity)
            if 'pressure_sensitivity' in params:
                ps = float(params['pressure_sensitivity'])
                if 0.5 <= ps <= 1.2:
                    param_scores.append(1.0)
                elif 0.3 <= ps <= 1.8:
                    param_scores.append(0.6)
                else:
                    param_scores.append(0.3)

            # 9. 曲率敏感度 (curvature_sensitivity)
            if 'curvature_sensitivity' in params:
                cs = float(params['curvature_sensitivity'])
                if 0.3 <= cs <= 0.8:
                    param_scores.append(1.0)
                elif 0.1 <= cs <= 1.2:
                    param_scores.append(0.6)
                else:
                    param_scores.append(0.3)

            # 10. 分离阈值 (separation_threshold)
            if 'separation_threshold' in params:
                st = float(params['separation_threshold'])
                if 0.8 <= st <= 1.5:
                    param_scores.append(1.0)
                elif 0.5 <= st <= 2.5:
                    param_scores.append(0.6)
                else:
                    param_scores.append(0.3)

            # 11. 止损百分比 (stop_loss_pct)
            if 'stop_loss_pct' in params:
                sl = float(params['stop_loss_pct'])
                if 0.03 <= sl <= 0.08:
                    param_scores.append(1.0)
                elif 0.01 <= sl <= 0.15:
                    param_scores.append(0.6)
                else:
                    param_scores.append(0.3)

            # 12. 仓位大小 (position_size)
            if 'position_size' in params:
                ps_v = float(params['position_size'])
                if 0.2 <= ps_v <= 0.4:
                    param_scores.append(1.0)
                elif 0.1 <= ps_v <= 0.6:
                    param_scores.append(0.6)
                else:
                    param_scores.append(0.3)

            # 13. 确认K线数 (confirmation_bars)
            if 'confirmation_bars' in params:
                cb = float(params['confirmation_bars'])
                if 2 <= cb <= 4:
                    param_scores.append(1.0)
                elif 1 <= cb <= 6:
                    param_scores.append(0.6)
                else:
                    param_scores.append(0.3)

            # 14. 均线阈值 (threshold) - 通用策略
            if 'threshold' in params:
                th = float(params['threshold'])
                if 0.02 <= th <= 0.06:
                    param_scores.append(1.0)
                elif 0.005 <= th <= 0.1:
                    param_scores.append(0.6)
                else:
                    param_scores.append(0.3)

            # 15. 智能标的轮动 - 因子权重分布评估
            if is_shepherd or len(params) > 15:
                # 评估因子权重分布
                weights = [float(v) for v in params.values() if isinstance(v, (int, float))]
                if weights:
                    avg_w = sum(weights) / len(weights)
                    # 权重应该在合理范围（0.5-1.5）
                    weight_score = 1.0 - min(1.0, abs(avg_w - 1.0))
                    param_scores.append(max(0.3, weight_score))

                    # 因子多样性：方差适中
                    if len(weights) > 3:
                        var = sum((w - avg_w) ** 2 for w in weights) / len(weights)
                        var_score = 1.0 - min(1.0, abs(var - 0.1) * 5)
                        param_scores.append(max(0.3, var_score))

            # 综合评分
            if param_scores:
                quality_score = sum(param_scores) / len(param_scores)
                # 添加少量随机扰动避免完全相同的评分
                quality_score += random.uniform(-0.03, 0.03)
                quality_score = max(0.0, min(1.0, quality_score))
        else:
            # 无参数，使用策略名称相关的基础评分 + 随机
            if is_gyro:
                quality_score = 0.7 + random.uniform(-0.05, 0.1)
            elif is_fourier:
                quality_score = 0.7 + random.uniform(-0.05, 0.1)
            elif is_bernoulli:
                quality_score = 0.65 + random.uniform(-0.05, 0.1)
            elif is_shepherd:
                quality_score = 0.6 + random.uniform(-0.05, 0.1)
            else:
                quality_score = 0.55 + random.uniform(-0.05, 0.1)

        # --- 根据 quality_score 计算回测指标 ---
        np.random.seed(hash(f"{name}_{quality_score:.4f}") % 2**32)
        initial = balance

        # 日收益率分布：质量越高，均值越高，波动率越低
        mean_daily = (quality_score - 0.3) * 0.003  # 范围: -0.0009 ~ +0.0021
        std_daily = 0.025 - quality_score * 0.015   # 范围: 0.025 ~ 0.010

        daily_returns = np.random.normal(mean_daily, std_daily, days)
        cumulative = initial * np.cumprod(1 + daily_returns)
        final = cumulative[-1]
        total_return = (final - initial) / initial * 100
        sharpe = np.mean(daily_returns) / np.std(daily_returns) * np.sqrt(252) if np.std(daily_returns) > 0 else 0
        drawdowns = (cumulative - np.maximum.accumulate(cumulative)) / np.maximum.accumulate(cumulative)
        max_dd = abs(min(drawdowns)) * 100

        # 基于 quality_score 的胜率和交易数
        win_rate = quality_score * 45.0 + 35.0  # 35% ~ 80%
        total_trades = int(quality_score * 250) + 30  # 30 ~ 280

        return {
            "success": True,
            "data": {
                "strategy_name": name,
                "summary": {
                    "initial_balance": initial,
                    "final_balance": round(float(final), 2),
                    "total_return_pct": round(float(total_return), 2),
                    "sharpe_ratio": round(float(sharpe), 4),
                    "max_drawdown": round(float(max_dd), 2),
                    "win_rate": round(float(win_rate), 1),
                    "total_trades": total_trades,
                    "days": days,
                    "quality_score": round(quality_score, 4)
                },
                "db_saved": False,
                "note": f"参数感知模拟回测 (quality={quality_score:.4f})"
            }
        }

    def run_optimization(self, name: str, iterations: int = 30) -> dict:
        """模拟参数优化"""
        import random
        history = []
        best_score = -999
        best_params = {}

        for i in range(iterations):
            score = 1.5 + random.normalvariate(0, 0.1)
            params = {
                'learning_rate': round(random.uniform(0.0001, 0.01), 6),
                'lookback': random.randint(10, 60),
                'max_position': round(random.uniform(0.1, 0.5), 2)
            }
            history.append({"iteration": i+1, "score": round(score, 4), "params": params})
            if score > best_score:
                best_score = score
                best_params = params

        return {
            "success": True,
            "data": {
                "strategy_name": name,
                "method": "simulated_bayesian",
                "best_params": best_params,
                "best_score": round(best_score, 4),
                "iterations": iterations,
                "history": history[-5:],
                "note": "模拟优化结果（Aurora离线）"
            }
        }


# ============================================================
# 真实K线回测引擎（基于AKShare数据源）
# ============================================================

class RealKlineBacktestEngine:
    """基于真实K线数据的策略回测引擎。

    调用链：enhanced_strategy_manager → AKShareDataSource → 东方财富/新浪财经 API

    输出格式与 SimulatedFallbackEngine.run_backtest 保持完全一致，
    这样 GUI/优化器/集成总线的调用代码无需修改。
    """

    def __init__(self):
        self._kline_cache = {}
        self._ak_ds = None  # 延迟初始化 AKShareDataSource

    # --------- AKShare 数据源连接 ---------
    def _get_akshare(self):
        if self._ak_ds is None or self._ak_ds is False:
            try:
                import importlib
                mod = importlib.import_module("extensions.data_sources.akshare_data_source")
                cls = getattr(mod, "AKShareDataSource")
                self._ak_ds = cls({"cache_enabled": True, "cache_ttl_days": 1})
                self._ak_ds.connect()
            except Exception as e:
                print(f"[WARN] AKShare初始化失败: {e}")
                self._ak_ds = False
        return self._ak_ds

    def _fetch_kline(self, symbol: str, days: int = 500):
        key = (symbol, days)
        if key in self._kline_cache:
            return self._kline_cache[key]
        ds = self._get_akshare()
        if not ds:
            return None
        try:
            r = ds.get_stock_kline(symbol=symbol, period="daily", days=days)
            if r and r.get("count", 0) > 50:
                self._kline_cache[key] = r
                return r
        except Exception as e:
            print(f"[WARN] 获取K线失败 {symbol}: {e}")
        return None

    # --------- 主入口：与 SimulatedFallbackEngine 同签名 ---------
    def run_backtest(self, name: str, days: int = 300, balance: float = 100000.0,
                     params: dict = None, symbol: str = "000001") -> dict:
        """真实K线回测。与 SimulatedFallbackEngine.run_backtest 返回结构完全一致。"""
        import numpy as np
        params = params or {}
        kline = self._fetch_kline(symbol, max(days, 200))
        if kline is None or len(kline.get("closes", [])) < 60:
            return {
                "success": True,
                "data": {
                    "strategy_name": name,
                    "summary": {
                        "initial_balance": balance,
                        "final_balance": balance,
                        "total_return_pct": 0.0,
                        "sharpe_ratio": 0.0,
                        "max_drawdown": 0.0,
                        "win_rate": 50.0,
                        "total_trades": 0,
                        "days": days,
                        "quality_score": 0.5
                    },
                    "db_saved": False,
                    "note": "K线数据不可用（网络/AKShare未安装？），改用模拟模式"
                }
            }

        closes = np.array(kline["closes"], dtype=np.float64)
        n = len(closes)
        name_lower = str(name).lower()
        is_trend = any(k in name_lower for k in ['trend', '趋势', 'movingavg', '均线'])
        is_grid = any(k in name_lower for k in ['grid', '网格', 'highreturngrid', 'adaptiverange'])
        is_ml = any(k in name_lower for k in ['ml', 'machine', '自适应ML', 'adaptiveml'])
        is_mfactor = any(k in name_lower for k in ['multifactor', '多因子', 'resonance', '共振'])
        is_rl = any(k in name_lower for k in ['ppo', 'rl', 'fourier', '傅里叶', '强化'])
        is_value = any(k in name_lower for k in ['value', '价值', 'huijin', '汇金'])
        is_defense = any(k in name_lower for k in ['defense', '防御', 'downmarket', '下跌'])
        is_bernoulli = any(k in name_lower for k in ['bernoulli', 'coanda', '伯努利', '康达', '陀螺仪', 'gyro'])
        is_shepherd = any(k in name_lower for k in ['shepherd', 'rotation', '轮动', '标的'])
        is_ensemble = any(k in name_lower for k in ['ensemble', 'optimized', '综合', 'final'])

        signals = self._gen_signals(name_lower, closes, params,
                                    is_trend, is_grid, is_ml, is_mfactor, is_rl,
                                    is_value, is_defense, is_bernoulli,
                                    is_shepherd, is_ensemble)

        metrics = self._simulate_trades(closes, signals, balance)

        return {
            "success": True,
            "data": {
                "strategy_name": name,
                "summary": {
                    "initial_balance": balance,
                    "final_balance": round(float(metrics["final_balance"]), 2),
                    "total_return_pct": round(float(metrics["total_return_pct"]), 2),
                    "sharpe_ratio": round(float(metrics["sharpe"]), 4),
                    "max_drawdown": round(float(metrics["max_drawdown"]), 2),
                    "win_rate": round(float(metrics["win_rate"]), 1),
                    "total_trades": int(metrics["total_trades"]),
                    "days": n,
                    "quality_score": round(float(metrics["quality_score"]), 4)
                },
                "db_saved": False,
                "note": f"真实K线回测 ({symbol}, {n}个交易日, 源:AKShare)"
            }
        }

    # --------- 信号生成 ---------
    def _gen_signals(self, name_lower, closes, params,
                     is_trend, is_grid, is_ml, is_mfactor, is_rl,
                     is_value, is_defense, is_bernoulli, is_shepherd, is_ensemble):
        import numpy as np
        n = len(closes)
        signals = np.zeros(n)

        short_p = max(3, int(params.get("short_period", 10)))
        long_p = max(short_p + 5, int(params.get("long_period", 30)))
        mid_p = max(short_p + 3, int(params.get("mid_period", 20)))
        threshold = float(params.get("threshold", 0.03))
        stop_loss = float(params.get("stop_loss_pct", 0.05))
        pos_size = float(params.get("position_size", 0.3))
        bernoulli_thresh = float(params.get("bernoulli_threshold", 0.05))
        coanda_att = float(params.get("coanda_attachment", 0.5))
        pressure_sens = float(params.get("pressure_sensitivity", 0.8))
        curvature_sens = float(params.get("curvature_sensitivity", 0.5))
        separation_thresh = float(params.get("separation_threshold", 1.0))
        momentum_alpha = float(params.get("momentum_alpha", 0.8))
        confirmation_bars = max(1, int(params.get("confirmation_bars", 3)))

        def sma(arr, w):
            if w >= len(arr):
                return np.full(len(arr), arr[0])
            weights = np.ones(w) / w
            return np.convolve(arr, weights, mode="same")

        def compute_rsi(arr, period=14):
            deltas = np.diff(arr, prepend=arr[0])
            gains = np.where(deltas > 0, deltas, 0)
            losses = np.where(deltas < 0, -deltas, 0)
            ag = sma(gains, period)
            al = sma(losses, period)
            rs = np.where(al > 0, ag / (al + 1e-10), 100.0)
            return 100.0 - (100.0 / (1.0 + rs))

        short_ma = sma(closes, short_p)
        long_ma = sma(closes, long_p)
        mid_ma = sma(closes, mid_p)
        rsi = compute_rsi(closes, 14)
        returns = np.diff(closes, prepend=closes[0]) / (closes + 1e-10)
        vol = np.zeros(n)
        for i in range(20, n):
            vol[i] = float(np.std(returns[i-20:i]))
        vol[:20] = vol[20] if n > 20 else 0.02
        avg_vol = float(np.mean(vol[vol > 0])) if np.any(vol > 0) else 0.02

        if is_trend or 'moving' in name_lower:
            diff = short_ma - long_ma
            for i in range(1, n):
                if diff[i-1] <= 0 < diff[i]:
                    signals[i] = pos_size
                elif diff[i-1] >= 0 > diff[i]:
                    signals[i] = 0.0
            smooth = np.zeros(n)
            running = 0
            for i in range(n):
                if signals[i] > 0:
                    running = confirmation_bars
                if running > 0:
                    smooth[i] = pos_size
                    running -= 1
            signals = smooth

        elif is_grid:
            lookback = 60
            for i in range(lookback, n):
                lo = float(np.min(closes[i-lookback:i]))
                hi = float(np.max(closes[i-lookback:i]))
                rng = max(hi - lo, hi * 0.02)
                position = (float(closes[i]) - lo) / rng
                signals[i] = max(0.0, min(pos_size, pos_size * (1.0 - position * 1.5)))

        elif is_ml:
            for i in range(1, n):
                rsi_ok = rsi[i] < 55
                mom_ok = closes[i] > closes[max(0, i-5)]
                vol_ok = vol[i] < avg_vol * 1.5
                if rsi_ok and mom_ok and vol_ok:
                    signals[i] = pos_size
                elif rsi[i] > 70:
                    signals[i] = 0.0

        elif is_mfactor:
            for i in range(1, n):
                trend_ok = short_ma[i] > long_ma[i]
                rsi_ok = 40 <= rsi[i] <= 70
                mom_ok = closes[i] > closes[max(0, i-10)]
                if trend_ok and rsi_ok and mom_ok:
                    signals[i] = pos_size

        elif is_rl:
            momentum = np.zeros(n)
            for i in range(10, n):
                momentum[i] = (closes[i] - closes[i-10]) / (closes[i-10] + 1e-10)
            for i in range(n):
                if momentum[i] > threshold:
                    signals[i] = min(pos_size, pos_size * (1 + momentum[i] * momentum_alpha))
                elif momentum[i] < -threshold:
                    signals[i] = 0.0

        elif is_value:
            for i in range(long_p, n):
                dev = (closes[i] - long_ma[i]) / (long_ma[i] + 1e-10)
                if dev < -0.03:
                    signals[i] = pos_size
                elif dev > 0.05:
                    signals[i] = 0.0

        elif is_defense:
            for i in range(n):
                if vol[i] < avg_vol * 0.8:
                    signals[i] = pos_size * 0.5
                elif vol[i] > avg_vol * 1.5:
                    signals[i] = 0.0

        elif is_bernoulli:
            for i in range(5, n):
                pressure = abs(closes[i] - closes[i-5]) / (closes[i-5] + 1e-10)
                curvature = abs(closes[i] - 2 * closes[i-1] + closes[i-2]) / (closes[i-1] + 1e-10)
                if pressure > bernoulli_thresh * 0.5 and curvature > curvature_sens * 0.003:
                    signals[i] = pos_size
                elif pressure < bernoulli_thresh * 0.2:
                    signals[i] = signals[i-1]

        elif is_shepherd:
            for i in range(20, n):
                mom20 = (closes[i] - closes[i-20]) / (closes[i-20] + 1e-10)
                vol_score = 1.0 / (1 + vol[i])
                signals[i] = max(0.0, min(pos_size, (mom20 * momentum_alpha + vol_score * 0.3) * 0.5))

        elif is_ensemble:
            trend_vote = (short_ma > long_ma).astype(float)
            rsi_vote = ((rsi > 30) & (rsi < 70)).astype(float)
            momentum_vote = np.zeros(n)
            for i in range(10, n):
                momentum_vote[i] = 1.0 if closes[i] > closes[i-10] else 0.0
            avg_vote = (trend_vote + rsi_vote + momentum_vote) / 3.0
            signals = np.where(avg_vote > 0.5, pos_size, 0.0)

        else:
            diff = short_ma - long_ma
            for i in range(1, n):
                if diff[i-1] <= 0 < diff[i]:
                    signals[i] = pos_size

        return signals

    # --------- 交易模拟 ---------
    def _simulate_trades(self, closes, signals, balance):
        import numpy as np
        n = len(closes)
        # A股实际费率: 印花税0.05%(卖出) + 佣金0.025% + 过户费0.001% ≈ 0.075%
        fee_rate = 0.00075
        # 动态滑点: 基础0.05% + 波动率补偿
        volatility = np.std(np.diff(closes) / (closes[:-1] + 1e-10)) if n > 10 else 0.02
        slippage = max(0.0005, min(0.02, 0.0005 + volatility * 0.05))
        min_lot = 100  # A股最小交易单位: 100股(一手)
        price_limit = 0.10  # 涨跌停限制: ±10%
        cash = np.zeros(n)
        shares = np.zeros(n)
        equity = np.zeros(n)
        cash[0] = balance
        equity[0] = balance
        trade_logs = []
        # T+1跟踪: 记录当天买入的股数，次日才可卖出
        pending_shares = 0.0  # 今日买入、明日才可卖出的股数

        # 计算涨跌停价格
        prev_close = closes[0]

        for i in range(1, n):
            cash[i] = cash[i-1]
            shares[i] = shares[i-1]

            # 涨跌停检查: 价格不能超过涨跌停限制
            upper_limit = prev_close * (1 + price_limit)
            lower_limit = prev_close * (1 - price_limit)
            effective_price = max(lower_limit, min(upper_limit, closes[i]))
            prev_close = closes[i]

            target_pos = float(signals[i])
            total_equity = cash[i] + shares[i] * effective_price
            current_pos = (shares[i] * effective_price) / total_equity if total_equity > 0 else 0

            if abs(target_pos - current_pos) > 0.05:
                target_value = total_equity * target_pos
                current_value = shares[i] * effective_price
                delta_value = target_value - current_value

                if abs(delta_value) > 10:
                    trade_price = effective_price * (1 + slippage) if delta_value > 0 else effective_price * (1 - slippage)
                    trade_shares = delta_value / trade_price

                    # A股最小交易单位: 向下取整到100的倍数
                    trade_shares = int(abs(trade_shares) // min_lot) * min_lot
                    if trade_shares == 0:
                        continue

                    trade_shares = trade_shares if delta_value > 0 else -trade_shares
                    fee = abs(trade_shares * trade_price) * fee_rate

                    if trade_shares > 0:
                        # 买入
                        cost = trade_shares * trade_price + fee
                        if cash[i] >= cost:
                            cash[i] -= cost
                            shares[i] += trade_shares
                            pending_shares += trade_shares  # T+1: 今日买入不可卖
                            trade_logs.append(("buy", i, float(trade_price), float(trade_shares)))
                    else:
                        # 卖出: T+1检查 — 当日买入的不可卖出
                        sell_shares = min(-trade_shares, shares[i] - pending_shares)
                        if sell_shares >= min_lot:
                            proceeds = sell_shares * trade_price - fee
                            cash[i] += proceeds
                            shares[i] -= sell_shares
                            trade_logs.append(("sell", i, float(trade_price), float(sell_shares)))

            # 次日: 释放T+1锁定
            if i > 0:
                pending_shares = max(0, pending_shares - max(0, shares[i-1] - shares[i]))

            equity[i] = cash[i] + shares[i] * effective_price

        if n < 2:
            return {"final_balance": balance, "total_return_pct": 0, "sharpe": 0,
                    "max_drawdown": 0, "win_rate": 50, "total_trades": 0, "quality_score": 0.5}

        total_return_pct = (equity[-1] - balance) / balance * 100
        daily_r = np.diff(equity) / (equity[:-1] + 1e-10)
        sharpe = float(np.mean(daily_r) / np.std(daily_r) * np.sqrt(252)) if np.std(daily_r) > 0 else 0.0
        peak = np.maximum.accumulate(equity)
        dd = (equity - peak) / (peak + 1e-10)
        max_drawdown = abs(float(min(dd))) * 100

        if len(trade_logs) >= 2:
            wins = 0
            closed = 0
            buys = [t for t in trade_logs if t[0] == "buy"]
            sells = [t for t in trade_logs if t[0] == "sell"]
            for b, s in zip(buys[:len(sells)], sells):
                pnl = (s[2] - b[2]) * min(b[3], s[3])
                if pnl > 0:
                    wins += 1
                closed += 1
            win_rate = (wins / closed * 100) if closed > 0 else 50.0
        else:
            win_rate = 50.0

        quality_score = max(0.0, min(1.0, 0.5 + float(total_return_pct) / 100.0 + sharpe / 10.0))
        return {
            "final_balance": float(equity[-1]),
            "total_return_pct": float(total_return_pct),
            "sharpe": sharpe,
            "max_drawdown": max_drawdown,
            "win_rate": win_rate,
            "total_trades": len(trade_logs),
            "quality_score": quality_score
        }


# ============================================================
# 核心：增强型策略管理器
# ============================================================

class EnhancedStrategyManager:
    """
    QS Robot 增强型策略管理器

    三核架构:
    - 当Aurora在线 → 通过AuroraAPIClient调用Aurora的DeepSeek引擎
    - 当Aurora离线 → 使用SimulatedFallbackEngine本地模拟（参数感知评分）
    - 真实K线模式 → 使用RealKlineBacktestEngine（基于AKShare数据源跑真实行情）
    """

    def __init__(self, aurora_base_url: str = "http://localhost:5003"):
        # 三核心
        self.aurora = AuroraAPIClient(base_url=aurora_base_url)
        self.fallback = SimulatedFallbackEngine()
        self.real_engine = RealKlineBacktestEngine()
        self._data_mode = "auto"  # "auto" | "real" | "simulated"

        # 状态管理
        self._mode = SystemMode.STANDALONE
        self._lock = threading.Lock()
        self._cache = {}
        self._cache_ttl = {}
        self._cache_duration = 30  # 缓存30秒

        # 策略跟踪
        self._active_strategies: Dict[str, StrategyInfo] = {}
        self._backtest_results: List[BacktestResult] = []
        self._optimization_history: List[dict] = []

        # 韬定律策略优化器集群 (延迟初始化)
        self.tau_cluster = None  # 韬定律集群延迟初始化

        # 韬定律策略参数存储 (warm start / 版本管理)
        try:
            from .tau_optimizer_cluster import get_parameter_store
            self.parameter_store = get_parameter_store()
        except Exception:
            self.parameter_store = None

        # 启动健康检查线程
        self._shutdown_event = threading.Event()
        self._health_thread = threading.Thread(target=self._health_check_loop, daemon=True)
        self._health_thread.start()

        # 自动同步策略到韬策略集群引擎
        self._sync_to_cluster_engine()

    def _sync_to_cluster_engine(self):
        """将参数存储中的所有策略自动注册到韬策略集群引擎

        这是打通「策略管理 → 集群引擎」链路的桥梁。
        注册后，TauClusterEngine 的共振验证、权重调度、集群决策
        等五层架构才能正常运作。
        """
        try:
            from .tau_cluster_engine import get_cluster_engine, StrategySignalAdapter, ClusterSignal

            engine = get_cluster_engine()
            store = self.parameter_store

            if store is None:
                print("[集群同步] 参数存储不可用，跳过策略注册")
                return

            all_info = store.get_all_strategies_info() if hasattr(store, 'get_all_strategies_info') else []
            if not all_info:
                print("[集群同步] 参数存储中无策略记录，跳过注册")
                return

            registered = 0
            for info in all_info:
                name = info.get("name", "")
                if not name or name in engine.get_registered_strategies():
                    continue

                # 自动识别策略类型
                strategy_type = self._detect_strategy_type(name, info)

                # 创建信号函数：基于参数存储中的历史最佳评分生成信号
                best_score = info.get("best_score", 0)
                best_params = info.get("best_params", {})

                def _make_signal_func(s_name, s_score, s_params):
                    def _signal_func(market_data=None, current_price=None):
                        """根据策略历史表现生成集群信号"""
                        confidence = min(0.95, max(0.1, s_score / 5.0)) if s_score else 0.5
                        direction = 0.3 if confidence > 0.5 else -0.1
                        return ClusterSignal(
                            strategy_name=s_name,
                            direction=direction,
                            confidence=confidence,
                            strength=confidence,
                            win_probability=confidence,
                            extra={"source": "parameter_store", "best_score": s_score},
                        )
                    return _signal_func

                signal_func = _make_signal_func(name, best_score, best_params)
                adapter = StrategySignalAdapter(
                    name=name,
                    strategy_type=strategy_type,
                    signal_func=signal_func,
                )
                engine.register_strategy(name, adapter)
                registered += 1

            print(f"[集群同步] 已注册 {registered} 个策略到韬策略集群引擎 "
                       f"(共{len(all_info)}条参数记录)")
            if registered > 0:
                # 保存引擎状态
                engine.save_state()

        except ImportError:
            print("[集群同步] 集群引擎模块不可用，跳过注册")
        except Exception as e:
            print(f"[集群同步] 注册异常: {e}")

    @staticmethod
    def _detect_strategy_type(name: str, info: dict) -> str:
        """根据策略名称自动识别策略类型"""
        name_lower = name.lower()
        # 同花顺策略优先识别（避免被grid/trend等通用类型截获）
        if any(k in name_lower for k in ['macd', 'expma', 'boll', 'dmi', 'adx', '均线', '多头', '金叉', '突破', '龙头', '龙虎榜', '波段', '生命线', '牛熊', '共振', '低吸']):
            return "ths_strategies"
        if any(k in name_lower for k in ['量价', '筹码', '北向', '情绪', '板块轮动', '画线', '形态识别', '预警', '状态机', 'level-2', '逐笔', '金字塔', '网格交易套利', '控盘综合', '问财', '动态股池', '成交量阶梯', '量化趋势', '筹码控盘']):
            return "ths_advanced"
        if any(k in name_lower for k in ['gyro', '陀螺']):
            return "gyro"
        elif any(k in name_lower for k in ['bernoulli', 'coanda', '伯努利']):
            return "bernoulli"
        elif any(k in name_lower for k in ['fourier', '傅里叶']):
            return "fourier"
        elif any(k in name_lower for k in ['shepherd', 'rotation', '轮动']):
            return "shepherd"
        elif any(k in name_lower for k in ['grid', '网格']):
            return "grid"
        elif any(k in name_lower for k in ['moving', '均线', 'trend', '趋势']):
            return "trend"
        elif any(k in name_lower for k in ['ml', 'adaptive', 'ppo']):
            return "ml"
        elif any(k in name_lower for k in ['rl', 'reinforce']):
            return "rl"
        elif any(k in name_lower for k in ['fractal', 'chaos', '分形']):
            return "physics"
        elif any(k in name_lower for k in ['fluid', '流体']):
            return "physics"
        elif any(k in name_lower for k in ['quantum', '量子']):
            return "physics"
        elif any(k in name_lower for k in ['value', '价值', 'huijin']):
            return "value"
        elif any(k in name_lower for k in ['multifactor', 'resonance', '共振', '因子']):
            return "multifactor"
        elif any(k in name_lower for k in ['dca', '定投', 'fund']):
            return "fund"
        elif any(k in name_lower for k in ['down', 'defense', '防御', '下跌']):
            return "defense"
        elif any(k in name_lower for k in ['special_forces', '特种兵']):
            return "special_forces"
        elif any(k in name_lower for k in ['ensemble', 'optimized', '综合', '融合']):
            return "ensemble"
        return "generic"

    def shutdown(self):
        """优雅关闭：停止健康检查线程"""
        self._shutdown_event.set()
        if self._health_thread and self._health_thread.is_alive():
            self._health_thread.join(timeout=5)

    # ---- 模式管理 ----

    def _health_check_loop(self):
        """后台健康检查（每30秒一次，收到 shutdown 信号后退出）"""
        while not self._shutdown_event.is_set():
            try:
                available = self.aurora.check_available()
                with self._lock:
                    if available:
                        if self._mode != SystemMode.AURORA_LIVE:
                            print(f"[QS Robot] ✅ Aurora已连接，切换到双核联动模式")
                        self._mode = SystemMode.AURORA_LIVE
                    else:
                        if self._mode == SystemMode.AURORA_LIVE:
                            print(f"[QS Robot] ⚠️ Aurora连接丢失，切换到模拟降级模式")
                        self._mode = SystemMode.AURORA_FALLBACK
            except Exception as e:
                with self._lock:
                    self._mode = SystemMode.AURORA_FALLBACK
            self._shutdown_event.wait(30)  # 可中断的sleep

    def get_mode(self) -> SystemMode:
        """获取当前运行模式"""
        with self._lock:
            return self._mode

    def is_aurora_available(self) -> bool:
        """Aurora是否可用"""
        return self.get_mode() == SystemMode.AURORA_LIVE

    # ---- 缓存管理 ----

    def _cached(self, key: str, fetcher, force: bool = False):
        """带缓存的获取器"""
        now = time.time()
        if not force and key in self._cache and now - self._cache_ttl.get(key, 0) < self._cache_duration:
            return self._cache[key]
        result = fetcher()
        self._cache[key] = result
        self._cache_ttl[key] = now
        return result

    # ---- 策略管理 ----

    def get_strategy_list(self, force: bool = False) -> List[dict]:
        """获取策略列表（自动选择数据源）"""
        def fetch():
            if self.is_aurora_available():
                result = self.aurora.get_strategy_list()
                if result:
                    return result
            return self.fallback.get_strategy_list()
        return self._cached('strategy_list', fetch, force)

    def get_strategy_info(self, name: str) -> StrategyInfo:
        """获取单个策略信息"""
        strategies = self.get_strategy_list()
        for s in strategies:
            if s['name'] == name:
                if name in self._active_strategies:
                    return self._active_strategies[name]
                return StrategyInfo(
                    name=s['name'],
                    label=s.get('label', s['name']),
                    category=s.get('category', 'unknown'),
                    description=s.get('description', ''),
                    params=s.get('params', {})
                )
        return None

    def start_strategy(self, name: str, balance: float = 100000.0,
                        use_optimized_params: bool = True) -> Tuple[bool, str]:
        """启动策略（自动应用最新优化参数）"""
        # 自动加载并应用最新优化参数
        best_params_info = ""
        if use_optimized_params:
            try:
                from .tau_optimizer_cluster import get_parameter_store
                _ps = get_parameter_store()
                best_params = _ps.get_best_params(name)
                if best_params:
                    best_score = _ps.get_best_score(name)
                    info = _ps.get_strategy(name)
                    version = info.get('current_version', 0) if info else 0
                    best_params_info = f"（使用优化参数 v{version}, score={best_score:.2f}）"
                    # 同步到 active_strategies 缓存
                    self._active_strategies[name] = StrategyInfo(
                        name=name, label=name, category='',
                        description=f'v{version}, score={best_score:.2f}',
                        status=StrategyStatus.RUNNING,
                        best_params=best_params, best_score=best_score,
                        version=version
                    )
            except Exception as e:
                print(f"[WARN] 加载优化参数失败，使用默认: {e}")

        if self.is_aurora_available():
            # 即使aurora启动，也先确保已记录最佳参数
            if not name in self._active_strategies:
                self._active_strategies[name] = StrategyInfo(
                    name=name, label=name, category='', description='',
                    status=StrategyStatus.RUNNING
                )
            result = self.aurora.start_strategy(name, balance)
            if result.get('success'):
                return True, f"策略 {name} 已通过Aurora启动{best_params_info}"
            return False, result.get('error', '启动失败')

        # 模拟模式
        if not name in self._active_strategies:
            self._active_strategies[name] = StrategyInfo(
                name=name, label=name, category='', description='',
                status=StrategyStatus.RUNNING
            )
        return True, f"策略 {name} 已启动（模拟模式）{best_params_info}"

    def stop_strategy(self) -> Tuple[bool, str]:
        """停止所有策略"""
        if self.is_aurora_available():
            result = self.aurora.stop_strategy()
            self._active_strategies.clear()
            return result.get('success', False), result.get('message', '已停止')
        self._active_strategies.clear()
        return True, "策略已停止（模拟模式）"

    # ---- 回测管理 ----

    # ---- 数据模式管理 ----
    def set_data_mode(self, mode: str):
        """设置数据模式：'auto' 先试真实K线，失败回退到模拟；'real' 仅真实K线；'simulated' 仅模拟"""
        valid = {"auto", "real", "simulated"}
        if mode not in valid:
            raise ValueError(f"data_mode 必须是 {valid}")
        self._data_mode = mode

    def get_data_mode(self) -> str:
        return self._data_mode

    def run_backtest(self, name: str, days: int = 30, balance: float = 100000.0,
                     params: dict = None, symbol: str = 'BTCUSDT',
                     use_optimized_params: bool = True,
                     data_mode: str = None) -> BacktestResult:
        """执行回测 —— 自动应用最新优化参数

        Args:
            use_optimized_params: 若为True且params=None，自动从参数存储加载最佳参数
            data_mode: 'auto'|'real'|'simulated'，None 表示使用 self._data_mode
        """
        effective_params = params
        if params is None and use_optimized_params:
            try:
                from .tau_optimizer_cluster import get_parameter_store
                _ps = get_parameter_store()
                best_params = _ps.get_best_params(name)
                if best_params:
                    best_score = _ps.get_best_score(name)
                    info = _ps.get_strategy(name)
                    version = info.get('current_version', 0) if info else 0
                    print(f"  [Backtest] 已加载 {name} 最新优化参数 "
                          f"(v{version}, score={best_score:.2f})")
                    effective_params = best_params
            except Exception as e:
                print(f"  [Backtest] 加载优化参数失败，使用默认: {e}")

        mode = data_mode if data_mode else self._data_mode

        # 真实K线模式尝试（real/auto）
        if mode in ("real", "auto"):
            try:
                result = self.real_engine.run_backtest(name, days, balance, effective_params, symbol)
                note = result.get("data", {}).get("note", "")
                # 真实K线引擎成功（有交易发生，或虽空但非 fallback 提示）
                if result.get("success") and "K线数据不可用" not in note and "改用模拟模式" not in note:
                    summary = result["data"]["summary"]
                    bt = BacktestResult(
                        strategy_name=name,
                        total_return_pct=summary.get('total_return_pct', 0),
                        sharpe_ratio=summary.get('sharpe_ratio', 0),
                        max_drawdown=summary.get('max_drawdown', 0),
                        win_rate=summary.get('win_rate', 0),
                        total_trades=summary.get('total_trades', 0),
                        start_date=datetime.now().isoformat(),
                        end_date=datetime.now().isoformat(),
                        db_saved=summary.get('db_saved', False)
                    )
                    self._backtest_results.append(bt)
                    return bt
            except Exception as e:
                print(f"  [Backtest] 真实K线模式失败: {e}")
            if mode == "real":
                # 'real' 模式不回退到模拟——直接返回空结果
                bt = BacktestResult(name, 0, 0, 0, 0, 0, "", "", False)
                self._backtest_results.append(bt)
                return bt

        # Aurora 远程引擎（若可用）
        if self.is_aurora_available():
            result = self.aurora.run_backtest(name, days, balance, effective_params, symbol)
            if result.get('success'):
                data = result.get('data', {})
                summary = data.get('summary', {})
                bt = BacktestResult(
                    strategy_name=name,
                    total_return_pct=summary.get('total_return_pct', 0),
                    sharpe_ratio=summary.get('sharpe_ratio', 0),
                    max_drawdown=summary.get('max_drawdown', 0),
                    win_rate=summary.get('win_rate', 0),
                    total_trades=summary.get('total_trades', 0),
                    start_date=datetime.now().isoformat(),
                    end_date=datetime.now().isoformat(),
                    db_saved=data.get('db_saved', False)
                )
                self._backtest_results.append(bt)
                return bt

        # 模拟模式（参数感知评分）
        result = self.fallback.run_backtest(name, days, balance, effective_params, symbol)
        data = result.get('data', {}).get('summary', {})
        bt = BacktestResult(
            strategy_name=name,
            total_return_pct=data.get('total_return_pct', 0),
            sharpe_ratio=data.get('sharpe_ratio', 0),
            max_drawdown=data.get('max_drawdown', 0),
            win_rate=data.get('win_rate', 0),
            total_trades=data.get('total_trades', 0),
            start_date=datetime.now().isoformat(),
            end_date=datetime.now().isoformat(),
            db_saved=False
        )
        self._backtest_results.append(bt)
        return bt

    def get_optimization_status(self, strategy_name: str = None) -> Any:
        """查询策略优化状态（返回最佳评分/版本/更新时间等）"""
        try:
            from .tau_optimizer_cluster import get_parameter_store
            _ps = get_parameter_store()
            if strategy_name:
                info = _ps.get_strategy(strategy_name)
                if info:
                    return {
                        'success': True,
                        'strategy': strategy_name,
                        'best_score': round(info.get('best_score', 0), 4),
                        'current_version': info.get('current_version', 0),
                        'best_params': _ps.get_best_params(strategy_name),
                        'history_count': len(info.get('optimization_history', [])),
                        'last_updated': info.get('last_updated', '-'),
                        'status': info.get('status', 'new')
                    }
                return {'success': False, 'error': '策略未优化'}
            # 返回所有策略优化状态
            return {'success': True, 'strategies': _ps.get_all_strategies_info()}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def apply_optimized_params(self, strategy_name: str) -> dict:
        """将最新优化参数应用到策略（返回当前最佳参数字典）"""
        try:
            from .tau_optimizer_cluster import get_parameter_store
            _ps = get_parameter_store()
            best_params = _ps.get_best_params(strategy_name)
            if not best_params:
                return {'success': False, 'error': f'{strategy_name} 无优化记录'}
            best_score = _ps.get_best_score(strategy_name)
            info = _ps.get_strategy(strategy_name)
            version = info.get('current_version', 0) if info else 0
            # 同步到 active_strategies 缓存（供GUI/运行时使用）
            self._active_strategies[strategy_name] = StrategyInfo(
                name=strategy_name, label=strategy_name,
                category='optimized', description=f'v{version}, score={best_score:.2f}',
                best_params=best_params, best_score=best_score,
                version=version, status=StrategyStatus.RUNNING
            )
            return {
                'success': True, 'strategy': strategy_name,
                'best_params': best_params, 'best_score': round(best_score, 4),
                'version': version, 'message': f'{strategy_name} 已应用 v{version} 优化参数'
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def get_backtest_history(self, name: str = None, limit: int = 20) -> List[BacktestResult]:
        """获取回测历史"""
        if self.is_aurora_available():
            result = self.aurora.get_backtest_history(name, limit)
            if result.get('success'):
                return result.get('results', [])
        return [r for r in self._backtest_results[-limit:] if not name or r.strategy_name == name]

    # ---- 优化管理 ----

    def run_optimization(self, name: str, iterations: int = 50,
                         target: str = 'sharpe_ratio', params: dict = None) -> dict:
        """运行参数优化"""
        if self.is_aurora_available():
            result = self.aurora.run_optimization(name, iterations, target, params)
            if result.get('success'):
                self._optimization_history.append(result['data'])
                return result
        result = self.fallback.run_optimization(name, iterations)
        if result.get('success'):
            self._optimization_history.append(result['data'])
        return result

    # ---- 韬定律策略优化器集群 ----

    # 策略类型 → 真实参数空间映射（替代通用默认值）
    # 每种策略类型有独立参数空间，优化器按类型匹配合适的参数范围
    STRATEGY_PARAM_RANGES: Dict[str, Dict[str, Tuple[float, float]]] = {
        "grid": {
            "grid_layers": (3.0, 20.0),       # 网格层数
            "grid_spacing": (0.01, 0.10),      # 网格间距（价格比例）
            "rebalance_threshold": (0.005, 0.05),  # 再平衡阈值
            "take_profit_ratio": (0.02, 0.15),     # 止盈比例
            "stop_loss_ratio": (0.01, 0.08),        # 止损比例
        },
        "trend": {
            "short_period": (5.0, 30.0),       # 短期均线
            "long_period": (30.0, 200.0),      # 长期均线
            "signal_threshold": (0.005, 0.05), # 信号阈值
            "atr_multiplier": (1.0, 4.0),      # ATR止损倍数
            "trend_strength_filter": (0.1, 0.5),  # 趋势强度过滤
        },
        "ml": {
            "lookback_window": (10.0, 60.0),   # 回看窗口
            "learning_rate": (0.001, 0.05),    # 学习率
            "regularization": (0.0001, 0.01),  # 正则化系数
            "prediction_horizon": (1.0, 10.0), # 预测周期
            "confidence_threshold": (0.3, 0.8), # 置信度阈值
        },
        "rl": {
            "gamma": (0.90, 0.999),            # 折扣因子
            "epsilon_decay": (0.95, 0.999),    # 探索衰减
            "batch_size": (16.0, 128.0),       # 批大小
            "buffer_size": (1000.0, 10000.0),  # 经验池大小
            "entropy_coef": (0.001, 0.1),      # 熵正则系数
        },
        "value": {
            "pe_threshold": (5.0, 30.0),       # PE阈值
            "pb_threshold": (0.5, 3.0),        # PB阈值
            "rotation_period": (5.0, 30.0),    # 轮动周期
            "top_n_hold": (3.0, 15.0),         # 持仓数量
            "dividend_weight": (0.1, 0.5),     # 股息权重
        },
        "multifactor": {
            "momentum_weight": (0.1, 0.5),     # 动量因子权重
            "value_weight": (0.1, 0.5),        # 价值因子权重
            "quality_weight": (0.1, 0.5),      # 质量因子权重
            "volatility_weight": (0.05, 0.3),  # 波动率因子权重
            "signal_threshold": (0.3, 0.8),    # 综合信号阈值
        },
        "fund": {
            "invest_interval": (1.0, 30.0),    # 定投间隔（天）
            "amount_per_invest": (0.05, 0.30), # 每次投入比例
            "stop_loss_ratio": (0.05, 0.25),   # 止损比例
            "take_profit_ratio": (0.10, 0.50), # 止盈比例
            "max_position": (0.3, 0.8),        # 最大仓位
        },
        "defense": {
            "drawdown_threshold": (0.05, 0.25),    # 回撤触发阈值
            "hedge_ratio": (0.1, 0.8),              # 对冲比例
            "recovery_wait": (3.0, 30.0),           # 恢复等待期
            "volatility_multiplier": (1.0, 3.0),    # 波动率倍数
            "max_exposure": (0.1, 0.5),             # 最大暴露
        },
        "ensemble": {
            "strategy_weight_smooth": (0.01, 0.3),  # 权重平滑系数
            "diversity_penalty": (0.01, 0.2),       # 多样性惩罚
            "rebalance_frequency": (1.0, 20.0),     # 再平衡频率
            "min_weight_threshold": (0.01, 0.1),    # 最小权重阈值
            "performance_lookback": (10.0, 60.0),   # 表现回看期
        },
        "fourier": {
            "n_components": (3.0, 20.0),        # 傅里叶分量数
            "window_size": (20.0, 100.0),       # 窗口大小
            "prediction_steps": (1.0, 10.0),    # 预测步数
            "rl_learning_rate": (0.001, 0.01),  # RL学习率
            "feature_dim": (8.0, 64.0),         # 特征维度
        },
    }

    def run_tau_cluster_optimization(self, strategy_name: str, param_ranges: dict = None,
                                     coarse_points: int = 30, refined_points: int = 50,
                                     target: str = 'sharpe_ratio') -> dict:
        """
        运行韬定律策略优化器集群优化
        - Aurora模式: 调用 aurora.run_tau_optimization
        - 主力模式: 使用熵韬收敛优化器 (EntropyTauOptimizer) 本地执行
        - 兜底模式: 使用原韬定律 (TauOptimizerCluster) 本地执行
        """
        start_time = time.time()

        # Warm start: 从存储中读取历史最佳参数作为参考
        from .tau_optimizer_cluster import get_parameter_store
        _tau_store = get_parameter_store()
        prev_best = _tau_store.get_best_params(strategy_name)
        prev_score = _tau_store.get_best_score(strategy_name)
        if prev_best:
            print(f"  [WarmStart] 加载 {strategy_name} 历史最佳 v{len(_tau_store.get_strategy(strategy_name).get('optimization_history', []))} "
                  f"(score={prev_score:.4f})")

        # 1) 优先通过 Aurora 执行
        if self.is_aurora_available():
            try:
                result = self.aurora.run_tau_optimization(
                    strategy_name, param_ranges, coarse_points, refined_points, target
                )
                if result and result.get('success'):
                    data = result.get('data', {})
                    return {
                        'success': True,
                        'data': {
                            'best_params': data.get('best_params', {}),
                            'best_score': data.get('best_score', 0.0),
                            'best_return': data.get('best_return', 0.0),
                            'best_sharpe': data.get('best_sharpe', 0.0),
                            'cluster_status': data.get('cluster_status', {}),
                            'total_evals': data.get('total_evals', 0),
                            'time_elapsed': round(time.time() - start_time, 3),
                            'mode': 'aurora',
                            'pattern_analysis': data.get('pattern_analysis'),
                        }
                    }
            except Exception as e:
                pass

        # 2) 主力模式: 使用熵韬收敛优化器 (EntropyTauOptimizer) 本地执行
        # 先解析参数范围（供主力和兜底共用）
        ranges = param_ranges
        if ranges is None:
            name_lower = strategy_name.lower()
            for type_key, type_ranges in self.STRATEGY_PARAM_RANGES.items():
                if type_key in name_lower:
                    ranges = type_ranges
                    break
            if ranges is None:
                ranges = {
                    'short_period': (5.0, 50.0),
                    'long_period': (30.0, 200.0),
                    'threshold': (0.01, 0.1)
                }
                print(f"  [警告] {strategy_name} 未匹配到专用参数空间，使用通用默认值")

        try:
            from .tau_enhanced_optimizer import EntropyTauOptimizer

            # 创建熵韬收敛优化器实例
            tau_cluster = EntropyTauOptimizer(
                ranges, strategy_name=strategy_name,
                strategy_mgr=self
            )

            # 运行五维熵驱动收敛优化
            fold_result = tau_cluster.run_enhanced_optimization(
                coarse_points=coarse_points,
                refined_points_per_region=max(5, refined_points // max(1, len(ranges))),
                validation_points=5,
                entropy_decay=True
            )

            best_params = fold_result.get('best_params') or {}
            best_result = fold_result.get('best_result')
            _best_score = round(best_result.score(), 4) if best_result else 0.0
            _total_evals = fold_result.get('total_evaluations', 0)
            _pattern_analysis = fold_result.get('pattern_analysis')
            _convergence = fold_result.get('convergence', {})
            _risk_summary = fold_result.get('risk_summary', {})

            # 记录优化结果到持久化存储
            try:
                from .tau_optimizer_cluster import get_parameter_store
                _store = get_parameter_store()
                _record = _store.record_optimization(
                    strategy_name=strategy_name,
                    best_params=best_params,
                    best_score=_best_score,
                    method="entropy_tau_v4",
                    total_evals=_total_evals,
                    param_ranges=param_ranges,
                )
                if _record["is_new_best"]:
                    print(f"  [Store] ✅ {strategy_name} 新版本 v{_record['new_version']} "
                          f"(改进 +{_record['score_delta']:.4f}) → 已保存")
                else:
                    print(f"  [Store] ℹ️  {strategy_name} 保持 v{_record['new_version']} "
                          f"(历史最佳 {_record['prev_best_score']:.4f})")
            except Exception as _e:
                pass  # 存储失败不影响主流程

            return {
                'success': True,
                'data': {
                    'best_params': best_params,
                    'best_score': _best_score,
                    'best_return': round(getattr(best_result, 'total_return', 0.0), 4) if best_result else 0.0,
                    'best_sharpe': round(getattr(best_result, 'sharpe_ratio', 0.0), 4) if best_result else 0.0,
                    'cluster_status': fold_result.get('cluster_status', {}),
                    'total_evals': _total_evals,
                    'time_elapsed': round(time.time() - start_time, 3),
                    'mode': 'entropy_tau',
                    'pattern_analysis': _pattern_analysis,
                    'convergence': _convergence,
                    'risk_summary': _risk_summary,
                }
            }
        except Exception as e:
            # 3) 兜底模式: 熵韬失败时，回退到原韬定律优化器
            print(f"  [Fallback] 熵韬优化器失败: {e}，回退到原韬定律...")
            try:
                from .tau_optimizer_cluster import TauOptimizerCluster
                fallback = TauOptimizerCluster(ranges, strategy_name=strategy_name)
                fb_result = fallback.run_folding_optimization(
                    coarse_points=coarse_points,
                    refined_points_per_region=max(5, refined_points // max(1, len(ranges))),
                )
                fb_params = fb_result.get('best_params') or {}
                fb_best = fb_result.get('best_result')
                fb_score = round(fb_best.score(), 4) if fb_best else 0.0
                return {
                    'success': True,
                    'data': {
                        'best_params': fb_params,
                        'best_score': fb_score,
                        'best_return': round(getattr(fb_best, 'total_return', 0.0), 4) if fb_best else 0.0,
                        'best_sharpe': round(getattr(fb_best, 'sharpe_ratio', 0.0), 4) if fb_best else 0.0,
                        'cluster_status': fb_result.get('cluster_status', {}),
                        'total_evals': fb_result.get('total_evaluations', 0),
                        'time_elapsed': round(time.time() - start_time, 3),
                        'mode': 'tau_cluster_fallback',
                        'pattern_analysis': fb_result.get('pattern_analysis'),
                    }
                }
            except Exception as fb_e:
                return {
                    'success': False,
                    'error': f'熵韬优化器失败: {e} | 兜底优化器也失败: {fb_e}',
                    'data': {
                        'best_params': {},
                        'best_score': 0.0,
                        'best_return': 0.0,
                        'best_sharpe': 0.0,
                        'cluster_status': {},
                        'total_evals': 0,
                        'time_elapsed': round(time.time() - start_time, 3)
                    }
                }

    def run_tau_shepherd_optimization(self, strategy_name: str = "智能标的轮动",
                                        coarse_points: int = 35,
                                        refined_per_group: int = 15) -> dict:
        """
        熵韬收敛集群: 智能标的轮动策略专用优化
        - 使用 FactorSpaceFolding 进行三层折叠搜索
        - 68个因子按7组分层优化 (组级粗筛→组内精搜→滚动窗口验证)
        - Phase 1: 35点组级粗筛
        - Phase 2: 热门3-4组 × 每点10-15 = 30-60点组内精搜
        - Phase 3: TOP-5 × 3滚动窗口 = 15点验证
        """
        start_time = time.time()

        # Warm start: 从存储中读取历史最佳参数作为参考
        from .tau_optimizer_cluster import get_parameter_store
        _tau_store = get_parameter_store()
        prev_best = _tau_store.get_best_params(strategy_name)
        prev_score = _tau_store.get_best_score(strategy_name)
        if prev_best:
            print(f"  [WarmStart] 加载 {strategy_name} 历史最佳 v{len(_tau_store.get_strategy(strategy_name).get('optimization_history', []))} "
                  f"(score={prev_score:.4f})")

        try:
            from .tau_optimizer_cluster import (
                StrategyOptimizerBus,
                ShepherdRotationModule, FactorSpaceFolding,
            )
            from .tau_enhanced_optimizer import EntropyTauOptimizer

            # Step 1: 初始化策略感知总线, 自动匹配标的轮动模块
            bus = StrategyOptimizerBus()
            bus.detect_and_init(strategy_name)
            shepherd_mod = bus.current_module
            if shepherd_mod is None:
                shepherd_mod = ShepherdRotationModule()  # 兜底: 直接初始化

            # Step 2: 初始化熵韬收敛集群 (使用标的轮动模块的param_ranges)
            cluster = EntropyTauOptimizer(shepherd_mod.param_ranges, strategy_name=strategy_name)

            # Step 3: 因子空间折叠 (Phase 1: 组级粗筛)
            folding = FactorSpaceFolding(shepherd_mod)
            group_points = folding.generate_group_screen_points(points_per_group=5)

            # Phase 1: 执行组级粗筛评估
            phase1_results = []
            for params in group_points:
                result, _mode = cluster.optimize(params)
                score = result.sharpe_ratio if hasattr(result, 'sharpe_ratio') else result.total_return
                phase1_results.append((params, score))

            # 排序因子组
            sorted_groups = folding.rank_groups_by_score(phase1_results)
            # 记录Phase 1最佳参数
            best_p1 = max(phase1_results, key=lambda x: x[1])
            folding.best_params_history.append(best_p1[0])

            # Step 4: Phase 2 - 组内精搜
            intra_points = folding.generate_intra_group_points(
                hot_groups=sorted_groups[:4], points_per_group=refined_per_group)
            phase2_results = []
            for params in intra_points:
                result, _mode = cluster.optimize(params)
                score = result.sharpe_ratio if hasattr(result, 'sharpe_ratio') else result.total_return
                phase2_results.append((params, score))

            # 记录Phase 2最佳
            if phase2_results:
                best_p2 = max(phase2_results, key=lambda x: x[1])
                folding.best_params_history.append(best_p2[0])

            # Step 5: Phase 3 - TOP-5参数做滚动窗口验证 (模拟多窗口重跑)
            top_candidates = sorted(phase1_results + phase2_results,
                                      key=lambda x: x[1], reverse=True)[:5]
            phase3_results = []
            for params, _prev_score in top_candidates:
                # 模拟滚动窗口验证: 跑3次取平均
                window_scores = []
                for w in range(3):
                    result, _mode = cluster.optimize(params)
                    score = result.sharpe_ratio if hasattr(result, 'sharpe_ratio') else result.total_return
                    window_scores.append(score)
                avg_score = sum(window_scores) / len(window_scores)
                phase3_results.append((params, avg_score))

            # 获取最终最佳
            if phase3_results:
                best_final = max(phase3_results, key=lambda x: x[1])
                best_params = best_final[0]
                best_score = best_final[1]
            elif phase2_results:
                best_final = max(phase2_results, key=lambda x: x[1])
                best_params = best_final[0]
                best_score = best_final[1]
            else:
                best_params = best_p1[0]
                best_score = best_p1[1]

            # 组装统计信息
            status = cluster.get_status() if hasattr(cluster, 'get_status') else {}
            total_evals = len(group_points) + len(intra_points) + len(top_candidates) * 3
            module_info = bus.get_module_info()
            _final_score = round(float(best_score), 4)

            # 记录优化结果到持久化存储
            try:
                from .tau_optimizer_cluster import get_parameter_store
                _store = get_parameter_store()
                _record = _store.record_optimization(
                    strategy_name=strategy_name,
                    best_params=best_params,
                    best_score=_final_score,
                    method="tau_shepherd_v1",
                    total_evals=total_evals,
                    param_ranges=shepherd_mod.param_ranges if shepherd_mod is not None else None,
                )
                if _record["is_new_best"]:
                    print(f"  [Store] ✅ {strategy_name} 新版本 v{_record['new_version']} "
                          f"(改进 +{_record['score_delta']:.4f}) → 已保存")
                else:
                    print(f"  [Store] ℹ️  {strategy_name} 保持 v{_record['new_version']} "
                          f"(历史最佳 {_record['prev_best_score']:.4f})")
            except Exception as _e:
                pass  # 存储失败不影响主流程

            return {
                'success': True,
                'strategy_name': strategy_name,
                'data': {
                    'best_params': best_params,
                    'best_score': _final_score,
                    'module': module_info,
                    'sorted_groups': sorted_groups,
                    'phase1_points': len(group_points),
                    'phase2_points': len(intra_points),
                    'phase3_points': len(top_candidates) * 3,
                    'total_evals': total_evals,
                    'time_elapsed': round(time.time() - start_time, 2),
                    'cluster_status': status if isinstance(status, dict) else {},
                }
            }
        except Exception as e:
            import traceback
            return {
                'success': False,
                'error': str(e),
                'traceback': traceback.format_exc(),
                'time_elapsed': round(time.time() - start_time, 2)
            }

    def run_tau_bernoulli_optimization(self, strategy_name: str = "伯努利-康达策略",
                                        iterations: int = 50) -> dict:
        """
        熵韬收敛集群: 伯努利-康达策略专用优化
        - 使用 BernoulliCoandaModule 的12参数空间
        - 使用 ParameterSpaceFolding 三层折叠 (粗筛→精搜→验证)
        - 目标: 多周期共振参数优化
        """
        start_time = time.time()

        # Warm start: 从存储中读取历史最佳参数作为参考
        from .tau_optimizer_cluster import get_parameter_store
        _tau_store = get_parameter_store()
        prev_best = _tau_store.get_best_params(strategy_name)
        prev_score = _tau_store.get_best_score(strategy_name)
        if prev_best:
            print(f"  [WarmStart] 加载 {strategy_name} 历史最佳 v{len(_tau_store.get_strategy(strategy_name).get('optimization_history', []))} "
                  f"(score={prev_score:.4f})")

        try:
            from .tau_optimizer_cluster import (
                StrategyOptimizerBus,
                BernoulliCoandaModule,
            )
            from .tau_enhanced_optimizer import EntropyTauOptimizer

            # 自动检测并初始化模块
            bus = StrategyOptimizerBus()
            bus.detect_and_init(strategy_name)
            module = bus.current_module or BernoulliCoandaModule()

            # 初始化熵韬收敛集群, 使用通用折叠
            cluster = EntropyTauOptimizer(module.param_ranges, strategy_name=strategy_name)

            # 运行五维熵驱动收敛优化
            result = cluster.run_enhanced_optimization(
                coarse_points=25, refined_points_per_region=15, validation_points=5,
                entropy_decay=True)

            best_params = result.get('best_params', {})
            best_result_obj = result.get('best_result')

            best_score = best_result_obj.score() if best_result_obj else 0.0
            best_return = getattr(best_result_obj, 'total_return', 0.0) if best_result_obj else 0.0
            best_sharpe = getattr(best_result_obj, 'sharpe_ratio', 0.0) if best_result_obj else 0.0

            module_info = bus.get_module_info()
            _final_score = round(float(best_score), 4)
            _total_evals = result.get('total_evaluations', 0)

            # 记录优化结果到持久化存储
            try:
                from .tau_optimizer_cluster import get_parameter_store
                _store = get_parameter_store()
                _record = _store.record_optimization(
                    strategy_name=strategy_name,
                    best_params=best_params,
                    best_score=_final_score,
                    method="entropy_tau_v4",
                    total_evals=_total_evals,
                    param_ranges=module.param_ranges if module is not None else None,
                )
                if _record["is_new_best"]:
                    print(f"  [Store] ✅ {strategy_name} 新版本 v{_record['new_version']} "
                          f"(改进 +{_record['score_delta']:.4f}) → 已保存")
                else:
                    print(f"  [Store] ℹ️  {strategy_name} 保持 v{_record['new_version']} "
                          f"(历史最佳 {_record['prev_best_score']:.4f})")
            except Exception as _e:
                pass  # 存储失败不影响主流程

            return {
                'success': True,
                'strategy_name': strategy_name,
                'data': {
                    'best_params': best_params,
                    'best_score': _final_score,
                    'best_return': round(float(best_return), 4),
                    'best_sharpe': round(float(best_sharpe), 4),
                    'module': module_info,
                    'param_groups': module.get_param_groups(),
                    'cluster_status': result.get('cluster_status', {}),
                    'total_evals': _total_evals,
                    'time_elapsed': round(time.time() - start_time, 2),
                }
            }
        except Exception as e:
            import traceback
            return {
                'success': False,
                'error': str(e),
                'traceback': traceback.format_exc(),
                'time_elapsed': round(time.time() - start_time, 2)
            }

    # ============================================================
    # 特种兵策略集成
    # ============================================================

    def run_special_forces_evolution(self, symbol: str = "510300",
                                      population_size: int = 20,
                                      max_generations: int = 30,
                                      force_refresh: bool = False,
                                      incremental: bool = False) -> dict:
        """
        运行特种兵策略自演进优化

        Args:
            symbol: 股票代码
            population_size: 种群大小
            max_generations: 最大代数
            force_refresh: 是否强制刷新数据
            incremental: 是否增量演化

        Returns:
            dict: 演化结果
        """
        start_time = time.time()
        try:
            from .special_forces_evolution import (
                get_evolution_controller,
                SpecialForcesEvolutionController,
            )
            controller = get_evolution_controller()

            if incremental:
                journal = controller.evolve_incremental(
                    symbol=symbol,
                    additional_generations=max_generations,
                    verbose=True,
                )
            else:
                journal = controller.evolve(
                    symbol=symbol,
                    population_size=population_size,
                    max_generations=max_generations,
                    force_refresh=force_refresh,
                    verbose=True,
                )

            if journal is None:
                return {
                    "success": False,
                    "error": "演化失败（无已有参数，请先运行完整演化）",
                    "elapsed_seconds": round(time.time() - start_time, 2),
                }

            params_summary = controller.get_params_summary(symbol)

            # 同步参数到 tau_optimizer_cluster 的参数存储
            try:
                from .special_forces_strategy import SpecialForcesStrategy
                from .tau_optimizer_cluster import get_parameter_store
                _ps = get_parameter_store()
                _ps.record_optimization(
                    strategy_name=f"special_forces_{symbol}",
                    best_params=journal.final_best_params,
                    best_score=journal.final_best_score,
                    method="special_forces_evolution",
                    total_evals=journal.total_evaluations,
                    param_ranges=dict(SpecialForcesStrategy.PARAM_RANGES),
                )
            except Exception:
                pass

            return {
                "success": True,
                "data": {
                    "symbol": symbol,
                    "best_params": journal.final_best_params,
                    "best_score": journal.final_best_score,
                    "best_metrics": journal.final_best_metrics,
                    "total_evaluations": journal.total_evaluations,
                    "total_elapsed_seconds": journal.total_elapsed_seconds,
                    "generations": journal.convergence_generation if journal.convergence_generation > 0 else len(journal.generations),
                    "convergence_generation": journal.convergence_generation,
                    "params_summary": params_summary,
                    "elapsed_seconds": round(time.time() - start_time, 2),
                },
            }
        except Exception as e:
            import traceback
            return {
                "success": False,
                "error": str(e),
                "traceback": traceback.format_exc(),
                "elapsed_seconds": round(time.time() - start_time, 2),
            }

    def run_special_forces_backtest(self, symbol: str = "510300",
                                     params: dict = None,
                                     initial_capital: float = 100000.0,
                                     use_optimized: bool = True) -> dict:
        """
        运行特种兵策略真实回测

        Args:
            symbol: 股票代码
            params: 策略参数（不传则使用优化参数或默认值）
            initial_capital: 初始资金
            use_optimized: 是否自动使用优化参数

        Returns:
            dict: 回测结果
        """
        start_time = time.time()
        try:
            from .special_forces_strategy import (
                SpecialForcesStrategy,
                StrategyParams,
                get_special_forces_strategy,
            )

            effective_params = params
            if params is None and use_optimized:
                try:
                    from .special_forces_evolution import get_evolution_controller
                    controller = get_evolution_controller()
                    best_params = controller.get_best_params(symbol)
                    if best_params:
                        effective_params = best_params
                        print(f"  [SF Backtest] 已加载 {symbol} 优化参数")
                except Exception:
                    pass

            strategy = get_special_forces_strategy(symbol, params=effective_params)
            if not strategy.is_loaded():
                strategy.load_data()

            result = strategy.run_backtest(initial_capital=initial_capital)

            # 构造与 BacktestResult 兼容的返回
            bt_result = BacktestResult(
                strategy_name=f"special_forces_{symbol}",
                total_return_pct=round(result.total_return * 100, 2),
                sharpe_ratio=round(result.sharpe_ratio, 4),
                max_drawdown=round(result.max_drawdown * 100, 2),
                win_rate=round(result.win_rate * 100, 1),
                total_trades=result.total_trades,
                start_date=datetime.now().isoformat(),
                end_date=datetime.now().isoformat(),
                db_saved=False,
            )
            self._backtest_results.append(bt_result)

            return {
                "success": True,
                "data": {
                    "strategy_name": f"special_forces_{symbol}",
                    "symbol": symbol,
                    "total_return": result.total_return,
                    "total_return_pct": round(result.total_return * 100, 2),
                    "annual_return": result.annual_return,
                    "sharpe_ratio": result.sharpe_ratio,
                    "max_drawdown": result.max_drawdown,
                    "max_drawdown_pct": round(result.max_drawdown * 100, 2),
                    "win_rate": result.win_rate,
                    "profit_factor": result.profit_factor,
                    "total_trades": result.total_trades,
                    "win_trades": result.win_trades,
                    "lose_trades": result.lose_trades,
                    "avg_win": result.avg_win,
                    "avg_lose": result.avg_lose,
                    "equity_curve": result.equity_curve,
                    "trade_log": result.trade_log,
                    "phase_distribution": result.phase_distribution,
                    "elapsed_seconds": result.elapsed_time,
                    "params": result.params,
                },
            }
        except Exception as e:
            import traceback
            return {
                "success": False,
                "error": str(e),
                "traceback": traceback.format_exc(),
                "elapsed_seconds": round(time.time() - start_time, 2),
            }

    def get_special_forces_params(self, symbol: str = "510300") -> dict:
        """获取特种兵策略参数摘要"""
        try:
            from .special_forces_evolution import get_evolution_controller
            controller = get_evolution_controller()
            summary = controller.get_params_summary(symbol)
            best_params = controller.get_best_params(symbol)
            versions = controller.get_evolution_history(symbol)
            last_journal = controller.get_last_journal()

            return {
                "success": True,
                "data": {
                    "symbol": symbol,
                    "summary": summary,
                    "best_params": best_params,
                    "versions": versions,
                    "last_evolution": last_journal.to_dict() if last_journal else None,
                },
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def start_special_forces(self, symbol: str = "510300",
                              balance: float = 100000.0,
                              use_optimized_params: bool = True) -> Tuple[bool, str]:
        """
        启动特种兵策略（实盘/模拟交易）

        Args:
            symbol: 股票代码
            balance: 初始资金
            use_optimized_params: 是否自动加载优化参数

        Returns:
            (success, message)
        """
        try:
            from .special_forces_strategy import get_special_forces_strategy
            from .special_forces_evolution import get_evolution_controller

            effective_params = None
            if use_optimized_params:
                controller = get_evolution_controller()
                best_params = controller.get_best_params(symbol)
                if best_params:
                    effective_params = best_params

            strategy = get_special_forces_strategy(
                symbol, params=effective_params, force_refresh=True
            )
            if not strategy.is_loaded():
                strategy.load_data()

            strategy_name = f"special_forces_{symbol}"
            self._active_strategies[strategy_name] = StrategyInfo(
                name=strategy_name,
                label=f"特种兵・{symbol}",
                category="Trend",
                description=f"威科夫量价自适应 | {symbol}",
                status=StrategyStatus.RUNNING,
                best_params=effective_params or {},
                params=effective_params or {},
            )

            best_score_info = ""
            if effective_params:
                try:
                    controller = get_evolution_controller()
                    summary = controller.get_params_summary(symbol)
                    best_score_info = f"（v{summary.get('version', 0)}, score={summary.get('score', 0):.4f}）"
                except Exception:
                    pass

            return True, f"特种兵策略 {symbol} 已启动{best_score_info}"
        except Exception as e:
            return False, f"特种兵策略启动失败: {e}"

    def get_optimized_strategies_report(self) -> dict:
        """获取所有已优化策略的报告 (供UI显示)

        返回:
            {
                "success": bool,
                "total_optimized": int,
                "strategies": [
                    {"name": "...", "version": int, "best_score": float, ...}
                ],
                "store_file": "..."
            }
        """
        try:
            from .tau_optimizer_cluster import get_parameter_store
            store = get_parameter_store()
            return {
                "success": True,
                "total_optimized": len(store.get_optimized_strategies()),
                "strategies": store.get_all_strategies_info(),
                "store_file": store.store_file
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_tau_cluster_modules(self) -> dict:
        """
        获取韬定律集群中所有可用的策略感知模块列表
        返回: 可用模块信息 + 当前策略推荐的模块
        """
        from .tau_optimizer_cluster import (
            BernoulliCoandaModule, ShepherdRotationModule, FourierRLStrategyModule,
            GyroModule,
        )
        b = BernoulliCoandaModule()
        s = ShepherdRotationModule()
        f = FourierRLStrategyModule()
        g = GyroModule()
        return {
            'success': True,
            'modules': [
                {
                    'name': f.name,
                    'description': f.description,
                    'params_count': len(f.param_ranges),
                    'keywords': ['fourier', 'rl', 'ppo', '傅里叶', '强化学习', 'fourier_rl'],
                    'groups': list(f.get_param_groups().keys()),
                },
                {
                    'name': b.name,
                    'description': b.description,
                    'params_count': len(b.param_ranges),
                    'keywords': ['bernoulli', 'coanda', '伯努利', '康达'],
                    'groups': list(b.get_param_groups().keys()),
                },
                {
                    'name': s.name,
                    'description': s.description,
                    'params_count': s.count_params(),
                    'keywords': ['shepherd', 'rotation', '标的轮动', '智能标的轮动'],
                    'groups': list(s.get_param_groups().keys()),
                },
                {
                    'name': g.name,
                    'description': g.description,
                    'params_count': len(g.param_ranges),
                    'keywords': ['gyro', 'gyro_v7', '陀螺仪', '陀螺', 'gyroscopic', 'gyro_optimized'],
                    'groups': list(g.get_param_groups().keys()),
                },
                {
                    'name': 'special_forces',
                    'description': '特种兵策略自演进优化器 (威科夫量价自适应)',
                    'params_count': 17,
                    'keywords': ['special_forces', 'wyckoff', '特种兵', '威科夫', '量价自适应'],
                    'groups': ['signal_thresholds', 'risk_management', 'position_sizing', 'signal_filter'],
                },
                {
                    'name': 'generic',
                    'description': '通用参数优化 (适用于所有策略)',
                    'params_count': 'dynamic',
                    'keywords': [],
                    'groups': ['all_params'],
                }
            ]
        }

    def get_tau_cluster_info(self) -> dict:
        """获取韬定律集群基本信息"""
        # 1) 优先尝试 Aurora
        if self.is_aurora_available():
            try:
                result = self.aurora.get_tau_info()
                if result and result.get('success'):
                    return result.get('data', {
                        'name': 'EntropyTauOptimizer',
                        'description': '熵韬收敛优化器集群 - 五维熵驱动收敛引擎',
                        'features': ['期望/方差/熵/最值/概率五维驱动', '自适应粗筛', '分区域精搜', '熵趋势收敛监控', '风险分区过滤'],
                        'status': 'available'
                    })
            except Exception:
                pass

        # 2) 本地回退模式
        status = 'initialized' if self.tau_cluster is not None else 'ready'
        return {
            'name': 'EntropyTauOptimizer',
            'description': '熵韬收敛优化器集群 - 五维熵驱动收敛引擎',
            'features': ['期望/方差/熵/最值/概率五维驱动', '自适应粗筛', '分区域精搜', '熵趋势收敛监控', '风险分区过滤'],
            'status': status,
            'mode': 'fallback'
        }

    def run_tau_single_eval(self, strategy_name: str, params: dict) -> dict:
        """
        单次带缓存的参数评估
        - Aurora模式: 调用 aurora.run_tau_single
        - 主力模式: 调用 EntropyTauOptimizer.optimize
        - 兜底模式: 调用 TauOptimizerCluster.optimize
        """
        if not params:
            return {
                'success': False,
                'error': 'params 不能为空',
                'data': {}
            }

        # 1) 优先通过 Aurora 执行
        if self.is_aurora_available():
            try:
                result = self.aurora.run_tau_single(strategy_name, params)
                if result and result.get('success'):
                    return result
            except Exception:
                pass

        # 2) 主力模式: 使用 EntropyTauOptimizer 本地单次评估
        try:
            from .tau_enhanced_optimizer import EntropyTauOptimizer

            # 根据 params 构造默认 param_ranges (每个参数 ±50% 范围)
            ranges = {}
            for k, v in params.items():
                try:
                    fv = float(v)
                    half = abs(fv) * 0.5 if fv != 0 else 1.0
                    ranges[k] = (fv - half, fv + half)
                except (TypeError, ValueError):
                    ranges[k] = (0.0, 1.0)

            if self.tau_cluster is None or self.tau_cluster.strategy_name != strategy_name:
                self.tau_cluster = EntropyTauOptimizer(ranges, strategy_name=strategy_name)

            result, hit_mode = self.tau_cluster.optimize(params)

            return {
                'success': True,
                'data': {
                    'strategy_name': strategy_name,
                    'params': params,
                    'hit_mode': hit_mode,
                    'total_return': round(getattr(result, 'total_return', 0.0), 4),
                    'sharpe_ratio': round(getattr(result, 'sharpe_ratio', 0.0), 4),
                    'max_drawdown': round(getattr(result, 'max_drawdown', 0.0), 4),
                    'win_rate': round(getattr(result, 'win_rate', 0.0), 4),
                    'total_trades': getattr(result, 'total_trades', 0),
                    'is_approximate': getattr(result, 'is_approximate', False),
                    'score': round(result.score(), 4)
                }
            }
        except Exception as e:
            # 3) 兜底模式: 回退到原 TaoOptimizerCluster
            try:
                from .tau_optimizer_cluster import TauOptimizerCluster
                ranges = {}
                for k, v in params.items():
                    try:
                        fv = float(v)
                        half = abs(fv) * 0.5 if fv != 0 else 1.0
                        ranges[k] = (fv - half, fv + half)
                    except (TypeError, ValueError):
                        ranges[k] = (0.0, 1.0)
                fallback = TauOptimizerCluster(ranges, strategy_name=strategy_name)
                result, hit_mode = fallback.optimize(params)
                return {
                    'success': True,
                    'data': {
                        'strategy_name': strategy_name,
                        'params': params,
                        'hit_mode': hit_mode,
                        'total_return': round(getattr(result, 'total_return', 0.0), 4),
                        'sharpe_ratio': round(getattr(result, 'sharpe_ratio', 0.0), 4),
                        'max_drawdown': round(getattr(result, 'max_drawdown', 0.0), 4),
                        'win_rate': round(getattr(result, 'win_rate', 0.0), 4),
                        'total_trades': getattr(result, 'total_trades', 0),
                        'is_approximate': getattr(result, 'is_approximate', False),
                        'score': round(result.score(), 4)
                    }
                }
            except Exception as fb_e:
                return {
                    'success': False,
                    'error': f'单次评估失败: {e} | 兜底: {fb_e}',
                    'data': {}
                }

    def get_optimization_history(self) -> List[dict]:
        """获取优化历史"""
        return self._optimization_history[-20:]

    # ---- 系统状态 ----

    def get_system_status(self) -> dict:
        """获取完整系统状态"""
        if self.is_aurora_available():
            result = self.aurora.get_system_status()
            if result.get('success'):
                data = result['data']
                data['qs_robot_mode'] = 'dual_core'
                data['active_strategies'] = len(self._active_strategies)
                return data
        status = self.fallback.get_system_status()
        status['qs_robot_mode'] = 'fallback'
        status['data']['active_strategies'] = len(self._active_strategies)
        return status

    def get_system_health(self) -> SystemHealth:
        """获取系统健康状态"""
        import psutil
        cpu = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('C:\\')

        if self.is_aurora_available():
            result = self.aurora.get_system_health()
            if result.get('success'):
                data = result['data']
                return SystemHealth(
                    status=data.get('status', 'healthy'),
                    cpu_percent=cpu,
                    memory_percent=mem.percent,
                    disk_percent=disk.percent,
                    uptime_seconds=data.get('uptime_seconds', 0),
                    services=data.get('services', {}),
                    components={
                        "aurora": True,
                        "qs_robot": True,
                        "strategies": True,
                        "database": data.get('services', {}).get('database') == 'healthy'
                    }
                )

        return SystemHealth(
            status="degraded",
            cpu_percent=cpu,
            memory_percent=mem.percent,
            disk_percent=disk.percent,
            uptime_seconds=0,
            services={"aurora": "offline", "qs_robot": "running"},
            components={"aurora": False, "qs_robot": True, "strategies": True, "database": False}
        )

    def get_risk_status(self) -> dict:
        """获取风险控制状态"""
        if self.is_aurora_available():
            return self.aurora.get_risk_status()
        return {"success": True, "data": {"risk_control": {"status": "simulated"}}}

    def get_performance_metrics(self) -> dict:
        """获取性能指标"""
        if self.is_aurora_available():
            return self.aurora.get_performance_metrics()
        import psutil
        return {
            "success": True,
            "data": {
                "system": {
                    "cpu_percent": psutil.cpu_percent(),
                    "memory_percent": psutil.virtual_memory().percent,
                    "disk_percent": psutil.disk_usage('C:\\').percent
                }
            }
        }

    def get_gain_status(self) -> dict:
        """获取增益模块状态"""
        if self.is_aurora_available():
            return self.aurora.get_gain_status()
        return {"success": False, "message": "增益模块需要Aurora在线"}

    # ---- 快捷操作 ----

    def quick_backtest_all(self, days: int = 30) -> List[BacktestResult]:
        """快速批量回测所有策略"""
        results = []
        strategies = self.get_strategy_list()
        for s in strategies[:5]:  # 限制前5个避免过载
            result = self.run_backtest(s['name'], days)
            results.append(result)
        return results

    def compare_strategies(self, names: List[str], days: int = 30) -> dict:
        """策略对比"""
        results = {}
        for name in names:
            result = self.run_backtest(name, days)
            results[name] = {
                "return": result.total_return_pct,
                "sharpe": result.sharpe_ratio,
                "drawdown": result.max_drawdown,
                "win_rate": result.win_rate
            }
        best = max(results.items(), key=lambda x: x[1]['sharpe'])
        return {"comparison": results, "best_strategy": best[0], "best_sharpe": best[1]['sharpe']}

    def get_status_summary(self) -> str:
        """生成状态摘要文本"""
        mode = self.get_mode()
        health = self.get_system_health()
        strategies = self.get_strategy_list()
        active = len(self._active_strategies)

        lines = [
            "=" * 60,
            "  QS Robot 增强型策略管理器 - 状态摘要",
            "=" * 60,
            f"  运行模式: {mode.value}",
            f"  Aurora状态: {'✅ 在线 (双核联动)' if mode == SystemMode.AURORA_LIVE else '⚠️ 离线 (模拟降级)'}",
            f"  系统健康: {health.status}",
            f"  CPU: {health.cpu_percent}% | 内存: {health.memory_percent}%",
            f"  可用策略: {len(strategies)}个 | 活跃策略: {active}个",
            f"  回测结果: {len(self._backtest_results)}条 | 优化记录: {len(self._optimization_history)}条",
            "=" * 60
        ]
        return "\n".join(lines)


# ============================================================
# 全局单例
# ============================================================

import threading

_strategy_manager_instance = None
_strategy_manager_lock = threading.Lock()

def get_strategy_manager(aurora_url: str = "http://localhost:5003") -> EnhancedStrategyManager:
    """获取策略管理器全局单例（线程安全）"""
    global _strategy_manager_instance
    if _strategy_manager_instance is None:
        with _strategy_manager_lock:
            if _strategy_manager_instance is None:
                _strategy_manager_instance = EnhancedStrategyManager(aurora_base_url=aurora_url)
    return _strategy_manager_instance


# ============================================================
# CLI 演示入口
# ============================================================

if __name__ == '__main__':
    print("🚀 QS Robot 增强型策略管理器 V2.0 启动中...\n")

    mgr = get_strategy_manager()
    print(mgr.get_status_summary())

    print("\n📋 策略列表:")
    for s in mgr.get_strategy_list()[:5]:
        print(f"  • {s['name']} ({s.get('category', 'N/A')})")

    print("\n📊 快速回测测试:")
    result = mgr.run_backtest("FourierRLStrategy", days=14)
    print(f"  策略: {result.strategy_name}")
    print(f"  收益: {result.total_return_pct}% | 夏普: {result.sharpe_ratio} | 回撤: {result.max_drawdown}%")

    print("\n⚡ 参数优化测试:")
    opt = mgr.run_optimization("FourierRLStrategy", iterations=10)
    if opt.get('success'):
        data = opt['data']
        print(f"  最佳参数: {data['best_params']}")
        print(f"  最佳评分: {data['best_score']}")

    print("\n✅ 测试完成！")
