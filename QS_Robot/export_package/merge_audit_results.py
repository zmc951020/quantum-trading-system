import csv, glob, os, sys, re

# 合并批次A（已落盘 CSV）+ 批次B（stdout 文本文件）的 5 分钟复核结果并统计
# 用法: python merge_audit_results.py <batchB_stdout.txt>

BASE = r"D:\Gupiao\升级vscode\QS_Robot\export_package"
batch_a_csv = os.path.join(BASE, "audit_results_batchA_44.csv")

rows = []

# 批次A
with open(batch_a_csv, newline="", encoding="utf-8") as fh:
    rd = csv.DictReader(fh)
    for r in rd:
        rows.append({
            "strategy": r["strategy"], "code": r["code"],
            "ret": float(r["ret_pct"]), "bench": float(r["bench_pct"]),
            "trades": int(r["trades"]), "wr": float(r["winrate_pct"]), "errs": int(r["errs"]),
            "batch": "A",
        })

# 批次B: 解析 stdout 文本
pat = re.compile(
    r"\[(\w+)\] (\d{6}): 收益\s*(-?[\d.]+)% vs 基准\s*(-?[\d.]+)% "
    r"交易(\d+)\(买(\d+)/卖(\d+)\) 胜率(\d+)% 异常(\d+)"
)
if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
    with open(sys.argv[1], encoding="utf-8", errors="ignore") as fh:
        text = fh.read()
    for m in pat.finditer(text):
        name, code, ret, bench, trades, buys, sells, wr, errs = m.groups()
        rows.append({
            "strategy": name, "code": code,
            "ret": float(ret), "bench": float(bench),
            "trades": int(trades), "wr": float(wr), "errs": int(errs),
            "batch": "B",
        })
else:
    print("警告: 未提供批次B stdout 文件，仅统计批次A")

# 汇总
print("总记录数:", len(rows), "| 覆盖股票数:", len(set(r["code"] for r in rows)))
for strat in ("final_market_adaptive", "high_return_grid", "adaptive_range_grid"):
    rr = [r for r in rows if r["strategy"] == strat]
    if not rr:
        continue
    n = len(rr)
    rets = [r["ret"] for r in rr]
    benchs = [r["bench"] for r in rr]
    trades = [r["trades"] for r in rr]
    wrs = [r["wr"] for r in rr]
    errs = sum(r["errs"] for r in rr)
    win_cnt = sum(1 for a, b in zip(rets, benchs) if a > b)
    print(f"{strat} ({n}只): 平均收益 {sum(rets)/n:7.2f}% vs 基准 {sum(benchs)/n:7.2f}% | "
          f"跑赢基准 {win_cnt}/{n} | 平均交易 {sum(trades)/n:.0f} | 平均胜率 {sum(wrs)/n:.0f}% | 异常总数 {errs}")

# 写出合并 CSV
out = os.path.join(BASE, "audit_results_merged.csv")
with open(out, "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh)
    w.writerow(["strategy", "code", "ret_pct", "bench_pct", "trades", "winrate_pct", "errs", "batch"])
    for r in rows:
        w.writerow([r["strategy"], r["code"], r["ret"], r["bench"], r["trades"], r["wr"], r["errs"], r["batch"]])
print("合并CSV已写出:", out)
