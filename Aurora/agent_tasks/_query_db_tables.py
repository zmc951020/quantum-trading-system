#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""查询数据库表结构"""
import sqlite3

conn = sqlite3.connect('aurora_backtest.db')
cursor = conn.cursor()

# 查看所有表
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
print('=== 数据库表列表 ===')
for t in tables:
    print(f'  {t[0]}')

# 查看每个表的结构
for t in tables:
    table_name = t[0]
    cursor.execute(f'PRAGMA table_info({table_name})')
    cols = cursor.fetchall()
    print(f'\n--- {table_name} 结构 ---')
    for c in cols:
        print(f'  {c[1]:30s} {c[2]:15s} nullable={not c[3]} default={c[4]}')
    # 查看行数
    cursor.execute(f'SELECT COUNT(*) FROM {table_name}')
    count = cursor.fetchone()[0]
    print(f'  行数: {count}')

conn.close()
