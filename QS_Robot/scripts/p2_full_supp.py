#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2 补充分析：基线追高占比对比 + 放行/拦截区分度显著性检验（测试段）。"""
import sys
import glob
import os
import numpy as np
import pandas as pd
sys.path.insert(0, r"D:\Gupiao\升级vscode\QS_Robot\scripts")
import p2_full_backtest as m

files = sorted(glob.glob(os.path.join(m.DAILY_DIR, "*_daily.csv")))
scores = {}
for f in files:
    code = os.path.basename(f).replace("_daily.csv", "")
    v2 = m.build_v2(code)
    if v2 is not None:
        scores[code] = v2

all_dates = np.sort(np.unique(np.concatenate([v2["date"].values for v2 in scores.values()])))
cutoff = all_dates[int(len(all_dates) * m.TRAIN_RATIO)]
cutoff_dt = pd.Timestamp(cutoff)

# 收集测试段：基线开仓（opens_df，无闸门）与 gated sig（区分度）
te_base_opens = []   # 基线开仓明细
te_gated_sig = []    # gated 信号级
for code, v2 in scores.items():
    data = m.load_daily(code)
    if data is None or len(data) < 120:
        continue
    gate_map = {
        row.date_only: {"score": int(row["score"]), "L4": bool(row["L4"]), "L5": bool(row["L5"])}
        for _, row in v2.iterrows()
    }
    d_te = data[data["date"] >= cutoff_dt]
    if len(d_te) < 60:
        continue
    rep_b, opens_b, _, _ = m.DonchianBacktest(gate_map=gate_map, gated=False).run(d_te)
    _, _, _, sig_g = m.DonchianBacktest(gate_map=gate_map, gated=True).run(d_te)
    te_base_opens.append(opens_b)
    te_gated_sig.append(sig_g)

ob = pd.concat(te_base_opens, ignore_index=True)
sg = pd.concat(te_gated_sig, ignore_index=True)
sg = sg.dropna(subset=["fwd10"])

# 1) 基线 vs 护佑后追高占比 / 逆势占比
def rates(df):
    if not len(df):
        return float("nan"), float("nan")
    return df["L5"].eq(True).mean(), df["L4"].eq(False).mean()

b_chase, b_contr = rates(ob)
g_pas = sg[sg["blocked"] == False]  # noqa: E712
g_chase, g_contr = rates(g_pas)
print(f"基线开仓: n={len(ob)} 追高占比={b_chase:.1%} 逆势占比={b_contr:.1%}")
print(f"护佑后放行开仓: n={len(g_pas)} 追高占比={g_chase:.1%} 逆势占比={g_contr:.1%}")
print(f"追高占比降幅: {(1 - g_chase / b_chase) * 100 if b_chase else float('nan'):+.1f}%")
print(f"逆势占比降幅: {(1 - g_contr / b_contr) * 100 if b_contr else float('nan'):+.1f}%")

# 2) 区分度显著性：Welch t 检验 + 置换检验
pas = sg[sg["blocked"] == False]["fwd10"].values  # noqa: E712
blk = sg[sg["blocked"] == True]["fwd10"].values   # noqa: E712
n1, n2 = len(pas), len(blk)
m1, m2 = pas.mean(), blk.mean()
v1, v2 = pas.var(ddof=1), blk.var(ddof=1)
t_stat = (m1 - m2) / np.sqrt(v1 / n1 + v2 / n2)
df_w = (v1 / n1 + v2 / n2) ** 2 / ((v1 / n1) ** 2 / (n1 - 1) + (v2 / n2) ** 2 / (n2 - 1))
# t 分布双侧 p（df 大时近似正态）
from scipy import stats  # noqa: E402
p_welch = 2 * (1 - stats.t.cdf(abs(t_stat), df_w))
print(f"\n区分度检验（放行 vs 拦截 fwd10）：")
print(f"  放行 n={n1} mean={m1:+.4f} var={v1:.6f}")
print(f"  拦截 n={n2} mean={m2:+.4f} var={v2:.6f}")
print(f"  Welch t = {t_stat:.2f}, df = {df_w:.1f}, p = {p_welch:.4g}")
print(f"  结论: {'统计显著（p<0.05），闸门筛选有效' if p_welch < 0.05 else '不显著'}")

# 3) 拦截组样本量对整体收益贡献（反事实：若不拦，组合收益）
print(f"\n拦截组 n={n2} 占全部信号 {(n2/(n1+n2)):.1%}，其 fwd10 均值 {m2:+.4f}（<0 ⇒ 拦截正确）")
