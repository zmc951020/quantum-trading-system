#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
盘中实时行情验证（免费数据源：腾讯主源 + 东财备源）
====================================================
用途：交易时段内验证 70 只股票池的实时行情获取能力，
     输出快照 CSV 到 results 目录，供人工核对即时数据可用性。

首次使用：2026-10-22（周四）盘中，挂一次性定时任务 10:30 触发。
后续可随时手动运行（python verify_realtime_intraday.py）。

依赖：D:\anaconda3\python.exe（已装 requests）
"""
import os
import sys
import time
import csv
from datetime import datetime

QS_ROOT = r"D:\Gupiao\升级vscode\QS_Robot"
MIN_DIR = os.path.join(QS_ROOT, "export_package", "data", "minute_data_ext")
RESULTS_DIR = os.path.join(QS_ROOT, "export_package", "strategies_local", "results")

sys.path.insert(0, QS_ROOT)
from core.data_sources.realtime_adapter import RealtimeAdapter  # noqa: E402


def main():
    codes = sorted(f.replace("_5min.csv", "") for f in os.listdir(MIN_DIR)
                   if f.endswith("_5min.csv"))
    print(f"[盘中验证] 股票池 {len(codes)} 只，开始拉取实时快照...")

    a = RealtimeAdapter()
    ok, fail = 0, []
    rows = []
    for i in range(0, len(codes), 40):
        qs = a.get_realtime_batch(codes[i:i + 40])
        for c in codes[i:i + 40]:
            q = qs.get(c)
            if q and q.get("price"):
                ok += 1
                rows.append({
                    "symbol": c, "name": q.get("name", ""),
                    "price": q.get("price"), "change_pct": q.get("change_pct"),
                    "source": q.get("source"),
                })
            else:
                fail.append(c)
        time.sleep(1)  # 避免触发限流

    os.makedirs(RESULTS_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    path = os.path.join(RESULTS_DIR, f"realtime_verify_{ts}.csv")
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["symbol", "name", "price", "change_pct", "source"])
        w.writeheader()
        w.writerows(rows)

    print(f"[盘中验证] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} 成功 {ok}/{len(codes)}")
    if fail:
        print(f"[盘中验证] 失败 {len(fail)} 只: {','.join(fail)}")
    print(f"[盘中验证] 结果已保存: {path}")
    return ok, fail


if __name__ == "__main__":
    main()
