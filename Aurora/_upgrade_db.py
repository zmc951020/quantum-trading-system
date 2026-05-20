"""一次性升级 Aurora 数据库 schema"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aurora_backtest.db")

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# 新增 performance 字段
new_cols = [
    ("sharpe_ratio", "REAL DEFAULT 0"),
    ("annual_return", "REAL DEFAULT 0"),
    ("max_drawdown", "REAL DEFAULT 0"),
    ("win_rate", "REAL DEFAULT 0"),
    ("total_trades", "INTEGER DEFAULT 0"),
    ("description", "TEXT DEFAULT ''"),
    ("parameters", "TEXT DEFAULT '{}'"),
    ("created_at", "TEXT DEFAULT ''"),
    ("updated_at", "TEXT DEFAULT ''"),
]

for col_name, col_def in new_cols:
    try:
        c.execute(f"ALTER TABLE strategy_registry ADD COLUMN {col_name} {col_def}")
        print(f"  ✓ 新增列: {col_name}")
    except Exception as e:
        if "duplicate" in str(e).lower():
            print(f"  - 已存在: {col_name}")
        else:
            print(f"  ✗ {col_name}: {e}")

conn.commit()
conn.close()
print("数据库升级完成")