"""
优化器Mock工具函数单元测试 - 边界情况
=====================================
测试 optimizer_bridge_mock.js 中 batchGenerateOptimizerMock
和 generateOptimizerHeatmapMock 的等价Python逻辑。

被测函数:
  - generateOptimizerMockResult(strategy, optimizer)
  - batchGenerateOptimizerMock(strategies, optimizers)
  - generateOptimizerHeatmapMock(strategies, optimizers)
  - formatOptimizerMockHTML(strategy, optimizer, result)
"""
import math
import random
import pytest
from datetime import datetime


# ══════════════════════════════════════════════════════
# 等价JS逻辑的Python实现（用于测试）
# ══════════════════════════════════════════════════════

OPTIMIZER_PARAM_RANGES = {
    "tau_cluster": {"sharpeRange": [1.2, 3.8], "drawdownRange": [3, 12], "iterRange": [80, 200]},
    "tau_enhanced_optimizer": {"sharpeRange": [1.0, 3.5], "drawdownRange": [5, 15], "iterRange": [60, 180]},
    "shepherd_optimizer": {"sharpeRange": [0.8, 3.0], "drawdownRange": [8, 18], "iterRange": [50, 150]},
    "gyro_optimizer": {"sharpeRange": [1.5, 4.0], "drawdownRange": [2, 10], "iterRange": [100, 250]},
    "genetic": {"sharpeRange": [0.5, 2.5], "drawdownRange": [10, 25], "iterRange": [30, 120]},
    "bayesian": {"sharpeRange": [0.8, 3.2], "drawdownRange": [6, 16], "iterRange": [40, 130]},
    "grid_search": {"sharpeRange": [0.3, 2.0], "drawdownRange": [12, 28], "iterRange": [20, 80]},
    "default": {"sharpeRange": [0.5, 3.0], "drawdownRange": [10, 20], "iterRange": [50, 150]},
}


def generate_optimizer_mock_result(strategy_name, optimizer_name):
    """等价于JS的 generateOptimizerMockResult"""
    range_ = OPTIMIZER_PARAM_RANGES.get(optimizer_name, OPTIMIZER_PARAM_RANGES["default"])
    sharpe = range_["sharpeRange"][0] + random.random() * (range_["sharpeRange"][1] - range_["sharpeRange"][0])
    drawdown = range_["drawdownRange"][0] + random.random() * (range_["drawdownRange"][1] - range_["drawdownRange"][0])
    iterations = int(range_["iterRange"][0] + random.random() * (range_["iterRange"][1] - range_["iterRange"][0]))
    return {
        "sharpe": round(sharpe, 4),
        "drawdown": round(drawdown, 2),
        "iterations": iterations,
        "params": {
            "u": round(0.1 + random.random() * 0.9, 2),
            "n": int(3 + random.random() * 7),
            "threshold": round(0.5 + random.random() * 0.5, 2),
        },
        "timestamp": datetime.now().isoformat(),
    }


def batch_generate_optimizer_mock(strategy_names, optimizer_names):
    """等价于JS的 batchGenerateOptimizerMock"""
    results = []
    for s in strategy_names:
        for o in optimizer_names:
            results.append({
                "strategy": s,
                "optimizer": o,
                "result": generate_optimizer_mock_result(s, o),
            })
    return results


def generate_optimizer_heatmap_mock(strategy_names, optimizer_names):
    """等价于JS的 generateOptimizerHeatmapMock"""
    matrix = []
    for s in strategy_names:
        row = []
        for o in optimizer_names:
            r = generate_optimizer_mock_result(s, o)
            row.append(round(r["sharpe"], 2))
        matrix.append(row)
    return {
        "strategies": strategy_names,
        "optimizers": optimizer_names,
        "matrix": matrix,
        "generated_at": datetime.now().isoformat(),
    }


# ══════════════════════════════════════════════════════
# 测试用例
# ══════════════════════════════════════════════════════


class TestGenerateOptimizerMockResult:
    """单次Mock结果生成"""

    def test_known_optimizer_returns_in_range(self):
        r = generate_optimizer_mock_result("test_strategy", "tau_cluster")
        assert 1.2 <= r["sharpe"] <= 3.8, f"sharpe {r['sharpe']} out of [1.2, 3.8]"
        assert 3 <= r["drawdown"] <= 12, f"drawdown {r['drawdown']} out of [3, 12]"
        assert 80 <= r["iterations"] <= 200, f"iterations {r['iterations']} out of [80, 200]"

    def test_unknown_optimizer_uses_default(self):
        r = generate_optimizer_mock_result("test", "nonexistent_optimizer")
        assert 0.5 <= r["sharpe"] <= 3.0, f"default sharpe {r['sharpe']} out of [0.5, 3.0]"
        assert 10 <= r["drawdown"] <= 20

    def test_empty_string_optimizer(self):
        r = generate_optimizer_mock_result("test", "")
        assert 0.5 <= r["sharpe"] <= 3.0

    def test_params_structure(self):
        r = generate_optimizer_mock_result("s1", "tau_cluster")
        assert "params" in r
        assert 0.1 <= r["params"]["u"] <= 1.0
        assert 3 <= r["params"]["n"] <= 9
        assert 0.5 <= r["params"]["threshold"] <= 1.0

    def test_timestamp_is_iso_format(self):
        r = generate_optimizer_mock_result("s", "o")
        assert "T" in r["timestamp"]
        datetime.fromisoformat(r["timestamp"])

    def test_all_optimizers_in_range(self):
        for name in OPTIMIZER_PARAM_RANGES:
            if name == "default":
                continue
            r = generate_optimizer_mock_result("s", name)
            rng = OPTIMIZER_PARAM_RANGES[name]
            assert rng["sharpeRange"][0] <= r["sharpe"] <= rng["sharpeRange"][1], \
                f"{name}: sharpe {r['sharpe']} out of {rng['sharpeRange']}"


class TestBatchGenerateOptimizerMock:
    """批量Mock生成"""

    def test_basic_combination(self):
        results = batch_generate_optimizer_mock(["s1", "s2"], ["o1", "o2"])
        assert len(results) == 4
        assert results[0]["strategy"] == "s1"
        assert results[0]["optimizer"] == "o1"
        assert results[3]["strategy"] == "s2"
        assert results[3]["optimizer"] == "o2"

    def test_empty_strategies(self):
        results = batch_generate_optimizer_mock([], ["o1", "o2"])
        assert results == []

    def test_empty_optimizers(self):
        results = batch_generate_optimizer_mock(["s1", "s2"], [])
        assert results == []

    def test_empty_both(self):
        results = batch_generate_optimizer_mock([], [])
        assert results == []

    def test_single_strategy_multi_optimizer(self):
        results = batch_generate_optimizer_mock(["s1"], ["o1", "o2", "o3"])
        assert len(results) == 3
        assert all(r["strategy"] == "s1" for r in results)

    def test_multi_strategy_single_optimizer(self):
        results = batch_generate_optimizer_mock(["s1", "s2", "s3"], ["o1"])
        assert len(results) == 3
        assert all(r["optimizer"] == "o1" for r in results)

    def test_large_batch(self):
        results = batch_generate_optimizer_mock(
            [f"s{i}" for i in range(50)],
            [f"o{i}" for i in range(20)]
        )
        assert len(results) == 1000

    def test_each_result_has_required_keys(self):
        results = batch_generate_optimizer_mock(["s1"], ["o1"])
        for r in results:
            assert "strategy" in r
            assert "optimizer" in r
            assert "result" in r
            assert "sharpe" in r["result"]
            assert "drawdown" in r["result"]
            assert "iterations" in r["result"]

    def test_duplicate_strategy_names(self):
        results = batch_generate_optimizer_mock(["s1", "s1"], ["o1"])
        assert len(results) == 2
        assert results[0]["strategy"] == results[1]["strategy"]


class TestGenerateOptimizerHeatmapMock:
    """热力图Mock生成"""

    def test_basic_heatmap(self):
        h = generate_optimizer_heatmap_mock(["s1", "s2"], ["o1", "o2", "o3"])
        assert h["strategies"] == ["s1", "s2"]
        assert h["optimizers"] == ["o1", "o2", "o3"]
        assert len(h["matrix"]) == 2
        assert len(h["matrix"][0]) == 3
        assert len(h["matrix"][1]) == 3

    def test_empty_strategies(self):
        h = generate_optimizer_heatmap_mock([], ["o1", "o2"])
        assert h["strategies"] == []
        assert h["matrix"] == []

    def test_empty_optimizers(self):
        h = generate_optimizer_heatmap_mock(["s1"], [])
        assert h["optimizers"] == []
        assert h["matrix"] == [[]]

    def test_empty_both(self):
        h = generate_optimizer_heatmap_mock([], [])
        assert h["matrix"] == []

    def test_matrix_values_are_numeric(self):
        h = generate_optimizer_heatmap_mock(["s1", "s2"], ["o1", "o2"])
        for row in h["matrix"]:
            for val in row:
                assert isinstance(val, (int, float)), f"Expected numeric, got {type(val)}"
                assert 0.1 <= val <= 5.0, f"sharpe {val} out of reasonable range"

    def test_generated_at_timestamp(self):
        h = generate_optimizer_heatmap_mock(["s1"], ["o1"])
        assert "generated_at" in h
        datetime.fromisoformat(h["generated_at"])

    def test_single_cell_heatmap(self):
        h = generate_optimizer_heatmap_mock(["s1"], ["o1"])
        assert len(h["matrix"]) == 1
        assert len(h["matrix"][0]) == 1

    def test_matrix_shape_consistency(self):
        h = generate_optimizer_heatmap_mock(
            [f"s{i}" for i in range(10)],
            [f"o{i}" for i in range(5)]
        )
        assert len(h["matrix"]) == 10
        assert all(len(row) == 5 for row in h["matrix"])


class TestFormatOptimizerMockHTML:
    """HTML格式化"""

    def test_high_sharpe_returns_green(self):
        result = {"sharpe": 3.0, "drawdown": 5.0, "iterations": 100, "params": {"u": 0.5, "n": 5}}
        color = _get_color(result["sharpe"])
        assert color == "#00c853"

    def test_medium_sharpe_returns_orange(self):
        result = {"sharpe": 1.8, "drawdown": 5.0, "iterations": 100, "params": {"u": 0.5, "n": 5}}
        color = _get_color(result["sharpe"])
        assert color == "#ffab40"

    def test_low_sharpe_returns_red(self):
        result = {"sharpe": 0.5, "drawdown": 5.0, "iterations": 100, "params": {"u": 0.5, "n": 5}}
        color = _get_color(result["sharpe"])
        assert color == "#ff5252"

    def test_boundary_sharpe_2_5(self):
        assert _get_color(2.5) == "#00c853"

    def test_boundary_sharpe_1_5(self):
        assert _get_color(1.5) == "#ffab40"

    def test_negative_sharpe(self):
        assert _get_color(-0.5) == "#ff5252"


def _get_color(sharpe):
    """等价于JS的 color 计算逻辑"""
    return "#00c853" if sharpe >= 2.5 else "#ffab40" if sharpe >= 1.5 else "#ff5252"


class TestIntegrationWithRealOptimizerNames:
    """集成测试：使用真实优化器名称"""

    REAL_STRATEGIES = ["fourier_rl", "bernoulli_coanda", "gyro", "shepherd_rotation"]
    REAL_OPTIMIZERS = ["tau_cluster", "gyro_optimizer", "genetic", "bayesian", "grid_search"]

    def test_batch_with_real_names(self):
        results = batch_generate_optimizer_mock(self.REAL_STRATEGIES, self.REAL_OPTIMIZERS)
        assert len(results) == 20

    def test_heatmap_with_real_names(self):
        h = generate_optimizer_heatmap_mock(self.REAL_STRATEGIES, self.REAL_OPTIMIZERS)
        assert len(h["matrix"]) == 4
        assert len(h["matrix"][0]) == 5

    def test_all_real_optimizers_have_ranges(self):
        for opt in self.REAL_OPTIMIZERS:
            assert opt in OPTIMIZER_PARAM_RANGES, f"Missing range for real optimizer: {opt}"

    def test_deterministic_with_seed(self):
        random.seed(42)
        r1 = generate_optimizer_mock_result("s", "tau_cluster")
        random.seed(42)
        r2 = generate_optimizer_mock_result("s", "tau_cluster")
        assert r1["sharpe"] == r2["sharpe"]
        assert r1["iterations"] == r2["iterations"]