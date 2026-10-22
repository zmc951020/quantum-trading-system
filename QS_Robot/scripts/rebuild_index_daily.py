# -*- coding: utf-8 -*-
"""
rebuild_index_daily.py — 指数日线全量重建（修复 2026-10-22 发现的污染）

背景：daily_incremental_update.py 的 symbol_for() 对非 6/9 开头代码一律加 "sz" 前缀，
导致 000300(沪深300,sh)/000905(中证500,sh)/000852(中证1000,sh) 被拼成 sz 前缀：
  - sz000300 接口无数据 -> KeyError('date') 失败；
  - sz000905/sz000852 实际返回深市个股 000905/000852 的行情（8.54/5.31 元），
    而非指数点位（6875/6780 点）——daily_data_ext 中这两只指数文件全历史被污染。
399001(深证成指,sz)/399006(创业板指,sz) 则因文件不存在从未被处理。

本脚本：用正确 symbol 从 akshare 拉全历史，重建/新建 5 张指数 CSV，
统一格式 date/open/high/low/close/volume（6 列，utf-8-sig），与 000300 原格式一致。

用法：D:\\Program Files\\Python314\\python.exe rebuild_index_daily.py
"""
import os
import pandas as pd
import akshare as ak

DATA_DIR = r"D:\Gupiao\升级vscode\QS_Robot\export_package\data\daily_data_ext"
# 指数代码 -> 正确交易所前缀
INDEX_SYMBOLS = {
    "000300": "sh000300",  # 沪深300（上交所）
    "000905": "sh000905",  # 中证500（上交所）
    "000852": "sh000852",  # 中证1000（上交所）
    "399001": "sz399001",  # 深证成指（深交所）
    "399006": "sz399006",  # 创业板指（深交所）
}


def main():
    for code, sym in INDEX_SYMBOLS.items():
        fp = os.path.join(DATA_DIR, "%s_daily.csv" % code)
        try:
            df = ak.stock_zh_index_daily(symbol=sym)
        except Exception as e:
            print("[ERR] %s %s: %r" % (code, sym, e))
            continue
        if df is None or len(df) == 0:
            print("[ERR] %s %s: empty" % (code, sym))
            continue
        df = df[["date", "open", "high", "low", "close", "volume"]].copy()
        df["date"] = df["date"].astype(str)
        df = df.drop_duplicates(subset="date", keep="last")
        df = df.sort_values("date").reset_index(drop=True)
        df.to_csv(fp, index=False, encoding="utf-8-sig")
        print("[OK] %s %s rows=%d max=%s close=%s" % (code, sym, len(df), df["date"].max(), df["close"].iloc[-1]))


if __name__ == "__main__":
    main()
