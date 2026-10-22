# -*- coding: utf-8 -*-
"""
全市场 A 股日线下载（akshare，断点续传）
===========================================
目的：P0-C/P0-D 用户闸门质疑——选股扫描应在全市场 5000+ 只上进行，而非 499 只既有池。
存储：export_package/data/market_wide_daily/{code}_daily.csv
字段：date,open,high,low,close,volume,amount,outstanding_share,turnover
      （outstanding_share 由 volume/turnover 反推近似；turnover 直接用 akshare 换手率列）
"""
import os
import time
import glob
import logging

import akshare as ak
import pandas as pd

OUT_DIR = r"D:\Gupiao\升级vscode\QS_Robot\export_package\data\market_wide_daily"
START = "20231001"   # 3 年，够 250 日窗口 + 验证期
END = "20261023"
LOG = os.path.join(OUT_DIR, "download.log")

os.makedirs(OUT_DIR, exist_ok=True)
logging.basicConfig(filename=LOG, level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
console = logging.StreamHandler()
console.setLevel(logging.INFO)
logging.getLogger().addHandler(console)


def get_all_codes():
    df = ak.stock_info_a_code_name()
    return df["code"].tolist()


def download_one(code):
    fn = os.path.join(OUT_DIR, f"{code}_daily.csv")
    if os.path.exists(fn) and os.path.getsize(fn) > 1000:
        return "skip"
    for attempt in range(3):
        try:
            df = ak.stock_zh_a_hist(symbol=code, period="daily",
                                    start_date=START, end_date=END, adjust="")
            if df is None or df.empty:
                return "empty"
            out = pd.DataFrame({
                "date": pd.to_datetime(df["日期"]),
                "open": df["开盘"], "high": df["最高"], "low": df["最低"],
                "close": df["收盘"], "volume": df["成交量"],
                "amount": df["成交额"], "turnover": df["换手率"] / 100.0,
            })
            # outstanding_share ≈ volume / turnover（换手率>0 时反推）
            tv = out["turnover"].replace(0, pd.NA)
            out["outstanding_share"] = (out["volume"] / tv).astype(float)
            out["outstanding_share"] = out["outstanding_share"].fillna(0.0)
            out.to_csv(fn, index=False, encoding="utf-8-sig")
            return "ok"
        except Exception as e:
            if attempt == 2:
                logging.warning(f"{code} FAIL after 3 attempts: {e}")
                return "fail"
            time.sleep(3)
    return "fail"


def main():
    codes = get_all_codes()
    logging.info(f"全市场代码数={len(codes)}")
    stats = {"ok": 0, "skip": 0, "fail": 0, "empty": 0}
    for i, code in enumerate(codes, 1):
        r = download_one(code)
        stats[r] = stats.get(r, 0) + 1
        if i % 200 == 0 or r in ("fail", "empty"):
            logging.info(f"[{i}/{len(codes)}] {code} -> {r} | 累计 {stats}")
    logging.info(f"完成: {stats}")
    print(stats)


if __name__ == "__main__":
    main()
