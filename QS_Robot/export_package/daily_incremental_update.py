# -*- coding: utf-8 -*-
"""
daily_incremental_update.py — daily_data_ext 日线增量更新（FIX ①-1, 2026-10-20）

背景：backfill_daily_data.py 仅在行数 <500 时回填，>=500 永远跳过；
16:30 定时任务更新的是 5 分钟K线（minute_data_ext），与日线无关。
导致 daily_data_ext 个股日线停滞（2026-10-20 实测停在 10-16），
每日 15:30 融合扫描基于过时数据出名单。

本脚本：对 daily_data_ext 每只 {code}_daily.csv：
  1) 读旧文件最新日期 old_max
  2) akshare 拉取 qfq 日线（指数走 stock_zh_index_daily，个股走 stock_zh_a_daily）
  3) 只取 date > old_max 的新行，追加合并（同日期新行覆盖旧行）
  4) 写回原 CSV（不碰 minute_data_ext）
支持 --full 全量重建（复权基准统一校准），--limit 调试。

用法：
  python daily_incremental_update.py                 # 增量更新全部
  python daily_incremental_update.py --limit 3       # 调试：只跑前 3 只
  python daily_incremental_update.py --full          # 全量重建（慢，校准用）
"""
import os
import sys
import time
import random
import argparse
from datetime import datetime

import pandas as pd
import akshare as ak

DATA_DIR = r"D:\Gupiao\升级vscode\QS_Robot\export_package\data\daily_data_ext"
LOG_PATH = r"D:\Gupiao\升级vscode\QS_Robot\export_package\daily_incremental_update.log"
COLS = ["date", "open", "high", "low", "close", "volume",
        "amount", "outstanding_share", "turnover"]
# 指数代码集合。注意：000001 在 daily_data_ext 里是「平安银行」个股（9列），
# 不是上证指数——必须走个股接口，绝不能放进这里（否则会覆盖污染个股文件）。
# 前缀必须显式映射（sh/sz），不能靠首字符推断：000300/000905/000852 属沪市指数，
# 若拼成 sz 前缀会拉到深市同名个股（000905=8.54元 vs 中证500=6840点），造成整文件污染。
INDEX_CODES = {"000300", "399001", "399006", "000905", "000852"}
INDEX_SYMBOLS = {
    "000300": "sh000300",
    "000905": "sh000905",
    "000852": "sh000852",
    "399001": "sz399001",
    "399006": "sz399006",
}


def log(msg):
    line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def symbol_for(code):
    if code.startswith(("6", "9")):
        return "sh" + code
    return "sz" + code


def fetch_daily(code, retries=2):
    """拉取日线；指数走 index_daily（显式 sh/sz 前缀），个股走 a_daily(qfq)。失败重试。"""
    last_err = None
    for i in range(retries + 1):
        try:
            if code in INDEX_CODES:
                df = ak.stock_zh_index_daily(symbol=INDEX_SYMBOLS[code])
            else:
                df = ak.stock_zh_a_daily(symbol=symbol_for(code), adjust="qfq")
            if df is None or len(df) == 0:
                raise RuntimeError("empty result for %s" % symbol_for(code))
            df = df.copy()
            df["date"] = df["date"].astype(str)
            return df
        except Exception as e:
            last_err = e
            if i < retries:
                time.sleep(1.5 * (i + 1))
    raise RuntimeError("fetch failed for %s: %s" % (code, last_err))


def process_one(code, full=False):
    fp = os.path.join(DATA_DIR, "%s_daily.csv" % code)
    if not os.path.exists(fp):
        return {"code": code, "status": "missing", "added": 0}
    try:
        old = pd.read_csv(fp, dtype={"date": str})
    except Exception as e:
        return {"code": code, "status": "read_err", "added": 0, "err": str(e)}

    old_max = str(old["date"].max())
    df = fetch_daily(code)
    # 对齐列：缺失列补 NA
    cols = list(old.columns)
    for c in cols:
        if c not in df.columns:
            df[c] = pd.NA
    df = df[cols]

    if not full:
        new_rows = df[df["date"] > old_max]
        if len(new_rows) == 0:
            return {"code": code, "status": "uptodate", "added": 0,
                    "old_max": old_max, "new_max": old_max}
        merged = pd.concat([old, new_rows], ignore_index=True)
    else:
        merged = df  # 全量重建：以 akshare 最新复权基准为准

    merged = merged.drop_duplicates(subset="date", keep="last")
    merged = merged.sort_values("date").reset_index(drop=True)
    merged.to_csv(fp, index=False, encoding="utf-8-sig")
    return {"code": code, "status": "ok", "added": int(len(new_rows)) if not full else len(merged),
            "old_max": old_max, "new_max": str(merged["date"].max())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 只（调试）")
    ap.add_argument("--full", action="store_true", help="全量重建（校准复权基准）")
    ap.add_argument("--codes", default="", help="逗号分隔指定代码，默认全部")
    args = ap.parse_args()

    files = sorted(f for f in os.listdir(DATA_DIR) if f.endswith("_daily.csv"))
    codes = []
    if args.codes:
        codes = [c.strip() for c in args.codes.split(",") if c.strip()]
    else:
        codes = [f.replace("_daily.csv", "") for f in files]
    if args.limit:
        codes = codes[: args.limit]

    log("开始增量更新 %d 只 (full=%s)" % (len(codes), args.full))
    stats = {"ok": 0, "uptodate": 0, "skip": 0, "fail": 0}
    fails = []
    for i, code in enumerate(codes):
        try:
            r = process_one(code, full=args.full)
        except Exception as e:
            r = {"code": code, "status": "err", "err": str(e)}
        tag = r.get("status")
        if tag in ("ok",):
            stats["ok"] += 1
        elif tag in ("uptodate",):
            stats["uptodate"] += 1
        elif tag in ("missing", "read_err", "err"):
            stats["fail"] += 1
            fails.append((code, tag, r.get("err", "")))
        log("%3d/%d %s %s added=%s old_max=%s new_max=%s %s"
            % (i + 1, len(codes), code, tag, r.get("added", 0),
               r.get("old_max", ""), r.get("new_max", ""),
               r.get("err", "")))
        if (i + 1) % 50 == 0:
            time.sleep(2)  # 限流缓冲
        else:
            time.sleep(0.3)

    log("完成: 新增 %d | 已最新 %d | 失败 %d" % (stats["ok"], stats["uptodate"], stats["fail"]))
    for c, t, e in fails[:20]:
        log("  失败 %s [%s] %s" % (c, t, e))
    return 0 if stats["fail"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
