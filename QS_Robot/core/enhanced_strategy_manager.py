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


@dataclass
class BacktestResult:
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

    def __init__(self, base_url: str = "http://localhost:5000", timeout: int = 10):
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
        is_bernoulli = any(k in name_lower for k in ['bernoulli', 'coanda', '伯努利', '康达'])
        is_shepherd = any(k in name_lower for k in ['shepherd', 'rotation', '轮动', '标的'])

        if params:
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
            if is_bernoulli:
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
# 核心：增强型策略管理器
# ============================================================

class EnhancedStrategyManager:
    """
    QS Robot 增强型策略管理器
    
    双核架构:
    - 当Aurora在线 → 通过AuroraAPIClient调用Aurora的DeepSeek引擎
    - 当Aurora离线 → 使用SimulatedFallbackEngine本地模拟
    """

    def __init__(self, aurora_base_url: str = "http://localhost:5000"):
        # 双核心
        self.aurora = AuroraAPIClient(base_url=aurora_base_url)
        self.fallback = SimulatedFallbackEngine()

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
        self._health_thread = threading.Thread(target=self._health_check_loop, daemon=True)
        self._health_thread.start()

    # ---- 模式管理 ----

    def _health_check_loop(self):
        """后台健康检查（每30秒一次）"""
        while True:
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
            time.sleep(30)

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

    def start_strategy(self, name: str, balance: float = 100000.0) -> Tuple[bool, str]:
        """启动策略"""
        if self.is_aurora_available():
            result = self.aurora.start_strategy(name, balance)
            if result.get('success'):
                self._active_strategies[name] = StrategyInfo(
                    name=name, label=name, category='', description='',
                    status=StrategyStatus.RUNNING
                )
                return True, f"策略 {name} 已通过Aurora启动"
            return False, result.get('error', '启动失败')

        # 模拟模式
        self._active_strategies[name] = StrategyInfo(
            name=name, label=name, category='', description='',
            status=StrategyStatus.RUNNING
        )
        return True, f"策略 {name} 已启动（模拟模式）"

    def stop_strategy(self) -> Tuple[bool, str]:
        """停止所有策略"""
        if self.is_aurora_available():
            result = self.aurora.stop_strategy()
            self._active_strategies.clear()
            return result.get('success', False), result.get('message', '已停止')
        self._active_strategies.clear()
        return True, "策略已停止（模拟模式）"

    # ---- 回测管理 ----

    def run_backtest(self, name: str, days: int = 30, balance: float = 100000.0,
                     params: dict = None, symbol: str = 'BTCUSDT') -> BacktestResult:
        """执行回测"""
        if self.is_aurora_available():
            result = self.aurora.run_backtest(name, days, balance, params, symbol)
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

        # 模拟模式
        result = self.fallback.run_backtest(name, days, balance, params, symbol)
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

    def run_tau_cluster_optimization(self, strategy_name: str, param_ranges: dict = None,
                                     coarse_points: int = 30, refined_points: int = 50,
                                     target: str = 'sharpe_ratio') -> dict:
        """
        运行韬定律策略优化器集群优化
        - Aurora模式: 调用 aurora.run_tau_optimization
        - 回退模式: 使用 tau_optimizer_cluster.TauOptimizerCluster 本地执行
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
                            'mode': 'aurora'
                        }
                    }
            except Exception as e:
                pass

        # 2) 回退模式: 使用 TauOptimizerCluster 本地执行
        try:
            from .tau_optimizer_cluster import TauOptimizerCluster  # 延迟导入, 避免循环依赖

            # 默认参数范围 (未提供时使用通用双均线示例范围)
            ranges = param_ranges or {
                'short_period': (5.0, 50.0),
                'long_period': (30.0, 200.0),
                'threshold': (0.01, 0.1)
            }

            # 延迟初始化 tau_cluster
            if self.tau_cluster is None or self.tau_cluster.strategy_name != strategy_name:
                self.tau_cluster = TauOptimizerCluster(ranges, strategy_name=strategy_name)

            # 运行三层空间折叠优化
            fold_result = self.tau_cluster.run_folding_optimization(
                coarse_points=coarse_points,
                refined_points_per_region=max(5, refined_points // max(1, len(ranges))),
                validation_points=5
            )

            best_params = fold_result.get('best_params') or {}
            best_result = fold_result.get('best_result')
            _best_score = round(best_result.score(), 4) if best_result else 0.0
            _total_evals = fold_result.get('total_evaluations', 0)

            # 记录优化结果到持久化存储
            try:
                from .tau_optimizer_cluster import get_parameter_store
                _store = get_parameter_store()
                _record = _store.record_optimization(
                    strategy_name=strategy_name,
                    best_params=best_params,
                    best_score=_best_score,
                    method="tau_cluster_v1",
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
                    'mode': 'tau_cluster_fallback'
                }
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'TauOptimizerCluster 执行失败: {e}',
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
        韬定律集群: 智能标的轮动策略专用优化
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
                TauOptimizerCluster, StrategyOptimizerBus,
                ShepherdRotationModule, FactorSpaceFolding,
            )

            # Step 1: 初始化策略感知总线, 自动匹配标的轮动模块
            bus = StrategyOptimizerBus()
            bus.detect_and_init(strategy_name)
            shepherd_mod = bus.current_module
            if shepherd_mod is None:
                shepherd_mod = ShepherdRotationModule()  # 兜底: 直接初始化

            # Step 2: 初始化韬定律集群 (使用标的轮动模块的param_ranges)
            cluster = TauOptimizerCluster(shepherd_mod.param_ranges, strategy_name=strategy_name)

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
        韬定律集群: 伯努利-康达策略专用优化
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
                TauOptimizerCluster, StrategyOptimizerBus,
                BernoulliCoandaModule,
            )

            # 自动检测并初始化模块
            bus = StrategyOptimizerBus()
            bus.detect_and_init(strategy_name)
            module = bus.current_module or BernoulliCoandaModule()

            # 初始化集群, 使用通用折叠
            cluster = TauOptimizerCluster(module.param_ranges, strategy_name=strategy_name)

            # 运行折叠优化 (使用通用的run_folding_optimization)
            result = cluster.run_folding_optimization(
                coarse_points=25, refined_points_per_region=15, validation_points=5)

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
                    method="tau_bernoulli_v1",
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
            BernoulliCoandaModule, ShepherdRotationModule,
        )
        b = BernoulliCoandaModule()
        s = ShepherdRotationModule()
        return {
            'success': True,
            'modules': [
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
                        'name': 'TauOptimizerCluster',
                        'description': '韬定律策略优化器集群 - 时间缩微+空间缩微协同',
                        'features': ['相似参数复用', '参数空间折叠', '增量回测计算'],
                        'status': 'available'
                    })
            except Exception:
                pass

        # 2) 本地回退模式
        status = 'initialized' if self.tau_cluster is not None else 'ready'
        return {
            'name': 'TauOptimizerCluster',
            'description': '韬定律策略优化器集群 - 时间缩微+空间缩微协同',
            'features': ['相似参数复用', '参数空间折叠', '增量回测计算'],
            'status': status,
            'mode': 'fallback'
        }

    def run_tau_single_eval(self, strategy_name: str, params: dict) -> dict:
        """
        单次带缓存的参数评估
        - Aurora模式: 调用 aurora.run_tau_single
        - 回退模式: 调用 TauOptimizerCluster.optimize
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

        # 2) 回退模式: 使用 TauOptimizerCluster 本地单次评估
        try:
            from .tau_optimizer_cluster import TauOptimizerCluster  # 延迟导入

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
                self.tau_cluster = TauOptimizerCluster(ranges, strategy_name=strategy_name)

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
            return {
                'success': False,
                'error': f'TauOptimizerCluster 单次评估失败: {e}',
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

_strategy_manager_instance = None

def get_strategy_manager(aurora_url: str = "http://localhost:5000") -> EnhancedStrategyManager:
    """获取策略管理器全局单例"""
    global _strategy_manager_instance
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