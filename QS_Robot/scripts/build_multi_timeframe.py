#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
多周期数据层构建（零下载成本：全部由现有日线/5min 重采样派生）
================================================================
公转自转大小周期体系数据层：
  日线  →  年线(YE)/季线(QE)/月线(ME)/周线(W)
  5min  →  60min / 30min / 15min

输出目录：export_package/data/multi_timeframe/{period}/{code}.csv
列格式与源一致：time,open,high,low,close,volume,amount,day

用法：
  python build_multi_timeframe.py            # 全周期
  python build_multi_timeframe.py --daily    # 仅日线→年/季/月/周
  python build_multi_timeframe.py --minute   # 仅5min→60/30/15
依赖：D:\anaconda3\python.exe（pandas>=2.2 支持 YE/QE/ME）
"""
import os
import sys
import argparse
from datetime import datetime

import pandas as pd

QS_ROOT = r"D:\Gupiao\升级vscode\QS_Robot"
DAILY_DIR = os.path.join(QS_ROOT, "export_package", "data", "daily_data_ext")
MIN5_DIR = os.path.join(QS_ROOT, "export_package", "data", "minute_data_ext")
OUT_ROOT = os.path.join(QS_ROOT, "export_package", "data", "multi_timeframe")

# 日线周期: (目录名, resample频率)
DAILY_PERIODS = [
    ("daily_year", "YE"),
    ("daily_quarter", "QE"),
    ("daily_month", "ME"),
    ("daily_week", "W"),
]
# 5min周期: (目录名, resample频率)
MINUTE_PERIODS = [
    ("min60", "60min"),
    ("min30", "30min"),
    ("min15", "15min"),
]

AGG = {
    "open": "first", "high": "max", "low": "min",
    "close": "last", "volume": "sum", "amount": "sum",
}


def resample_file(src_path: str, out_path: str, freq: str) -> int:
    """重采样单个CSV，返回产出根数。"""
    df = pd.read_csv(src_path)
    if df.empty:
        return 0
    # 列名自适应: 日线用 date, 5min 用 time
    if "time" not in df.columns and "date" in df.columns:
        df = df.rename(columns={"date": "time"})
    if "time" not in df.columns:
        raise ValueError(f"缺时间列: {list(df.columns)}")
    # 时间格式混合(部分文件无秒: "2026-09-01 09:35" / "2026-09-01 09:35:00")
    df["time"] = pd.to_datetime(df["time"], format="mixed")
    df = df.sort_values("time").set_index("time")
    agg = {c: AGG[c] for c in AGG if c in df.columns}
    out = df.resample(freq, label="left").agg(agg).dropna(subset=["open"])
    out = out.reset_index()
    out["day"] = out["time"].dt.strftime("%Y-%m-%d")
    out["time"] = out["time"].dt.strftime("%Y-%m-%d %H:%M:%S")
    cols = ["time", "open", "high", "low", "close", "volume", "amount", "day"]
    out = out[[c for c in cols if c in out.columns]]
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    out.to_csv(out_path, index=False)
    return len(out)


def build(source_dir: str, suffix: str, periods, label: str):
    files = sorted(f for f in os.listdir(source_dir) if f.endswith(suffix))
    print(f"[{label}] {len(files)} 个源文件，开始重采样...")
    summary = []
    errs = []
    for i, f in enumerate(files):
        # 代码提取: 日线 000001_daily.csv → 000001; 5min 601088_5min.csv → 601088
        base = f[: -len(suffix)]
        if base.endswith("_daily"):
            code = base[: -len("_daily")]
        else:
            code = base
        src = os.path.join(source_dir, f)
        for pname, freq in periods:
            out_path = os.path.join(OUT_ROOT, pname, f"{code}.csv")
            try:
                n = resample_file(src, out_path, freq)
                summary.append((pname, code, n))
            except Exception as e:
                summary.append((pname, code, f"ERR:{str(e)[:40]}"))
                if len(errs) < 8:
                    errs.append(f"{pname}/{code}: {e}")
        if (i + 1) % 100 == 0:
            print(f"  [{label}] 进度 {i+1}/{len(files)}")
    if errs:
        print(f"[{label}] 失败样例({len(errs)}/前8):")
        for e in errs:
            print(f"  {e}")
    # 汇总
    from collections import Counter, defaultdict
    per_period = defaultdict(list)
    for pname, code, n in summary:
        per_period[pname].append(n if isinstance(n, int) else 0)
    print(f"[{label}] 完成，各周期产出:")
    for pname, counts in per_period.items():
        cnt = sum(1 for x in counts if x)
        total = sum(counts)
        print(f"  {pname}: 文件 {cnt}/{len(files)}  总根数 {total}  min {min(counts) if counts else 0}  max {max(counts) if counts else 0}")
    return summary


def main():
    parser = argparse.ArgumentParser(description="多周期数据层构建(重采样)")
    parser.add_argument("--daily", action="store_true", help="仅日线→年/季/月/周")
    parser.add_argument("--minute", action="store_true", help="仅5min→60/30/15")
    args = parser.parse_args()
    do_daily = args.daily or not (args.daily or args.minute)
    do_minute = args.minute or not (args.daily or args.minute)

    t0 = datetime.now()
    if do_daily:
        build(DAILY_DIR, ".csv", DAILY_PERIODS, "日线→多周期")
    if do_minute:
        build(MIN5_DIR, "_5min.csv", MINUTE_PERIODS, "5min→多周期")
    print(f"总耗时 {datetime.now() - t0}")
    print(f"输出根目录: {OUT_ROOT}")


if __name__ == "__main__":
    main()
