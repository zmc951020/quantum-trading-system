#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
P2.8 卖点镜像实证预研（Q6 立项验证闸门 1：卖点反转原理）
==========================================================
背景：用户指示（2026-10-22）——买点已实证"空头+低位=反转买点候选"
     （P2.7：fwd10 +0.0100 vs 空头+高位 -0.0365），**卖点的审视与
     精准把控必须基于类似反转原理**（对称性）：买点看"空头+低位
     反转"，卖点看"多头+高位反转"（顶部反转卖点=逃顶）。

本预研（P2.8）回答（实证闸门 1）：
    测试段（530 纯净个股池）的 Donchian 20 **向下突破**信号
     （c[i] < min(l[i-20:i])，下跌启动）中，按 周线EMA状态(多/空)
     × 高位(现价>上年末)/低位(现价<上年末) 分四组：
     多头+高位向下突破 = 逃顶卖点候选（顶部反转，fwd10 应显著为负）
     多头+低位向下突破 = 洗盘/回踩（下跌有限）
     空头+高位向下突破 = 下跌加速（空头中继）
     空头+低位向下突破 = 下跌末段（接近底部，跌幅收窄）
     检验"多头+高位 vs 多头+低位"：若 fwd10 差异显著且多头+高位
     显著为负 → "多头+高位=逃顶卖点候选"成立（卖点反转原理闸门 1）。

输出：results/p28_sell_probe_YYYYMMDD.md
用法：D:\anaconda3\python.exe p28_sell_probe.py
"""
import os
import glob
from datetime import datetime

import numpy as np
import pandas as pd
from scipy import stats

QS_ROOT = r"D:\Gupiao\升级vscode\QS_Robot"
DAILY_DIR = os.path.join(QS_ROOT, "export_package", "data", "daily_data_ext")
MTF_ROOT = os.path.join(QS_ROOT, "export_package", "data", "multi_timeframe")
RESULT_DIR = os.path.join(QS_ROOT, "results")

LOOKBACK = 500
TRAIN_RATIO = 0.60
ENTRY_N = 20
INDEX_EXCLUDE = {"000300", "399001", "399006", "000905", "000852"}


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


def load_daily(code: str):
    f = os.path.join(DAILY_DIR, f"{code}_daily.csv")
    if not os.path.exists(f):
        return None
    df = pd.read_csv(f)
    date_col = "date" if "date" in df.columns else "time"
    out = pd.DataFrame({
        "date": pd.to_datetime(df[date_col], format="mixed", errors="coerce"),
        "close": pd.to_numeric(df["close"], errors="coerce"),
        "high": pd.to_numeric(df["high"], errors="coerce"),
        "low": pd.to_numeric(df["low"], errors="coerce"),
    }).dropna(subset=["close", "high", "low"]).tail(LOOKBACK)
    return out


def welch2(a, b):
    a = a[~np.isnan(a)]
    b = b[~np.isnan(b)]
    if len(a) < 5 or len(b) < 5:
        return None
    t_stat = (a.mean() - b.mean()) / np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    df_w = (a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b)) ** 2 / (
        (a.var(ddof=1) / len(a)) ** 2 / (len(a) - 1) + (b.var(ddof=1) / len(b)) ** 2 / (len(b) - 1))
    p = 2 * (1 - stats.t.cdf(abs(t_stat), df_w))
    return t_stat, p


def main():
    print("[P2.8] 卖点镜像实证预研开始...")
    files = sorted(glob.glob(os.path.join(DAILY_DIR, "*_daily.csv")))
    rows = []
    for f in files:
        code = os.path.basename(f).replace("_daily.csv", "")
        if code in INDEX_EXCLUDE:
            continue
        data = load_daily(code)
        if data is None or len(data) < 120:
            continue
        c = data["close"].values
        l = data["low"].values
        dates = data["date"].dt.date.values
        n = len(c)
        py = prev_close("daily_year", code)
        wk = week_ema_state(code)
        if wk is None:
            continue
        for i in range(ENTRY_N, n):
            # 向下突破：收盘 < 前 20 日最低（下跌启动）
            if c[i] < np.min(l[i - ENTRY_N:i]):
                fwd10 = c[i + 10] / c[i] - 1.0 if i + 10 < n else np.nan
                rows.append({
                    "date": str(dates[i]),
                    "close": c[i],
                    "wk_bull": bool(wk),
                    "high": bool(np.isfinite(py) and c[i] > py),
                    "fwd10": fwd10,
                })

    df = pd.DataFrame(rows).dropna(subset=["fwd10"])
    print(f"向下突破信号合计：{len(df)}")

    groups = {
        "多头+高位": df[(df["wk_bull"]) & (df["high"])],
        "多头+低位": df[(df["wk_bull"]) & (~df["high"])],
        "空头+高位": df[(~df["wk_bull"]) & (df["high"])],
        "空头+低位": df[(~df["wk_bull"]) & (~df["high"])],
    }

    L = []
    L.append("# P2.8 卖点镜像实证预研报告（Q6 立项验证闸门 1：卖点反转原理）")
    L.append("")
    L.append(f"- 生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}")
    L.append("- 问题（用户指示）：卖点审视与精准把控应基于与买点类似的「反转原理」——"
             "买点看『空头+低位反转』（P2.7 已证），卖点看『多头+高位反转』（顶部反转卖点=逃顶）。")
    L.append("- 口径：530 纯净个股池测试段；Donchian 20 向下突破（c[i] < min(l[i-20:i])）= 下跌启动；"
             "周线多头 = EMA20>EMA50；高位 = 现价 > 上年末收盘（V2 rL1 的反面）；fwd10 = 下破后 10 日收益"
             "（越负 = 卖点信号质量越好）")
    L.append("")

    L.append(f"- 信号总量：{len(df)}")
    L.append("")
    L.append("## 1. 四组分布与质量（卖点视角）")
    L.append("")
    L.append("| 组 | 信号数 | 占比 | fwd10均值 | fwd10<0占比 | 中位数 | 解读 |")
    L.append("|---|---|---|---|---|---|---|")
    order = ["多头+高位", "多头+低位", "空头+高位", "空头+低位"]
    interp = {
        "多头+高位": "**逃顶卖点候选（顶部反转，应卖出）**",
        "多头+低位": "洗盘/回踩（下跌有限，可持）",
        "空头+高位": "下跌加速（空头中继，继续规避）",
        "空头+低位": "下跌末段（接近底部，跌幅收窄）",
    }
    for g in order:
        s = groups[g]["fwd10"]
        if not len(s):
            L.append(f"| {g} | 0 | 0.0% | — | — | — | {interp[g]} |")
            continue
        L.append(f"| {g} | {len(s)} | {len(s) / len(df):.1%} | {s.mean():+.4f} | "
                 f"{(s < 0).mean():.1%} | {s.median():+.4f} | {interp[g]} |")
    L.append("")
    L.append("- 解读：若'多头+高位'组 fwd10 显著为负且与'多头+低位'差异显著 → "
             "'多头+高位=逃顶卖点候选'成立（卖点反转原理闸门 1 通过）。")
    L.append("")

    L.append("## 2. 关键检验（卖点反转原理假设）")
    L.append("")
    mh = groups["多头+高位"]["fwd10"].values
    ml = groups["多头+低位"]["fwd10"].values
    w = welch2(mh, ml)
    if w:
        L.append(f"- 多头+高位 vs 多头+低位：fwd10 {mh.mean():+.4f} vs {ml.mean():+.4f}"
                 f"，Welch t={w[0]:.2f}，p={w[1]:.4g}"
                 f"（{'显著 → 多头+高位≠多头+低位，逃顶卖点需高位条件' if w[1] < 0.05 else '不显著'}）")
    else:
        L.append("- 多头+高位 vs 多头+低位：样本不足")
    L.append("")
    sh = groups["空头+高位"]["fwd10"].values
    sl = groups["空头+低位"]["fwd10"].values
    w2 = welch2(sl, sh)
    if w2:
        L.append(f"- 空头+低位 vs 空头+高位：fwd10 {sl.mean():+.4f} vs {sh.mean():+.4f}"
                 f"，Welch t={w2[0]:.2f}，p={w2[1]:.4g}"
                 f"（{'显著 → 空头低位下跌收窄（近底），与买点侧空头低位候选呼应' if w2[1] < 0.05 else '不显著'}）")
    else:
        L.append("- 空头+低位 vs 空头+高位：样本不足")
    L.append("")

    L.append("## 3. 逃顶卖点候选画像（多头+高位且 fwd10<0）")
    L.append("")
    cand = groups["多头+高位"][groups["多头+高位"]["fwd10"] < 0]
    L.append(f"- 多头+高位信号中 fwd10<0 占比：{(groups['多头+高位']['fwd10'] < 0).mean():.1%}"
             f"（总量 {len(groups['多头+高位'])}）")
    L.append(f"- 多头+高位+逃顶候选（fwd10<0）：{len(cand)} 个，其 fwd10 均值 "
             f"{cand['fwd10'].mean():+.4f}（中位 {cand['fwd10'].median():+.4f}）——逃顶卖出的"
             f"平均避损")
    L.append("")
    L.append("## 4. 结论（闸门 1）")
    L.append("")
    L.append("> 结论由上方数字决定：若'多头+高位'下破 fwd10 显著为负 → 卖点反转原理成立，"
             "Q6 立项；'多头+高位'=逃顶卖点候选，需反转确认（顶部结构/量能背离/破位确认）"
             "与 S1-S8 卖点谱系对接；并与买点侧'空头+低位'形成完整买卖点分类矩阵。")
    L.append("")

    os.makedirs(RESULT_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    out_path = os.path.join(RESULT_DIR, f"p28_sell_probe_{stamp}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print("\n".join(L))
    print(f"\n报告已落盘: {out_path}")
    return out_path


if __name__ == "__main__":
    main()
