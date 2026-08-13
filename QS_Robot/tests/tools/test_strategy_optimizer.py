"""策略优化器单元测试
验证 ShepherdOptimizer / TauOptimizer 的架构正确性：
- 参数空间校验
- 收敛性（迭代后分数应提升）
- 帕累托前沿（非支配解数量）
- 空参数/边界参数/极端数据容错
"""
import math
import random
import pytest
from typing import Any


def mock_evaluate(params: dict) -> dict:
    """模拟评估函数：参数越接近最优值分数越高"""
    optimal = {"fast": 12, "slow": 26, "signal": 9}
    score = 0.0
    for k, v in params.items():
        opt = optimal.get(k, v)
        score -= (v - opt) ** 2
    sharpe = 1.0 + score / 100
    max_dd = max(0.02, 0.1 - score / 500)
    return {"score": max(score, -10), "sharpe": max(sharpe, -2), "max_drawdown": max_dd, "win_rate": 0.45}


class TestShepherdOptimizer:
    """牧羊人优化器测试"""

    @pytest.fixture
    def optimizer(self):
        from core.shepherd_optimizer import ShepherdOptimizer, ShepherdVersion
        return ShepherdOptimizer(version=ShepherdVersion.V6)

    @pytest.fixture
    def param_ranges(self):
        return {"fast": (5, 30), "slow": (20, 40), "signal": (5, 15)}

    def test_init(self, optimizer):
        """初始化后种群大小正确"""
        assert optimizer._population_size == 30
        assert optimizer._generations == 20
        assert optimizer._mutation_rate == 0.15
        assert optimizer._adaptive_mutation is True
        assert optimizer._debate_fusion is True

    def test_optimize_convergence(self, optimizer, param_ranges):
        """迭代后最优分数应 >= 初始分数"""
        result = optimizer.optimize(
            strategy_name="test_strategy",
            param_ranges=param_ranges,
            evaluate_func=mock_evaluate,
            iterations=10,
        )
        assert result.success
        assert result.total_evaluations > 0
        assert result.best_score > -100  # 不应极端差
        assert len(result.convergence_curve) > 0
        # 收敛：最后1/3的平均分应 >= 前1/3
        curve = result.convergence_curve
        third = len(curve) // 3
        if third > 0:
            first_avg = sum(curve[:third]) / third
            last_avg = sum(curve[-third:]) / third
            assert last_avg >= first_avg * 0.5, f"优化未收敛: first={first_avg:.2f} last={last_avg:.2f}"

    def test_pareto_front(self, optimizer, param_ranges):
        """帕累托前沿应有非支配解"""
        result = optimizer.optimize(
            strategy_name="test_strategy",
            param_ranges=param_ranges,
            evaluate_func=mock_evaluate,
            iterations=10,
        )
        assert result.success
        assert len(result.pareto_front) >= 1
        for c in result.pareto_front:
            assert c.score > -100
            assert c.sharpe > -10

    def test_empty_param_ranges(self, optimizer):
        """空参数空间应优雅处理"""
        result = optimizer.optimize(
            strategy_name="test",
            param_ranges={},
            evaluate_func=mock_evaluate,
            iterations=5,
        )
        assert not result.success or result.total_evaluations == 0

    def test_single_param(self, optimizer):
        """单参数优化"""
        result = optimizer.optimize(
            strategy_name="test",
            param_ranges={"fast": (5, 30)},
            evaluate_func=mock_evaluate,
            iterations=5,
        )
        assert result.success
        assert "fast" in result.best_params

    def test_v5_version(self, param_ranges):
        """V5优化器基本可用"""
        from core.shepherd_optimizer import ShepherdOptimizer, ShepherdVersion
        opt = ShepherdOptimizer(version=ShepherdVersion.V5)
        assert opt._population_size == 20
        assert opt._generations == 15
        result = opt.optimize("test", param_ranges, mock_evaluate, iterations=5)
        assert result.success

    def test_best_params_in_range(self, optimizer, param_ranges):
        """最优参数应在参数范围内"""
        result = optimizer.optimize("test", param_ranges, mock_evaluate, iterations=10)
        for k, v in result.best_params.items():
            low, high = param_ranges[k]
            assert low <= v <= high, f"{k}={v} out of [{low}, {high}]"

    def test_deterministic_seed(self, optimizer, param_ranges):
        """同seed应产生相同结果"""
        random.seed(42)
        import numpy as np
        np.random.seed(42)
        r1 = optimizer.optimize("test", param_ranges, mock_evaluate, iterations=5)

        random.seed(42)
        np.random.seed(42)
        r2 = optimizer.optimize("test", param_ranges, mock_evaluate, iterations=5)

        assert r1.best_score == r2.best_score
        assert r1.best_params == r2.best_params


class TestOptimizerEdgeCases:
    """优化器边界场景测试"""

    def test_constant_evaluate(self):
        """评估函数返回常数 → 优化器应完成而不崩溃"""
        from core.shepherd_optimizer import ShepherdOptimizer, ShepherdVersion
        opt = ShepherdOptimizer(version=ShepherdVersion.V6)
        result = opt.optimize("test", {"a": (0, 10)}, lambda p: {"score": 0, "sharpe": 0, "max_drawdown": 0, "win_rate": 0}, iterations=5)
        assert result.success

    def test_extreme_evaluate(self):
        """评估函数返回极端值"""
        from core.shepherd_optimizer import ShepherdOptimizer, ShepherdVersion
        opt = ShepherdOptimizer(version=ShepherdVersion.V6)
        result = opt.optimize("test", {"a": (0, 10)}, lambda p: {"score": 1e9, "sharpe": 100, "max_drawdown": 0.001, "win_rate": 0.99}, iterations=5)
        assert result.success
        assert result.best_score > 0

    def test_nan_evaluate(self):
        """评估函数返回NaN → 应优雅处理"""
        from core.shepherd_optimizer import ShepherdOptimizer, ShepherdVersion
        opt = ShepherdOptimizer(version=ShepherdVersion.V6)
        result = opt.optimize("test", {"a": (0, 10)}, lambda p: {"score": float("nan"), "sharpe": 0, "max_drawdown": 0, "win_rate": 0}, iterations=5)
        assert result.success
        assert not math.isnan(result.best_score)


class TestStrategyParamValidation:
    """策略参数校验测试"""

    @pytest.fixture
    def strategy(self):
        import importlib
        mod = importlib.import_module("core.strategies.ths_strategies.14_strategies.01_macd_wave")
        return mod.MACDWaveStrategy()

    def test_valid_params(self, strategy):
        """默认参数应通过校验"""
        assert strategy.validate_params({"fast": 12, "slow": 26, "signal": 9})

    def test_fast_greater_than_slow(self, strategy):
        """fast >= slow 应失败"""
        assert not strategy.validate_params({"fast": 30, "slow": 20, "signal": 9})

    def test_out_of_range(self, strategy):
        """参数超出范围应失败"""
        assert not strategy.validate_params({"fast": 0, "slow": 26, "signal": 9})
        assert not strategy.validate_params({"fast": 12, "slow": 50, "signal": 9})
        assert not strategy.validate_params({"fast": 12, "slow": 26, "signal": 0})

    def test_boundary_values(self, strategy):
        """边界值应通过"""
        assert strategy.validate_params({"fast": 5, "slow": 20, "signal": 5})
        assert strategy.validate_params({"fast": 30, "slow": 40, "signal": 15})

    def test_missing_param(self, strategy):
        """缺少参数使用默认值→通过"""
        assert strategy.validate_params({})

    def test_param_space_structure(self, strategy):
        """参数空间结构正确"""
        space = strategy.get_param_space()
        assert "fast" in space
        assert "slow" in space
        assert "signal" in space
        for k, v in space.items():
            assert isinstance(v, tuple)
            assert len(v) == 2
            assert v[0] < v[1]


class TestOptimizerStrategyIntegration:
    """优化器与真实策略集成测试"""

    def test_optimize_macd_with_mock(self):
        """用Mock数据测试完整优化流程"""
        import importlib
        from core.shepherd_optimizer import ShepherdOptimizer, ShepherdVersion

        mod = importlib.import_module("core.strategies.ths_strategies.14_strategies.01_macd_wave")
        strategy = mod.MACDWaveStrategy()

        # 生成Mock数据
        random.seed(42)
        bars = []
        price = 10.0
        from datetime import datetime, timedelta
        base = datetime(2024, 1, 2)
        for i in range(200):
            date = base + timedelta(days=i)
            if date.weekday() >= 5:
                continue
            price = price * (1 + random.gauss(0.001, 0.02))
            bars.append({
                "date": date.strftime("%Y-%m-%d"), "open": price * 0.99,
                "high": price * 1.02, "low": price * 0.98,
                "close": price, "volume": int(random.uniform(500000, 2000000)),
            })

        def eval_fn(params):
            buys = sells = 0
            rets = []
            bp = None
            for i in range(len(bars)):
                window = bars[:i + 1]
                try:
                    sig = strategy.generate_signal(window, params)
                except Exception:
                    continue
                if sig is None:
                    continue
                if sig.get("action") == "buy" and bp is None:
                    bp = sig.get("price", bars[i]["close"])
                elif sig.get("action") == "sell" and bp is not None:
                    sp = sig.get("price", bars[i]["close"])
                    rets.append((sp - bp) / bp)
                    sells += 1
                    bp = None
                if sig.get("action") == "buy":
                    buys += 1

            if not rets:
                return {"score": -10, "sharpe": -2, "max_drawdown": 0.5, "win_rate": 0}
            total_ret = sum(rets)
            max_dd = 0.0
            eq = 1.0
            peak = 1.0
            for r in rets:
                eq *= (1 + r)
                peak = max(peak, eq)
                max_dd = max(max_dd, (peak - eq) / peak)
            mean_r = total_ret / len(rets)
            std_r = math.sqrt(sum((r - mean_r) ** 2 for r in rets) / len(rets)) if len(rets) > 1 else 0.01
            sharpe = mean_r / std_r * math.sqrt(252) if std_r > 0 else 0
            return {"score": total_ret * 100, "sharpe": sharpe, "max_drawdown": max_dd, "win_rate": sum(1 for r in rets if r > 0) / len(rets)}

        param_ranges = {"fast": (5.0, 30.0), "slow": (20.0, 40.0), "signal": (5.0, 15.0)}
        opt = ShepherdOptimizer(version=ShepherdVersion.V6)
        result = opt.optimize("MACD顺势波段", param_ranges, eval_fn, iterations=10)

        assert result.success
        assert result.total_evaluations > 0
        assert "fast" in result.best_params
        assert "slow" in result.best_params
        assert "signal" in result.best_params
        # 快线应小于慢线
        assert result.best_params["fast"] < result.best_params["slow"]