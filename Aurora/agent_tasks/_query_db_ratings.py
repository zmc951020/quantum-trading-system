"""
从数据库查询策略评分和回测记录
"""
import sqlite3
import sys

db_path = r'd:\Gupiao\量化交易测试设备方案\攒机\最后评估01\DS-V3.2T量化交易专用工作站配置深度研判与采购决策报告02_files\攒机配置\Aurora\aurora_backtest.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 查询所有表
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
print("=== 数据库表 ===")
for t in tables:
    print(f"  {t[0]}")

# 查询 strategy_registry 表
print("\n=== strategy_registry 表结构 ===")
cursor.execute("PRAGMA table_info(strategy_registry)")
for col in cursor.fetchall():
    print(f"  {col}")

print("\n=== strategy_registry 数据 ===")
try:
    cursor.execute("SELECT * FROM strategy_registry")
    rows = cursor.fetchall()
    for r in rows:
        print(f"  {r}")
except Exception as e:
    print(f"  查询失败: {e}")

# 查询 backtest_records 表
print("\n=== backtest_records 表结构 ===")
cursor.execute("PRAGMA table_info(backtest_records)")
for col in cursor.fetchall():
    print(f"  {col}")

print("\n=== backtest_records 数据（按评分降序） ===")
try:
    cursor.execute("SELECT id, strategy_name, rating, sharpe_ratio, total_return, max_drawdown, status FROM backtest_records ORDER BY rating DESC")
    rows = cursor.fetchall()
    for r in rows:
        print(f"  ID={r[0]} | {r[1]:<35} | 评分={r[2]:.4f} | 夏普={r[3]:.4f} | 收益={r[4]:.4f} | 回撤={r[5]:.4f} | {r[6]}")
except Exception as e:
    print(f"  查询失败: {e}")

# 查询 audit_reports 表
print("\n=== audit_reports 表结构 ===")
cursor.execute("PRAGMA table_info(audit_reports)")
for col in cursor.fetchall():
    print(f"  {col}")

print("\n=== audit_reports 数据 ===")
try:
    cursor.execute("SELECT id, strategy_name, audit_type, score, status, created_at FROM audit_reports ORDER BY created_at DESC")
    rows = cursor.fetchall()
    for r in rows:
        print(f"  ID={r[0]} | {r[1]:<35} | 类型={r[2]:<15} | 评分={r[3]:.4f} | {r[4]:<10} | {r[5]}")
except Exception as e:
    print(f"  查询失败: {e}")

conn.close()
