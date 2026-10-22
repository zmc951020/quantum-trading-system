#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
P2.7 空头反转买点实证预研（Q5 立项的第一验证步）
====================================================
背景：用户指出课题缺陷——市场分形研究偏重多头/趋势市，未系统研究
     熊市/空头分形；"空头一票否决"（V2a）混淆了"空头下跌中继"
     （不可操作）与"空头反转起点"（重要买点：威科夫 spring、缠论
     底背驰、关键支撑位反弹）。用户要求立项"空头反转相对低点/反转
     起点可买点"研究，并与已立项的逃顶卖点（S1-S8）形成买卖平衡。

本预研（P2.7）只回答一个问题（实证闸门 1）：
    测试段（2025-12-04 后，530 纯净个股池）的 Donchian 突破信号中，
    周线空头（EMA20<=EMA50）信号里有多少 fwd10>0（"反转买点候选"）？
    它们的特征是低位（现价<上年末）还是高位？与周线多头信号相比
    质量如何？——若空头+低位子集 fwd10 显著为正，则"空头反转买点=
    重要支撑位反弹"假设成立，V2 改进方向=为反转确认信号开专门放行
    通道而非一刀切否决。

方法：复用 P2.5/P2.6 数据层与信号识别（Donchian 20 突破），
     按 周线EMA状态(多/空) × 低位(现价<上年末, rL1) 分四组统计。
     输出：results/p27_short_reversal_probe_YYYYMMDD.md
用法：D:\anaconda3\python.exe p27_short_reversal_probe.py
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
    """Welch t 检验，返回 (t, p) 或 None。"""
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
    print("[P2.7] 空头反转买点实证预研开始...")
    files = sorted(glob.glob(os.path.join(DAILY_DIR, "*_daily.csv")))
    rows = []
    n_skip = 0
    for f in files:
        code = os.path.basename(f).replace("_daily.csv", "")
        if code in INDEX_EXCLUDE:
            continue
        data = load_daily(code)
        if data is None or len(data) < 120:
            n_skip += 1
            continue
        c = data["close"].values
        h = data["high"].values
        dates = data["date"].dt.date.values
        n = len(c)
        py = prev_close("daily_year", code)
        wk = week_ema_state(code)
        if wk is None:
            continue
        for i in range(ENTRY_N, n):
            if c[i] > np.max(h[i - ENTRY_N:i]):
                fwd10 = c[i + 10] / c[i] - 1.0 if i + 10 < n else np.nan
                rows.append({
                    "date": str(dates[i]),
                    "close": c[i],
                    "wk_bull": bool(wk),
                    "low": bool(np.isfinite(py) and c[i] < py),
                    "fwd10": fwd10,
                })

    df = pd.DataFrame(rows).dropna(subset=["fwd10"])
    print(f"突破信号合计：{len(df)}（覆盖 {len(files) - n_skip} 只测试段）")

    # 四组
    groups = {
        "多头+高位": df[(df["wk_bull"]) & (~df["low"])],
        "多头+低位": df[(df["wk_bull"]) & (df["low"])],
        "空头+低位": df[(~df["wk_bull"]) & (df["low"])],
        "空头+高位": df[(~df["wk_bull"]) & (~df["low"])],
    }

    L = []
    L.append("# P2.7 空头反转买点实证预研报告（Q5 立项验证闸门 1）")
    L.append("")
    L.append(f"- 生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}")
    L.append("- 问题：测试段 Donchian 20 突破信号中，周线空头信号有多少 fwd10>0（反转买点候选）？"
             "其特征是低位（现价<上年末）还是高位？")
    L.append("- 口径：530 纯净个股池；周线空头 = EMA20<=EMA50（multi_timeframe/daily_week，T-1 冻结）；"
             "低位 = 现价 < 上年末收盘（V2 的 rL1）；fwd10 = 信号后 10 日收益")
    L.append("")
    L.append(f"- 信号总量：{len(df)}（测试段样本外）")
    L.append("")

    # 汇总表
    L.append("## 1. 四组分布与质量")
    L.append("")
    L.append("| 组 | 信号数 | 占比 | fwd10均值 | fwd10>0占比 | 中位数 | 解读 |")
    L.append("|---|---|---|---|---|---|---|")
    order = ["多头+低位", "多头+高位", "空头+低位", "空头+高位"]
    interp = {
        "多头+低位": "趋势向上+位置低（V2 理想放行组）",
        "多头+高位": "趋势向上+位置高（追高组）",
        "空头+低位": "**反转买点候选（关键组）**",
        "空头+高位": "下跌中继/高位坠落（应拦截组）",
    }
    for g in order:
        s = groups[g]["fwd10"]
        if not len(s):
            L.append(f"| {g} | 0 | 0.0% | — | — | — | {interp[g]} |")
            continue
        L.append(f"| {g} | {len(s)} | {len(s) / len(df):.1%} | {s.mean():+.4f} | "
                 f"{(s > 0).mean():.1%} | {s.median():+.4f} | {interp[g]} |")
    L.append("")
    L.append("- 解读：若'空头+低位'组 fwd10 均值显著为正或接近 0，则被 V2a 否决的信号中混有反转买点；"
             "若显著为负，则空头信号整体仍应拦截，反转买点需额外确认条件（非仅低位）。")
    L.append("")

    # 关键检验
    L.append("## 2. 关键检验（空头反转买点假设）")
    L.append("")
    sh_low = groups["空头+低位"]["fwd10"].values
    sh_hi = groups["空头+高位"]["fwd10"].values
    w = welch2(sh_low, sh_hi)
    if w:
        L.append(f"- 空头+低位 vs 空头+高位：fwd10 {sh_low.mean():+.4f} vs {sh_hi.mean():+.4f}"
                 f"，Welch t={w[0]:.2f}，p={w[1]:.4g}"
                 f"（{'显著 → 低位空头≠高位空头，反转买点需低位条件' if w[1] < 0.05 else '不显著'}）")
    else:
        L.append("- 空头+低位 vs 空头+高位：样本不足，无法检验")
    L.append("")
    bu_low = groups["多头+低位"]["fwd10"].values
    w2 = welch2(sh_low, bu_low)
    if w2:
        L.append(f"- 空头+低位 vs 多头+低位：fwd10 {sh_low.mean():+.4f} vs {bu_low.mean():+.4f}"
                 f"，Welch t={w2[0]:.2f}，p={w2[1]:.4g}"
                 f"（{'显著 → 空头低位质量与多头低位不同，需区分处理' if w2[1] < 0.05 else '不显著 → 空头低位可作买点候选'}）")
    else:
        L.append("- 空头+低位 vs 多头+低位：样本不足，无法检验")
    L.append("")

    # 反转候选特征
    L.append("## 3. 反转买点候选画像（空头且 fwd10>0）")
    L.append("")
    cand = groups["空头+低位"][groups["空头+低位"]["fwd10"] > 0]
    cand_all = df[(~df["wk_bull"]) & (df["fwd10"] > 0)]
    L.append(f"- 空头信号中 fwd10>0 占比：{(df[~df['wk_bull']]['fwd10'] > 0).mean():.1%}（总量 "
             f"{len(df[~df['wk_bull']])}）")
    L.append(f"- 其中低位占比：{len(cand) / len(df[~df['wk_bull']]) if len(df[~df['wk_bull']]) else 0:.1%}"
             f"（{len(cand)} 个）")
    L.append(f"- 空头+低位+反转候选信号数：{len(cand)}；其 fwd10 均值 "
             f"{cand['fwd10'].mean():+.4f}（正收益中位 {cand['fwd10'].median():+.4f}）")
    L.append("")
    L.append("## 4. 结论（闸门 1）")
    L.append("")
    L.append("> 结论由上方数字决定：若空头+低位存在显著正收益子集 → Q5 立项成立，"
             "V2 改进=反转确认通道（非一刀切否决）；若整体为负 → 反转买点需额外确认条件"
             "（底背驰/spring/支撑位）进一步筛取，研究转向确认信号工程化。")
    L.append("")

    os.makedirs(RESULT_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    out_path = os.path.join(RESULT_DIR, f"p27_short_reversal_probe_{stamp}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print("\n".join(L))
    print(f"\n报告已落盘: {out_path}")
    return out_path


if __name__ == "__main__":
    main()
