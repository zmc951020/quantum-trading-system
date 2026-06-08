#!/usr/bin/env python3
"""
韬定律一键式优化工具 (Tau One-Click Optimizer)
=================================================
将 integration_bus.py 的全流程封装为命令行一键调用：

  # 对单个策略执行：优化 → 回测 → 应用最佳参数
  python -m extensions.tools.tau_oneclick --strategy "智能标的轮动"

  # 对多个策略批量优化
  python -m extensions.tools.tau_oneclick --strategy "智能标的轮动" --strategy "双均线策略"

  # 执行完整工作流（含股票池匹配 + 交易配置生成）
  python -m extensions.tools.tau_oneclick --strategy "智能标的轮动" --full

  # 只检查优化状态（不执行优化）
  python -m extensions.tools.tau_oneclick --status

  # 检查所有已优化策略的状态
  python -m extensions.tools.tau_oneclick --status-all

依赖：
  - core.integration_bus.StrategyIntegrationBus  (全流程编排)
  - core.enhanced_strategy_manager                (策略管理 + 回测)
  - core.tau_optimizer_cluster.StrategyParameterStore (参数持久化)
"""

import os
import sys
import json
import time
import argparse
from datetime import datetime

# 路径设置：确保可导入 core / extensions 包
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_current_dir))  # QS_Robot/
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


# ============================================================
# 工具核心
# ============================================================

class TauOneClickOptimizer:
    """韬定律一键式优化执行器

    固定流程（不可更改顺序）：
      1. 初始化集成总线
      2. 对每个策略：执行 auto_full_workflow（优化 + 股票池 + 配置）
      3. 对每个策略：应用最新优化参数到策略管理器
      4. 对每个策略：用最新参数执行回测验证
      5. 输出汇总报告
    """

    def __init__(self, verbose: bool = True, data_mode: str = "auto", symbol: str = "000001"):
        self.verbose = verbose
        self.data_mode = data_mode  # "auto" | "real" | "simulated"
        self.symbol = symbol        # 股票代码（真实K线模式下使用）
        self.results = []           # 每个策略的执行结果
        try:
            from core.integration_bus import get_integration_bus
            self.bus = get_integration_bus()
            # 把 data_mode 应用到底层策略管理器
            if self.bus and getattr(self.bus, "strategy_manager", None):
                try:
                    self.bus.strategy_manager.set_data_mode(data_mode)
                except Exception:
                    pass
            sm = self.bus.strategy_manager
            self._log(f"✅ 集成总线已就绪（策略管理器: {'可用' if sm else 'N/A'}, "
                      f"data_mode={data_mode}, symbol={symbol})")
        except Exception as e:
            self._log(f"❌ 集成总线初始化失败: {e}")
            self.bus = None
            raise

    # ---------- 日志 ----------

    def _log(self, msg: str):
        """统一日志输出（带时间戳）"""
        if self.verbose:
            ts = datetime.now().strftime("%H:%M:%S")
            print(f"[{ts}] {msg}")

    # ---------- 核心流程 ----------

    def optimize_and_apply(self, strategy_name: str,
                            coarse_points: int = 30,
                            refined_points: int = 15,
                            do_full_workflow: bool = False) -> dict:
        """对单个策略执行：优化 → 应用 → 回测

        Args:
            strategy_name: 策略名称
            coarse_points: 粗筛点数
            refined_points: 精搜点数
            do_full_workflow: True=完整流程（含股票池+交易配置），False=只优化+应用+回测

        Returns:
            dict: 结构化执行报告
        """
        start = time.time()
        self._log(f"\n{'='*60}")
        self._log(f"▶ 开始优化策略: {strategy_name}")
        self._log(f"{'='*60}")

        report = {
            "strategy": strategy_name,
            "start_time": datetime.now().isoformat(),
            "optimization": None,
            "backtest": None,
            "applied": False,
            "success": False,
            "elapsed_seconds": 0.0,
            "error": None
        }

        # --- 步骤 1: 韬定律优化 ---
        try:
            self._log(f"  [1/3] 🔬 韬定律优化 (粗筛={coarse_points}, 精搜={refined_points}) ...")
            if do_full_workflow:
                opt_result = self.bus.auto_full_workflow(
                    strategy_name,
                    coarse_points=coarse_points,
                    refined_points_per_region=refined_points
                )
                report["optimization"] = {
                    "score": opt_result.get("summary", {}).get("best_score", 0),
                    "improvement": opt_result.get("summary", {}).get("improvement", 0),
                    "matched_stocks": opt_result.get("summary", {}).get("matched_stocks", 0),
                    "ready_to_trade": opt_result.get("summary", {}).get("config_ready", False),
                    "details": opt_result
                }
            else:
                opt_result = self.bus.auto_optimize_strategy(
                    strategy_name,
                    coarse_points=coarse_points,
                    refined_points_per_region=refined_points,
                    use_warm_start=True
                )
                report["optimization"] = {
                    "score": opt_result.get("best_score", 0),
                    "total_evaluations": opt_result.get("total_evaluations", 0),
                    "version": opt_result.get("version", 0),
                    "is_new_best": opt_result.get("is_new_best", False),
                    "method": opt_result.get("method", "tau_cluster"),
                    "elapsed_seconds": opt_result.get("elapsed_seconds", 0)
                }

            sc = report["optimization"].get("score", 0)
            self._log(f"  [1/3] ✅ 优化完成，评分={sc:.4f}")
        except Exception as e:
            self._log(f"  [1/3] ❌ 优化失败: {e}")
            report["error"] = f"优化失败: {e}"
            report["elapsed_seconds"] = round(time.time() - start, 2)
            return report

        # --- 步骤 2: 应用最新优化参数到策略管理器 ---
        try:
            self._log(f"  [2/3] 🔄 应用最新优化参数到策略管理器 ...")
            applied = self.bus.strategy_manager.apply_optimized_params(strategy_name)
            report["applied"] = applied.get("success", False)
            version = applied.get("version", 0)
            score = applied.get("best_score", 0)
            self._log(f"  [2/3] ✅ 已应用 v{version} (score={score:.4f})")
        except Exception as e:
            self._log(f"  [2/3] ⚠️ 应用参数失败（不影响优化结果）: {e}")
            report["error"] = report.get("error", "") + f" | 应用失败: {e}"

        # --- 步骤 3: 用最新优化参数执行回测 ---
        try:
            self._log(f"  [3/3] 📈 执行回测验证（使用最新优化参数, symbol={self.symbol}, data_mode={self.data_mode}）...")
            bt = self.bus.strategy_manager.run_backtest(
                strategy_name,
                days=300,  # 真实K线模式需要更多历史数据
                balance=100000,
                symbol=self.symbol,
                use_optimized_params=True
            )
            report["backtest"] = {
                "total_return_pct": round(getattr(bt, "total_return_pct", 0), 2),
                "sharpe_ratio": round(getattr(bt, "sharpe_ratio", 0), 4),
                "max_drawdown": round(getattr(bt, "max_drawdown", 0), 2),
                "win_rate": round(getattr(bt, "win_rate", 0), 2),
                "total_trades": getattr(bt, "total_trades", 0)
            }
            self._log(f"  [3/3] ✅ 回测完成: 收益={report['backtest']['total_return_pct']}%, "
                      f"夏普={report['backtest']['sharpe_ratio']}")
        except Exception as e:
            self._log(f"  [3/3] ⚠️ 回测失败（不影响优化结果）: {e}")
            report["error"] = report.get("error", "") + f" | 回测失败: {e}"

        report["success"] = report["optimization"] is not None
        report["elapsed_seconds"] = round(time.time() - start, 2)

        self._log(f"\n  ✔ {strategy_name} 完成，总耗时 {report['elapsed_seconds']}s")
        return report

    # ---------- 批量 / 状态查询 ----------

    def run_multiple(self, strategy_names: list, **kwargs) -> list:
        """批量执行多个策略"""
        all_results = []
        for name in strategy_names:
            r = self.optimize_and_apply(name, **kwargs)
            all_results.append(r)
        return all_results

    def get_status(self, strategy_name: str) -> dict:
        """查询单个策略的当前优化状态"""
        try:
            return self.bus.strategy_manager.get_optimization_status(strategy_name)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_all_status(self) -> list:
        """查询所有已优化策略的状态"""
        try:
            result = self.bus.strategy_manager.get_optimization_status()
            return result.get("strategies", []) if isinstance(result, dict) else []
        except Exception as e:
            self._log(f"❌ 获取状态失败: {e}")
            return []

    # ---------- 报告 ----------

    def print_summary(self, results: list = None):
        """打印汇总报告"""
        results = results or self.results
        if not results:
            print("\n没有可汇报的结果")
            return

        print(f"\n{'='*70}")
        print(f"  📊 韬定律一键优化 - 汇总报告")
        print(f"{'='*70}")
        print(f"  {'策略名称':<20} {'评分':<10} {'收益%':<8} {'夏普':<8} {'最大回撤':<8} {'耗时(s)':<8} {'状态'}")
        print(f"  {'-'*70}")

        success_count = 0
        for r in results:
            name = r.get("strategy", "?")
            opt = r.get("optimization") or {}
            bt = r.get("backtest") or {}
            score = opt.get("score", opt.get("best_score", 0))
            ret_pct = bt.get("total_return_pct", 0)
            sharpe = bt.get("sharpe_ratio", 0)
            dd = bt.get("max_drawdown", 0)
            elapsed = r.get("elapsed_seconds", 0)
            status = "✅" if r.get("success") else "❌"
            if r.get("error"):
                status = "⚠️ "

            print(f"  {name:<20} {score:<10.4f} {ret_pct:<8.2f} {sharpe:<8.4f} {dd:<8.2f} {elapsed:<8.2f} {status}")

        success_count = sum(1 for r in results if r.get("success"))
        print(f"\n  总计: {success_count}/{len(results)} 策略成功优化")
        print(f"{'='*70}\n")


# ============================================================
# 命令行入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="韬定律一键式优化工具 (优化 → 应用 → 回测)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 单个策略优化
  python -m extensions.tools.tau_oneclick --strategy "智能标的轮动"

  # 批量优化多个策略
  python -m extensions.tools.tau_oneclick --strategy "智能标的轮动" --strategy "双均线策略"

  # 完整工作流（含股票池匹配+交易配置）
  python -m extensions.tools.tau_oneclick --strategy "智能标的轮动" --full

  # 检查所有策略优化状态
  python -m extensions.tools.tau_oneclick --status-all
"""
    )
    parser.add_argument("--strategy", "-s", action="append", default=[],
                        help="要优化的策略名称（可多次指定多个）")
    parser.add_argument("--coarse", type=int, default=25, help="粗筛点数（默认 25）")
    parser.add_argument("--refined", type=int, default=12, help="精搜点数（默认 12）")
    parser.add_argument("--full", action="store_true",
                        help="执行完整工作流（含股票池匹配+交易配置）")
    parser.add_argument("--status", action="store_true",
                        help="只检查状态（不执行优化），需配合 --strategy 使用")
    parser.add_argument("--status-all", action="store_true",
                        help="查看所有已优化策略的状态")
    parser.add_argument("--data-source", choices=["auto", "real", "simulated"],
                        default="auto",
                        help="数据模式：auto(先试真实K线，失败回退)、real(仅真实K线)、simulated(仅模拟)。默认 auto")
    parser.add_argument("--symbol", default="000001",
                        help="真实K线模式下使用的股票代码（默认 000001=平安银行）。示例: 600519/000001/000858")
    parser.add_argument("--output", "-o", help="将结果输出为 JSON 文件")
    parser.add_argument("--quiet", "-q", action="store_true", help="静默模式（减少输出）")

    args = parser.parse_args()

    optimizer = TauOneClickOptimizer(verbose=not args.quiet,
                                      data_mode=args.data_source,
                                      symbol=args.symbol)

    # --- 模式 1: 查看所有策略状态 ---
    if args.status_all:
        strategies = optimizer.get_all_status()
        if not strategies:
            print("暂无已优化的策略")
            return
        print(f"\n{'='*70}")
        print(f"  📋 策略优化状态总览 (共 {len(strategies)} 个)")
        print(f"{'='*70}")
        print(f"  {'策略名称':<25} {'版本':<8} {'评分':<10} {'状态'}")
        print(f"  {'-'*70}")
        for s in strategies:
            print(f"  {s.get('name','?'):<25} "
                  f"v{s.get('current_version',0):<6} "
                  f"{s.get('best_score',0):<10.4f} "
                  f"{s.get('status','?')}")
        print(f"{'='*70}\n")
        return

    # --- 模式 2: 查看单个策略状态 ---
    if args.status and args.strategy:
        for name in args.strategy:
            status = optimizer.get_status(name)
            print(f"\n【{name}】")
            print(json.dumps(status, indent=2, ensure_ascii=False))
        return

    # --- 模式 3: 执行优化（默认）---
    if not args.strategy:
        parser.print_help()
        print("\n❌ 请至少指定一个 --strategy")
        sys.exit(1)

    results = optimizer.run_multiple(
        args.strategy,
        coarse_points=args.coarse,
        refined_points=args.refined,
        do_full_workflow=args.full
    )
    optimizer.results = results

    optimizer.print_summary(results)

    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump({
                    "timestamp": datetime.now().isoformat(),
                    "total_strategies": len(results),
                    "success_count": sum(1 for r in results if r.get("success")),
                    "results": results
                }, f, indent=2, ensure_ascii=False)
            print(f"\n✅ 详细报告已保存到: {args.output}")
        except Exception as e:
            print(f"\n❌ 保存报告失败: {e}")


if __name__ == "__main__":
    main()
