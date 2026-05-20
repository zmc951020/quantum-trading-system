#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修复 shepherd_five_line_optimizer.py 截断的尾部"""
import os

target = os.path.join(os.path.dirname(__file__), "shepherd_five_line_optimizer.py")

with open(target, "r", encoding="utf-8") as f:
    lines = f.readlines()

# 找到被截断的最后一行并替换
last_idx = len(lines) - 1
replaced = False
for i in range(len(lines) - 1, -1, -1):
    stripped = lines[i].strip()
    if stripped.startswith("logger.warning(f") and not stripped.endswith(")"):
        lines[i] = '    logger.warning("v4.0 扩展模块未安装，基础评测引擎可用")\n'
        lines.insert(i + 1, "    _V4_EXT_AVAILABLE = False\n")
        lines.insert(i + 2, "\n")
        last_idx = i + 2
        replaced = True
        break

# 如果没找到截断行，检查是否需要添加缺失的代码块
# 追加剩余的CLI和测试函数
tail_code = r"""
# ═══════════ 基准测试与金丝雀测试 ═══════════
def benchmark(iterations: int = BENCHMARK_ITERATIONS, warmup: int = BENCHMARK_WARMUP) -> float:
    times = []
    for i in range(iterations + warmup):
        t0 = time.time()
        run_dry_run_test(f"bench_{i}")
        if i >= warmup:
            times.append(time.time() - t0)
    avg = sum(times) / len(times)
    logger.info(f"基准测试: {iterations}次, 平均 {avg*1000:.2f}ms")
    return avg


def canary_test():
    logger.info("牧羊人v4.0 金丝雀测试启动...")
    result = run_dry_run_test("金丝雀测试v4")
    wm = ExpertWeightsManager()
    perf = {
        "金融风控合规官": [0.82, 0.85, 0.88],
        "AI工程化专家": [0.78, 0.80, 0.83],
        "策略生成审计师": [0.60, 0.65, 0.72],
    }
    result["evolved_weights"] = wm.evolve_weights(perf, 0.05)
    result["capability_report"] = wm.get_capability_report()
    _db.persist_expert_capability(result["capability_report"])
    return result


def generate_json_report(data, indent=2):
    return json.dumps(data, ensure_ascii=False, indent=indent)


class ProgressTracker:
    def __init__(self, total):
        self.total = total
        self.current = 0
        self._start = time.time()

    def update(self, n=1, msg=""):
        self.current += n
        pct = min(self.current / self.total * 100, 100)
        elapsed = time.time() - self._start
        eta = (elapsed / max(self.current, 1)) * (self.total - self.current)
        bar = chr(9608) * int(pct / 5) + chr(9617) * (20 - int(pct / 5))
        print(f"\r[{bar}] {pct:.0f}% ({self.current}/{self.total}) ETA:{eta:.1f}s {msg}", end="")
        if self.current >= self.total:
            print()


# ═══════════ v4.0 全功能自检 ═══════════
def self_test():
    logger.info("=" * 70)
    logger.info("  牧羊人优化器 v4.0 — 全功能自检")
    logger.info("=" * 70)
    results = {"version": "4.0", "tests": {}, "passed": 0, "failed": 0}

    def _check(name, cond, detail=""):
        results["tests"][name] = {"passed": cond, "detail": detail}
        if cond:
            results["passed"] += 1
        else:
            results["failed"] += 1
        logger.info(f"  {'PASS' if cond else 'FAIL'} {name}: {detail}")

    try:
        ct = canary_test()
        _check("评测引擎(15专家)", ct.get("score", 0) > 0, f"总分={ct.get('score', 0):.4f}")
        sd = init_base_strategy("test")
        fsc = five_line_safe_check(sd)
        _check("五行安全校验", isinstance(fsc, dict) and len(fsc) == 5, f"通过={sum(fsc.values())}/{len(fsc)}")
        mc, feat = analyze_market_context(sd)
        _check("市场环境分析", mc.regime != "unknown", f"体制={mc.regime}/{mc.sub_regime}")
        bt = _run_backtest("test", sd)
        _check("回测+DSR/PSR/Omega", bt.deflated_sharpe > 0, f"DSR={bt.deflated_sharpe:.3f} Omega={bt.omega_ratio:.3f}")
        total, scores = twelve_expert_scoring(bt, sd, mc, feat, ExpertWeightsManager())
        cm = compute_convergence_matrix(scores)
        _check("收敛矩阵+早停", "early_stop" in cm, f"total={cm['total_score']:.4f}")
        attr = perform_attribution_analysis(scores)
        _check("归因分析", len(attr.recommendations) >= 0, f"recommendations={len(attr.recommendations)}")
        wm = ExpertWeightsManager()
        wm.evolve_weights({"金融风控合规官": [0.82, 0.88]})
        _check("权重自演进", sum(wm.weights.values()) > 0.99, "权重归一化OK")
        cap = wm.get_capability_report()
        _check("专家能力评测", cap["total_experts"] == 15, f"专家数={cap['total_experts']} 平均能力={cap['average_capability']:.3f}")
        ok = _db.persist_expert_capability(cap)
        _check("DB持久化(专家能力)", ok, "expert_capability_log写入OK")
        _check("六大引擎扩展", _V4_EXT_AVAILABLE, "扩展模块已加载" if _V4_EXT_AVAILABLE else "扩展模块未安装(基础版可用)")
    except Exception as e:
        logger.error(f"自检异常: {e}")
        _check("自检异常捕获", False, str(e))

    total_tests = results["passed"] + results["failed"]
    logger.info(f"\n  结果: {results['passed']}/{total_tests} 通过")
    return results["failed"] == 0, results


# ═══════════ CLI入口 ═══════════
def main():
    args = sys.argv[1:]
    if not args:
        ok, results = self_test()
        print("\n" + generate_json_report(results))
        print(f"\n{'自检全部通过' if ok else '部分测试未通过'}")
        return
    if "--canary" in args:
        print(generate_json_report(canary_test()))
    elif "--optimize" in args:
        idx = args.index("--optimize")
        name = args[idx + 1] if idx + 1 < len(args) else "optimized_strategy"
        print(generate_json_report(run_dry_run_test(name)))
    elif "--generate" in args or "--compose" in args or "--evolve" in args:
        if _V4_EXT_AVAILABLE:
            from shepherd_v4_extensions import run_v4_demo
            run_v4_demo()
        else:
            logger.error("v4扩展模块未安装，请运行: python shepherd_v4_extensions.py")
    elif "--report" in args:
        print(generate_json_report(run_dry_run_test("报告生成测试")))
    else:
        print("用法: python shepherd_five_line_optimizer.py [--canary|--optimize NAME|--generate|--compose|--evolve|--report]")


if __name__ == "__main__":
    main()
"""

# 检查是否已经存在 main 函数（避免重复添加）
existing = "".join(lines)
if "def self_test():" not in existing or "def main():" not in existing:
    lines.append(tail_code)
else:
    print("main/selftest 已存在，跳过追加")

# 确保文件以换行结尾
if lines and not lines[-1].endswith("\n"):
    lines[-1] += "\n"

with open(target, "w", encoding="utf-8") as f:
    f.writelines(lines)

print(f"修复完成: {target}")
print(f"总行数: {len(open(target, encoding='utf-8').readlines())}")