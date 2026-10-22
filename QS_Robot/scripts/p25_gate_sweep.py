#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
P2.5 放行线档位敏感性扫描（P2-Full 后续动作）
================================================
背景：P2-Full 判定 V2 ≥4/6 方向验证通过但过度拦截（拦截率 81.6%、
     开仓数 -72% 超稳定性"信号总数损失≤30%"红线）。P2.5 目标：
     策略级扫描放行线档位 ≥2/≥3/≥4/≥5，验证"降低拦截率同时保持
     区分度"是否存在甜点位（如 ≥3 档拦截率约 60%、fwd10 仍为正）。

复用 P2-Full 完全相同的回测框架（Donchian 20/10 突破 + ATR×2 止损
+ 单票 20% 仓位 + 0.15% 双边费用 + 期末平仓；walk-forward 全局
日历 60% 训练 / 40% 测试样本外），仅将固定 MIN_SCORE=4 改为档位扫描。

判据（V1.5 §3.2 达标线 + P2 报告口径，测试段）：
  安全性：最大回撤降≥15% 且 pooled PF 不劣化（≥1 且 ≥基线）
  高效性：信号效率（收益/开仓）提升≥20% 或转正
  精准性：信号级区分度 Welch p<0.05 且放行组 fwd10 均值>0
          （突破载体天然高位，追高占比指标不适用，以区分度为准）
  稳定性：开仓次数损失≤30%（对基线）——P2 ≥4/6 唯一未达项
甜点位：四维中稳定性达标且其余三维保持的最严档位；若多档达标，
        取 fwd10 区分度最优且拦截率最低的折中档。

输出：results/p25_gate_sweep_YYYYMMDD.md
用法：D:\anaconda3\python.exe p25_gate_sweep.py
"""
import os
import glob
from datetime import datetime

import numpy as np
import pandas as pd
from scipy import stats

QS_ROOT = r"D:\Gupiao\升级vscode\QS_Robot"
DAILY_DIR = os.path.join(QS_ROOT, "export_package", "data", "daily_data_ext")
MTF_ROOT = os.path.join(QS_ROOT, "export_package", "data", "multi_timeframe")
RESULT_DIR = os.path.join(QS_ROOT, "results")

LOOKBACK = 500
TRAIN_RATIO = 0.60
SWEEP = [2, 3, 4, 5]          # 扫描档位
COST = 0.0015
ENTRY_N = 20
EXIT_N = 10
ATR_N = 14
ATR_STOP_MULT = 2.0
POS_PCT = 0.20
WINDOW_ATR = 20
WINDOW_ATR_MEAN = 60
WINDOW_ZONE = 500
# 指数文件（非交易标的）：000300/000905/000852 曾因前缀 bug 混入回测池
# （P2-Full 池 533 含 3 个非个股文件）；P2.5 使用纯净个股池并显式排除，
# 保证档位扫描结论不被指数行情（点位级）或污染数据干扰。
INDEX_EXCLUDE = {"000300", "399001", "399006", "000905", "000852"}


# ---------- V2 打分（与 P2-Full 完全一致） ----------

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


# ---------- Donchian 突破策略（与 P2-Full 完全一致，min_score 参数化） ----------

class DonchianBacktest:
    """Donchian 20/10 突破，ATR 仓位 + ATR×2 止损，含双边费用。"""

    def __init__(self, gate_map=None, gated=False, min_score=4):
        self.gate_map = gate_map or {}
        self.gated = gated
        self.min_score = min_score

    def run(self, data: pd.DataFrame):
        c = data["close"].values
        h = data["high"].values
        l = data["low"].values
        dates = data["date"].dt.date.values
        n = len(c)
        equity = np.zeros(n)
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

        atr_arr = np.full(n, np.nan)
        for i in range(ATR_N, n):
            atr_arr[i] = np.mean([max(h[j] - l[j], abs(h[j] - c[j - 1]), abs(l[j] - c[j - 1]))
                                  for j in range(i - ATR_N + 1, i + 1)])

        for i in range(n):
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
                    shares = 0
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
            "total_buys": len(opens), "final_capital": cash, "wins": wins, "losses": losses,
        }
        opens_df = pd.DataFrame(opens) if opens else pd.DataFrame(
            columns=["date", "price", "score", "L4", "L5"])
        sig_df = pd.DataFrame(sig_rows) if sig_rows else pd.DataFrame(
            columns=["date", "price", "score", "L4", "L5", "blocked", "fwd10"])
        return report, opens_df, blocked, sig_df


# ---------- 聚合与统计 ----------

def signal_eff(report: dict, opens_df: pd.DataFrame):
    nb = len(opens_df)
    return report["total_return"] / nb if nb > 0 else np.nan


def pooled_pf(rows):
    wins = sum(r["report"]["wins"] for r in rows)
    losses = sum(r["report"]["losses"] for r in rows)
    if losses > 0:
        return wins / losses
    return np.inf if wins > 0 else np.nan


def gate_stats(rows):
    """rows: list of {report, opens_df, blocked} → 聚合行"""
    out = []
    for r in rows:
        o = r["opens_df"]
        out.append({
            "ret": r["report"]["total_return"], "dd": r["report"]["max_drawdown"],
            "pf": r["report"]["pf"], "wr": r["report"]["win_rate"],
            "sharpe": r["report"]["sharpe_ratio"], "n_buys": len(o),
            "blocked": r["blocked"],
            "blocked_rate": r["blocked"] / (len(o) + r["blocked"]) if (len(o) + r["blocked"]) else np.nan,
            "sig_eff": signal_eff(r["report"], o),
        })
    return pd.DataFrame(out)


def welch(sig_df: pd.DataFrame):
    """信号级区分度：放行 vs 拦截 fwd10 的 Welch t 检验"""
    s = sig_df.dropna(subset=["fwd10"])
    if not len(s):
        return None
    pas = s[s["blocked"] == False]  # noqa: E712
    blk = s[s["blocked"] == True]   # noqa: E712
    if not len(pas) or not len(blk):
        return None
    a, b = pas["fwd10"].values, blk["fwd10"].values
    t_stat = (a.mean() - b.mean()) / np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    df_w = (a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b)) ** 2 / (
        (a.var(ddof=1) / len(a)) ** 2 / (len(a) - 1) + (b.var(ddof=1) / len(b)) ** 2 / (len(b) - 1))
    p = 2 * (1 - stats.t.cdf(abs(t_stat), df_w))
    return {"t": t_stat, "df": df_w, "p": p,
            "n_pas": len(a), "fwd_pas": a.mean(), "wr_pas": (a > 0).mean(),
            "n_blk": len(b), "fwd_blk": b.mean(), "wr_blk": (b > 0).mean()}


def main():
    print("[P2.5] 放行线档位敏感性扫描（≥2/≥3/≥4/≥5）开始...")
    files = sorted(glob.glob(os.path.join(DAILY_DIR, "*_daily.csv")))
    scores = {}
    for f in files:
        code = os.path.basename(f).replace("_daily.csv", "")
        if code in INDEX_EXCLUDE:
            continue
        v2 = build_v2(code)
        if v2 is not None:
            scores[code] = v2
    print(f"V2 打分构建完成：{len(scores)} 只")

    all_dates = np.sort(np.unique(np.concatenate([v2["date"].values for v2 in scores.values()])))
    cutoff = all_dates[int(len(all_dates) * TRAIN_RATIO)]
    cutoff_dt = pd.Timestamp(cutoff)
    print(f"walk-forward：训练 <{cutoff_dt:%Y-%m-%d} / 测试 ≥（样本外）")

    # 测试段每只：基线 + 各档位
    te_base, te_by_min = [], {m: [] for m in SWEEP}
    for code, v2 in scores.items():
        data = load_daily(code)
        if data is None or len(data) < 120:
            continue
        gate_map = {
            row.date_only: {"score": int(row["score"]), "L4": bool(row["L4"]), "L5": bool(row["L5"])}
            for _, row in v2.iterrows()
        }
        d_te = data[data["date"] >= cutoff_dt]
        if len(d_te) < 60:
            continue
        rep_b, opens_b, _, _ = DonchianBacktest(gate_map=gate_map, gated=False).run(d_te)
        te_base.append({"code": code, "report": rep_b, "opens_df": opens_b, "blocked": 0})
        for m in SWEEP:
            rep_g, opens_g, blk, sig_g = DonchianBacktest(gate_map=gate_map, gated=True, min_score=m).run(d_te)
            te_by_min[m].append({"code": code, "report": rep_g, "opens_df": opens_g,
                                 "blocked": blk, "sig_df": sig_g})

    a_b = gate_stats(te_base)
    n_buys_b = a_b["n_buys"].mean()
    dd_b = a_b["dd"].mean()
    pfp_b = pooled_pf(te_base)
    se_b = a_b["sig_eff"].mean()
    wr_b = a_b["wr"].mean()

    L = []
    L.append("# P2.5 放行线档位敏感性扫描报告（策略级，Donchian 主载体）")
    L.append("")
    L.append(f"- 生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}")
    L.append(f"- 背景：P2-Full 判定 V2 ≥4/6 方向通过但过度拦截（拦截率 81.6%、开仓 -72% 超稳定性红线），"
             f"本扫描验证降低放行档位是否存在甜点位")
    L.append(f"- 扫描档位：≥2 / ≥3 / ≥4 / ≥5（基线 B0 = 无闸门）")
    L.append(f"- walk-forward：训练 <{cutoff_dt:%Y-%m-%d} → 测试段样本外（n={len(te_base)} 只）")
    L.append(f"- 基线（测试段）：开仓均值 {n_buys_b:.1f} | 回撤 {dd_b:.4f} | pooled PF {pfp_b:.2f}"
             f" | 胜率 {wr_b:.1%} | 信号效率 {se_b:+.5f}")
    L.append("")

    # 汇总表
    L.append("## 1. 档位汇总（测试段）")
    L.append("")
    L.append("| 档位 | 开仓均值 | 开仓损失 | 拦截率 | 回撤 | pooled PF | 胜率 | 信号效率 | 放行fwd10 | 拦截fwd10 | Welch p |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|")
    rows_sum = []
    for m in SWEEP:
        a_g = gate_stats(te_by_min[m])
        w = welch(pd.concat([r["sig_df"] for r in te_by_min[m]], ignore_index=True))
        rows_sum.append({
            "m": m, "n_buys": a_g["n_buys"].mean(),
            "loss": 1 - a_g["n_buys"].mean() / n_buys_b if n_buys_b else np.nan,
            "blk": a_g["blocked_rate"].mean(), "dd": a_g["dd"].mean(),
            "pf": pooled_pf(te_by_min[m]), "wr": a_g["wr"].mean(),
            "se": a_g["sig_eff"].mean(),
            "fwd_pas": w["fwd_pas"] if w else np.nan,
            "fwd_blk": w["fwd_blk"] if w else np.nan,
            "p": w["p"] if w else np.nan,
        })
        L.append(f"| ≥{m} | {rows_sum[-1]['n_buys']:.1f} | {rows_sum[-1]['loss']:.1%} | "
                 f"{rows_sum[-1]['blk']:.1%} | {rows_sum[-1]['dd']:.4f} | "
                 f"{rows_sum[-1]['pf']:.2f} | {rows_sum[-1]['wr']:.1%} | "
                 f"{rows_sum[-1]['se']:+.5f} | {rows_sum[-1]['fwd_pas']:+.4f} | "
                 f"{rows_sum[-1]['fwd_blk']:+.4f} | {rows_sum[-1]['p']:.4g} |")
    L.append("")
    L.append("- 开仓损失 = 1 − 护佑后开仓均值 / 基线开仓均值（稳定性红线：≤30%）")
    L.append("- 拦截率 = 拦截信号数 / 全部突破信号数（信号级）")
    L.append("- Welch p：放行 vs 拦截 fwd10 差异显著性（<0.05 ⇒ 区分度成立）")
    L.append("")

    # 四维护佑判定
    L.append("## 2. 四维护佑判定（对照 V1.5 §3.2 达标线）")
    L.append("")
    L.append("| 档位 | 安全性(回撤降≥15%且PF不劣化) | 高效性(信号效率提升≥20%或转正) | 精准性(Welch p<0.05且放行fwd10>0) | 稳定性(开仓损失≤30%) | 综合 |")
    L.append("|---|---|---|---|---|---|")
    verdicts = []
    for r in rows_sum:
        safe = (r["dd"] <= dd_b * 0.85) and (r["pf"] >= 1.0)
        eff = (r["se"] >= max(se_b * 1.2, 0)) if np.isfinite(se_b) else (r["se"] > 0)
        prec = (r["p"] < 0.05) and (r["fwd_pas"] > 0)
        stab = r["loss"] <= 0.30
        ok_all = safe and eff and prec and stab
        verdicts.append({"m": r["m"], "safe": safe, "eff": eff, "prec": prec, "stab": stab, "ok_all": ok_all})
        L.append(f"| ≥{r['m']} | {'✅' if safe else '❌'} | {'✅' if eff else '❌'} | "
                 f"{'✅' if prec else '❌'} | {'✅' if stab else '❌'} | "
                 f"{'✅ 四维达标' if ok_all else '—'} |")
    L.append("")

    # 结论
    L.append("## 3. 结论（甜点位）")
    L.append("")
    passed = [v for v in verdicts if v["ok_all"]]
    if passed:
        best = max(passed, key=lambda v: v["m"])
        L.append(f"**甜点位候选：≥{best['m']}**（四维护佑全部达标的最严档位）")
    else:
        partial = [v for v in verdicts if v["safe"] and v["eff"] and v["prec"]]
        if partial:
            best = max(partial, key=lambda v: v["m"])
            L.append(f"**无四维全达标档**；最接近：≥{best['m']}（安全/高效/精准达标，稳定性未达："
                     f"开仓损失 {[r['loss'] for r in rows_sum if r['m'] == best['m']][0]:.1%}）")
        else:
            L.append("**无达标档**：需回到 V2 层本身（层权重/层构成）调整，而非仅调放行阈值。")
    L.append("")
    L.append("> 注意：P2.5 仅调放行阈值（同一 V2 打分），不改 V2 层构成；"
             "档位定稿后再进 P4 逐真实策略接入验证。V2 写入 decision_engine 前"
             "须 P2.5 结论 + P4 真实策略增效验证双通过。")
    L.append("")

    os.makedirs(RESULT_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    out_path = os.path.join(RESULT_DIR, f"p25_gate_sweep_{stamp}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print("\n".join(L))
    print(f"\n报告已落盘: {out_path}")
    return out_path


if __name__ == "__main__":
    main()
