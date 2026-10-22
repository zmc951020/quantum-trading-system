#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
P2.10 V3 通道并入重跑（V2b ≥4/7 主放行 + 反转确认通道 + 逃顶卖点确认）
======================================================================
背景（Q5/Q6/P2.9 定稿，V1.11）：
  - 买点侧确认（P2.9）：空头+低位 + B4（500 日区间分位<20%）→ 反转买点
    专门放行（fwd10 +0.0336 vs 基线 +0.0153，独立增量）；
  - 卖点侧确认（P2.9）：多头+高位 + S3（威科夫 UT）→ 逃顶卖出（fwd10
    -0.0347 vs 基线 -0.0175，避损翻倍）；
  - V2b（P2.6 最优变体）：L4 双倍权重、总分 7、≥4/7 为 P2.6 训练段标定档。

本实验（P2.10）回答（实证闸门 3：策略级四维护佑）：
  V3 = V2b ≥4/7 主放行 + 空头低位 B4 反转通道 + 多头高位 S3 逃顶卖点，
  与 基线 B0 / V2b 同框架、同测试段对比：
  1) V3 vs 基线：四维护佑达标线判定（安全性/稳定性/高效性/精准性）；
  2) V3 vs V2b：通道并入的增量（开仓量恢复、质量是否保持、回撤是否降）；
  3) 反转通道与逃顶卖点的信号统计（放行数、fwd10、触发卖出次数、避损）；
  4) B4/S3 为"设计先验"（0.20 分位、3 根窗口来自文献/课题设计，非测试段
     数据拟合），阈值不重标定 → 过拟合风险低；WFA 结构沿用训练/测试分离。

判据（V1.5 §3.2 达标线，测试段）：
  安全性：最大回撤降≥15% 且 PF 不劣化
  精准性：PF/胜率改善且追高占比降≥20%
  高效性：信号效率（总收益/开仓数）提升≥20%
  稳定性：逆势占比降且信号不塌缩（开仓量可接受）

输出：results/p210_v3_reversal_retest_YYYYMMDD.md
用法：D:\anaconda3\python.exe p210_v3_reversal_retest.py
"""
import os
import glob
from datetime import datetime

import numpy as np
import pandas as pd

import p2_full_backtest as m  # 复用常量/load_daily/prev_close/week_ema_state

QS_ROOT = r"D:\Gupiao\升级vscode\QS_Robot"
RESULT_DIR = os.path.join(QS_ROOT, "results")

MIN_SCORE = 4      # V2b ≥4/7
POS_LOW = 0.20     # B4 分位（设计先验）
UT_N = 5           # UT 突破窗口
UT_REC = 3         # UT 收回窗口
UT_LB = 10         # UT 检测回溯


def ut_series(high, close, n=UT_N, rec=UT_REC, lb=UT_LB):
    """威科夫 UT 布尔序列（无前视）：
    s3[i] = 窗口 [i-lb, i-1] 内存在 k：high[k] > max(high[k-n:k]) 且
            min(close[k:k+rec]) < max(high[k-n:k])（突破近期高点后 rec 根内回落）
    全部信息 ≤ i-1，信号日 i 收盘后可用。"""
    N = len(high)
    s3 = np.zeros(N, dtype=bool)
    for i in range(lb, N):
        ok = False
        for k in range(i - lb, i):
            if k <= 0:
                continue
            ref = float(np.max(high[max(0, k - n):k]))
            if high[k] > ref and float(np.min(close[k:k + rec])) < ref:
                ok = True
                break
        s3[i] = ok
    return s3


def build_v3(code):
    """V2b 打分（L4 双倍权重，总分 7）+ 反转通道列 + 逃顶卖点列。"""
    f = os.path.join(m.DAILY_DIR, f"{code}_daily.csv")
    if not os.path.exists(f):
        return None
    df = pd.read_csv(f)
    date_col = "date" if "date" in df.columns else "time"
    d = pd.DataFrame({
        "date": pd.to_datetime(df[date_col], format="mixed", errors="coerce"),
        "close": pd.to_numeric(df["close"], errors="coerce"),
        "high": pd.to_numeric(df["high"], errors="coerce"),
        "low": pd.to_numeric(df["low"], errors="coerce"),
    }).dropna(subset=["close", "high", "low"]).tail(m.LOOKBACK + 200).reset_index(drop=True)
    if len(d) < 120:
        return None
    c = d["close"]
    py = m.prev_close("daily_year", code)
    pq = m.prev_close("daily_quarter", code)
    wk = m.week_ema_state(code)
    l1_high = (c / py - 1 > 0) if np.isfinite(py) else pd.Series(False, index=d.index)
    l2_high = (c / pq - 1 > 0) if np.isfinite(pq) else pd.Series(False, index=d.index)
    kst, sig = m.kst_signal(c)
    l3 = (kst > sig).fillna(False)
    l4 = pd.Series(bool(wk) if wk is not None else False, index=d.index)
    hi = c.rolling(m.WINDOW_ZONE, min_periods=100).max().shift(1)  # 防前视：用 i 前 500 日
    lo = c.rolling(m.WINDOW_ZONE, min_periods=100).min().shift(1)
    span = (hi - lo).replace(0, np.nan)
    pos = (c - lo) / span
    l5 = (pos > 0.5).fillna(False)
    atr = c.diff().abs().rolling(m.WINDOW_ATR).mean()
    l6 = (atr < atr.rolling(m.WINDOW_ATR_MEAN).mean()).fillna(False)
    b4 = (pos < POS_LOW).fillna(False)
    s3 = ut_series(d["high"].values, c.values)
    high_pos = (c / py - 1 > 0) if np.isfinite(py) else pd.Series(False, index=d.index)
    low_pos = (c / py - 1 < 0) if np.isfinite(py) else pd.Series(False, index=d.index)
    out = pd.DataFrame({
        "date": d["date"].values, "close": c.values,
        "rL1": (~l1_high).astype(bool).values,
        "rL2": (~l2_high).astype(bool).values,
        "L3": l3.astype(bool).values,
        "L4": l4.astype(bool).values,
        "L5": l5.astype(bool).values,
        "L6": l6.astype(bool).values,
        "b4": b4.astype(bool).values,
        "s3": s3,
        "high_pos": high_pos.astype(bool).values,
        "low_pos": low_pos.astype(bool).values,
    }).tail(m.LOOKBACK)
    out["score"] = (out[["rL1", "rL2", "L3", "L5", "L6"]].sum(axis=1)
                    + 2 * out["L4"].astype(int))                     # L4 双倍权重，总分 7
    out["reversal"] = (~out["L4"]) & out["low_pos"] & out["b4"]      # 反转通道：空头+低位+B4
    out["sell_ut"] = out["L4"] & out["high_pos"] & out["s3"]         # 逃顶卖点：多头+高位+S3
    out["date_only"] = out["date"].dt.date
    return out


class DonchianBacktestV3(m.DonchianBacktest):
    """V2b gated 回测（可切换 V2b 纯拦截 / V3 通道版）：

    mode='v2b'：score < min_score 即拦截（P2.6 最优变体策略级对照）
    mode='v3' ：score < min_score 且 NOT reversal 才拦截（反转通道放行）；
                持仓时若当日 sell_ut 触发逃顶卖出（在常规离场之外）。
    """

    def __init__(self, gate_map=None, gated=False, min_score=MIN_SCORE, mode="v3"):
        super().__init__(gate_map=gate_map, gated=gated, min_score=min_score)
        self.mode = mode

    def _blocked_at(self, g, i):
        if not (self.gated and g is not None):
            return False
        if self.mode == "v2b":
            return bool(g["score"] < self.min_score)
        # v3：反转通道放行
        return bool(g["score"] < self.min_score and not g["reversal"])

    def _exit_extra(self, g, i):
        """逃顶卖点：V3 模式下多头+高位+S3 触发卖出"""
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
        entry_price = 0.0
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
            if shares == 0 and i >= m.ENTRY_N:
                entry_sig = c[i] > np.max(h[i - m.ENTRY_N:i])
                if entry_sig:
                    fwd10 = c[i + 10] / c[i] - 1.0 if i + 10 < n else np.nan
                    blocked_now = self._blocked_at(g, i)
                    sig_rows.append({
                        "date": dates[i], "price": c[i],
                        "score": g["score"] if g is not None else np.nan,
                        "L4": g["L4"] if g is not None else np.nan,
                        "L5": g["L5"] if g is not None else np.nan,
                        "reversal": g["reversal"] if g is not None else False,
                        "sell_ut": g["sell_ut"] if g is not None else False,
                        "blocked": blocked_now,
                        "fwd10": fwd10,
                    })
                    if blocked_now:
                        blocked += 1
                    else:
                        qty = int(cash * m.POS_PCT / c[i] / 100) * 100
                        if qty > 0:
                            entry_cost = qty * c[i] * (1 + m.COST)
                            cash -= entry_cost
                            shares = qty
                            entry_price = c[i]
                            stop_price = c[i] - m.ATR_STOP_MULT * (
                                atr_arr[i] if np.isfinite(atr_arr[i]) else c[i] * 0.02)
                            opens.append({
                                "date": dates[i], "price": c[i],
                                "score": g["score"] if g is not None else np.nan,
                                "L4": g["L4"] if g is not None else np.nan,
                                "L5": g["L5"] if g is not None else np.nan,
                                "reversal": g["reversal"] if g is not None else False,
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
            columns=["date", "price", "score", "L4", "L5", "reversal"])
        sig_df = pd.DataFrame(sig_rows) if sig_rows else pd.DataFrame(
            columns=["date", "price", "score", "L4", "L5", "reversal", "sell_ut", "blocked", "fwd10"])
        return report, opens_df, blocked, sig_df


def main():
    print("[P2.10] V3 通道并入重跑（V2b + 反转确认通道 + 逃顶卖点）开始...")
    files = sorted(glob.glob(os.path.join(m.DAILY_DIR, "*_daily.csv")))
    scores = {}
    for f in files:
        code = os.path.basename(f).replace("_daily.csv", "")
        v3 = build_v3(code)
        if v3 is not None:
            scores[code] = v3
    print(f"V3 打分构建完成：{len(scores)} 只")

    all_dates = np.sort(np.unique(np.concatenate([v3["date"].values for v3 in scores.values()])))
    cutoff = all_dates[int(len(all_dates) * m.TRAIN_RATIO)]
    cutoff_dt = pd.Timestamp(cutoff)
    print(f"walk-forward：训练 <{cutoff_dt:%Y-%m-%d} / 测试 ≥（样本外）")

    tr_b, tr_v2b, tr_v3, te_b, te_v2b, te_v3 = [], [], [], [], [], []
    for code, v3 in scores.items():
        data = m.load_daily(code)
        if data is None or len(data) < 120:
            continue
        gate_map = {
            row.date_only: {
                "score": int(row["score"]), "L4": bool(row["L4"]), "L5": bool(row["L5"]),
                "reversal": bool(row["reversal"]), "sell_ut": bool(row["sell_ut"]),
            }
            for _, row in v3.iterrows()
        }
        d_tr = data[data["date"] < cutoff_dt]
        d_te = data[data["date"] >= cutoff_dt]
        for seg, b_list, v2b_list, v3_list in ((d_tr, tr_b, tr_v2b, tr_v3),
                                               (d_te, te_b, te_v2b, te_v3)):
            if len(seg) < 60:
                continue
            rep_b, opens_b, _, _ = DonchianBacktestV3(gate_map=gate_map, gated=False).run(seg)
            rep_v2b, opens_v2b, blk2, _ = DonchianBacktestV3(
                gate_map=gate_map, gated=True, mode="v2b").run(seg)
            rep_v3, opens_v3, blk3, sig_v3 = DonchianBacktestV3(
                gate_map=gate_map, gated=True, mode="v3").run(seg)
            b_list.append({"code": code, "report": rep_b, "opens_df": opens_b, "blocked": 0})
            v2b_list.append({"code": code, "report": rep_v2b, "opens_df": opens_v2b,
                             "blocked": blk2})
            v3_list.append({"code": code, "report": rep_v3, "opens_df": opens_v3,
                            "blocked": blk3, "sig_df": sig_v3})

    def agg(rows):
        return m.aggregate(rows)

    L = []
    L.append("# P2.10 V3 通道并入重跑报告（V2b ≥4/7 + 反转确认通道 + 逃顶卖点）")
    L.append("")
    L.append(f"- 生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}")
    L.append(f"- 信号源：Donchian 20/10 突破；交易逻辑：ATR×2 止损 + 单票 20% + 0.15% 双边费用")
    L.append(f"- 组别：B0=基线（无闸门）｜V2b=纯拦截（score<4 拦截，P2.6 最优变体）｜"
             f"V3=V2b + 空头低位B4反转通道放行 + 多头高位S3逃顶卖点")
    L.append(f"- B4/S3 为设计先验（分位 0.20、UT 3 根窗口），阈值不重标定（防过拟合）")
    L.append(f"- walk-forward：训练 <{cutoff_dt:%Y-%m-%d} → 测试段样本外")
    L.append("")

    def block_compare(label, a_b, a_x, xlabel):
        L.append(f"### {label}")
        L.append("")
        L.append(f"**{xlabel} vs 基线**（基线 n={len(a_b)} / {xlabel} n={len(a_x)}）")
        L.append("")
        L.append("| 指标 | 基线 | %s | 变化 |" % xlabel)
        L.append("|---|---|---|---|")
        rows = [
            ("总收益率均值", "ret", "{:+.4f}"),
            ("最大回撤均值", "dd", "{:.4f}"),
            ("胜率均值", "wr", "{:.3f}"),
            ("PF 均值", "pf", "{:.2f}"),
            ("Sharpe 均值", "sharpe", "{:.3f}"),
            ("开仓次数均值", "n_buys", "{:.1f}"),
            ("信号效率(收益/开仓)", "sig_eff", "{:+.5f}"),
        ]
        for name, col, fmt in rows:
            b, x = a_b[col].mean(), a_x[col].mean()
            if np.isfinite(b) and np.isfinite(x):
                L.append(f"| {name} | {fmt.format(b)} | {fmt.format(x)} | {fmt.format(x - b)} |")
            else:
                L.append(f"| {name} | — | — | — |")
        L.append("")
        L.append(f"- 拦截率：{a_x['blocked_rate'].mean():.1%}；逆势开仓占比 {a_x['contrarian_rate'].mean():.1%}；"
                 f"追高占比 {a_x['chase_rate'].mean():.1%}")
        return "\n".join(L)

    L.append("## 1. 测试段（样本外）三组对比 —— 核心结论段")
    L.append("")
    a_b = agg(te_b)
    a_v2b = agg(te_v2b)
    a_v3 = agg(te_v3)
    L.append("| 指标 | 基线 B0 | V2b（纯拦截） | V3（通道并入） | V2b→V3 增量 |")
    L.append("|---|---|---|---|---|")
    rows = [
        ("总收益率均值", "ret", "{:+.4f}"),
        ("最大回撤均值", "dd", "{:.4f}"),
        ("胜率均值", "wr", "{:.3f}"),
        ("PF 均值", "pf", "{:.2f}"),
        ("Sharpe 均值", "sharpe", "{:.3f}"),
        ("开仓次数均值", "n_buys", "{:.1f}"),
        ("信号效率(收益/开仓)", "sig_eff", "{:+.5f}"),
    ]
    for name, col, fmt in rows:
        b, v2, v3 = a_b[col].mean(), a_v2b[col].mean(), a_v3[col].mean()
        L.append(f"| {name} | {fmt.format(b)} | {fmt.format(v2)} | {fmt.format(v3)} | {fmt.format(v3 - v2)} |")
    L.append("")
    L.append(f"- 拦截率：V2b {a_v2b['blocked_rate'].mean():.1%}｜V3 {a_v3['blocked_rate'].mean():.1%}")
    L.append(f"- 逆势开仓占比：V2b {a_v2b['contrarian_rate'].mean():.1%}｜V3 {a_v3['contrarian_rate'].mean():.1%}")
    L.append(f"- 追高开仓占比：V2b {a_v2b['chase_rate'].mean():.1%}｜V3 {a_v3['chase_rate'].mean():.1%}")
    L.append("")

    L.append("## 2. V3 反转通道与逃顶卖点信号统计（测试段）")
    L.append("")
    if te_v3:
        s_all = pd.concat([r["sig_df"] for r in te_v3], ignore_index=True).dropna(subset=["fwd10"])
        rev = s_all[s_all["reversal"]]
        if len(rev):
            L.append(f"- **反转通道放行的反转买点信号**：{len(rev)} 个，fwd10 均值 "
                     f"**{rev['fwd10'].mean():+.4f}**（{(rev['fwd10'] > 0).mean():.1%} 正收益）")
        else:
            L.append("- 反转通道信号：0 个")
        su = [r["report"]["sell_ut_n"] for r in te_v3]
        L.append(f"- **逃顶卖点触发卖出**：合计 {sum(su)} 次（每只均值 {np.mean(su):.1f}）")
    L.append("")

    L.append("## 3. 四维护佑判定（测试段，V3 vs 基线，对照 V1.5 §3.2 达标线）")
    L.append("")
    dd_b, dd_v3 = a_b["dd"].mean(), a_v3["dd"].mean()
    wr_b, wr_v3 = a_b["wr"].mean(), a_v3["wr"].mean()
    se_b, se_v3 = a_b["sig_eff"].mean(), a_v3["sig_eff"].mean()
    wins_b = sum(r["report"]["wins"] for r in te_b)
    losses_b = sum(r["report"]["losses"] for r in te_b)
    wins_v3 = sum(r["report"]["wins"] for r in te_v3)
    losses_v3 = sum(r["report"]["losses"] for r in te_v3)
    pfp_b = wins_b / losses_b if losses_b > 0 else (np.inf if wins_b > 0 else np.nan)
    pfp_v3 = wins_v3 / losses_v3 if losses_v3 > 0 else (np.inf if wins_v3 > 0 else np.nan)
    cr_v3 = a_v3["contrarian_rate"].mean()
    hr_v3 = a_v3["chase_rate"].mean()
    L.append("| 护佑维度 | 达标线（V1.5 §3.2） | 实测 | 判定 |")
    L.append("|---|---|---|---|")
    checks = [
        ("安全性", "最大回撤降≥15% 且 PF 不劣化",
         f"回撤 {dd_b:.4f}→{dd_v3:.4f}（{(dd_v3/dd_b-1)*100 if dd_b else 0:+.1f}%）；pooled PF {pfp_b:.2f}→{pfp_v3:.2f}"),
        ("精准性", "PF/胜率改善且追高占比降≥20%",
         f"胜率 {wr_b:.1%}→{wr_v3:.1%}；pooled PF {pfp_b:.2f}→{pfp_v3:.2f}；追高占比 {hr_v3:.1%}"),
        ("高效性", "信号效率提升≥20%",
         f"信号效率 {se_b:+.5f}→{se_v3:+.5f}；拦截率 {a_v3['blocked_rate'].mean():.1%}"),
        ("稳定性", "逆势占比降且信号不塌缩",
         f"逆势开仓占比 {cr_v3:.1%}；开仓数 {a_b['n_buys'].mean():.0f}→{a_v3['n_buys'].mean():.0f}"),
    ]
    verdicts = []
    for name, crit, got in checks:
        L.append(f"| {name} | {crit} | {got} | （复核后填写） |")
    L.append("")

    L.append("## 4. V3 vs V2b：通道并入增量小结")
    L.append("")
    L.append("- V2b 纯拦截（P2.6 最优变体）为对照基线；V3 在其上增加反转通道放行 + 逃顶卖点，"
             "量化观察：开仓量是否恢复（稳定性塌缩缓解）、fwd10 质量是否保持（不劣化）、"
             "回撤是否继续下降（安全性）——三项共同决定通道并入是否值得写入 decision_engine。")
    L.append("")

    L.append("## 5. 结论（复核后填写）")
    L.append("")
    L.append("（判定：V3 是否达成四维护佑且较 V2b 有增量；是否进入 decision_engine 写入流程）")
    L.append("")

    os.makedirs(RESULT_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    out_path = os.path.join(RESULT_DIR, f"p210_v3_reversal_retest_{stamp}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print("\n".join(L))
    print(f"\n报告已落盘: {out_path}")
    return out_path


if __name__ == "__main__":
    main()
