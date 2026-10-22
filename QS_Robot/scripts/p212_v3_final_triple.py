#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
P2.12 V3 定稿三件套确认（V3d：UT_N=5/UT_REC=3/UT_LB=5）
======================================================================
背景（P2.11 定稿，结论见 p211_ut_optimization_20261022.md）：
  V3 定稿参数 = V3d（UT 检测回溯 10→5）：逃顶卖出 -13.1%、总收益 +0.0038
  （优于 V2b +0.0026）、信号效率转正 +0.00134、禁域占比 0.3% → 四维护佑
  3 达标 + 1 部分达标。按 P2.10 定稿要求，写入 decision_engine 前须过
  P2.11 后重跑三件套确认。

本实验（P2.12，三件套）：
  Part 1 区分度检验（V1.5 gate_validation 范式）：测试段全突破信号——
    放行组（score≥4 或 reversal 反转通道放行）vs 拦截组（score<4 且非
    reversal）fwd10 + Welch t；反转通道放行子组单独统计；
  Part 2 完整回测（P2-Full 范式，530 只全池）：基线 / V2b / V3d 三组测试段
    四维护佑判定（稳定性用禁域占比新口径）；
  Part 3 逃顶卖点避损评估：sell_ut 触发卖出日 fwd10（卖出后 10 日收益）
    验证 UT 卖点避损有效性 + 误杀统计（卖出后继续上涨比例）。

判据（V1.5 §3.2 达标线，测试段）：
  安全性：最大回撤降≥15% 且 PF 不劣化
  精准性：PF/胜率改善且追高占比降≥20%
  高效性：信号效率（总收益/开仓数）提升≥20%
  稳定性：禁域占比低（空头+高位开仓占比）且信号不塌缩

用法：D:\anaconda3\python.exe p212_v3_final_triple.py
输出：results/p212_v3_final_triple_YYYYMMDD.md
"""
import os
import glob
from datetime import datetime

import numpy as np
import pandas as pd
from scipy import stats

import p210_v3_reversal_retest as p210
import p2_full_backtest as m

QS_ROOT = r"D:\Gupiao\升级vscode\QS_Robot"
RESULT_DIR = os.path.join(QS_ROOT, "results")

UT_N, UT_REC, UT_LB = 5, 3, 5  # V3d 定稿参数


def build_v3d(code):
    p210.UT_N, p210.UT_REC, p210.UT_LB = UT_N, UT_REC, UT_LB
    return p210.build_v3(code)


class V3dBacktest(m.DonchianBacktest):
    """V3d 模式：V2b 主放行 + 反转通道放行 + V3d UT 逃顶卖点；
    记录全信号（含被拦）fwd10 + 状态 + 逃顶卖出避损。"""

    def __init__(self, gate_map=None, gated=False, min_score=4, mode="v3d"):
        super().__init__(gate_map=gate_map, gated=gated, min_score=min_score)
        self.mode = mode

    def _blocked_at(self, g, i):
        if not (self.gated and g is not None):
            return False
        if self.mode == "v2b":
            return bool(g["score"] < self.min_score)
        return bool(g["score"] < self.min_score and not g["reversal"])

    def _exit_extra(self, g, i):
        if self.mode != "v3d":
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
        sig_all = []
        blocked = 0
        wins = losses = 0.0
        sell_ut_n = 0
        sell_ut_fwd10 = []  # 逃顶卖出日 fwd10（避损评估）

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
                    is_ut = g is not None and self._exit_extra(g, i) and not (
                        (i >= m.EXIT_N and c[i] < np.min(l[i - m.EXIT_N:i])) or c[i] < stop_price)
                    if is_ut:
                        sell_ut_n += 1
                        if i + 10 < n:
                            sell_ut_fwd10.append(c[i + 10] / c[i] - 1.0)
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
            if i >= m.ENTRY_N and c[i] > np.max(h[i - m.ENTRY_N:i]):
                fwd10 = c[i + 10] / c[i] - 1.0 if i + 10 < n else np.nan
                blocked_now = self._blocked_at(g, i) if g is not None else False
                sig_all.append({
                    "date": dates[i], "code_idx": None, "fwd10": fwd10,
                    "blocked": blocked_now,
                    "reversal": bool(g["reversal"]) if g is not None else False,
                    "score": g["score"] if g is not None else np.nan,
                })
            if shares == 0 and entry_sig:
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
        sig_df = pd.DataFrame(sig_all) if sig_all else pd.DataFrame(
            columns=["date", "fwd10", "blocked", "reversal", "score"])
        return report, opens_df, blocked, sig_df, sell_ut_fwd10


def main():
    print("[P2.12] V3 定稿三件套确认（V3d：UT_N=5/UT_REC=3/UT_LB=5）开始...")
    files = sorted(glob.glob(os.path.join(m.DAILY_DIR, "*_daily.csv")))

    all_dates_list = []
    maps = {}
    for f in files:
        code = os.path.basename(f).replace("_daily.csv", "")
        v3 = build_v3d(code)
        if v3 is not None:
            maps[code] = v3
            all_dates_list.append(v3["date"].values)
    all_dates = np.sort(np.unique(np.concatenate(all_dates_list)))
    cutoff = all_dates[int(len(all_dates) * m.TRAIN_RATIO)]
    cutoff_dt = pd.Timestamp(cutoff)
    print(f"walk-forward：训练 <{cutoff_dt:%Y-%m-%d} / 测试 ≥（样本外），池 {len(maps)} 只")

    te_b, te_v2b, te_v3d = [], [], []
    sig_all_rows = []
    su_fwd = []
    for code, v3 in maps.items():
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
        rep_b, ob_b, _, sig_b, _ = V3dBacktest(gate_map=gate_map, gated=False).run(d_te)
        rep_v2b, ob_v2b, blk2, _, _ = V3dBacktest(gate_map=gate_map, gated=True, mode="v2b").run(d_te)
        rep_v3d, ob_v3d, blk3, sig_v3d, su = V3dBacktest(gate_map=gate_map, gated=True, mode="v3d").run(d_te)
        te_b.append({"code": code, "report": rep_b, "opens_df": ob_b})
        te_v2b.append({"code": code, "report": rep_v2b, "opens_df": ob_v2b, "blocked": blk2})
        te_v3d.append({"code": code, "report": rep_v3d, "opens_df": ob_v3d, "blocked": blk3})
        sig_all_rows.append(sig_v3d)
        su_fwd.extend(su)

    # ---- Part 1 区分度 ----
    L = []
    L.append("# P2.12 V3 定稿三件套确认报告（V3d：UT_N=5/UT_REC=3/UT_LB=5）")
    L.append("")
    L.append(f"- 生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}")
    L.append(f"- 信号源：Donchian 20/10 突破；交易逻辑：ATR×2 止损 + 单票 20% + 0.15% 双边费用")
    L.append(f"- V3d = V2b ≥4/7 主放行 + 空头低位 B4 反转通道 + V3d UT 逃顶卖点（lb=5）")
    L.append(f"- walk-forward：训练 <{cutoff_dt:%Y-%m-%d} → 测试段样本外，池 {len(maps)} 只")
    L.append("")

    sig = pd.concat([s for s in sig_all_rows if len(s)], ignore_index=True).dropna(subset=["fwd10"])
    pas = sig[sig["blocked"] == False]
    blk = sig[sig["blocked"] == True]
    rev = pas[pas["reversal"] == True]
    L.append("## Part 1：放行/否决区分度（测试段全突破信号）")
    L.append("")
    L.append(f"| 组 | 数量 | fwd10 均值 | 正收益占比 | Welch t (vs 拦截) | p |")
    L.append("|---|---|---|---|---|---|")
    t_pas, p_pas = stats.ttest_ind(pas["fwd10"], blk["fwd10"], equal_var=False)
    t_rev, p_rev = stats.ttest_ind(rev["fwd10"], blk["fwd10"], equal_var=False)
    L.append(f"| 放行组（V2b 高分 + 反转通道） | {len(pas)} | {pas['fwd10'].mean():+.4f} | "
             f"{(pas['fwd10'] > 0).mean():.1%} | {t_pas:.2f} | {p_pas:.3g} |")
    L.append(f"| 反转通道放行子组（空头+低位+B4） | {len(rev)} | {rev['fwd10'].mean():+.4f} | "
             f"{(rev['fwd10'] > 0).mean():.1%} | {t_rev:.2f} | {p_rev:.3g} |")
    L.append(f"| 拦截组（score<4 且非反转） | {len(blk)} | {blk['fwd10'].mean():+.4f} | "
             f"{(blk['fwd10'] > 0).mean():.1%} | — | — |")
    L.append("")

    # ---- Part 2 完整回测三组对比 + 四维护佑 ----
    def agg(rows):
        df = pd.DataFrame([{
            "ret": r["report"]["total_return"], "dd": r["report"]["max_drawdown"],
            "wr": r["report"]["win_rate"], "pf": r["report"]["pf"],
            "sharpe": r["report"]["sharpe_ratio"], "n_buys": r["report"]["total_trades"],
            "blocked_rate": r.get("blocked", 0) / (len(r["opens_df"]) + r.get("blocked", 0))
            if (len(r["opens_df"]) + r.get("blocked", 0)) else np.nan,
            "banned": (r["opens_df"]["L4"].eq(False) & r["opens_df"]["high_pos"].eq(True)).mean()
            if len(r["opens_df"]) else np.nan,
            "contrarian": r["opens_df"]["L4"].eq(False).mean() if len(r["opens_df"]) else np.nan,
            "chase": r["opens_df"]["L5"].eq(True).mean() if len(r["opens_df"]) else np.nan,
        } for r in rows])
        df["sig_eff"] = df["ret"] / df["n_buys"].replace(0, np.nan)
        return df

    a_b, a_v2b, a_v3d = agg(te_b), agg(te_v2b), agg(te_v3d)
    L.append("## Part 2：完整回测三组对比（测试段样本外）")
    L.append("")
    L.append("| 指标 | 基线 B0 | V2b | V3d（定稿） | V3d vs 基线 |")
    L.append("|---|---|---|---|---|")
    for name, col, fmt in [("总收益率均值", "ret", "{:+.4f}"), ("最大回撤均值", "dd", "{:.4f}"),
                           ("胜率均值", "wr", "{:.3f}"), ("Sharpe", "sharpe", "{:.3f}"),
                           ("开仓次数均值", "n_buys", "{:.1f}"),
                           ("信号效率", "sig_eff", "{:+.5f}")]:
        b, v2, v3 = a_b[col].mean(), a_v2b[col].mean(), a_v3d[col].mean()
        L.append(f"| {name} | {fmt.format(b)} | {fmt.format(v2)} | {fmt.format(v3)} | {fmt.format(v3 - b)} |")
    wins_b = sum(r["report"]["wins"] for r in te_b); losses_b = sum(r["report"]["losses"] for r in te_b)
    wins_v3 = sum(r["report"]["wins"] for r in te_v3d); losses_v3 = sum(r["report"]["losses"] for r in te_v3d)
    pfp_b = wins_b / losses_b if losses_b > 0 else (np.inf if wins_b > 0 else np.nan)
    pfp_v3 = wins_v3 / losses_v3 if losses_v3 > 0 else (np.inf if wins_v3 > 0 else np.nan)
    L.append(f"- pooled PF：基线 {pfp_b:.2f} → V3d {pfp_v3:.2f}")
    L.append(f"- 禁域占比（开仓等权）：基线 {a_b['banned'].mean():.1%}｜V2b {a_v2b['banned'].mean():.1%}｜"
             f"V3d {a_v3d['banned'].mean():.1%}；逆势占比（旧口径）：V3d {a_v3d['contrarian'].mean():.1%}")
    L.append(f"- 追高占比：V3d {a_v3d['chase'].mean():.1%}；拦截率 V3d {a_v3d['blocked_rate'].mean():.1%}")
    L.append("")

    L.append("### 四维护佑判定（V3d vs 基线，V1.5 §3.2 达标线，稳定性用禁域占比新口径）")
    L.append("")
    L.append("| 维度 | 达标线 | 实测 | 判定 |")
    L.append("|---|---|---|---|")
    dd_b, dd_v3 = a_b["dd"].mean(), a_v3d["dd"].mean()
    wr_b, wr_v3 = a_b["wr"].mean(), a_v3d["wr"].mean()
    se_b, se_v3 = a_b["sig_eff"].mean(), a_v3d["sig_eff"].mean()
    h_v3 = a_v3d["chase"].mean()
    ba_v3 = a_v3d["banned"].mean()
    nb_b, nb_v3 = a_b["n_buys"].mean(), a_v3d["n_buys"].mean()
    checks = [
        ("安全性", "回撤降≥15% 且 PF 不劣化",
         f"回撤 {dd_b:.4f}→{dd_v3:.4f}（{(dd_v3/dd_b-1)*100 if dd_b else 0:+.1f}%）；pooled PF {pfp_b:.2f}→{pfp_v3:.2f}"),
        ("精准性", "PF/胜率改善且追高占比降≥20%",
         f"胜率 {wr_b:.1%}→{wr_v3:.1%}；pooled PF {pfp_b:.2f}→{pfp_v3:.2f}；追高占比 {h_v3:.1%}"),
        ("高效性", "信号效率提升≥20%",
         f"信号效率 {se_b:+.5f}→{se_v3:+.5f}（{((se_v3-se_b)/abs(se_b))*100 if se_b else 0:+.0f}%）"),
        ("稳定性", "禁域占比低且信号不塌缩（新口径）",
         f"禁域占比 {ba_v3:.1%}；开仓数 {nb_b:.0f}→{nb_v3:.0f}"),
    ]
    verdicts = []
    for name, crit, got in checks:
        L.append(f"| {name} | {crit} | {got} | （复核后填写） |")
    L.append("")

    # ---- Part 3 逃顶避损 ----
    L.append("## Part 3：逃顶卖点避损评估（测试段）")
    L.append("")
    su_arr = np.array(su_fwd) if su_fwd else np.array([])
    L.append(f"- **UT 触发卖出总次数**：{sum(r['report']['sell_ut_n'] for r in te_v3d)}（每只 "
             f"{np.mean([r['report']['sell_ut_n'] for r in te_v3d]):.1f}）")
    if len(su_arr):
        L.append(f"- **卖出日 fwd10 均值**：{su_arr.mean():+.4f}（{(su_arr < 0).mean():.1%} 卖出后 10 日下跌）")
        L.append(f"- **避损有效性**：卖出后继续下跌占比 {(su_arr < 0).mean():.1%}（>50% 即多数卖点避开了后续下跌）")
        L.append(f"- **误杀率**：卖出后 10 日上涨（反弹）占比 {(su_arr > 0).mean():.1%}——"
                 f"这部分是可能被砍掉的反弹利润（P2.10 逃顶过频的残留）")
    else:
        L.append("- 无逃顶卖出样本")
    L.append("")

    L.append("## 结论（复核后填写）")
    L.append("")
    L.append("（Part 1 区分度是否显著；Part 2 四维护佑是否全达标；Part 3 逃顶避损是否有效；"
             "V3d 是否写入 decision_engine）")
    L.append("")

    os.makedirs(RESULT_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    out_path = os.path.join(RESULT_DIR, f"p212_v3_final_triple_{stamp}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print("\n".join(L))
    print(f"\n报告已落盘: {out_path}")
    return out_path


if __name__ == "__main__":
    main()
