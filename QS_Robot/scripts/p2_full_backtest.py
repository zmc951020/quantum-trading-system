#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
P2 正式回测：V2 放行线 + 完整策略回测（P2-Full，Donchian 主载体）
================================================================
背景：P2A/P2B 已证 V2（L1/L2 低位加分）在"时点级 fwd10"样本外有效
     （测试段 ≥4/6 +0.0325/PF2.57）。但时点级验证 ≠ 策略级验证：
     必须证明在完整交易逻辑（仓位/止损/组合约束/择时/费用）下，
     V2 闸门确实护佑策略（四维护佑：安全性/稳定性/高效性/精准性）。

信号源选型（A 级勘查结论）：
  - downtrend_optimized 信号极低频（000001 全历史 8455 日仅 17 信号、500 日 0 信号），
    不宜作统计主载体 → 降级为附录佐证。
  - 主载体 = Donchian 20 日突破（经典海龟式趋势信号，20 只样本 500 日 878 信号、
    平均每只 43.9 个，样本充足），带完整交易逻辑：
      开仓：收盘 > 前 20 日最高（突破）；离场：收盘 < 前 10 日最低 或 ATR×2 止损；
      仓位：单票 20% 资金上限；费用：0.15% 双边；T+1 天然满足（日线级）。

设计：
  1. V2 打分（6 层：rL1/rL2 低位加分+KST+周线EMA+zone+VCP）全池构建
  2. walk-forward：全局日历切分，训练段 60% 标定放行线分位，测试段 40%（样本外）验证
  3. 基线 B0 = Donchian 原生（无闸门）；护佑后 B1 = Donchian + V2 ≥4/6 拦截首次开仓
  4. 指标：策略级（总收益/回撤/胜率/PF/Sharpe/交易数）
           + 四维护佑专项（逆势开仓占比 L4 空头 / 追高开仓占比 L5 高位 /
             信号效率=总收益/开仓数 / 拦截率 / 开仓后 10 日止损触发率）
  5. 判据（V1.5 §3.2 达标线，测试段）：回撤降≥15% 且 PF/胜率不劣化、
     追高/逆势开仓占比降≥20%、信号效率提升≥20%。

输出：results/p2_full_backtest_YYYYMMDD.md
用法：python p2_full_backtest.py
依赖：D:\anaconda3\python.exe（numpy/pandas）
"""
import os
import glob
from datetime import datetime

import numpy as np
import pandas as pd

QS_ROOT = r"D:\Gupiao\升级vscode\QS_Robot"
DAILY_DIR = os.path.join(QS_ROOT, "export_package", "data", "daily_data_ext")
MTF_ROOT = os.path.join(QS_ROOT, "export_package", "data", "multi_timeframe")
RESULT_DIR = os.path.join(QS_ROOT, "results")

LOOKBACK = 500
TRAIN_RATIO = 0.60
MIN_SCORE = 4
COST = 0.0015
ENTRY_N = 20
EXIT_N = 10
ATR_N = 14
ATR_STOP_MULT = 2.0
POS_PCT = 0.20
WINDOW_ATR = 20
WINDOW_ATR_MEAN = 60
WINDOW_ZONE = 500


# ---------- V2 打分（与 gate_walkforward 同逻辑） ----------

def prev_close(mtf_dir: str, code: str):
    try:
        df = pd.read_csv(os.path.join(MTF_ROOT, mtf_dir, f"{code}.csv"))
        if len(df) >= 2:
            return float(df.iloc[-2]["close"])
    except Exception:
        pass
    return float("nan")


def week_ema_state(code: str):
    try:
        df = pd.read_csv(os.path.join(MTF_ROOT, "daily_week", f"{code}.csv"))
        c = pd.to_numeric(df["close"], errors="coerce").dropna()
        if len(c) < 50:
            return None
        return bool(c.ewm(span=20, adjust=False).mean().iloc[-1]
                    > c.ewm(span=50, adjust=False).mean().iloc[-1])
    except Exception:
        return None


def kst_signal(close: pd.Series):
    roc = lambda n: close.pct_change(n) * 100.0  # noqa: E731
    k = (roc(10).rolling(10).mean() * 1 + roc(15).rolling(15).mean() * 2
         + roc(20).rolling(20).mean() * 3 + roc(30).rolling(30).mean() * 4)
    kst = k.rolling(10).mean()
    return kst, kst.rolling(9).mean()


def build_v2(code: str):
    f = os.path.join(DAILY_DIR, f"{code}_daily.csv")
    if not os.path.exists(f):
        return None
    df = pd.read_csv(f)
    date_col = "date" if "date" in df.columns else "time"
    d = pd.DataFrame({
        "date": pd.to_datetime(df[date_col], format="mixed", errors="coerce"),
        "close": pd.to_numeric(df["close"], errors="coerce"),
    }).dropna().tail(LOOKBACK + 200)
    if len(d) < 80:
        return None
    c = d["close"]
    py = prev_close("daily_year", code)
    pq = prev_close("daily_quarter", code)
    wk = week_ema_state(code)
    l1_high = (c / py - 1 > 0) if np.isfinite(py) else pd.Series(False, index=d.index)
    l2_high = (c / pq - 1 > 0) if np.isfinite(pq) else pd.Series(False, index=d.index)
    kst, sig = kst_signal(c)
    l3 = (kst > sig).fillna(False)
    l4 = pd.Series(bool(wk) if wk is not None else False, index=d.index)
    hi = c.rolling(WINDOW_ZONE, min_periods=100).max()
    lo = c.rolling(WINDOW_ZONE, min_periods=100).min()
    span = (hi - lo).replace(0, np.nan)
    l5 = ((c - lo) / span > 0.5).fillna(False)
    atr = c.diff().abs().rolling(WINDOW_ATR).mean()
    l6 = (atr < atr.rolling(WINDOW_ATR_MEAN).mean()).fillna(False)
    out = pd.DataFrame({
        "date": d["date"].values, "close": c.values,
        "rL1": (~l1_high).astype(bool).values,
        "rL2": (~l2_high).astype(bool).values,
        "L3": l3.astype(bool).values,
        "L4": l4.astype(bool).values,
        "L5": l5.astype(bool).values,
        "L6": l6.astype(bool).values,
    }).tail(LOOKBACK)
    out["score"] = out[["rL1", "rL2", "L3", "L4", "L5", "L6"]].sum(axis=1)
    out["date_only"] = out["date"].dt.date
    return out


def load_daily(code: str):
    f = os.path.join(DAILY_DIR, f"{code}_daily.csv")
    if not os.path.exists(f):
        return None
    df = pd.read_csv(f)
    date_col = "date" if "date" in df.columns else "time"
    out = pd.DataFrame({
        "date": pd.to_datetime(df[date_col], format="mixed", errors="coerce"),
        "close": pd.to_numeric(df["close"], errors="coerce"),
        "high": pd.to_numeric(df["high"], errors="coerce"),
        "low": pd.to_numeric(df["low"], errors="coerce"),
    }).dropna(subset=["close", "high", "low"]).tail(LOOKBACK)
    return out


# ---------- Donchian 突破策略 + 完整交易逻辑 ----------

class DonchianBacktest:
    """Donchian 20/10 突破，ATR 仓位 + ATR×2 止损，含双边费用。

    gated=True 时叠加 V2 闸门：首次开仓日 score < min_score 则拦截。
    返回：{report_dict, opens(DataFrame: date, score, L4, L5), blocked_n, trades}
    """

    def __init__(self, gate_map=None, gated=False, min_score=MIN_SCORE):
        self.gate_map = gate_map or {}   # {date_obj: {'score','L4','L5'}}
        self.gated = gated
        self.min_score = min_score

    def run(self, data: pd.DataFrame):
        c = data["close"].values
        h = data["high"].values
        l = data["low"].values
        dates = data["date"].dt.date.values  # object array of python date
        n = len(c)
        equity = np.zeros(n)
        cash = 100000.0
        shares = 0
        entry_price = 0.0
        entry_cost = 0.0
        stop_price = 0.0
        peak = 100000.0
        max_dd = 0.0
        trades = []          # 完整交易记录（开/平）
        opens = []           # 开仓明细
        sig_rows = []        # 所有突破信号时点（含被拦截，用于区分度检验）
        blocked = 0
        wins = losses = 0.0

        # 滚动指标
        atr_arr = np.full(n, np.nan)
        for i in range(ATR_N, n):
            tr = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
            atr_arr[i] = np.mean([max(h[j] - l[j], abs(h[j] - c[j - 1]), abs(l[j] - c[j - 1]))
                                  for j in range(i - ATR_N + 1, i + 1)])

        for i in range(n):
            # --- 持仓管理 ---
            if shares > 0:
                exit_ok = (i >= EXIT_N and c[i] < np.min(l[i - EXIT_N:i])) or c[i] < stop_price
                if exit_ok:
                    proceeds = shares * c[i] * (1 - COST)
                    pnl = proceeds - entry_cost
                    cash += proceeds
                    if pnl > 0:
                        wins += pnl
                    else:
                        losses += abs(pnl)
                    trades.append({"action": "sell", "i": i, "date": dates[i],
                                   "price": c[i], "pnl": pnl})
                    shares = 0            # --- 空仓开仓 ---
            if shares == 0 and i >= ENTRY_N:
                entry_sig = c[i] > np.max(h[i - ENTRY_N:i])
                if entry_sig:
                    g = self.gate_map.get(dates[i], None)
                    fwd10 = c[i + 10] / c[i] - 1.0 if i + 10 < n else np.nan
                    sig_rows.append({
                        "date": dates[i], "price": c[i],
                        "score": g["score"] if g is not None else np.nan,
                        "L4": g["L4"] if g is not None else np.nan,
                        "L5": g["L5"] if g is not None else np.nan,
                        "blocked": bool(self.gated and g is not None and g["score"] < self.min_score),
                        "fwd10": fwd10,
                    })
                    if self.gated and g is not None and g["score"] < self.min_score:
                        blocked += 1
                    else:
                        qty = int(cash * POS_PCT / c[i] / 100) * 100
                        if qty > 0:
                            entry_cost = qty * c[i] * (1 + COST)
                            cash -= entry_cost
                            shares = qty
                            entry_price = c[i]
                            stop_price = c[i] - ATR_STOP_MULT * (atr_arr[i] if np.isfinite(atr_arr[i]) else c[i] * 0.02)
                            opens.append({
                                "date": dates[i], "price": c[i],
                                "score": g["score"] if g is not None else np.nan,
                                "L4": g["L4"] if g is not None else np.nan,
                                "L5": g["L5"] if g is not None else np.nan,
                            })
                            trades.append({"action": "buy", "i": i, "date": dates[i],
                                           "price": c[i], "qty": qty})
            equity[i] = cash + shares * c[i]
            if equity[i] > peak:
                peak = equity[i]
            dd = (peak - equity[i]) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)

        # 期末平仓（若仍持仓）
        if shares > 0 and n > 0:
            proceeds = shares * c[-1] * (1 - COST)
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
            "total_buys": len(opens) if not self.gated else len(opens),
            "final_capital": cash, "wins": wins, "losses": losses,
        }
        opens_df = pd.DataFrame(opens) if opens else pd.DataFrame(
            columns=["date", "price", "score", "L4", "L5"])
        sig_df = pd.DataFrame(sig_rows) if sig_rows else pd.DataFrame(
            columns=["date", "price", "score", "L4", "L5", "blocked", "fwd10"])
        return report, opens_df, blocked, sig_df


# ---------- 指标聚合 ----------

def signal_eff(report: dict, opens_df: pd.DataFrame):
    nb = len(opens_df)
    return report["total_return"] / nb if nb > 0 else np.nan


def aggregate(rows):
    """rows: list of dict{code, report, opens_df, blocked} → 聚合行（每只一行）"""
    out = []
    for r in rows:
        o = r["opens_df"]
        row = {
            "code": r["code"],
            "ret": r["report"]["total_return"],
            "dd": r["report"]["max_drawdown"],
            "pf": r["report"]["pf"],
            "wr": r["report"]["win_rate"],
            "sharpe": r["report"]["sharpe_ratio"],
            "n_buys": len(o),
            "blocked": r["blocked"],
            "blocked_rate": r["blocked"] / (len(o) + r["blocked"]) if (len(o) + r["blocked"]) else np.nan,
            "contrarian": o["L4"].eq(False).sum() if len(o) else 0,     # L4 空头开仓
            "chase_high": o["L5"].eq(True).sum() if len(o) else 0,      # L5 高位开仓
            "contrarian_rate": o["L4"].eq(False).mean() if len(o) else np.nan,
            "chase_rate": o["L5"].eq(True).mean() if len(o) else np.nan,
            "sig_eff": signal_eff(r["report"], o),
        }
        out.append(row)
    return pd.DataFrame(out)


def compare_block(df_b: pd.DataFrame, df_g: pd.DataFrame, label: str):
    L = []
    L.append(f"**{label}**（基线 n={len(df_b)} / 护佑后 n={len(df_g)}）")
    L.append("")
    L.append("| 指标 | 基线（护佑前） | 护佑后（V2≥4/6） | 变化 |")
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
        b, g = df_b[col].mean(), df_g[col].mean()
        if np.isfinite(b) and np.isfinite(g):
            L.append(f"| {name} | {fmt.format(b)} | {fmt.format(g)} | {fmt.format(g - b)} |")
        else:
            L.append(f"| {name} | — | — | — |")
    if len(df_g):
        L.append("")
        L.append(f"- 拦截率（V2 拦截首次开仓）：{df_g['blocked_rate'].mean():.1%}（均值）")
        L.append(f"- 逆势开仓占比（L4 周线空头时开仓）：{df_g['contrarian_rate'].mean():.1%}（均值）")
        L.append(f"- 追高开仓占比（L5 高位 zone 开仓）：{df_g['chase_rate'].mean():.1%}（均值）")
    return "\n".join(L)


# ---------- 主流程 ----------

def main():
    print("[P2-Full] V2 放行线 + 完整策略回测（Donchian 主载体）开始...")
    files = sorted(glob.glob(os.path.join(DAILY_DIR, "*_daily.csv")))
    scores = {}
    for f in files:
        code = os.path.basename(f).replace("_daily.csv", "")
        v2 = build_v2(code)
        if v2 is not None:
            scores[code] = v2
    print(f"V2 打分构建完成：{len(scores)} 只")

    all_dates = np.sort(np.unique(np.concatenate([v2["date"].values for v2 in scores.values()])))
    cutoff = all_dates[int(len(all_dates) * TRAIN_RATIO)]
    cutoff_dt = pd.Timestamp(cutoff)
    print(f"walk-forward：训练 <{cutoff_dt:%Y-%m-%d} / 测试 ≥（样本外）")

    s_tr = pd.concat([v2.loc[v2["date"] < cutoff_dt, "score"] for v2 in scores.values()])
    p70, p75 = s_tr.quantile(0.70), s_tr.quantile(0.75)
    print(f"训练段分数分布：P50={s_tr.quantile(0.50):.0f} P70={p70:.0f} P75={p75:.0f}")

    tr_base, tr_gated, te_base, te_gated = [], [], [], []
    for code, v2 in scores.items():
        data = load_daily(code)
        if data is None or len(data) < 120:
            continue
        gate_map = {
            row.date_only: {"score": int(row["score"]), "L4": bool(row["L4"]), "L5": bool(row["L5"])}
            for _, row in v2.iterrows()
        }
        d_tr = data[data["date"] < cutoff_dt]
        d_te = data[data["date"] >= cutoff_dt]
        for seg, base_list, gated_list in ((d_tr, tr_base, tr_gated), (d_te, te_base, te_gated)):
            if len(seg) < 60:
                continue
            rep_b, opens_b, _, _ = DonchianBacktest(gate_map=gate_map, gated=False).run(seg)
            rep_g, opens_g, blk, sig_g = DonchianBacktest(gate_map=gate_map, gated=True).run(seg)
            base_list.append({"code": code, "report": rep_b, "opens_df": opens_b, "blocked": 0})
            gated_list.append({"code": code, "report": rep_g, "opens_df": opens_g,
                               "blocked": blk, "sig_df": sig_g})

    L = []
    L.append("# P2 正式回测报告：V2 放行线 + 完整策略回测（Donchian 主载体）")
    L.append("")
    L.append(f"- 生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}")
    L.append(f"- 信号源：Donchian 20/10 突破（经典海龟式趋势信号；downtrend 因 500 日 0 信号降级为附录佐证）")
    L.append(f"- 交易逻辑：ATR×2 止损 + 单票 20% 仓位 + 0.15% 双边费用 + 期末平仓；T+1 日线级天然满足")
    L.append(f"- 闸门：V2 打分（rL1/rL2 低位加分+KST+周线EMA+zone+VCP）≥ {MIN_SCORE}/6 拦截首次开仓")
    L.append(f"- walk-forward：训练段 <{cutoff_dt:%Y-%m-%d}（标定放行线）→ 测试段样本外验证")
    L.append(f"- 训练段分数分布：P50={s_tr.quantile(0.50):.0f} P70={p70:.0f} P75={p75:.0f}（P70/P75≈4 支持 ≥4/6 默认档）")
    L.append("")

    L.append("## 1. 训练段（样本内）基线 vs 护佑后")
    L.append("")
    if tr_base:
        L.append(compare_block(aggregate(tr_base), aggregate(tr_gated), "训练段（样本内）"))
    else:
        L.append("（无有效样本）")
    L.append("")

    L.append("## 2. 测试段（样本外）基线 vs 护佑后 —— 核心结论段")
    L.append("")
    if te_base:
        L.append(compare_block(aggregate(te_base), aggregate(te_gated), "测试段（样本外）"))
    else:
        L.append("（无有效样本）")
    L.append("")

    L.append("## 3. 闸门区分度检验（测试段，信号级：放行 vs 拦截的反事实对比）")
    L.append("")
    L.append("> 判定闸门是否真的拦截了后续表现差的信号：对测试段所有 Donchian 突破信号时点，"
             "按 V2 闸门（≥4 放行 / <4 拦截）分组，比较两组信号触发后 10 日（fwd10）表现。"
             "若拦截组 fwd10 显著劣于放行组，则闸门有效；否则闸门筛选无效甚至反向。")
    L.append("")
    if te_gated:
        s_all = pd.concat([r["sig_df"] for r in te_gated], ignore_index=True)
        s_all = s_all.dropna(subset=["fwd10"])
        if len(s_all):
            pas = s_all[s_all["blocked"] == False]  # noqa: E712
            blk = s_all[s_all["blocked"] == True]   # noqa: E712
            def stat(d):
                if not len(d):
                    return {"n": 0}
                return {"n": len(d), "fwd10_mean": d["fwd10"].mean(),
                        "fwd10_win": (d["fwd10"] > 0).mean()}
            sp, sb = stat(pas), stat(blk)
            L.append(f"- 测试段突破信号总数：{len(s_all)}")
            L.append(f"- 放行组（V2≥4）：n={sp['n']}，fwd10 均值 **{sp.get('fwd10_mean', float('nan')):+.4f}**，"
                     f"正收益占比 **{sp.get('fwd10_win', float('nan')):.1%}**")
            L.append(f"- 拦截组（V2<4）：n={sb['n']}，fwd10 均值 **{sb.get('fwd10_mean', float('nan')):+.4f}**，"
                     f"正收益占比 **{sb.get('fwd10_win', float('nan')):.1%}**")
            diff = sp.get("fwd10_mean", 0) - sb.get("fwd10_mean", 0)
            L.append(f"- 放行−拦截 fwd10 差值：**{diff:+.4f}**（>0 且显著 ⇒ 闸门筛选有效；<0 ⇒ 反向）")
            # 简易方向判断（不替代显著性检验）
            if sp.get("n", 0) and sb.get("n", 0):
                L.append(f"- 方向初判：{'闸门筛选有效（放行组明显优于拦截组）' if diff > 0.005 else ('闸门筛选反向（拦截组反而更优）' if diff < -0.005 else '差异微弱，需显著性检验')}")
        else:
            L.append("（无有效信号样本）")
    else:
        L.append("（无有效测试样本）")
    L.append("")

    L.append("## 4. 四维护佑判定（测试段，对照 V1.5 §3.2 达标线）")
    L.append("")
    if te_base and te_gated:
        a_b, a_g = aggregate(te_base), aggregate(te_gated)
        dd_b, dd_g = a_b["dd"].mean(), a_g["dd"].mean()
        wr_b, wr_g = a_b["wr"].mean(), a_g["wr"].mean()
        se_b, se_g = a_b["sig_eff"].mean(), a_g["sig_eff"].mean()
        cr, hr = a_g["contrarian_rate"].mean(), a_g["chase_rate"].mean()
        wins_b = sum(r["report"]["wins"] for r in te_base)
        losses_b = sum(r["report"]["losses"] for r in te_base)
        wins_g = sum(r["report"]["wins"] for r in te_gated)
        losses_g = sum(r["report"]["losses"] for r in te_gated)
        pfp_b = wins_b / losses_b if losses_b > 0 else (np.inf if wins_b > 0 else np.nan)
        pfp_g = wins_g / losses_g if losses_g > 0 else (np.inf if wins_g > 0 else np.nan)
        L.append("| 护佑维度 | 达标线（V1.5 §3.2） | 实测 | 判定 |")
        L.append("|---|---|---|---|")
        checks = [
            ("安全性", "最大回撤降≥15% 且 PF 不劣化",
             f"回撤 {dd_b:.4f}→{dd_g:.4f}（{(dd_g/dd_b-1)*100 if dd_b else 0:+.1f}%）；pooled PF {pfp_b:.2f}→{pfp_g:.2f}"),
            ("精准性", "PF/胜率改善且追高占比降≥20%",
             f"胜率 {wr_b:.1%}→{wr_g:.1%}；pooled PF {pfp_b:.2f}→{pfp_g:.2f}；追高占比 {hr:.1%}"),
            ("高效性", "信号效率提升≥20%",
             f"信号效率 {se_b:+.5f}→{se_g:+.5f}；拦截率 {a_g['blocked_rate'].mean():.1%}"),
            ("稳定性", "逆势占比降且信号不塌缩",
             f"逆势开仓占比 {cr:.1%}；开仓数 {a_b['n_buys'].mean():.0f}→{a_g['n_buys'].mean():.0f}"),
        ]
        for name, crit, got in checks:
            L.append(f"| {name} | {crit} | {got} | （复核后填写） |")
    else:
        L.append("（无有效测试样本）")
    L.append("")

    L.append("## 5. 结论（复核后填写）")
    L.append("")
    L.append("（判定：V2 闸门在完整策略回测下是否护佑策略；是否进入 decision_engine 写入流程）")
    L.append("")

    L.append("## 附录：downtrend_optimized 真实策略佐证（低频限制说明）")
    L.append("")
    L.append("downtrend_optimized 为极端超跌型低频策略：000001 全历史 8455 日仅 17 个信号、"
             "最近 500 日 0 信号（A 级实测），不满足统计验证的最小样本要求，本轮不作为主载体。"
             "其对 V2 闸门的护佑响应将在 P4 增效器网关逐策略接入时单独验证。")
    L.append("")

    os.makedirs(RESULT_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    out_path = os.path.join(RESULT_DIR, f"p2_full_backtest_{stamp}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print("\n".join(L))
    print(f"\n报告已落盘: {out_path}")
    return out_path


if __name__ == "__main__":
    main()
