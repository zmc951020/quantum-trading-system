#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""查询策略注册表和回测记录，寻找适合与傅里叶并行运用的技术算法"""
import sqlite3
import json

conn = sqlite3.connect('aurora_backtest.db')
cursor = conn.cursor()

print("=" * 80)
print("【1】策略注册表 - 所有已注册策略")
print("=" * 80)
cursor.execute("SELECT * FROM strategy_registry")
rows = cursor.fetchall()
for r in rows:
    print(f"  ID={r[0]}, 名称={r[1]}, 类型={r[3]}, 启用={r[4]}, 评分={r[6]}, 状态={r[7]}")
    print(f"  文件路径: {r[2]}")

print("\n" + "=" * 80)
print("【2】回测记录 - 所有历史回测结果")
print("=" * 80)
cursor.execute("SELECT * FROM backtest_records ORDER BY timestamp DESC")
rows = cursor.fetchall()
for r in rows:
    print(f"  ID={r[0]}, 时间={r[1]}, 策略={r[2]}")
    print(f"    年化={r[3]:.2%}, 夏普={r[4]:.2f}, 回撤={r[5]:.2%}, 胜率={r[6]:.2%}, 交易={r[7]}")
    print(f"    状态={r[8]}, 备注={r[9]}")

print("\n" + "=" * 80)
print("【3】审核报告 - 技术建议")
print("=" * 80)
cursor.execute("SELECT * FROM audit_reports ORDER BY timestamp DESC")
rows = cursor.fetchall()
for r in rows:
    print(f"  ID={r[0]}, 时间={r[1]}, 类型={r[2]}")
    print(f"  内容摘要: {str(r[3])[:200] if r[3] else 'N/A'}")
    print(f"  建议: {str(r[4])[:200] if r[4] else 'N/A'}")

conn.close()

print("\n" + "=" * 80)
print("【4】分析：适合与傅里叶并行运用的技术算法")
print("=" * 80)
print("""
基于数据库中的策略注册表，以下技术算法适合与FourierRLStrategy并行运用：

一、信号层并行（多信号融合）
  1. 市场自适应网格策略 - 全市场覆盖 + 机器学习市场分类
     → 与傅里叶频域分析互补：网格策略擅长震荡市，傅里叶擅长趋势识别
  2. 机构终极自适应ML策略 - 三种市场自动切换 + ML永久记忆
     → 提供市场状态分类，傅里叶提供频域特征，两者可做特征融合

二、模型层并行（多模型集成）
  3. LSTM时序预测 - 擅长捕捉长期依赖关系
     → 与傅里叶的频域分析形成时频域互补
  4. Transformer时间序列 - 自注意力机制捕捉全局模式
     → 与傅里叶的周期分解形成双重验证

三、风险控制层并行
  5. 汇金价值AI轮动策略 - 基本面驱动 + 长期稳健
     → 作为傅里叶策略的风控互补层

四、优化建议
  - 将Fourier变换提取的频域特征作为LSTM/Transformer的输入特征
  - 使用市场状态分类器动态切换傅里叶/网格策略权重
  - 构建多策略投票机制：傅里叶(趋势) + 网格(震荡) + 价值(防御)
""")
