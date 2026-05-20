"""
智能体牧羊人迭代回测优化观察计划
==================================
目标：密切观察智能优化迭代行为，评估是否达到开发效果

观察维度：
1. 策略评分排名与选择逻辑
2. 牧羊人优化器的迭代行为（参数搜索、收敛速度）
3. 优化前后的性能对比
4. 增益性优化效果
5. 多策略并行优化能力
"""
import sys
sys.path.insert(0, r'd:\Gupiao\量化交易测试设备方案\攒机\最后评估01\DS-V3.2T量化交易专用工作站配置深度研判与采购决策报告02_files\攒机配置\Aurora')

print("=" * 80)
print("智能体牧羊人迭代回测优化观察计划")
print("=" * 80)

# 1. 查看当前策略评分排名
from strategies.strategy_registry import STRATEGY_REGISTRY
import sqlite3

db_path = r'd:\Gupiao\量化交易测试设备方案\攒机\最后评估01\DS-V3.2T量化交易专用工作站配置深度研判与采购决策报告02_files\攒机配置\Aurora\aurora_backtest.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("\n【阶段1】当前策略评分排名")
print("-" * 60)
cursor.execute("SELECT strategy_name, performance_score, status, last_backtest FROM strategy_registry ORDER BY performance_score DESC")
rows = cursor.fetchall()
for i, (name, score, status, last) in enumerate(rows, 1):
    print(f"  {i:2d}. {name:<35} 评分={score:.4f}  状态={status:<8}  最后回测={last}")

# 2. 查看历史回测记录
print("\n【阶段2】历史回测记录")
print("-" * 60)
cursor.execute("SELECT id, strategy_name, annual_return, sharpe_ratio, max_drawdown, win_rate, total_trades, timestamp FROM backtest_records ORDER BY timestamp DESC")
rows = cursor.fetchall()
print(f"  共 {len(rows)} 条回测记录")
for r in rows[:10]:
    print(f"  ID={r[0]} | {r[1]:<35} | 年化={r[2]:.4f} | 夏普={r[3]:.4f} | 回撤={r[4]:.4f} | 胜率={r[5]:.2f} | 交易={r[6]} | {r[7]}")

# 3. 查看审核报告
print("\n【阶段3】审核报告")
print("-" * 60)
cursor.execute("SELECT id, report_type, approved, timestamp FROM audit_reports ORDER BY timestamp DESC")
rows = cursor.fetchall()
for r in rows:
    print(f"  ID={r[0]} | 类型={r[1]:<20} | 已批准={r[2]} | {r[3]}")

# 4. 分析牧羊人优化器
print("\n【阶段4】牧羊人优化器分析")
print("-" * 60)
from auto_backtest.strategy_optimizer import StrategyOptimizer
import inspect

# 查看优化器的方法
methods = [m for m in dir(StrategyOptimizer) if not m.startswith('__')]
print(f"  StrategyOptimizer 方法: {methods}")

# 查看优化器的 __init__ 签名
sig = inspect.signature(StrategyOptimizer.__init__)
print(f"  __init__ 签名: {sig}")

# 5. 查看牧羊人优化器
print("\n【阶段5】牧羊人五线优化器分析")
print("-" * 60)
from shepherd_five_line_optimizer import ShepherdFiveLineOptimizer

methods = [m for m in dir(ShepherdFiveLineOptimizer) if not m.startswith('__')]
print(f"  ShepherdFiveLineOptimizer 方法: {methods}")

sig = inspect.signature(ShepherdFiveLineOptimizer.__init__)
print(f"  __init__ 签名: {sig}")

# 检查是否有 optimize_strategy 方法
if hasattr(ShepherdFiveLineOptimizer, 'optimize_strategy'):
    sig2 = inspect.signature(ShepherdFiveLineOptimizer.optimize_strategy)
    print(f"  optimize_strategy 签名: {sig2}")

if hasattr(ShepherdFiveLineOptimizer, 'run_optimization_cycle'):
    sig3 = inspect.signature(ShepherdFiveLineOptimizer.run_optimization_cycle)
    print(f"  run_optimization_cycle 签名: {sig3}")

conn.close()
print("\n" + "=" * 80)
print("观察计划就绪，准备执行牧羊人优化迭代")
print("=" * 80)
