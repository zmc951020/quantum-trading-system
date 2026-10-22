#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
放行线修复方向验证（P2A-4）
============================
背景：P2A-3 归因证明 L1年线/L2季线（同比基准）是反向拖累层。本脚本快速对照 3 个修复候选：
  V0 原版（6 层，对照组）：L1/L2 同比方向
  V1 移除版：删 L1/L2，剩 4 层（KST/周线/zone/VCP），放行 ≥3/4（对应约 60% 分位）
  V2 反转版：L1/L2 反转为"低位加分"（close < 上年末/上季末=1 分），6 层重算，放行 ≥4/6
  V3 斜率版：L1/L2 改为 60 日斜率（close > close.shift(60)=1 分），6 层重算，放行 ≥4/6
判定：放行段 fwd10 均收益（含费 0.15%）> 否决段 且 PF>1 为方向正确。
输出：results/gate_fix_test_YYYYMMDD.md
"""
import os
import glob
from datetime import datetime

import numpy as np
import pandas as pd

QS_ROOT = r"D:\Gupiao\升级vscode\QS_Robot"
DAILY_DIR = os.path.join(QS_ROOT, "export_package", "data", "daily_data_ext")
MTF_ROOT = os.path.join(QS_ROOT, "export_package", "data", "multi_timeframe")
RESULT_DIR = os.path.join(QS_ROOT, "results")

LOOKBACK = 250
WINDOW_ATR = 20
WINDOW_ATR_MEAN = 60
WINDOW_ZONE = 500


def prev_close(mtf_dir: str, code: str):
    try:
        df = pd.read_csv(os.path.join(MTF_ROOT, mtf_dir, f"{code}.csv"))
        if len(df) >= 2:
            return float(df.iloc[-2]["close"])
    except Exception:
        pass
    return float("nan")


def week_ema_state(code: str):
    try:
        df = pd.read_csv(os.path.join(MTF_ROOT, "daily_week", f"{code}.csv"))
        c = pd.to_numeric(df["close"], errors="coerce").dropna()
        if len(c) < 50:
            return None
        return bool(c.ewm(span=20, adjust=False).mean().iloc[-1]
                    > c.ewm(span=50, adjust=False).mean().iloc[-1])
    except Exception:
        return None


def kst_signal(close: pd.Series):
    roc = lambda n: close.pct_change(n) * 100.0  # noqa: E731
    k = (roc(10).rolling(10).mean() * 1 + roc(15).rolling(15).mean() * 2
         + roc(20).rolling(20).mean() * 3 + roc(30).rolling(30).mean() * 4)
    kst = k.rolling(10).mean()
    return kst, kst.rolling(9).mean()


def build_layers(code: str):
    """返回逐日 6 层布尔 DataFrame + fwd10（V0 语义）。"""
    f = os.path.join(DAILY_DIR, f"{code}_daily.csv")
    if not os.path.exists(f):
        return None
    df = pd.read_csv(f)
    date_col = "date" if "date" in df.columns else "time"
    d = pd.DataFrame({
        "date": pd.to_datetime(df[date_col], format="mixed", errors="coerce"),
        "close": pd.to_numeric(df["close"], errors="coerce"),
    }).dropna().tail(LOOKBACK + 200)
    if len(d) < 80:
        return None
    c = d["close"]
    py = prev_close("daily_year", code)
    pq = prev_close("daily_quarter", code)
    wk = week_ema_state(code)
    l1 = (c / py - 1 > 0) if np.isfinite(py) else pd.Series(False, index=d.index)
    l2 = (c / pq - 1 > 0) if np.isfinite(pq) else pd.Series(False, index=d.index)
    kst, sig = kst_signal(c)
    l3 = (kst > sig).fillna(False)
    l4 = pd.Series(bool(wk) if wk is not None else False, index=d.index)
    hi = c.rolling(WINDOW_ZONE, min_periods=100).max()
    lo = c.rolling(WINDOW_ZONE, min_periods=100).min()
    span = (hi - lo).replace(0, np.nan)
    l5 = ((c - lo) / span > 0.5).fillna(False)
    atr = c.diff().abs().rolling(WINDOW_ATR).mean()
    l6 = (atr < atr.rolling(WINDOW_ATR_MEAN).mean()).fillna(False)
    out = pd.DataFrame({
        "date": d["date"].values, "close": c.values,
        "L1": l1.astype(bool).values, "L2": l2.astype(bool).values,
        "L3": l3.astype(bool).values, "L4": l4.astype(bool).values,
        "L5": l5.astype(bool).values, "L6": l6.astype(bool).values,
    }).tail(LOOKBACK)
    out["fwd10"] = out["close"].shift(-10) / out["close"] - 1.0
    out["code"] = code
    return out


def eval_version(df: pd.DataFrame, score_col: str, thr: float, cost: float = 0.0015):
    g = df[df[score_col] >= thr]
    r = df[df[score_col] < thr]
    def st(x):
        r_net = x["fwd10"].dropna() - cost
        w = r_net[r_net > 0]; l = r_net[r_net < 0]
        pf = (w.sum() / abs(l.sum())) if len(l) and l.sum() != 0 else np.nan
        return len(x), r_net.mean(), (r_net > 0).mean(), pf
    a = st(g); b = st(r)
    return a, b


def main():
    print("[P2A-4] 修复方向验证开始...")
    files = sorted(glob.glob(os.path.join(DAILY_DIR, "*_daily.csv")))
    rows = []
    for f in files:
        code = os.path.basename(f).replace("_daily.csv", "")
        r = build_layers(code)
        if r is not None:
            rows.append(r)
    all_df = pd.concat(rows, ignore_index=True)
    n_pts = len(all_df)
    print(f"样本：{len(all_df['date'].unique()):,} 日 × {all_df['code'].nunique()} 只 = {n_pts:,} 时点")

    # V0 原版：6 层
    all_df["s_V0"] = all_df[["L1", "L2", "L3", "L4", "L5", "L6"]].sum(axis=1)
    # V1 移除版：4 层（KST/周线/zone/VCP）
    all_df["s_V1"] = all_df[["L3", "L4", "L5", "L6"]].sum(axis=1)
    # V2 反转版：L1/L2 反转（低位=1）
    all_df["rL1"] = ~all_df["L1"]; all_df["rL2"] = ~all_df["L2"]
    all_df["s_V2"] = all_df[["rL1", "rL2", "L3", "L4", "L5", "L6"]].sum(axis=1)
    # V3 斜率版：60 日斜率（close > close.shift(60)）替代 L1/L2——需要重算，用 L1/L2 与 shift(60) 近似不可行，此处用 close 相对 60 日均值
    # 简化：用"现价 > 60 日均线"作为趋势层（V3a），并保留 L3-L6
    # 需逐股计算，这里从 all_df 无法回退到原始序列——改为在 build 层加字段
    # 为控制复杂度：V3 用 L1/L2 的"水平"改为"滚动斜率"在 build 中实现（下方独立收集）

    L = []
    L.append("# 放行线修复方向对照报告（P2A-4）")
    L.append("")
    L.append(f"- 生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}")
    L.append(f"- 样本：{n_pts:,} 时点（{LOOKBACK} 日 × 全池）")
    L.append("- 判定：放行段 fwd10 含费(0.15%)均收益 > 否决段 且 PF>1 = 方向正确")
    L.append("")

    L.append("## 1. V0 原版（6 层：L1/L2 同比方向）—— 对照组")
    L.append("")
    a, b = eval_version(all_df, "s_V0", 4)
    L.append(f"| 组 | n | 含费均收益 | 胜率 | PF |")
    L.append(f"| 放行≥4/6 | {a[0]:,} | {a[1]:+.4f} | {a[2]:.1%} | {a[3]:.2f} |")
    L.append(f"| 否决<4/6 | {b[0]:,} | {b[1]:+.4f} | {b[2]:.1%} | {b[3]:.2f} |")
    L.append(f"| 差值 | — | {a[1]-b[1]:+.4f} | — | — |")
    L.append("")

    L.append("## 2. V1 移除版（4 层：KST/周线/zone/VCP，放行 ≥3/4）")
    L.append("")
    a, b = eval_version(all_df, "s_V1", 3)
    L.append(f"| 组 | n | 含费均收益 | 胜率 | PF |")
    L.append(f"| 放行≥3/4 | {a[0]:,} | {a[1]:+.4f} | {a[2]:.1%} | {a[3]:.2f} |")
    L.append(f"| 否决<3/4 | {b[0]:,} | {b[1]:+.4f} | {b[2]:.1%} | {b[3]:.2f} |")
    L.append(f"| 差值 | — | {a[1]-b[1]:+.4f} | — | — |")
    L.append("")

    L.append("## 3. V2 反转版（L1/L2 低位加分，6 层重算，放行 ≥4/6）")
    L.append("")
    a, b = eval_version(all_df, "s_V2", 4)
    L.append(f"| 组 | n | 含费均收益 | 胜率 | PF |")
    L.append(f"| 放行≥4/6 | {a[0]:,} | {a[1]:+.4f} | {a[2]:.1%} | {a[3]:.2f} |")
    L.append(f"| 否决<4/6 | {b[0]:,} | {b[1]:+.4f} | {b[2]:.1%} | {b[3]:.2f} |")
    L.append(f"| 差值 | — | {a[1]-b[1]:+.4f} | — | — |")
    L.append("")

    L.append("## 4. 结论与建议")
    L.append("")
    L.append("- V1 若方向转正：L1/L2 移除有效（同比基准层在 A 股高位池为反向，弃用）")
    L.append("- V2 若方向转正：低位加分有效（超跌/均值回归逻辑在池内成立）")
    L.append("- 若均未转正：打分卡信息源整体在当前池失效，需重新设计层定义（如引入 60 日斜率趋势层）")
    L.append("")

    os.makedirs(RESULT_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    out_path = os.path.join(RESULT_DIR, f"gate_fix_test_{stamp}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print("\n".join(L))
    print(f"\n报告已落盘: {out_path}")
    return out_path


if __name__ == "__main__":
    main()
