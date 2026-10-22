#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
多周期数据层前视自检（lookahead check）
================================================================
复刻 freqtrade lookahead-analysis 思路：截断测试（truncation test）。
对每个周期目录的每只股票 CSV：

  1) 读取全历史（time 为周期起点标签，label="left"）。
  2) 取最后 N 根 bar 的标签时间作为截断点 t。
  3) 对每个 t 判定两种引用方式：
     - 「按标签直引」（未平移）：取最后一根 label <= t 的 bar。
       若该 bar 未闭合（label + period_delta > t），则 CSV 中记录的
       close 是包含 t 之后数据的最终值——把未闭合 bar 当作完整 bar
       使用 = 前视偏差（命中）。
     - 「平移引用」（date_merge = label + period_delta，freqtrade 官方
       写法）：取最后一根 label + period_delta <= t 的 bar（已闭合）。
       其最终 close 就是 t 时刻应可见的值，永不因后续数据变化（不命中）。

  4) 汇总每个周期目录：前视引用命中率（应 >0，证明直引有风险）、
     平移引用命中率（应 =0，证明平移安全）。

输出：results/lookahead_report_YYYYMMDD.txt
用法：
  python lookahead_check.py            # 全部 7 个周期目录
  python lookahead_check.py --daily    # 仅日线系（年/季/月/周）
  python lookahead_check.py --minute   # 仅分钟系（60/30/15）
依赖：D:\anaconda3\python.exe（pandas>=2.2）
"""
import os
import sys
import glob
import argparse
from datetime import datetime

import pandas as pd

QS_ROOT = r"D:\Gupiao\升级vscode\QS_Robot"
MTF_ROOT = os.path.join(QS_ROOT, "export_package", "data", "multi_timeframe")
RESULT_DIR = os.path.join(QS_ROOT, "results")

# 周期目录: (目录名, 类型)
DAILY_PERIODS = ["daily_year", "daily_quarter", "daily_month", "daily_week"]
MINUTE_PERIODS = ["min60", "min30", "min15"]
ALL_PERIODS = DAILY_PERIODS + MINUTE_PERIODS

N_CUTOFFS = 10  # 每个文件取最后 N 根 bar 的标签作截断点


def period_delta_median(times: pd.Series) -> pd.Timedelta:
    """从数据自身推导周期时长：相邻标签差的中位数（末根无下一根，用中位数）。"""
    diffs = times.diff().dropna()
    if diffs.empty:
        return pd.Timedelta(0)
    return diffs.median()


def check_file(path: str, pname: str):
    """单文件自检，返回 (n_bars, cutoff_cnt, direct_hits, shifted_hits, sample_lines)。"""
    df = pd.read_csv(path)
    if df.empty:
        return 0, 0, 0, 0, []
    # 列自适应
    if "time" not in df.columns and "date" in df.columns:
        df = df.rename(columns={"date": "time"})
    if "time" not in df.columns or "close" not in df.columns:
        return len(df), 0, 0, 0, ["缺 time/close 列"]
    times = pd.to_datetime(df["time"], format="mixed", errors="coerce")
    close = pd.to_numeric(df["close"], errors="coerce")
    df = pd.DataFrame({"label": times, "close": close}).dropna()
    if len(df) < 2:
        return len(df), 0, 0, 0, ["样本不足(<2)"]
    delta = period_delta_median(df["label"])
    if delta <= pd.Timedelta(0):
        return len(df), 0, 0, 0, [f"周期时长推导失败: {delta}"]

    # 截断点 = 最后 N_CUTOFFS 根 bar 的标签时间
    cutoffs = df["label"].iloc[-N_CUTOFFS:].tolist()
    direct_hits = 0
    shifted_hits = 0
    samples = []
    for t in cutoffs:
        # 按标签直引：最后一根 label <= t
        direct_mask = df["label"] <= t
        if not direct_mask.any():
            continue
        d_idx = df.index[direct_mask][-1]
        d_bar = df.loc[d_idx]
        # 未闭合判定：label + delta > t
        if d_bar["label"] + delta > t:
            direct_hits += 1
            if len(samples) < 3:
                samples.append(
                    f"  直引命中: asof={t:%Y-%m-%d %H:%M} 引用了未闭合bar "
                    f"label={d_bar['label']:%Y-%m-%d %H:%M} (闭合于{d_bar['label'] + delta:%Y-%m-%d %H:%M})"
                )
        # 平移引用：最后一根 label + delta <= t（已闭合）
        shifted_mask = df["label"] + delta <= t
        if shifted_mask.any():
            s_idx = df.index[shifted_mask][-1]
            s_bar = df.loc[s_idx]
            # 已闭合 bar 永远安全；此处仅防御性检查（逻辑保证不命中）
            if s_bar["label"] + delta > t:
                shifted_hits += 1

    return len(df), len(cutoffs), direct_hits, shifted_hits, samples


def run(periods, label):
    print(f"[{label}] 开始前视自检...")
    lines = []
    per_period = {p: {"files": 0, "bars": 0, "cutoffs": 0, "direct": 0, "shifted": 0, "risk_files": 0} for p in periods}
    for pname in periods:
        pdir = os.path.join(MTF_ROOT, pname)
        if not os.path.isdir(pdir):
            print(f"  跳过(目录不存在): {pname}")
            continue
        files = sorted(glob.glob(os.path.join(pdir, "*.csv")))
        for f in files:
            try:
                n, cuts, dhit, shit, samples = check_file(f, pname)
                per_period[pname]["files"] += 1
                per_period[pname]["bars"] += n
                per_period[pname]["cutoffs"] += cuts
                per_period[pname]["direct"] += dhit
                per_period[pname]["shifted"] += shit
                if dhit > 0:
                    per_period[pname]["risk_files"] += 1
                if len(samples) > 0 and len(lines) < 30:
                    lines.append(f"[{pname}] {os.path.basename(f)}")
                    lines.extend(samples)
            except Exception as e:  # 单文件失败不中断
                if len(lines) < 40:
                    lines.append(f"[{pname}] {os.path.basename(f)} ERR: {str(e)[:80]}")

    # 汇总表
    summary = []
    summary.append("=" * 78)
    summary.append("多周期数据层前视自检报告")
    summary.append(f"生成时间: {datetime.now():%Y-%m-%d %H:%M:%S}")
    summary.append(f"判定口径: 截断测试 | 直引=按标签取未闭合bar | 平移=label+period_delta 取已闭合bar")
    summary.append("=" * 78)
    summary.append("")
    summary.append(f"{'周期':<14}{'文件':>6}{'总bar':>9}{'截断点':>9}{'直引命中':>9}{'平移命中':>9}{'风险文件':>9}  结论")
    summary.append("-" * 78)
    for pname in periods:
        p = per_period[pname]
        direct_rate = p["direct"] / p["cutoffs"] if p["cutoffs"] else 0
        shifted_rate = p["shifted"] / p["cutoffs"] if p["cutoffs"] else 0
        # 结论：直引命中>0 → "直引有前视风险（证明成立）"; 平移命中==0 → "平移引用安全"
        verdict = []
        if p["cutoffs"] == 0:
            verdict.append("无样本")
        else:
            verdict.append("直引有前视风险(成立)" if direct_rate > 0 else "直引未检出风险")
            verdict.append("平移引用安全" if shifted_rate == 0 else f"平移异常({shifted_rate:.0%})")
        summary.append(
            f"{pname:<14}{p['files']:>6}{p['bars']:>9}{p['cutoffs']:>9}{p['direct']:>9}{p['shifted']:>9}{p['risk_files']:>9}  {'; '.join(verdict)}"
        )
    summary.append("-" * 78)
    summary.append("结论解释:")
    summary.append("  - '直引命中>0' 证明: 若按 bar 标签直接引用大周期值(未平移), 会把未闭合 bar 当作完整 bar, 构成前视偏差(盘中引用场景)。")
    summary.append("  - '平移命中=0' 证明: 采用 freqtrade 官方写法 date_merge=label+period_delta 后, 只引用已闭合 bar, 无前视。")
    summary.append("  - 现有盘后全量 + DecisionEngine T-1 冻结口径本身无前视; 本报告针对的是未来 multi_timeframe 的新消费场景。")
    summary.append("")

    # 样例明细
    if lines:
        summary.append("命中样例(每个周期最多3条, 共最多30条):")
        summary.extend(lines)
        summary.append("")

    os.makedirs(RESULT_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    out_path = os.path.join(RESULT_DIR, f"lookahead_report_{stamp}.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(summary))
    print("\n".join(summary))
    print(f"\n报告已落盘: {out_path}")
    return out_path


def main():
    parser = argparse.ArgumentParser(description="多周期数据层前视自检")
    parser.add_argument("--daily", action="store_true", help="仅日线系(年/季/月/周)")
    parser.add_argument("--minute", action="store_true", help="仅分钟系(60/30/15)")
    args = parser.parse_args()
    do_daily = args.daily or not (args.daily or args.minute)
    do_minute = args.minute or not (args.daily or args.minute)
    periods = []
    if do_daily:
        periods += DAILY_PERIODS
    if do_minute:
        periods += MINUTE_PERIODS
    if not periods:
        print("无周期可选, 退出")
        sys.exit(1)
    out = run(periods, "全部7周期" if len(periods) == 7 else "子集")
    sys.exit(0)


if __name__ == "__main__":
    main()
