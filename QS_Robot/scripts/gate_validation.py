#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
放行线三件套补测（P2A：先例报告 Q1 要求的 ≥4/6 闭环验证）
============================================================
目的：把 P1b 的"放行线 ≥4/6（6/10 临时口径）"从分布标定升级为**信号质量闭环验证**：
  ① 含费回测：放行段 vs 否决段的收益差异（含 A 股双边成本，0.15%/0.30% 两档）
  ② 放行线敏感性扫描：3/6 → 6/6 的放行率-收益-胜率-PF 连续曲线
  ③ 随机放行置换检验：随机选 28% 时点 vs 打分放行 28% 时点，收益差是否显著
  ④ 四维护佑对比：安全性（尾部损失）/稳定性（波动）/高效性（频率+单信号收益）/精准性（胜率盈亏比）
     —— 放行段 vs 否决段逐维对比

口径（与 P1b 完全一致，6/10 临时口径）：
  可算 6 层 = 方向 4（年线斜率、季线斜率、KST、周线 EMA20>50）+ 位置 2（zone 分位、VCP 收缩）
  缠论/背驰/spring-VSA/regime 官方版待 P2 接入（本轮不计分，不冒充 10/10）

费用假设（A 股日线波段，持有 10~20 日）：
  cost 0.15% = 佣金万2.5双边(0.05%) + 卖出印花税(0.05%) + 滑点(0.05%)
  cost 0.30% = 保守上档（含冲击成本）

验收判据（V1.4 §3.4 修订）：
  - 放行段含费均收益显著 > 否决段（置换检验 p<0.05）
  - 放行段含费 PF > 1 且 > 否决段
  - 放行段尾部损失（P5）小于否决段
  - 敏感性曲线上 ≥4/6 不是"过拟合甜点"（相邻档位收益不塌缩）

输出：results/gate_validation_YYYYMMDD.md
用法：python gate_validation.py
依赖：D:\anaconda3\python.exe（pandas/numpy）
"""
import os
import sys
import glob
from datetime import datetime

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import layer_score_calibration as p1b  # 复用 kst_signal / daily_prev_year_close 等

QS_ROOT = r"D:\Gupiao\升级vscode\QS_Robot"
DAILY_DIR = os.path.join(QS_ROOT, "export_package", "data", "daily_data_ext")
MTF_ROOT = os.path.join(QS_ROOT, "export_package", "data", "multi_timeframe")
RESULT_DIR = os.path.join(QS_ROOT, "results")

LOOKBACK = 250
WINDOW_ATR = 20
WINDOW_VCP = 20
WINDOW_ATR_MEAN = 60
WINDOW_ZONE = 500
HORIZONS = (5, 10, 20)          # 持有期
COSTS = (0.0, 0.0015, 0.003)    # 0 / 0.15% / 0.30% 双边
THRESHOLDS = (3, 4, 5, 6)       # 敏感性扫描放行线
PERM_N = 2000                   # 置换检验次数


def score_with_ret(code: str):
    """单股：返回 DataFrame[date, score, fwd5/10/20, L1..L6]。无样本返回 None。"""
    f = os.path.join(DAILY_DIR, f"{code}_daily.csv")
    if not os.path.exists(f):
        return None
    df = pd.read_csv(f)
    if "close" not in df.columns or df.empty:
        return None
    date_col = "date" if "date" in df.columns else "time"
    d = pd.DataFrame({
        "date": pd.to_datetime(df[date_col], format="mixed", errors="coerce"),
        "close": pd.to_numeric(df["close"], errors="coerce"),
    }).dropna().tail(LOOKBACK + 200)  # 多留 200 根：rolling 预热 + fwd 收益
    if len(d) < 80:
        return None
    c = d["close"]
    prev_yr = p1b.daily_prev_year_close(code)
    prev_q = p1b.daily_prev_quarter_close(code)
    wk = p1b.week_ema_state(code)
    l1 = (c / prev_yr - 1 > 0) if np.isfinite(prev_yr) else pd.Series(False, index=d.index)
    l2 = (c / prev_q - 1 > 0) if np.isfinite(prev_q) else pd.Series(False, index=d.index)
    kst, sig = p1b.kst_signal(c)
    l3 = (kst > sig).fillna(False)
    l4 = pd.Series(bool(wk) if wk is not None else False, index=d.index)
    hi = c.rolling(WINDOW_ZONE, min_periods=100).max()
    lo = c.rolling(WINDOW_ZONE, min_periods=100).min()
    span = (hi - lo).replace(0, np.nan)
    l5 = ((c - lo) / span > 0.5).fillna(False)
    atr = c.diff().abs().rolling(WINDOW_ATR).mean()
    atr_mean = atr.rolling(WINDOW_ATR_MEAN).mean()
    l6 = (atr < atr_mean).fillna(False)
    out = pd.DataFrame({
        "date": d["date"].values,
        "close": c.values,
        "L1年线": l1.astype(bool).values,
        "L2季线": l2.astype(bool).values,
        "L3KST": l3.astype(bool).values,
        "L4周线": l4.astype(bool).values,
        "L5zone": l5.astype(bool).values,
        "L6VCP": l6.astype(bool).values,
    }).tail(LOOKBACK)
    out["score"] = out[["L1年线", "L2季线", "L3KST", "L4周线", "L5zone", "L6VCP"]].sum(axis=1)
    for h in HORIZONS:
        out[f"fwd{h}"] = out["close"].shift(-h) / out["close"] - 1.0
    out["code"] = code
    return out


def stats_for(df: pd.DataFrame, cost: float, fwd_col: str = "fwd10"):
    """单组统计：n、放行率、均收益(含费)、胜率、PF、P5 尾部、收益std。空组返回 None。"""
    if df is None or df.empty or fwd_col not in df.columns:
        return None
    r = df[fwd_col].dropna()
    if len(r) == 0:
        return None
    r_net = r - cost
    wins = r_net[r_net > 0]
    losses = r_net[r_net < 0]
    pf = (wins.sum() / abs(losses.sum())) if len(losses) and losses.sum() != 0 else np.nan
    return {
        "n": len(r),
        "mean_net": r_net.mean(),
        "win_rate": (r_net > 0).mean(),
        "pf": pf,
        "p5": r.quantile(0.05),
        "p1": r.quantile(0.01),
        "std": r.std(),
    }


def main():
    print("[P2A] 放行线三件套补测开始...")
    files = sorted(glob.glob(os.path.join(DAILY_DIR, "*_daily.csv")))
    rows = []
    n_stocks = 0
    for f in files:
        code = os.path.basename(f).replace("_daily.csv", "")
        r = score_with_ret(code)
        if r is None or r.empty:
            continue
        n_stocks += 1
        rows.append(r)
    if not rows:
        print("无可用样本"); return
    all_df = pd.concat(rows, ignore_index=True)
    n_pts = len(all_df)
    print(f"样本：{n_stocks} 只 × {LOOKBACK} 日 = {n_pts:,} 个时点")

    L = []
    L.append("# 放行线三件套补测报告（P2A）")
    L.append("")
    L.append(f"- 生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}")
    L.append(f"- 样本：{n_stocks} 只 × 最近 {LOOKBACK} 交易日 = {n_pts:,} 个时点")
    L.append("- 口径：6/10 临时口径（方向 4 + 位置 2）；缠论/背驰/spring-VSA/regime 待 P2 接入")
    L.append(f"- 持有期：{HORIZONS} 日；费用档：0 / 0.15% / 0.30%（双边）")
    L.append("- 判据（V1.4 §3.4）：放行段含费收益显著>否决段 + PF>1 + 尾部损失更小 + 敏感性无甜点塌缩")
    L.append("")

    # 1) 放行 vs 否决：核心对比（默认 ≥4/6，fwd10）
    L.append("## 1. 放行段（≥4/6） vs 否决段（<4/6）核心对比（持有 10 日）")
    L.append("")
    for cost in COSTS:
        g_pass = all_df[all_df["score"] >= 4]
        g_rej = all_df[all_df["score"] < 4]
        sp = stats_for(g_pass, cost)
        sr = stats_for(g_rej, cost)
        if sp and sr:
            L.append(f"### 费用档：{cost:.2%}")
            L.append("")
            L.append("| 组 | 时点数 | 含费均收益 | 胜率 | PF | P5尾部 | P1尾部 | 收益std |")
            L.append("|---|---|---|---|---|---|---|---|")
            L.append(f"| 放行(≥4/6) | {sp['n']:,} | {sp['mean_net']:+.4f} | {sp['win_rate']:.1%} | {sp['pf']:.2f} | {sp['p5']:+.3f} | {sp['p1']:+.3f} | {sp['std']:.3f} |")
            L.append(f"| 否决(<4/6) | {sr['n']:,} | {sr['mean_net']:+.4f} | {sr['win_rate']:.1%} | {sr['pf']:.2f} | {sr['p5']:+.3f} | {sr['p1']:+.3f} | {sr['std']:.3f} |")
            L.append(f"| 差值 | — | {sp['mean_net']-sr['mean_net']:+.4f} | {sp['win_rate']-sr['win_rate']:+.1%} | — | {sp['p5']-sr['p5']:+.3f} | — | — |")
            L.append("")
    L.append("")

    # 2) 敏感性扫描
    L.append("## 2. 放行线敏感性扫描（3/6 → 6/6，持有 10 日，费用 0.15%）")
    L.append("")
    L.append("| 放行线 | 放行率 | 含费均收益 | 胜率 | PF | P5尾部 | 时点数 |")
    L.append("|---|---|---|---|---|---|---|")
    for thr in THRESHOLDS:
        g = all_df[all_df["score"] >= thr]
        s = stats_for(g, 0.0015)
        if s:
            L.append(f"| ≥{thr}/6 | {len(g)/n_pts:.1%} | {s['mean_net']:+.4f} | {s['win_rate']:.1%} | {s['pf']:.2f} | {s['p5']:+.3f} | {s['n']:,} |")
    L.append("")
    L.append("> 读法：若 ≥5/6 较 ≥4/6 收益大幅塌缩、或 ≥4/6 恰是唯一正 PF 档，警惕'阈值甜点过拟合'；")
    L.append("> 若收益随阈值单调改善且相邻档无断崖，则放行线稳健。")
    L.append("")

    # 3) 置换检验
    L.append("## 3. 随机放行置换检验（打分放行 vs 随机同比例放行）")
    L.append("")
    fwd_col = "fwd10"
    r_all = all_df[fwd_col].dropna().values
    thr = 4
    mask = all_df.loc[all_df[fwd_col].notna(), "score"].values >= thr
    actual_diff = r_all[mask].mean() - r_all[~mask].mean()
    perm_diffs = []
    np.random.seed(20261022)
    n_perm = min(PERM_N, 2000)
    for _ in range(n_perm):
        idx = np.random.choice(len(r_all), size=mask.sum(), replace=False)
        perm_diffs.append(r_all[idx].mean() - np.delete(r_all, idx).mean())
    perm_diffs = np.array(perm_diffs)
    p_value = (np.abs(perm_diffs) >= abs(actual_diff)).mean()
    # 打分放行自身收益（fwd10，含费 0.15%）
    mean_pass = r_all[mask].mean() - 0.0015
    mean_rand = perm_diffs.mean()  # 随机组均收益 ≈ 全样本均收益
    L.append(f"- 放行组实际均收益（fwd10，含费后）：{mean_pass:+.4f}")
    L.append(f"- 随机组均收益（同比例 {mask.mean():.1%} 随机放行）：{mean_rand:+.4f}")
    L.append(f"- 实际放行-否决收益差：{actual_diff:+.4f}；置换分布 std：{perm_diffs.std():.4f}")
    L.append(f"- **置换检验 p 值：{p_value:.4f}**（{'p<0.05 显著优于随机放行' if p_value < 0.05 else '未达显著'}）")
    L.append("")

    # 4) 四维护佑对比（放行 vs 否决）
    L.append("## 4. 四维护佑对比（放行段 vs 否决段，fwd10 口径）")
    L.append("")
    L.append("| 护佑维度 | 指标 | 放行段 | 否决段 | 判读 |")
    L.append("|---|---|---|---|---|")
    g_pass = all_df[all_df["score"] >= 4]
    g_rej = all_df[all_df["score"] < 4]
    sp = stats_for(g_pass, 0.0); sr = stats_for(g_rej, 0.0)
    L.append(f"| 安全性 | P5 尾部损失 | {sp['p5']:+.3f} | {sr['p5']:+.3f} | {'放行段尾部更小（更安全）' if sp['p5'] > sr['p5'] else '放行段尾部更差（存疑）'} |")
    L.append(f"| 稳定性 | 收益 std | {sp['std']:.3f} | {sr['std']:.3f} | {'放行段波动更小' if sp['std'] < sr['std'] else '放行段波动更大'} |")
    L.append(f"| 高效性 | 放行率（信号频率） | {len(g_pass)/n_pts:.1%} | {len(g_rej)/n_pts:.1%} | 低放行率=信号更精 |")
    L.append(f"| 高效性 | 单信号均收益(fwd10) | {sp['mean_net']:+.4f} | {sr['mean_net']:+.4f} | {'放行段单位信号产出更高' if sp['mean_net'] > sr['mean_net'] else '存疑'} |")
    L.append(f"| 精准性 | 胜率 | {sp['win_rate']:.1%} | {sr['win_rate']:.1%} | {'放行段胜率更高' if sp['win_rate'] > sr['win_rate'] else '存疑'} |")
    L.append(f"| 精准性 | PF | {sp['pf']:.2f} | {sr['pf']:.2f} | {'放行段盈亏比更好' if sp['pf'] > sr['pf'] else '存疑'} |")
    L.append("")

    # 5) 结论
    L.append("## 5. 闸门结论")
    L.append("")
    L.append("（由独立复核后填写：是否满足 ①含费显著优于否决 ②PF>1 ③尾部更小 ④无阈值甜点 ⑤置换检验 p<0.05）")
    L.append("")

    os.makedirs(RESULT_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    out_path = os.path.join(RESULT_DIR, f"gate_validation_{stamp}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print("\n".join(L))
    print(f"\n报告已落盘: {out_path}")
    return out_path


if __name__ == "__main__":
    main()
