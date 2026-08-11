"""生产环境部署检查清单 — 动态生成，随策略/模块/链路变化自动更新
用法: python extensions/tools/deploy_checklist.py [--output md|json|html]
"""
import os
import sys
import json
import time
import inspect
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

CHECKLIST_DIR = os.path.join(PROJECT_ROOT, "data", "deploy_checklists")
os.makedirs(CHECKLIST_DIR, exist_ok=True)

# ============================================================
# 动态扫描器
# ============================================================

def scan_security_modules():
    """扫描安全相关模块"""
    items = []
    # 扫描 api/gateway.py 的安全装饰器
    try:
        gateway_path = os.path.join(PROJECT_ROOT, "api", "gateway.py")
        with open(gateway_path, "r", encoding="utf-8") as f:
            content = f.read()
        checks = {
            "认证装饰器": "require_auth" in content,
            "CSRF防护": "require_csrf" in content,
            "频率限制": "rate_limit" in content,
            "输入净化": "sanitize_input" in content,
            "来源检查": "check_origin" in content,
            "威胁检测": "check_threat" in content,
            "威胁检查(蓝图)": "gateway_threat_check" in content,
            "数据脱敏": "DataMasker" in content,
            "输入验证": "InputValidator" in content,
        }
        for name, ok in checks.items():
            items.append({"category": "API安全", "item": name, "status": "pass" if ok else "fail",
                          "detail": "已实现" if ok else "未实现", "auto": True})
    except Exception as e:
        items.append({"category": "API安全", "item": "安全模块扫描", "status": "fail",
                      "detail": str(e), "auto": True})

    # 扫描安全配置
    try:
        from core.security import (
            get_input_validator, get_data_masker, get_csrf_manager,
            get_rate_limiter, get_threat_detector
        )
        sec_checks = {
            "输入验证器": get_input_validator,
            "数据脱敏器": get_data_masker,
            "CSRF管理器": get_csrf_manager,
            "频率限制器": get_rate_limiter,
            "威胁检测器": get_threat_detector,
        }
        for name, getter in sec_checks.items():
            try:
                obj = getter()
                items.append({"category": "安全组件", "item": name, "status": "pass",
                              "detail": f"实例化成功: {type(obj).__name__}", "auto": True})
            except Exception as e:
                items.append({"category": "安全组件", "item": name, "status": "fail",
                              "detail": str(e), "auto": True})
    except ImportError:
        items.append({"category": "安全组件", "item": "core.security", "status": "fail",
                      "detail": "模块不可导入", "auto": True})

    return items


def scan_config():
    """扫描配置安全"""
    items = []
    config_path = os.path.join(PROJECT_ROOT, "config.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        # 检查敏感配置
        sensitive_keys = ["secret_key", "jwt_secret", "api_key", "password", "token"]
        for key in sensitive_keys:
            found = any(k.lower().find(key) >= 0 for k in config.keys())
            if found:
                items.append({"category": "配置安全", "item": f"敏感配置-{key}",
                              "status": "warn", "detail": "配置文件中含敏感字段，建议使用环境变量",
                              "auto": True})
        # 端口配置
        port = config.get("port", config.get("qs_robot_port", 5003))
        items.append({"category": "配置安全", "item": "服务端口", "status": "pass",
                      "detail": f"端口={port}", "auto": True})
        # 调试模式
        debug = config.get("debug", False)
        items.append({"category": "配置安全", "item": "调试模式", "status": "fail" if debug else "pass",
                      "detail": "已开启(生产应关闭)" if debug else "已关闭", "auto": True})
    except Exception as e:
        items.append({"category": "配置安全", "item": "配置文件", "status": "fail",
                      "detail": f"读取失败: {e}", "auto": True})

    # 检查 .env 文件
    env_path = os.path.join(PROJECT_ROOT, ".env")
    if os.path.exists(env_path):
        items.append({"category": "配置安全", "item": ".env文件", "status": "pass",
                      "detail": "存在", "auto": True})
    else:
        items.append({"category": "配置安全", "item": ".env文件", "status": "warn",
                      "detail": "不存在，建议使用环境变量管理敏感配置", "auto": True})

    # 检查 .gitignore
    gitignore_path = os.path.join(PROJECT_ROOT, ".gitignore")
    if os.path.exists(gitignore_path):
        with open(gitignore_path, "r", encoding="utf-8") as f:
            content = f.read()
        for pattern in [".env", "config.json", "*.pem", "*.key", "credentials"]:
            if pattern in content:
                items.append({"category": "配置安全", "item": f"gitignore-{pattern}",
                              "status": "pass", "detail": f"{pattern} 已排除", "auto": True})
            else:
                items.append({"category": "配置安全", "item": f"gitignore-{pattern}",
                              "status": "warn", "detail": f"{pattern} 未排除，有泄露风险", "auto": True})

    return items


def scan_modules():
    """动态扫描系统模块"""
    items = []
    core_modules = [
        "system_health_checker", "l2_inspector", "tau_cluster_engine",
        "adaptive_market_regime", "backtest_engine", "risk_control",
        "strategy_auto_discovery", "shepherd_optimizer", "workflow_engine",
        "order_manager", "trade_executor", "security",
    ]
    for mod_name in core_modules:
        try:
            __import__(f"core.{mod_name}")
            items.append({"category": "核心模块", "item": mod_name, "status": "pass",
                          "detail": "可导入", "auto": True})
        except ImportError:
            items.append({"category": "核心模块", "item": mod_name, "status": "fail",
                          "detail": "不可导入", "auto": True})

    # 扫描全部 API 路由（不限定蓝图，覆盖 api_gateway / api_login / cluster_routes 等）
    try:
        from ui.server import app
        routes = [rule.rule for rule in app.url_map.iter_rules()
                  if rule.endpoint and not rule.endpoint.startswith('static')]
        items.append({"category": "API端点", "item": "API路由数", "status": "pass",
                      "detail": f"{len(routes)}个端点", "auto": True})
        # 关键端点检查
        key_routes = [
            "/api/health/check", "/api/health/check/l2",
            "/api/health/check/three_entry", "/api/health/auto-fix",
            "/api/strategy/list", "/api/risk/status",
            "/api/auth/login", "/api/security/config",
        ]
        for route in key_routes:
            found = any(r == route or str(r).startswith(route) for r in routes)
            items.append({"category": "API端点", "item": route, "status": "pass" if found else "fail",
                          "detail": "已注册" if found else "未注册", "auto": True})
    except Exception as e:
        items.append({"category": "API端点", "item": "API扫描", "status": "fail",
                      "detail": str(e), "auto": True})

    return items


def scan_strategies():
    """动态扫描策略"""
    items = []
    try:
        import requests
        r = requests.post("http://127.0.0.1:5003/api/auth/login",
                         json={"username": "admin", "password": "admin123"}, timeout=5)
        sid = r.json().get("session_id", "")
        r2 = requests.get("http://127.0.0.1:5003/api/strategy/list",
                         cookies={"session_id": sid}, timeout=5)
        strategies = r2.json().get("data", {}).get("strategies", [])
        items.append({"category": "策略注册", "item": "已注册策略数", "status": "pass",
                      "detail": f"{len(strategies)}个", "auto": True})

        # 策略类型分布
        type_counts = {}
        for s in strategies:
            t = s.get("strategy_type", s.get("type", "unknown"))
            type_counts[t] = type_counts.get(t, 0) + 1
        for t, c in type_counts.items():
            items.append({"category": "策略类型", "item": t, "status": "pass",
                          "detail": f"{c}个策略", "auto": True})

        # 策略状态
        enabled = sum(1 for s in strategies if s.get("enabled"))
        disabled = len(strategies) - enabled
        items.append({"category": "策略状态", "item": "已启用/已禁用", "status": "pass",
                      "detail": f"{enabled}/{disabled}", "auto": True})
    except Exception as e:
        items.append({"category": "策略注册", "item": "策略扫描", "status": "fail",
                      "detail": str(e), "auto": True})

    return items


def scan_links():
    """动态扫描业务链路"""
    items = []
    from core.l2_inspector import L2Inspector
    inspector = L2Inspector(mode="quick")
    try:
        report = inspector.run()
        for item in inspector._results:
            items.append({"category": "业务链路", "item": item.name, "status": "pass" if item.passed else "fail",
                          "detail": item.detail, "auto": True})
    except Exception as e:
        items.append({"category": "业务链路", "item": "链路扫描", "status": "fail",
                      "detail": str(e), "auto": True})

    # 三大入口链路
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_v", os.path.join(PROJECT_ROOT, "_verify_three_entries.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        entry_names = [
            ("verify_closed_n1", "全链路-健康检查"), ("verify_closed_n2", "全链路-一键巡检"),
            ("verify_closed_n3", "全链路-选股分流"), ("verify_closed_n4", "全链路-容错"),
            ("verify_closed_n5", "全链路-配置"), ("verify_original_n1", "原始策略-发现"),
            ("verify_original_n2", "原始策略-注册"), ("verify_original_n3", "原始策略-回测"),
            ("verify_original_n4", "原始策略-优化"), ("verify_original_n5", "原始策略-风控"),
            ("verify_vibe_n1", "Vibe-注册"), ("verify_vibe_n2", "Vibe-注册表"),
            ("verify_vibe_n3", "Vibe-调度"), ("verify_vibe_n4", "Vibe-集成"),
            ("verify_vibe_n5", "Vibe-因子"), ("verify_ths_n1", "同花顺-桥接"),
            ("verify_ths_n2", "同花顺-信号"), ("verify_ths_n3", "同花顺-问财"),
            ("verify_ths_n4", "同花顺-行情"), ("verify_ths_n5", "同花顺-发现"),
            ("verify_resource_n1", "资源-并发"), ("verify_resource_n2", "资源-模拟"),
        ]
        for fn_name, label in entry_names:
            fn = getattr(mod, fn_name, None)
            if fn:
                r = fn()
                p = r.get("passed", False) if isinstance(r, dict) else r[0]
                d = r.get("detail", "") if isinstance(r, dict) else ""
                items.append({"category": "三大入口", "item": label, "status": "pass" if p else "fail",
                              "detail": d, "auto": True})
    except Exception as e:
        items.append({"category": "三大入口", "item": "入口扫描", "status": "fail",
                      "detail": str(e), "auto": True})

    return items


def scan_environment():
    """扫描运行环境"""
    items = []
    # Python 版本
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    items.append({"category": "运行环境", "item": "Python版本", "status": "pass" if sys.version_info >= (3, 10) else "fail",
                  "detail": py_ver, "auto": True})

    # 依赖检查
    required = ["flask", "requests", "urllib3"]
    for pkg in required:
        try:
            __import__(pkg)
            items.append({"category": "运行环境", "item": f"依赖-{pkg}", "status": "pass",
                          "detail": "已安装", "auto": True})
        except ImportError:
            items.append({"category": "运行环境", "item": f"依赖-{pkg}", "status": "fail",
                          "detail": "未安装", "auto": True})

    # 磁盘空间
    import shutil
    total, used, free = shutil.disk_usage(PROJECT_ROOT)
    free_gb = round(free / (1024 ** 3), 1)
    items.append({"category": "运行环境", "item": "磁盘空间", "status": "pass" if free_gb > 1 else "warn",
                  "detail": f"剩余{free_gb}GB", "auto": True})

    return items


# ============================================================
# 报告生成
# ============================================================

def generate_checklist(output_format="md"):
    """生成完整部署检查清单"""
    all_items = []
    scanners = [scan_security_modules, scan_config, scan_modules,
                scan_strategies, scan_links, scan_environment]
    for scanner in scanners:
        try:
            all_items.extend(scanner())
        except Exception as e:
            all_items.append({"category": "扫描错误", "item": scanner.__name__,
                              "status": "fail", "detail": str(e), "auto": True})

    # 统计
    total = len(all_items)
    passed = sum(1 for i in all_items if i["status"] == "pass")
    failed = sum(1 for i in all_items if i["status"] == "fail")
    warned = sum(1 for i in all_items if i["status"] == "warn")
    score = round(passed / total * 100, 1) if total > 0 else 0

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if output_format == "json":
        result = {
            "timestamp": ts, "total": total, "passed": passed,
            "failed": failed, "warned": warned, "score": score,
            "items": all_items,
        }
        path = os.path.join(CHECKLIST_DIR, f"deploy_checklist_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        return path, result

    elif output_format == "html":
        html = _generate_html(all_items, ts, passed, failed, warned, total, score)
        path = os.path.join(CHECKLIST_DIR, f"deploy_checklist_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        return path, {"score": score}

    else:  # markdown
        md = _generate_md(all_items, ts, passed, failed, warned, total, score)
        path = os.path.join(CHECKLIST_DIR, f"deploy_checklist_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(md)
        return path, {"score": score}


def _generate_md(items, ts, passed, failed, warned, total, score):
    """生成 Markdown 报告"""
    lines = [
        f"# Aurora 量化交易系统 — 生产环境部署检查清单",
        f"",
        f"> **生成时间**: {ts}",
        f"> **自动更新**: 随策略增减、模块增减、链路变化自动更新",
        f"> **重新生成**: `python extensions/tools/deploy_checklist.py`",
        f"",
        f"## 总览",
        f"",
        f"| 指标 | 数值 |",
        f"|------|------|",
        f"| 总检查项 | {total} |",
        f"| ✅ 通过 | {passed} |",
        f"| ❌ 失败 | {failed} |",
        f"| ⚠️ 警告 | {warned} |",
        f"| 部署就绪度 | **{score}%** |",
        f"",
        f"> 部署就绪度 ≥ 90% 可安全部署；< 80% 需修复后再部署",
        f"",
    ]

    # 按类别分组
    categories = {}
    for item in items:
        cat = item["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(item)

    for cat, cat_items in categories.items():
        cat_passed = sum(1 for i in cat_items if i["status"] == "pass")
        cat_total = len(cat_items)
        icon = "✅" if cat_passed == cat_total else ("⚠️" if cat_passed >= cat_total * 0.8 else "❌")
        lines.append(f"## {icon} {cat} ({cat_passed}/{cat_total})")
        lines.append("")
        lines.append("| 状态 | 检查项 | 详情 |")
        lines.append("|------|--------|------|")
        for item in cat_items:
            s = {"pass": "✅", "fail": "❌", "warn": "⚠️"}.get(item["status"], "❓")
            lines.append(f"| {s} | {item['item']} | {item['detail']} |")
        lines.append("")

    lines.append("---")
    lines.append(f"*此清单由 deploy_checklist.py 自动生成，最后更新: {ts}*")
    return "\n".join(lines)


def _generate_html(items, ts, passed, failed, warned, total, score):
    """生成 HTML 报告"""
    sc = "#00c853" if score >= 90 else ("#f39c12" if score >= 70 else "#e74c5c")
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>生产环境部署检查清单</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#0a0d14;color:#e8ecf1;font-family:'PingFang SC','Microsoft YaHei',sans-serif;padding:40px;max-width:1000px;margin:0 auto}}
.header{{text-align:center;margin-bottom:30px;padding:30px;background:linear-gradient(135deg,#1a2744,#0d1526);border-radius:16px;border:1px solid rgba(255,255,255,0.08)}}
.header h1{{font-size:24px;background:linear-gradient(135deg,#00d4c8,#4a7dff);-webkit-background-clip:text;-webkit-text-fill-color:transparent}}
.score{{font-size:64px;font-weight:800;color:{sc};text-align:center;margin:20px 0}}
.summary{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:30px}}
.card{{background:#111620;border:1px solid rgba(255,255,255,0.08);border-radius:12px;padding:20px;text-align:center}}
.card .val{{font-size:28px;font-weight:700}}
.card .lbl{{font-size:12px;color:#8895a9;margin-top:4px}}
.section{{background:#111620;border:1px solid rgba(255,255,255,0.08);border-radius:12px;padding:20px;margin-bottom:16px}}
.section h3{{font-size:16px;margin-bottom:12px}}
.row{{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid rgba(255,255,255,0.04);font-size:13px}}
.pass{{color:#00c853}}.fail{{color:#e74c5c}}.warn{{color:#f39c12}}
.footer{{text-align:center;color:#667;font-size:12px;margin-top:30px}}
</style></head>
<body>
<div class="header"><h1>🚀 Aurora 生产环境部署检查清单</h1><div style="color:#8895a9;margin-top:8px">生成时间: {ts}</div></div>
<div class="score">{score}<span style="font-size:20px">%</span></div>
<div class="summary">
<div class="card"><div class="val" style="color:#4a7dff">{total}</div><div class="lbl">总检查项</div></div>
<div class="card"><div class="val" style="color:#00c853">{passed}</div><div class="lbl">通过</div></div>
<div class="card"><div class="val" style="color:#e74c5c">{failed}</div><div class="lbl">失败</div></div>
<div class="card"><div class="val" style="color:#f39c12">{warned}</div><div class="lbl">警告</div></div>
</div>
"""
    categories = {}
    for item in items:
        cat = item["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(item)

    for cat, cat_items in categories.items():
        cp = sum(1 for i in cat_items if i["status"] == "pass")
        html += f'<div class="section"><h3>{cat} ({cp}/{len(cat_items)})</h3>'
        for item in cat_items:
            s = {"pass": "✅", "fail": "❌", "warn": "⚠️"}.get(item["status"], "❓")
            cls = item["status"]
            html += f'<div class="row"><span class="{cls}">{s} {item["item"]}</span><span>{item["detail"]}</span></div>'
        html += "</div>"

    html += f'<div class="footer">Aurora 量化交易系统 · 部署检查清单 · {ts}<br>自动生成，随策略/模块/链路变化更新</div></body></html>'
    return html


def _generate_docx(items, ts, passed, failed, warned, total, score):
    """生成 Word (.docx) 报告"""
    from docx import Document
    from docx.shared import Inches, Pt, Cm, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.oxml.ns import qn

    doc = Document()
    style = doc.styles['Normal']
    font = style.font
    font.name = 'Microsoft YaHei'
    font.size = Pt(10)
    style.element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')

    # 标题
    title = doc.add_heading('Aurora 量化交易系统 — 生产环境部署检查清单', level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # 元信息
    meta = doc.add_paragraph()
    meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
    meta.add_run(f'生成时间: {ts}').font.size = Pt(10)
    meta.add_run('\n自动更新: 随策略增减、模块增减、链路变化自动更新').font.size = Pt(9)

    # 总览
    doc.add_heading('总览', level=1)
    overview_table = doc.add_table(rows=1, cols=2)
    overview_table.style = 'Light Grid Accent 1'
    overview_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr = overview_table.rows[0].cells
    hdr[0].text = '指标'
    hdr[1].text = '数值'
    for label, val in [('总检查项', str(total)), ('✅ 通过', str(passed)),
                        ('❌ 失败', str(failed)), ('⚠️ 警告', str(warned)),
                        ('部署就绪度', f'{score}%')]:
        row = overview_table.add_row()
        row.cells[0].text = label
        row.cells[1].text = val

    sc = RGBColor(0, 200, 83) if score >= 90 else RGBColor(243, 156, 18) if score >= 70 else RGBColor(231, 76, 92)
    p = doc.add_paragraph()
    p.add_run('✅ 满足生产环境部署要求' if score >= 90 else '⚠️ 需修复').font.color.rgb = sc

    # 分类详情
    categories = {}
    for item in items:
        cat = item["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(item)

    for cat, cat_items in categories.items():
        cp = sum(1 for i in cat_items if i["status"] == "pass")
        icon = "✅" if cp == len(cat_items) else ("⚠️" if cp >= len(cat_items) * 0.8 else "❌")
        doc.add_heading(f'{icon} {cat} ({cp}/{len(cat_items)})', level=2)

        t = doc.add_table(rows=1, cols=3)
        t.style = 'Light Grid Accent 1'
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        hdr = t.rows[0].cells
        hdr[0].text = '状态'
        hdr[1].text = '检查项'
        hdr[2].text = '详情'
        for item in cat_items:
            row = t.add_row()
            s = {"pass": "✅", "fail": "❌", "warn": "⚠️"}.get(item["status"], "❓")
            row.cells[0].text = s
            row.cells[1].text = item["item"]
            row.cells[2].text = item["detail"]

    doc.add_paragraph('')
    footer = doc.add_paragraph()
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer.add_run(f'此清单由 deploy_checklist.py 自动生成，最后更新: {ts}').font.size = Pt(9)

    path = os.path.join(CHECKLIST_DIR, f"deploy_checklist_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx")
    doc.save(path)
    return path


def main():
    import argparse
    parser = argparse.ArgumentParser(description="生产环境部署检查清单生成器")
    parser.add_argument("--output", "-o", choices=["md", "json", "html", "docx"], default="md",
                       help="输出格式 (默认: md)")
    args = parser.parse_args()

    print("=" * 60)
    print("  生产环境部署检查清单生成器")
    print("  动态扫描: 安全配置 · 模块 · 策略 · 链路 · 环境")
    print("=" * 60)

    if args.output == "docx":
        all_items = []
        scanners = [scan_security_modules, scan_config, scan_modules,
                    scan_strategies, scan_links, scan_environment]
        for scanner in scanners:
            try:
                all_items.extend(scanner())
            except Exception as e:
                all_items.append({"category": "扫描错误", "item": scanner.__name__,
                                  "status": "fail", "detail": str(e), "auto": True})
        total = len(all_items)
        passed = sum(1 for i in all_items if i["status"] == "pass")
        failed = sum(1 for i in all_items if i["status"] == "fail")
        warned = sum(1 for i in all_items if i["status"] == "warn")
        score = round(passed / total * 100, 1) if total > 0 else 0
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        path = _generate_docx(all_items, ts, passed, failed, warned, total, score)
        print(f"\n  部署就绪度: {score}%")
        print(f"  Word 报告路径: {path}")
    else:
        path, result = generate_checklist(args.output)
        score = result.get("score", 0)
        print(f"\n  部署就绪度: {score}%")
        print(f"  报告路径: {path}")

    if score >= 90:
        print("  ✅ 满足生产环境部署要求")
    elif score >= 70:
        print("  ⚠️ 需要修复后再部署")
    else:
        print("  ❌ 不满足部署要求，请先修复")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())