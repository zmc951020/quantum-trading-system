#!/usr/bin/env python3
"""检查数据库结构"""
import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), 'data', 'trading_system.db')
print(f"DB path: {db_path}")
print(f"DB exists: {os.path.exists(db_path)}")

conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
print('Tables:', tables)
for t in tables:
    cursor.execute(f'PRAGMA table_info({t[0]})')
    cols = cursor.fetchall()
    print(f'\nTable {t[0]}:')
    for c in cols:
        print(f'  {c}')
    cursor.execute(f'SELECT COUNT(*) FROM {t[0]}')
    count = cursor.fetchone()[0]
    print(f'  Row count: {count}')
conn.close()
