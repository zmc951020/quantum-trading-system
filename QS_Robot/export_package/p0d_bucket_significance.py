# -*- coding: utf-8 -*-
"""P0-D 补充：分桶显著性检验 + 阈值带收紧假说检验"""
import pandas as pd
import numpy as np
from scipy import stats as st

CSV = r"D:\Gupiao\升级vscode\QS_Robot\results\p0d_contradiction_analysis_20261023.csv"
df = pd.read_csv(CSV)

print("=== 分桶显著性（T收盘→10日收益，Welch t 检验）===")
# 涨幅分桶
a = df[df["pct"] < 0.035]["ret_close_N10"].dropna()
b = df[df["pct"] >= 0.035]["ret_close_N10"].dropna()
t, p = st.ttest_ind(a, b, equal_var=False)
print(f"涨幅<3.5% (n={len(a)}, {a.mean()*100:.2f}%) vs 涨幅>=3.5% (n={len(b)}, {b.mean()*100:.2f}%): t={t:.2f} p={p:.5f}")

# 换手分桶
a = df[df["turnover"] < 0.07]["ret_close_N10"].dropna()
b = df[df["turnover"] >= 0.07]["ret_close_N10"].dropna()
t, p = st.ttest_ind(a, b, equal_var=False)
print(f"换手<7% (n={len(a)}, {a.mean()*100:.2f}%) vs 换手>=7% (n={len(b)}, {b.mean()*100:.2f}%): t={t:.2f} p={p:.5f}")

# 单条件涨幅2-3.5% vs 全市场
print("\n=== 阈值带收紧假说（样本内）===")
# 构造"收紧版"条件：涨幅2-3.5% + 换手7-10%，其余同A1
tight = df[(df["pct"] < 0.035) & (df["turnover"] >= 0.07)]
print(f"收紧版(涨幅2-3.5% 且 换手7-10%): n={len(tight)} ret_close_10={tight['ret_close_N10'].mean()*100:.2f}%  "
      f"ret_close_5={tight['ret_close_N5'].mean()*100:.2f}%  ret_close_20={tight['ret_close_N20'].mean()*100:.2f}%")
t, p = st.ttest_1samp(tight["ret_close_N10"].dropna(), 0)
print(f"  vs 0: t={t:.2f} p={p:.4f}")

# 对照：涨幅3.5-5% 且 换手5-7%（双坏区）
bad = df[(df["pct"] >= 0.035) & (df["turnover"] < 0.07)]
print(f"双坏区(涨幅3.5-5% 且 换手5-7%): n={len(bad)} ret_close_10={bad['ret_close_N10'].mean()*100:.2f}%")

# 20日视角
print("\n=== 收紧版 20 日 ===")
t20 = tight["ret_close_N20"].dropna()
t, p = st.ttest_1samp(t20, 0)
print(f"n={len(t20)} mean={t20.mean()*100:.2f}% t={t:.2f} p={p:.4f}")
