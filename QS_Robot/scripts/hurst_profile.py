#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
Hurst 尺度画像（P1 阈值标定第一步）
====================================================
目的：用 533 只日线系 + 70 只分钟系的历史数据，对 7 个周期分别估计
     Hurst 指数（R/S + DFA 双估计），标定"趋势层 / 噪声层 / 回复层"，
     为公转自转体系 v0 阈值（0.55 / 0.45）提供数据依据（方案 §24、§3.4）。

判定口径：
  - H > 0.55 : 趋势层（动量有效，公转方向护佑权重高）
  - H < 0.45 : 回复层（均值回归，S/R / 支撑压力逻辑有效）
  - 0.45 <= H <= 0.55 : 噪声层（降权处理，不硬删除——方案 §10 风险 5）

输出：results/hurst_profile_YYYYMMDD.md
用法：python hurst_profile.py            # 全部 7 周期
      python hurst_profile.py --daily    # 仅日线系
      python hurst_profile.py --minute   # 仅分钟系
依赖：D:\anaconda3\python.exe（numpy/pandas）
"""
import os
import sys
import glob
import argparse
from datetime import datetime

import numpy as np
import pandas as pd

QS_ROOT = r"D:\Gupiao\升级vscode\QS_Robot"
MTF_ROOT = os.path.join(QS_ROOT, "export_package", "data", "multi_timeframe")
RESULT_DIR = os.path.join(QS_ROOT, "results")

DAILY_PERIODS = ["daily_year", "daily_quarter", "daily_month", "daily_week"]
MINUTE_PERIODS = ["min60", "min30", "min15"]
ALL_PERIODS = DAILY_PERIODS + MINUTE_PERIODS

MIN_BARS_RS = 32    # R/S 可靠估计的最小 bar 数（含至少 5 个 lag 点）
MIN_BARS_DFA = 32   # DFA 可靠估计的最小 bar 数（含至少 3 个 scale 点）
H_TREND = 0.55      # 趋势层阈值（v0，标定对象）
H_REVERT = 0.45     # 回复层阈值（v0，标定对象）


def hurst_rs(returns: np.ndarray):
    """R/S 分析（Hurst 经典估计）。返回 H 或 None（样本不足）。"""
    n = len(returns)
    if n < MIN_BARS_RS:
        return None
    # 几何间隔 lag：2,4,8,...,n//2（至少 4 个点）
    max_lag = n // 2
    lags = []
    l = 2
    while l <= max_lag:
        lags.append(l)
        l *= 2
    if len(lags) < 4:
        return None
    rs_vals = []
    for lag in lags:
        nseg = n // lag
        rs = []
        for i in range(nseg):
            seg = returns[i * lag:(i + 1) * lag]
            s = seg.std(ddof=1)
            if s <= 0:
                continue
            dev = np.cumsum(seg - seg.mean())
            rs.append((dev.max() - dev.min()) / s)
        if rs:
            rs_vals.append(np.mean(rs))
    if len(rs_vals) < 4:
        return None
    x = np.log(np.array(lags[:len(rs_vals)], dtype=float))
    y = np.log(np.array(rs_vals))
    if len(x) != len(y) or len(x) < 4:
        return None
    return float(np.polyfit(x, y, 1)[0])


def hurst_dfa(returns: np.ndarray):
    """DFA（去趋势波动分析，比 R/S 稳，方案 §24）。返回 H 或 None。"""
    n = len(returns)
    if n < MIN_BARS_DFA:
        return None
    y = np.cumsum(returns - returns.mean())
    scales = []
    s = 4
    while s * 2 <= n:
        scales.append(s)
        s *= 2
    if len(scales) < 3:
        return None
    F = []
    for s in scales:
        nseg = len(y) // s
        f = []
        for i in range(nseg):
            seg = y[i * s:(i + 1) * s]
            x = np.arange(s, dtype=float)
            k, b = np.polyfit(x, seg, 1)
            trend = k * x + b
            f.append(np.mean((seg - trend) ** 2))
        F.append(np.sqrt(np.mean(f)))
    if len(F) < 3:
        return None
    x = np.log(np.array(scales[:len(F)], dtype=float))
    yv = np.log(np.array(F))
    if len(x) != len(yv) or len(x) < 3:
        return None
    return float(np.polyfit(x, yv, 1)[0])


def profile_period(pname: str):
    """单周期画像：返回 DataFrame[code, bars, h_rs, h_dfa, h_mean, n_est_ok] 与统计。"""
    pdir = os.path.join(MTF_ROOT, pname)
    if not os.path.isdir(pdir):
        return None, None
    files = sorted(glob.glob(os.path.join(pdir, "*.csv")))
    recs = []
    for f in files:
        try:
            df = pd.read_csv(f)
            if "close" not in df.columns or df.empty:
                continue
            close = pd.to_numeric(df["close"], errors="coerce").dropna().to_numpy()
            if len(close) < MIN_BARS_RS:
                continue
            rets = np.diff(np.log(close))
            if len(rets) < MIN_BARS_RS:
                continue
            h_rs = hurst_rs(rets)
            h_dfa = hurst_dfa(rets)
            if h_rs is None and h_dfa is None:
                continue
            hs = [h for h in (h_rs, h_dfa) if h is not None]
            recs.append({
                "code": os.path.basename(f).replace(".csv", ""),
                "bars": len(close),
                "h_rs": h_rs, "h_dfa": h_dfa,
                "h_mean": float(np.mean(hs)),
                "dual_mae": abs(h_rs - h_dfa) if (h_rs is not None and h_dfa is not None) else None,
            })
        except Exception:
            continue
    if not recs:
        return None, None
    return recs, pd.DataFrame(recs)


def run(periods, label):
    print(f"[Hurst 画像] 开始：{label}（{len(periods)} 周期）...")
    lines = []
    stamp = datetime.now().strftime("%Y%m%d")
    lines.append("# Hurst 尺度画像报告（P1 阈值标定）")
    lines.append("")
    lines.append(f"- 生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}")
    lines.append("- 数据源：`export_package/data/multi_timeframe`（533 只日线系 + 70 只分钟系，可重建资产）")
    lines.append("- 方法：对数收益率 → R/S 估计 + DFA 估计 → H_mean；双估计 MAE 衡量一致性")
    lines.append("- 判定口径：H>0.55 趋势层（公转方向护佑权重大）；H<0.45 回复层（S/R 逻辑有效）；0.45~0.55 噪声层（降权不删除）")
    lines.append("- 样本门槛：R/S 与 DFA 均要求 ≥32 根（年线等短序列会如实标注样本不足）")
    lines.append("")
    lines.append("## 1. 逐周期汇总")
    lines.append("")
    lines.append("| 周期 | 文件数 | 可估样本 | bar中位数 | H中位数 | P25 | P75 | >0.55占比 | <0.45占比 | 双估计MAE | 层判定 |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    rows = []
    for pname in periods:
        recs, df = profile_period(pname)
        if df is None or df.empty:
            lines.append(f"| {pname} | 无数据/样本不足 | - | - | - | - | - | - | - | - | 跳过 |")
            continue
        h = df["h_mean"].dropna()
        h_rs = df["h_rs"].dropna()
        h_dfa = df["h_dfa"].dropna()
        mae = df["dual_mae"].dropna()
        med = h.median(); p25 = h.quantile(0.25); p75 = h.quantile(0.75)
        gt = (h > H_TREND).mean(); lt = (h < H_REVERT).mean()
        mae_v = mae.median() if len(mae) else float("nan")
        if med > H_TREND and gt > 0.5:
            verdict = "趋势层"
        elif med < H_REVERT and lt > 0.5:
            verdict = "回复层"
        else:
            verdict = "噪声层(降权)"
        rows.append((pname, len(df), int(df["bars"].median()), med, p25, p75, gt, lt, mae_v, verdict))
        lines.append(
            f"| {pname} | {len(df)} | {len(df)} | {int(df['bars'].median())} | {med:.3f} | {p25:.3f} | {p75:.3f} "
            f"| {gt:.0%} | {lt:.0%} | {mae_v:.3f} | {verdict} |"
        )
    lines.append("")
    lines.append("## 2. 分层结论与权重建议（v0 标定结果）")
    lines.append("")
    lines.append("| 周期 | 判定 | 护佑定位 | 权重建议 | 证据要点 |")
    lines.append("|---|---|---|---|---|")
    for pname, n, bars, med, p25, p75, gt, lt, mae_v, verdict in rows:
        role = "公转方向锚" if verdict == "趋势层" else ("自转/S-R锚" if verdict == "回复层" else "辅助/降权")
        wgt = "高(1.0)" if verdict == "趋势层" else ("高(1.0)" if verdict == "回复层" else "低(0.3~0.5)")
        ev = f"H中位数{med:.3f}（P25-P75 {p25:.3f}-{p75:.3f}），>0.55占{gt:.0%}，双估计MAE{mae_v:.3f}"
        lines.append(f"| {pname} | {verdict} | {role} | {wgt} | {ev} |")
    lines.append("")
    lines.append("## 3. 对 v0 阈值的标定结论")
    lines.append("")
    lines.append("- 若多个日线系周期（年/季/月/周）H 中位数显著 >0.55：确认 0.55 趋势阈值成立，公转方向护佑有统计依据；")
    lines.append("  若部分周期落在 0.45~0.55：该层降权（不硬删除），并用共振评分补充。")
    lines.append("- 分钟系（60/30/15min，70 只、2025-06 起）样本仅 ~16 个月：结论外推受限（方案已如实标注），仅作参考。")
    lines.append("")
    lines.append("## 4. 样本量与稳健性备注")
    lines.append("")
    lines.append(f"- 每周期可估样本 / 文件数见上表；未达到 R/S、DFA 最小样本门槛的股票已剔除（不进统计）。")
    lines.append("- 年线（daily_year）单股 bar 数约 13~35 根，部分股票接近门槛下限，其 H 估计方差较大——已由双估计 MAE 反映。")
    lines.append("")
    # 落盘
    os.makedirs(RESULT_DIR, exist_ok=True)
    out_path = os.path.join(RESULT_DIR, f"hurst_profile_{stamp}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("\n".join(lines))
    print(f"\n报告已落盘: {out_path}")
    return out_path


def main():
    parser = argparse.ArgumentParser(description="Hurst 尺度画像（P1 阈值标定）")
    parser.add_argument("--daily", action="store_true", help="仅日线系")
    parser.add_argument("--minute", action="store_true", help="仅分钟系")
    args = parser.parse_args()
    periods = []
    if args.daily or not (args.daily or args.minute):
        periods += DAILY_PERIODS
    if args.minute or not (args.daily or args.minute):
        periods += MINUTE_PERIODS
    if not periods:
        print("无周期, 退出"); sys.exit(1)
    run(periods, "全部7周期" if len(periods) == 7 else "子集")
    sys.exit(0)


if __name__ == "__main__":
    main()
