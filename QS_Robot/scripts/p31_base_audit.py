#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
P3.1 逐策略底座约束审计探针（18 个非魔法策略 + 魔法对照）
======================================================================
目标：用户口径"魔法策略目前没加底座等约束条件；其它 18 个策略应该有
底座等约束条件，没有的要添加"。
审计维度（每策略）：
  1) 是否存在"底座"痕迹：继承/导入 strategy_base / UnifiedStrategyBase
  2) 显式风控字段：stop_loss / take_profit / position(仓位上限) / cooldown(冷却)
  3) 趋势/市况闸门：market_type / regime / gate（公转层接口痕迹）
  4) 参数持久化/热启动：json/pickle 加载
  5) 策略本身自带买卖点信号函数名（供后续 13 章买卖点审计用）

用法：D:\anaconda3\python.exe p31_base_audit.py
输出：results/p31_base_constraint_audit_YYYYMMDD.md
"""
import os
import re
import glob
from datetime import datetime

QS_ROOT = r"D:\Gupiao\升级vscode\QS_Robot"
LOCAL_DIR = os.path.join(QS_ROOT, "export_package", "strategies_local")

# 19 策略（用户口径）：14 完整 + 魔法 + 3 网格 + 1 非网格
AUDIT_LIST = [
    # 14 完整（10-18 核验名单）
    "downtrend_optimized", "multi_factor_resonance", "gyro_minute_strategy_v6_optimized",
    "gyro_precession_strategy", "fund_allocation", "golden_bowl_ice_break",
    "final_optimized_strategy", "adaptive_ml_strategy", "newton_momentum_enhanced",
    "thermodynamic_entropy_enhanced", "fractal_chaos_strategy", "fluid_dynamics_strategy",
    "rl_adaptive_param_strategy", "bernoulli_coanda_strategy",
    # 魔法
    "minervini_sepa_strategy",
    # 3 网格（效果好）
    "adaptive_range_grid", "high_return_grid", "final_market_adaptive",
]

PATTERNS = {
    "base_inherit": re.compile(r"(class\s+\w+\s*\([^)]*(StrategyBase|UnifiedStrategyBase|BaseStrategy)[^)]*\))"),
    "base_import": re.compile(r"(import\s+\w*strategy_base|from\s+\w*strategy_base|import\s+\w*base\w*)", re.I),
    "stop_loss": re.compile(r"(stop_loss|stop_price|check_stop_loss|fixed_stop|SL)", re.I),
    "take_profit": re.compile(r"(take_profit|take_profit_pct|check_take_profit|TP\b)", re.I),
    "position": re.compile(r"(max_position|position_pct|position_limit|仓位上限|max_holdings)", re.I),
    "cooldown": re.compile(r"(cooldown|cool_down|冷却|last_trade_time)", re.I),
    "trend_gate": re.compile(r"(market_type|market_state|regime|trend_gate|市况|闸门|GATE)", re.I),
    "persist": re.compile(r"(json\.load|pickle\.load|\.db\b|best_params\s*=|load_state|memory_file)", re.I),
    "update_price": re.compile(r"def update_price"),
    "sell_signal": re.compile(r"(def\s+\w*(sell|exit|escape|close|quit)\w*\(|sell_signal|exit_signal|escape_top)", re.I),
    "buy_signal": re.compile(r"(def\s+\w*(buy|enter|entry|open|spring)\w*\(|buy_signal|entry_signal)", re.I),
}


def find_file(name):
    for d in (LOCAL_DIR, os.path.join(QS_ROOT, "core")):
        p = os.path.join(d, name + ".py")
        if os.path.exists(p):
            return p
    # 可能带不同文件名
    for d in (LOCAL_DIR, os.path.join(QS_ROOT, "core")):
        hits = glob.glob(os.path.join(d, name + "*.py"))
        if hits:
            return hits[0]
    return None


def audit(name):
    path = find_file(name)
    if not path:
        return {"name": name, "path": None, "size": 0, "hits": {}, "doc_head": ""}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            src = f.read()
    except Exception as e:
        return {"name": name, "path": path, "size": 0, "hits": {}, "doc_head": f"READ_ERROR {e}"}
    hits = {}
    for key, pat in PATTERNS.items():
        found = pat.findall(src)
        hits[key] = len(found)
    doc_head = "\n".join(src.splitlines()[:8])[:400]
    return {"name": name, "path": path, "size": len(src), "hits": hits, "doc_head": doc_head}


def main():
    print("[P3.1] 底座约束审计探针开始...")
    rows = [audit(n) for n in AUDIT_LIST]
    L = []
    L.append("# P3.1 逐策略底座约束审计清单（19 策略）")
    L.append("")
    L.append(f"- 生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}")
    L.append(f"- 审计维度：底座继承/导入、止损、止盈、仓位上限、冷却、趋势/市况闸门、参数持久化、"
             f"update_price 在线接口、买卖点信号函数（13 章买卖点审计前置）")
    L.append(f"- 口径：用户 2026-10-22 —— 魔法策略目前没加底座约束；其它 18 个应有底座约束，没有的要添加")
    L.append("")
    L.append("| # | 策略 | 文件 | 行数 | 底座 | 止损 | 止盈 | 仓位上限 | 冷却 | 趋势闸门 | 持久化 | update_price | 买点函数 | 卖点函数 | 缺口 |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for i, r in enumerate(rows, 1):
        if not r["path"]:
            L.append(f"| {i} | {r['name']} | **未找到文件** | - | - | - | - | - | - | - | - | - | - | **文件缺失** |")
            continue
        h = r["hits"]
        fname = os.path.basename(r["path"])
        lines = r["size"]
        gaps = []
        if h["base_inherit"] == 0 and h["base_import"] == 0:
            gaps.append("无底座继承")
        if h["stop_loss"] == 0:
            gaps.append("无止损")
        if h["take_profit"] == 0:
            gaps.append("无止盈")
        if h["position"] == 0:
            gaps.append("无仓位上限")
        if h["cooldown"] == 0:
            gaps.append("无冷却")
        if h["trend_gate"] == 0:
            gaps.append("无市况闸门")
        if h["update_price"] == 0:
            gaps.append("**无 update_price**")
        gap_s = "；".join(gaps) if gaps else "齐全"
        L.append(f"| {i} | {r['name']} | {fname} | {lines} | {h['base_inherit']}/{h['base_import']} | "
                 f"{h['stop_loss']} | {h['take_profit']} | {h['position']} | {h['cooldown']} | "
                 f"{h['trend_gate']} | {h['persist']} | {h['update_price']} | {h['buy_signal']} | "
                 f"{h['sell_signal']} | {gap_s} |")
    L.append("")
    L.append("> 数字 = 关键词命中次数（0 表示缺失/极可能缺失，需人工复核）。闸门口径=趋势/市况关键词命中。")
    L.append("")
    L.append("## 结论（复核后填写）")
    L.append("")
    L.append("（逐策略缺口清单；魔法策略底座现状确认；其它 18 个中哪些无底座约束需添加；添加方式建议）")
    L.append("")
    os.makedirs(os.path.join(QS_ROOT, "results"), exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    out_path = os.path.join(QS_ROOT, "results", f"p31_base_constraint_audit_{stamp}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print("\n".join(L))
    print(f"\n报告已落盘: {out_path}")
    return out_path


if __name__ == "__main__":
    main()
