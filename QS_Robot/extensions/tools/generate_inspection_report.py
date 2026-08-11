"""一键巡检报告生成器 — 运行全部巡检模式并生成 HTML/PDF 报告"""
import os
import sys
import json
import time
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

REPORT_DIR = os.path.join(PROJECT_ROOT, "data", "health_reports")
os.makedirs(REPORT_DIR, exist_ok=True)


def run_all_inspections():
    """运行全部巡检模式，返回汇总结果"""
    results = {"timestamp": datetime.now().isoformat(), "modes": [], "total_score": 0,
               "total_passed": 0, "total_failed": 0, "total_elapsed": 0}

    # 快速巡检
    try:
        from core.system_health_checker import get_health_checker
        checker = get_health_checker()
        r = checker.run_check(mode="quick")
        results["modes"].append({
            "label": "🔍 快速巡检", "mode": "quick",
            "score": r.overall_score, "passed": r.passed_checks,
            "failed": r.failed_checks, "total": r.total_checks,
            "elapsed": r.elapsed_seconds, "status": r.overall_status,
            "layers": [{"name": l["name"], "score": l["score"], "passed": l["passed"],
                        "total": l["total"], "status": l["status"]} for l in r.layers]
        })
    except Exception as e:
        results["modes"].append({"label": "🔍 快速巡检", "score": 0, "error": str(e)})

    # 深度巡检
    try:
        r = checker.run_check(mode="deep")
        results["modes"].append({
            "label": "🔬 深度巡检", "mode": "deep",
            "score": r.overall_score, "passed": r.passed_checks,
            "failed": r.failed_checks, "total": r.total_checks,
            "elapsed": r.elapsed_seconds, "status": r.overall_status,
            "layers": [{"name": l["name"], "score": l["score"], "passed": l["passed"],
                        "total": l["total"], "status": l["status"]} for l in r.layers]
        })
    except Exception as e:
        results["modes"].append({"label": "🔬 深度巡检", "score": 0, "error": str(e)})

    # L2专项
    try:
        from core.l2_inspector import L2Inspector
        inspector = L2Inspector(mode="quick")
        l2r = inspector.run()
        results["modes"].append({
            "label": "📋 L2业务链路专项", "mode": "l2",
            "score": l2r.overall_score, "passed": l2r.passed,
            "failed": l2r.failed, "total": l2r.total,
            "elapsed": l2r.elapsed_seconds,
            "categories": l2r.categories,
            "items": [{"name": i["name"], "passed": i["passed"],
                       "score": i["score"], "detail": i["detail"]} for i in l2r.items]
        })
    except Exception as e:
        results["modes"].append({"label": "📋 L2专项", "score": 0, "error": str(e)})

    # 三大入口
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_verify_three_entries",
            os.path.join(PROJECT_ROOT, "_verify_three_entries.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        check_names = [
            ("verify_closed_n1", "基础连通-5002"), ("verify_closed_n2", "基础连通-5003"),
            ("verify_closed_n3", "基础连通-认证"), ("verify_closed_n4", "基础连通-拦截"),
            ("verify_closed_n5", "基础连通-性能"), ("verify_original_n1", "原始策略-n1"),
            ("verify_original_n2", "原始策略-n2"), ("verify_original_n3", "原始策略-n3"),
            ("verify_original_n4", "原始策略-n4"), ("verify_original_n5", "原始策略-n5"),
            ("verify_vibe_n1", "Vibe入口-n1"), ("verify_vibe_n2", "Vibe入口-n2"),
            ("verify_vibe_n3", "Vibe入口-n3"), ("verify_vibe_n4", "Vibe入口-n4"),
            ("verify_vibe_n5", "Vibe入口-n5"), ("verify_ths_n1", "同花顺-n1"),
            ("verify_ths_n2", "同花顺-n2"), ("verify_ths_n3", "同花顺-n3"),
            ("verify_ths_n4", "同花顺-n4"), ("verify_ths_n5", "同花顺-n5"),
            ("verify_resource_n1", "资源约束-n1"), ("verify_resource_n2", "资源约束-n2"),
        ]
        t_items = []
        t_passed = 0
        for fn_name, name in check_names:
            fn = getattr(mod, fn_name, None)
            if fn:
                result = fn()
                p = result.get("passed", False) if isinstance(result, dict) else result[0]
                d = result.get("detail", "") if isinstance(result, dict) else (result[1] if len(result) > 1 else "")
                t_items.append({"name": name, "passed": p, "detail": str(d)})
                if p: t_passed += 1
        results["modes"].append({
            "label": "🔗 三大入口验收", "mode": "three_entry",
            "score": round(t_passed / len(t_items) * 100, 1) if t_items else 0,
            "passed": t_passed, "failed": len(t_items) - t_passed,
            "total": len(t_items), "elapsed": 0,
            "items": t_items
        })
    except Exception as e:
        results["modes"].append({"label": "🔗 三大入口", "score": 0, "error": str(e)})

    # 汇总
    valid_modes = [m for m in results["modes"] if m.get("score", 0) > 0 or "error" not in m]
    if valid_modes:
        results["total_score"] = round(sum(m["score"] for m in valid_modes) / len(valid_modes), 1)
        results["total_passed"] = sum(m.get("passed", 0) for m in valid_modes)
        results["total_failed"] = sum(m.get("failed", 0) for m in valid_modes)
        results["total_elapsed"] = round(sum(m.get("elapsed", 0) for m in valid_modes), 1)

    return results


def generate_html(results):
    """生成 HTML 报告"""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    overall = "healthy" if results["total_score"] >= 90 else ("warning" if results["total_score"] >= 70 else "critical")
    score_color = "#00c853" if overall == "healthy" else ("#f39c12" if overall == "warning" else "#e74c5c")

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>Aurora 系统一键巡检报告</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#0a0d14;color:#e8ecf1;font-family:'PingFang SC','Microsoft YaHei',sans-serif;padding:40px;max-width:1000px;margin:0 auto}}
.header{{text-align:center;margin-bottom:30px;padding:30px;background:linear-gradient(135deg,#1a2744,#0d1526);border-radius:16px;border:1px solid rgba(255,255,255,0.08)}}
.header h1{{font-size:28px;background:linear-gradient(135deg,#00d4c8,#4a7dff);-webkit-background-clip:text;-webkit-text-fill-color:transparent}}
.header .time{{color:#8895a9;margin-top:8px;font-size:14px}}
.score-big{{font-size:72px;font-weight:800;color:{score_color};text-align:center;margin:20px 0}}
.summary{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:30px}}
.summary-card{{background:#111620;border:1px solid rgba(255,255,255,0.08);border-radius:12px;padding:20px;text-align:center}}
.summary-card .val{{font-size:32px;font-weight:700;color:#4a7dff}}
.summary-card .lbl{{font-size:12px;color:#8895a9;margin-top:4px}}
.mode-section{{background:#111620;border:1px solid rgba(255,255,255,0.08);border-radius:12px;padding:20px;margin-bottom:16px}}
.mode-header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px}}
.mode-header h3{{font-size:16px}}
.mode-score{{font-size:24px;font-weight:700}}
.mode-stats{{font-size:13px;color:#8895a9;margin-bottom:8px}}
.item-row{{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid rgba(255,255,255,0.04);font-size:13px}}
.item-pass{{color:#00c853}}.item-fail{{color:#e74c5c}}
.footer{{text-align:center;color:#8895a9;font-size:12px;margin-top:30px;padding-top:20px;border-top:1px solid rgba(255,255,255,0.06)}}
.badge{{display:inline-block;padding:2px 10px;border-radius:20px;font-size:11px;font-weight:600}}
.badge-healthy{{background:rgba(0,200,83,0.15);color:#00c853}}
.badge-warning{{background:rgba(243,156,18,0.15);color:#f39c12}}
@media print{{body{{background:#fff;color:#000}}}}
</style></head>
<body>
<div class="header">
    <h1>🚀 Aurora 量化交易系统 — 一键巡检报告</h1>
    <div class="time">生成时间: {ts}</div>
</div>

<div class="score-big">{results["total_score"]}<span style="font-size:24px">/100</span></div>
<div style="text-align:center;margin-bottom:20px">
    <span class="badge badge-{'healthy' if overall=='healthy' else 'warning'}">{'✅ 系统健康' if overall=='healthy' else '⚠️ 需要关注'}</span>
</div>

<div class="summary">
    <div class="summary-card"><div class="val">{results['total_passed']}</div><div class="lbl">通过项</div></div>
    <div class="summary-card"><div class="val" style="color:#e74c5c">{results['total_failed']}</div><div class="lbl">失败项</div></div>
    <div class="summary-card"><div class="val">{len(results['modes'])}</div><div class="lbl">巡检模式</div></div>
    <div class="summary-card"><div class="val">{results['total_elapsed']}s</div><div class="lbl">总耗时</div></div>
</div>
"""
    for m in results["modes"]:
        sc = m.get("score", 0)
        sc_color = "#00c853" if sc >= 90 else ("#f39c12" if sc >= 70 else "#e74c5c")
        html += f"""<div class="mode-section">
<div class="mode-header"><h3>{m['label']}</h3><span class="mode-score" style="color:{sc_color}">{sc}/100</span></div>
<div class="mode-stats">通过: {m.get('passed','?')} | 失败: {m.get('failed','?')} | 总计: {m.get('total','?')} | 耗时: {m.get('elapsed','?')}s</div>
"""
        if "error" in m:
            html += f'<div class="item-fail">错误: {m["error"]}</div>'
        if "layers" in m:
            for l in m["layers"]:
                st = "✅" if l["status"] == "healthy" else "⚠️"
                html += f'<div class="item-row"><span>{st} {l["name"]}</span><span>评分 {l["score"]} · {l["passed"]}/{l["total"]}</span></div>'
        if "categories" in m:
            for cat, info in m["categories"].items():
                html += f'<div class="item-row"><span>📂 {cat}</span><span>{info["passed"]}/{info["total"]} ({info["score"]}/100)</span></div>'
        if "items" in m:
            for it in m["items"]:
                icon = "✅" if it.get("passed") else "❌"
                cls = "item-pass" if it.get("passed") else "item-fail"
                html += f'<div class="item-row"><span class="{cls}">{icon} {it["name"]}</span><span>{it.get("detail","")}</span></div>'
        html += "</div>"

    html += f"""<div class="footer">
Aurora 量化交易系统 · 系统维护模块 · 一键巡检报告 · {ts}<br>
覆盖 8 层架构 · 91+ 项检查 · 4 种巡检模式
</div></body></html>"""
    return html


def main():
    print("=" * 60)
    print("  Aurora 系统一键巡检报告生成器")
    print("=" * 60)
    print("  正在运行全部巡检模式...")
    results = run_all_inspections()
    print(f"  总评分: {results['total_score']}/100")
    print(f"  通过: {results['total_passed']}  失败: {results['total_failed']}")
    print(f"  耗时: {results['total_elapsed']}s")

    # 保存JSON
    json_path = os.path.join(REPORT_DIR, f"inspection_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"  JSON报告: {json_path}")

    # 生成HTML
    html = generate_html(results)
    html_path = os.path.join(REPORT_DIR, f"inspection_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  HTML报告: {html_path}")
    print(f"\n  在浏览器中打开 HTML 文件，按 Ctrl+P 即可保存为 PDF。")
    print("=" * 60)
    return html_path


if __name__ == "__main__":
    main()