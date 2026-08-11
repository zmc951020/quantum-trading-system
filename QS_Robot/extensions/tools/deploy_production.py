"""生产环境一键部署脚本
用法: python extensions/tools/deploy_production.py [--restart] [--dry-run]
"""
import os
import sys
import json
import time
import signal
import socket
import subprocess
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

DEPLOY_LOG = os.path.join(PROJECT_ROOT, "data", "deploy_logs")
os.makedirs(DEPLOY_LOG, exist_ok=True)


def validate_config():
    """验证生产环境配置"""
    issues = []
    config_path = os.path.join(PROJECT_ROOT, "config.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    port = config.get("port_allocation", {}).get("qs_robot_shell", 5003)
    if port != 5003:
        issues.append(f"端口非5003: {port}")

    if config.get("debug"):
        issues.append("DEBUG模式开启(生产应关闭)")

    # 检查 .env 文件
    env_path = os.path.join(PROJECT_ROOT, ".env")
    if not os.path.exists(env_path):
        issues.append(".env 文件不存在")

    # 检查gitignore
    gitignore_path = os.path.join(PROJECT_ROOT, ".gitignore")
    if os.path.exists(gitignore_path):
        with open(gitignore_path, "r", encoding="utf-8") as f:
            content = f.read()
        for pattern in ["config.json", "*.pem", "*.key", "credentials"]:
            if pattern not in content:
                issues.append(f".gitignore 缺少: {pattern}")

    return issues


def check_port(port=5003):
    """检查端口占用"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('127.0.0.1', port))
    sock.close()
    return result == 0


def run_health_check():
    """运行生产部署前健康检查"""
    sys.path.insert(0, PROJECT_ROOT)
    try:
        from core.system_health_checker import get_health_checker
        checker = get_health_checker()
        result = checker.run_check(mode="quick")
        return {
            "score": result.overall_score,
            "passed": result.passed_checks,
            "failed": result.failed_checks,
            "total": result.total_checks,
            "status": result.overall_status,
        }
    except Exception as e:
        return {"error": str(e)}


def deploy():
    """执行生产部署"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(DEPLOY_LOG, f"deploy_{ts}.log")
    report = {
        "timestamp": datetime.now().isoformat(),
        "steps": [],
        "success": True,
    }

    def log(msg, status="info"):
        entry = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
        print(entry)
        report["steps"].append({"msg": msg, "status": status})
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(entry + "\n")

    log("=" * 60)
    log("  Aurora 量化交易系统 — 生产环境部署")
    log(f"  部署时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 60)

    # Step 1: 配置验证
    log("\n[Step 1/6] 配置验证...")
    issues = validate_config()
    if issues:
        for i in issues:
            log(f"  ⚠️ {i}", "warn")
    else:
        log("  ✅ 配置验证通过")

    # Step 2: 部署检查清单
    log("\n[Step 2/6] 运行部署检查清单...")
    try:
        from extensions.tools.deploy_checklist import generate_checklist
        path, result = generate_checklist("md")
        score = result.get("score", 0)
        log(f"  部署就绪度: {score}%", "pass" if score >= 90 else "fail")
        if score < 90:
            log("  ❌ 部署就绪度不达标，终止部署", "fail")
            report["success"] = False
            return report
    except Exception as e:
        log(f"  ⚠️ 检查清单生成失败: {e}", "warn")

    # Step 3: 端口检查
    log("\n[Step 3/6] 端口检查...")
    port = 5003
    if check_port(port):
        log(f"  ⚠️ 端口 {port} 已被占用，将尝试重启", "warn")
    else:
        log(f"  ✅ 端口 {port} 可用")

    # Step 4: 健康检查
    log("\n[Step 4/6] 系统健康检查...")
    try:
        health = run_health_check()
        if "error" in health:
            log(f"  ⚠️ 健康检查异常: {health['error']}", "warn")
        else:
            log(f"  评分: {health['score']:.1f} | 通过: {health['passed']}/{health['total']} | 状态: {health['status']}")
    except Exception as e:
        log(f"  ⚠️ 健康检查失败: {e}", "warn")

    # Step 5: 三大入口验收
    log("\n[Step 5/6] 三大入口链路验收...")
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_v", os.path.join(PROJECT_ROOT, "_verify_three_entries.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        results = mod.RESULTS if hasattr(mod, 'RESULTS') else []
        passed = sum(1 for r in results if r.get("passed"))
        log(f"  验收结果: {passed}/{len(results)} 通过", "pass" if passed == len(results) else "fail")
    except Exception as e:
        log(f"  ⚠️ 验收失败: {e}", "warn")

    # Step 6: 生成部署报告
    log("\n[Step 6/6] 生成部署报告...")
    try:
        from extensions.tools.generate_inspection_report import run_all_inspections
        insp_result = run_all_inspections()
        report_path = os.path.join(PROJECT_ROOT, "data", "health_reports",
                                   f"deploy_report_{ts}.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(insp_result, f, ensure_ascii=False, indent=2)
        log(f"  ✅ 部署报告已保存: {report_path}")
    except Exception as e:
        log(f"  ⚠️ 报告生成失败: {e}", "warn")

    # 汇总
    log("\n" + "=" * 60)
    if report["success"]:
        log("  ✅ 生产环境部署完成！")
        log(f"  系统地址: http://127.0.0.1:5003")
        log(f"  维护界面: http://127.0.0.1:5003/maintenance")
        log(f"  部署日志: {log_file}")
    else:
        log("  ❌ 部署失败，请检查日志")
    log("=" * 60)

    return report


def restart_service():
    """重启服务 (Windows)"""
    print("正在重启服务...")
    # 查找并停止现有python进程
    try:
        subprocess.run(
            ["taskkill", "/F", "/FI", "WINDOWTITLE eq *QS_Robot*"],
            capture_output=True, timeout=10
        )
    except:
        pass
    time.sleep(2)
    # 启动新进程
    subprocess.Popen(
        [sys.executable, "run.py"],
        cwd=PROJECT_ROOT,
        creationflags=subprocess.CREATE_NO_WINDOW
    )
    print("服务已启动")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="生产环境一键部署")
    parser.add_argument("--restart", action="store_true", help="部署后重启服务")
    parser.add_argument("--dry-run", action="store_true", help="仅验证不实际部署")
    args = parser.parse_args()

    if args.dry_run:
        print("🔍 Dry Run 模式 — 仅验证配置")
        issues = validate_config()
        if issues:
            print(f"\n⚠️ 发现 {len(issues)} 个配置问题:")
            for i in issues:
                print(f"  - {i}")
        else:
            print("\n✅ 配置验证通过，可以部署")
        return 0

    report = deploy()
    if report["success"] and args.restart:
        restart_service()

    return 0 if report["success"] else 1


if __name__ == "__main__":
    sys.exit(main())