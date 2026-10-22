#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
P2.11 V3 逃顶卖点优化 + 反转通道复核 + 禁域占比口径修订
======================================================================
背景（P2.10 定稿，V1.12）：
  V3 = V2b ≥4/7 主放行 + 空头低位 B4 反转通道 + 多头高位 S3 逃顶卖点。
  P2.10 遗留三项待优化（P2.11 立项）：
  ① 逃顶卖点 UT 触发过频（测试段 1379 次/每只 2.6）——回撤贡献显著但砍掉
     反弹利润（总收益 vs V2b 持平）→ 结构收紧扫描；
  ② 反转通道策略级信号 fwd10 +0.0022 vs 信号级 +0.0336 差异复核——样本期
     差异（P2.9 全历史 vs P2.10 测试段）或过滤差异（空仓约束）归因；
  ③ 稳定性考核口径：逆势占比（L4 空头开仓占比）对反转通道失效（反转通道
     放行的正是空头信号）→ 改"禁域占比"（空头+高位开仓占比，P2.7 已证
     fwd10 -0.0365 的禁域）作为稳定性考核口径。

本实验（P2.11）：
  Part A：UT 结构收紧 4 变体 vs 基线 V3（UT_N/UT_REC/UT_LB 参数化），
    对比触发次数/总收益/回撤/胜率/信号效率 → 选逃顶卖点最优参数；
  Part B：反转通道差异复核——测试段"全反转信号（突破日，无论持仓）fwd10"
    vs "策略级开仓信号 fwd10"，分解样本期差异 vs 过滤差异；
  Part C：禁域占比（空头+高位开仓占比）作为稳定性新口径，V2b/V3/最优变体
    三组对比输出。
  四维护佑按 V1.5 §3.2 达标线重判（稳定性用禁域占比口径）。

用法：D:\anaconda3\python.exe p211_ut_optimization.py
输出：results/p211_ut_optimization_YYYYMMDD.md
"""
import os
import glob
from datetime import datetime

import numpy as np
import pandas as pd

import p210_v3_reversal_retest as p210  # 复用 build_v3/ut_series/DonchianBacktestV3 常量
import p2_full_backtest as m

QS_ROOT = r"D:\Gupiao\升级vscode\QS_Robot"
RESULT_DIR = os.path.join(QS_ROOT, "results")


def build_v3_ut(code, ut_n, ut_rec, ut_lb):
    """参数化 UT 的 build_v3（monkey-patch p210 模块常量后调用）。"""
    p210.UT_N, p210.UT_REC, p210.UT_LB = ut_n, ut_rec, ut_lb
    return p210.build_v3(code)


def ut_stats_series(high, close, n=5, rec=3, lb=10):
    """UT 事件原始计数（每根 k 是否发生 UT，供触发次数诊断）。"""
    N = len(high)
    ev = np.zeros(N, dtype=bool)
    for k in range(1, N):
        ref = float(np.max(high[max(0, k - n):k]))
        if high[k] > ref and k + rec <= N and float(np.min(close[k:k + rec])) < ref:
            ev[k] = True
    return ev


class DonchianBacktestV3b(m.DonchianBacktest):
    """V3 模式 + opens 记录 high_pos/low_pos（禁域占比需要）+ 全信号 fwd10 记录。"""

    def __init__(self, gate_map=None, gated=False, min_score=4, mode="v3"):
        super().__init__(gate_map=gate_map, gated=gated, min_score=min_score)
        self.mode = mode

    def _blocked_at(self, g, i):
        if not (self.gated and g is not None):
            return False
        if self.mode == "v2b":
            return bool(g["score"] < self.min_score)
        return bool(g["score"] < self.min_score and not g["reversal"])

    def _exit_extra(self, g, i):
        if self.mode != "v3":
            return False
        return bool(self.gated and g is not None and g["sell_ut"])

    def run(self, data: pd.DataFrame):
        c = data["close"].values
        h = data["high"].values
        l = data["low"].values
        dates = data["date"].dt.date.values
        n = len(c)
        cash = 100000.0
        shares = 0
        entry_cost = 0.0
        stop_price = 0.0
        peak = 100000.0
        max_dd = 0.0
        trades = []
        opens = []
        sig_rows = []
        blocked = 0
        wins = losses = 0.0
        sell_ut_n = 0
        skipped_holding = 0  # 持仓中出现的反转信号（未开仓）——复核用

        atr_arr = np.full(n, np.nan)
        for i in range(m.ATR_N, n):
            atr_arr[i] = np.mean([max(h[j] - l[j], abs(h[j] - c[j - 1]), abs(l[j] - c[j - 1]))
                                  for j in range(i - m.ATR_N + 1, i + 1)])

        equity = np.zeros(n)
        for i in range(n):
            g = self.gate_map.get(dates[i], None)
            if shares > 0:
                exit_ok = (i >= m.EXIT_N and c[i] < np.min(l[i - m.EXIT_N:i])) or c[i] < stop_price
                exit_ok = exit_ok or self._exit_extra(g, i)
                if exit_ok:
                    if g is not None and self._exit_extra(g, i) and not (
                            (i >= m.EXIT_N and c[i] < np.min(l[i - m.EXIT_N:i])) or c[i] < stop_price):
                        sell_ut_n += 1
                    proceeds = shares * c[i] * (1 - m.COST)
                    pnl = proceeds - entry_cost
                    cash += proceeds
                    if pnl > 0:
                        wins += pnl
                    else:
                        losses += abs(pnl)
                    trades.append({"action": "sell", "i": i, "date": dates[i],
                                   "price": c[i], "pnl": pnl})
                    shares = 0
            entry_sig = (shares == 0 and i >= m.ENTRY_N and c[i] > np.max(h[i - m.ENTRY_N:i]))
            if i >= m.ENTRY_N:
                entry_sig_all = c[i] > np.max(h[i - m.ENTRY_N:i])
                # 全信号记录（无论持仓）——反转通道复核 Part B
                if entry_sig_all and g is not None and g["reversal"] and i + 10 < n:
                    sig_rows.append({
                        "date": dates[i], "price": c[i], "score": g["score"],
                        "reversal": True, "fwd10": c[i + 10] / c[i] - 1.0,
                        "holding": shares > 0,
                    })
            if shares == 0 and entry_sig:
                if g is not None and g["reversal"]:
                    skipped_holding += 0  # 空仓时才记录，持仓反转走全信号计数
                blocked_now = self._blocked_at(g, i)
                if blocked_now:
                    blocked += 1
                else:
                    qty = int(cash * m.POS_PCT / c[i] / 100) * 100
                    if qty > 0:
                        entry_cost = qty * c[i] * (1 + m.COST)
                        cash -= entry_cost
                        shares = qty
                        stop_price = c[i] - m.ATR_STOP_MULT * (
                            atr_arr[i] if np.isfinite(atr_arr[i]) else c[i] * 0.02)
                        opens.append({
                            "date": dates[i], "price": c[i],
                            "score": g["score"] if g is not None else np.nan,
                            "L4": g["L4"] if g is not None else np.nan,
                            "L5": g["L5"] if g is not None else np.nan,
                            "reversal": g["reversal"] if g is not None else False,
                            "high_pos": g["high_pos"] if g is not None else False,
                        })
                        trades.append({"action": "buy", "i": i, "date": dates[i],
                                       "price": c[i], "qty": qty})
            equity[i] = cash + shares * c[i]
            if equity[i] > peak:
                peak = equity[i]
            dd = (peak - equity[i]) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)

        if shares > 0 and n > 0:
            proceeds = shares * c[-1] * (1 - m.COST)
            pnl = proceeds - entry_cost
            cash += proceeds
            if pnl > 0:
                wins += pnl
            else:
                losses += abs(pnl)
            trades.append({"action": "sell", "i": n - 1, "date": dates[-1],
                           "price": c[-1], "pnl": pnl})

        total_return = cash / 100000.0 - 1.0
        pf = wins / losses if losses > 0 else (np.inf if wins > 0 else np.nan)
        rets = np.diff(equity) / np.maximum(equity[:-1], 1e-9)
        sharpe = (rets.mean() / rets.std() * np.sqrt(252)) if len(rets) > 1 and rets.std() > 0 else 0.0
        sells = [t for t in trades if t["action"] == "sell"]
        wr = sum(1 for t in sells if t["pnl"] > 0) / len(sells) if sells else 0.0
        report = {
            "total_return": total_return, "max_drawdown": max_dd, "sharpe_ratio": sharpe,
            "pf": pf, "win_rate": wr, "total_trades": len(trades) // 2,
            "final_capital": cash, "wins": wins, "losses": losses, "sell_ut_n": sell_ut_n,
        }
        opens_df = pd.DataFrame(opens) if opens else pd.DataFrame(
            columns=["date", "price", "score", "L4", "L5", "reversal", "high_pos"])
        sig_df = pd.DataFrame(sig_rows) if sig_rows else pd.DataFrame(
            columns=["date", "price", "score", "reversal", "fwd10", "holding"])
        return report, opens_df, blocked, sig_df


VARIANTS = [
    ("V3_base_ut5r3lb10", 5, 3, 10, "基线 V3（P2.10 定稿参数）"),
    ("V3a_rec2", 5, 2, 10, "UT 收回窗口 3→2（更快收回=更严格）"),
    ("V3b_n10", 10, 3, 10, "UT 突破窗口 5→10（更高高点=更严格）"),
    ("V3c_rec2n10", 10, 2, 10, "双重收紧（n=10 且 rec=2）"),
    ("V3d_lb5", 5, 3, 5, "UT 检测回溯 10→5（只算最近 5 根内 UT）"),
]


def main():
    print("[P2.11] V3 逃顶卖点优化 + 反转通道复核 + 禁域占比修订开始...")
    files = sorted(glob.glob(os.path.join(m.DAILY_DIR, "*_daily.csv")))

    all_dates_list = []
    base_maps = {}
    for f in files:
        code = os.path.basename(f).replace("_daily.csv", "")
        v3 = build_v3_ut(code, 5, 3, 10)  # 先用基线参数建日期轴
        if v3 is not None:
            base_maps[code] = v3
            all_dates_list.append(v3["date"].values)
    all_dates = np.sort(np.unique(np.concatenate(all_dates_list)))
    cutoff = all_dates[int(len(all_dates) * m.TRAIN_RATIO)]
    cutoff_dt = pd.Timestamp(cutoff)
    print(f"walk-forward：训练 <{cutoff_dt:%Y-%m-%d} / 测试 ≥（样本外）")

    # ---- Part A：UT 收紧变体扫描（测试段）----
    results = {}
    for name, ut_n, ut_rec, ut_lb, desc in VARIANTS:
        te = []
        for code in list(base_maps.keys()):
            v3 = build_v3_ut(code, ut_n, ut_rec, ut_lb)
            if v3 is None:
                continue
            data = m.load_daily(code)
            if data is None or len(data) < 120:
                continue
            gate_map = {
                row.date_only: {
                    "score": int(row["score"]), "L4": bool(row["L4"]), "L5": bool(row["L5"]),
                    "reversal": bool(row["reversal"]), "sell_ut": bool(row["sell_ut"]),
                    "high_pos": bool(row["high_pos"]),
                }
                for _, row in v3.iterrows()
            }
            d_te = data[data["date"] >= cutoff_dt]
            if len(d_te) < 60:
                continue
            rep, opens_df, blk, sig = DonchianBacktestV3b(
                gate_map=gate_map, gated=True, mode="v3").run(d_te)
            te.append({"code": code, "report": rep, "opens_df": opens_df,
                       "blocked": blk, "sig_df": sig, "gate_map": gate_map, "data": d_te})
        results[name] = {"te": te, "desc": desc, "ut": (ut_n, ut_rec, ut_lb)}

    # ---- Part C：禁域占比（稳定性新口径）----
    def banned_rate(opens_df):
        if len(opens_df) == 0:
            return np.nan
        return (opens_df["L4"].eq(False) & opens_df["high_pos"].eq(True)).mean()

    L = []
    L.append("# P2.11 V3 逃顶卖点优化 + 反转通道复核 + 禁域占比口径修订报告")
    L.append("")
    L.append(f"- 生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}")
    L.append(f"- 信号源：Donchian 20/10 突破；交易逻辑：ATR×2 止损 + 单票 20% + 0.15% 双边费用")
    L.append(f"- walk-forward：训练 <{cutoff_dt:%Y-%m-%d} → 测试段样本外")
    L.append("")

    L.append("## Part A：UT 逃顶卖点结构收紧变体扫描（测试段）")
    L.append("")
    L.append("| 变体 | 参数(n/rec/lb) | 说明 | 逃顶卖出次数 | 每只均值 | 总收益 | 最大回撤 | 胜率 | 开仓数 | 信号效率 |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for name, r in results.items():
        te = r["te"]
        su = sum(x["report"]["sell_ut_n"] for x in te)
        rp = [x["report"] for x in te]
        ret = float(np.mean([x["total_return"] for x in rp]))
        dd = float(np.mean([x["max_drawdown"] for x in rp]))
        wr = float(np.mean([x["win_rate"] for x in rp]))
        nb = float(np.mean([x["total_trades"] for x in rp]))
        se = ret / nb if nb > 0 else np.nan
        L.append(f"| {name} | {r['ut'][0]}/{r['ut'][1]}/{r['ut'][2]} | {r['desc']} | "
                 f"{su} | {su/len(te):.1f} | {ret:+.4f} | {dd:.4f} | {wr:.3f} | "
                 f"{nb:.1f} | {se:+.5f} |")
    L.append("")

    L.append("## Part B：反转通道策略级 vs 信号级差异复核（测试段）")
    L.append("")
    base_te = results["V3_base_ut5r3lb10"]["te"]
    all_rev = pd.concat([x["sig_df"] for x in base_te], ignore_index=True)
    rev_holding = all_rev[all_rev["holding"] == True]
    rev_open = all_rev[all_rev["holding"] == False]
    L.append(f"- **测试段全反转信号（突破日，含持仓中）**：{len(all_rev)} 个，fwd10 均值 "
             f"**{all_rev['fwd10'].mean():+.4f}**（{(all_rev['fwd10'] > 0).mean():.1%} 正）")
    L.append(f"- 其中持仓中出现的反转信号（策略级跳过未开仓）：{len(rev_holding)} 个，"
             f"fwd10 均值 {rev_holding['fwd10'].mean():+.4f}（{(rev_holding['fwd10'] > 0).mean():.1%} 正）")
    L.append(f"- 其中空仓时开仓信号：{len(rev_open)} 个，fwd10 均值 "
             f"**{rev_open['fwd10'].mean():+.4f}**（{(rev_open['fwd10'] > 0).mean():.1%} 正）")
    if len(rev_holding) and len(rev_open):
        L.append(f"- 持仓 vs 空仓 fwd10 差：{rev_holding['fwd10'].mean() - rev_open['fwd10'].mean():+.4f}"
                 f"（若持仓组显著更差→持仓中错过的反转信号质量低，空仓过滤有正向选择作用；"
                 f"若两组接近→差异来自样本期/市场环境而非过滤）")
    L.append("")

    L.append("## Part C：禁域占比（稳定性新口径）—— 三组对比")
    L.append("")
    L.append("> 旧口径「逆势占比」（L4 空头开仓占比）对反转通道失效（反转通道放行的正是空头信号）；"
             "新口径「禁域占比」= 空头+高位开仓占比（P2.7 已证 fwd10 -0.0365 的禁域），"
             "考核稳定性=禁域开仓占比低且开仓量不塌缩。两种聚合口径均给出："
             "开仓等权（合并全部开仓后占比）与股票等权（每只股票占比后平均，与 P2.10 报告可比）。")
    L.append("")
    L.append("| 组别 | 禁域占比(开仓等权) | 禁域占比(股票等权) | 逆势占比(旧口径) | 开仓数均值 | 总收益 |")
    L.append("|---|---|---|---|---|---|")

    def part_c_row(label, rows):
        ob = pd.concat([x["opens_df"] for x in rows], ignore_index=True) if rows else pd.DataFrame()
        if len(ob):
            ban_open = banned_rate(ob)
            ban_avg = float(np.nanmean([banned_rate(x["opens_df"]) for x in rows]))
            cr = ob["L4"].eq(False).mean()
        else:
            ban_open = ban_avg = cr = np.nan
        nb = np.mean([x["report"]["total_trades"] for x in rows]) if rows else 0
        rt = np.mean([x["report"]["total_return"] for x in rows]) if rows else np.nan
        L.append(f"| {label} | {ban_open:.1%} | {ban_avg:.1%} | {cr:.1%} | {nb:.1f} | {rt:+.4f} |")

    # V2b 组（同框架补跑）
    te_v2b = []
    for code in list(base_maps.keys()):
        v3 = base_maps[code]
        data = m.load_daily(code)
        if data is None or len(data) < 120:
            continue
        gate_map = {row.date_only: {"score": int(row["score"]), "L4": bool(row["L4"]),
                                    "L5": bool(row["L5"]), "reversal": bool(row["reversal"]),
                                    "sell_ut": bool(row["sell_ut"]), "high_pos": bool(row["high_pos"])}
                    for _, row in v3.iterrows()}
        d_te = data[data["date"] >= cutoff_dt]
        if len(d_te) < 60:
            continue
        rep, opens_df, blk, _ = DonchianBacktestV3b(
            gate_map=gate_map, gated=True, mode="v2b").run(d_te)
        te_v2b.append({"opens_df": opens_df, "report": rep})
    part_c_row("V2b（纯拦截）", te_v2b)
    part_c_row("V3（基线 ut5r3lb10）", base_te)
    for name, r in results.items():
        if name == "V3_base_ut5r3lb10":
            continue
        part_c_row(name, r["te"])
    L.append("")

    L.append("## 结论（复核后填写）")
    L.append("")
    L.append("（Part A 最优 UT 参数、逃顶触发次数达标性；Part B 差异归因；"
             "Part C 禁域占比口径是否采纳为稳定性考核口径；四维护佑重判）")
    L.append("")

    os.makedirs(RESULT_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    out_path = os.path.join(RESULT_DIR, f"p211_ut_optimization_{stamp}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print("\n".join(L))
    print(f"\n报告已落盘: {out_path}")
    return out_path


if __name__ == "__main__":
    main()
