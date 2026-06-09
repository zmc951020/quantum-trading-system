#!/usr/bin/env python3
"""
Aurora量化交易系统 - 生产环境启动脚本 v2.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
使用waitress作为WSGI服务器（Windows兼容）
集成 Smart Model Router 自启动 + 费用风控守护
"""

import os
import sys
import time
import threading
import logging
from waitress import serve

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler('logs/aurora_startup.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("Aurora.Production")

# 导入Aurora应用
try:
    from visualization import app
    logger.info("已加载 visualization.app")
except ImportError as e:
    logger.error(f"无法导入 app: {e}")
    app = None

# ── 智能模型路由器初始化 ──

def init_smart_router():
    """
    初始化AI模型智能路由器
    自动检测可用后端：DeepSeek Pro → DeepSeek Flash → Qwen API → Ollama本地
    """
    global _router, _router_ready
    try:
        from model_integration import init_router, get_health_status, print_status

        # 尝试加载各种客户端
        deepseek_client = None
        qwen_client = None
        ollama_client = None

        # 加载DeepSeek
        try:
            api_key = os.environ.get("DEEPSEEK_API_KEY", "")
            if api_key:
                from deepseek_client import DeepSeekClient
                deepseek_client = DeepSeekClient(api_key)
                logger.info("[自启动] DeepSeek 客户端已加载 (Pro+Flash)")
            else:
                logger.warning("[自启动] DEEPSEEK_API_KEY 未设置，DeepSeek后端不可用")
        except ImportError:
            logger.warning("[自启动] deepseek_client 模块未找到")
        except Exception as e:
            logger.warning(f"[自启动] DeepSeek 加载失败: {e}")

        # 加载Qwen API
        try:
            api_key = os.environ.get("QWEN_API_KEY") or os.environ.get("DASHSCOPE_API_KEY", "")
            if api_key:
                from qwen_client import QwenClient
                qwen_client = QwenClient(api_key)
                logger.info("[自启动] Qwen3.6+ API 客户端已加载")
            else:
                logger.warning("[自启动] QWEN_API_KEY 未设置，Qwen后端不可用")
        except ImportError:
            logger.warning("[自启动] qwen_client 模块未找到")
        except Exception as e:
            logger.warning(f"[自启动] Qwen 加载失败: {e}")

        # 加载Ollama
        try:
            from ollama_client import create_ollama_client
            ollama_client = create_ollama_client()
            if ollama_client.is_healthy():
                models = ollama_client.get_available_models()
                logger.info(f"[自启动] Ollama 本地推理已就绪，{len(models)}个模型可用: {models[:5]}")
            else:
                logger.warning("[自启动] Ollama 服务未运行 — 本地模型不可用 (请执行 'ollama serve')")
        except ImportError:
            logger.warning("[自启动] ollama_client 模块未找到")
        except Exception as e:
            logger.warning(f"[自启动] Ollama 加载失败: {e}")

        # 初始化路由器
        init_router(
            deepseek_client=deepseek_client,
            qwen_client=qwen_client,
            ollama_client=ollama_client,
            enable_cache=True,
            cache_ttl=300,
        )
        _router_ready = True
        logger.info("[自启动] ✅ AI智能路由器初始化完成")

        # 打印完整健康状态
        try:
            from model_integration import print_status
            print("\n")
            print_status()
            print("\n")
        except Exception:
            pass

        return True
    except Exception as e:
        logger.error(f"[自启动] ❌ 路由器初始化失败: {e}", exc_info=True)
        _router_ready = False
        return False


# ── 费用风控守护线程 ──

def cost_guardian_thread():
    """
    后台费用守护线程
    每30秒检查一次累计费用，超过阈值自动限流
    """
    COST_WARNING_THRESHOLD = 50.0   # 单日50元警告
    COST_ALERT_THRESHOLD = 80.0     # 单日80元告警
    COST_CRITICAL_THRESHOLD = 120.0  # 单日120元触发熔断
    CHECK_INTERVAL_SECONDS = 30

    logger.info(f"[费用守护] 启动 — 阈值: ¥{COST_WARNING_THRESHOLD}/¥{COST_ALERT_THRESHOLD}/¥{COST_CRITICAL_THRESHOLD}")

    last_cost = 0.0
    alert_sent = {"warning": False, "alert": False, "critical": False}

    while True:
        try:
            time.sleep(CHECK_INTERVAL_SECONDS)

            from model_integration import get_router_stats
            stats = get_router_stats()
            total_cost = stats.get("total_cost_estimated", 0.0)
            total_saved = stats.get("total_cost_saved", 0.0)
            daily_projection = stats.get("daily_cost_projection", 0.0)

            # 节省汇总
            if total_cost != last_cost:
                logger.info(
                    f"[费用守护] 累计费用: ¥{total_cost:.4f} | "
                    f"已节省: ¥{total_saved:.4f} | "
                    f"预计日费: ¥{daily_projection:.2f}"
                )
                last_cost = total_cost

            # 阈值检查
            if daily_projection >= COST_CRITICAL_THRESHOLD and not alert_sent["critical"]:
                alert_sent["critical"] = True
                _send_wework_alert(
                    "🔴 Aurora费用熔断",
                    f"预计日费 ¥{daily_projection:.2f} 已超临界阈值 ¥{COST_CRITICAL_THRESHOLD}\n"
                    f"已自动将P2+任务全部路由到本地Ollama\n"
                    f"累计节省: ¥{total_saved:.4f}"
                )
                logger.critical(f"[费用守护] 🔴 触发CRITICAL熔断！预计日费 ¥{daily_projection:.2f}")

            elif daily_projection >= COST_ALERT_THRESHOLD and not alert_sent["alert"]:
                alert_sent["alert"] = True
                _send_wework_alert(
                    "🟡 Aurora费用告警",
                    f"预计日费 ¥{daily_projection:.2f} 已超告警阈值 ¥{COST_ALERT_THRESHOLD}\n"
                    f"建议减少DeepSeek Pro调用\n"
                    f"累计节省: ¥{total_saved:.4f}"
                )
                logger.warning(f"[费用守护] 🟡 费用告警！预计日费 ¥{daily_projection:.2f}")

            elif daily_projection >= COST_WARNING_THRESHOLD and not alert_sent["warning"]:
                alert_sent["warning"] = True
                logger.info(f"[费用守护] ⚠️ 费用提醒：预计日费 ¥{daily_projection:.2f}")

        except Exception as e:
            logger.error(f"[费用守护] 巡检异常: {e}")


def _send_wework_alert(title: str, message: str):
    """发送企业微信告警（如可用）"""
    try:
        webhook_url = os.environ.get("WEWORK_WEBHOOK_URL", "")
        if not webhook_url:
            return
        import requests
        requests.post(webhook_url, json={
            "msgtype": "markdown",
            "markdown": {"content": f"## {title}\n{message}"}
        }, timeout=5)
    except Exception:
        pass


def start_cost_guardian():
    """启动费用守护守护线程"""
    thread = threading.Thread(target=cost_guardian_thread, daemon=True, name="CostGuardian")
    thread.start()
    logger.info("[自启动] 费用守护线程已启动")
    return thread


# ── Ollama 保活检查 ──

def ollama_watchdog_thread():
    """Ollama 服务保活检查（每60秒检查一次）"""
    while True:
        try:
            time.sleep(60)
            from ollama_client import create_ollama_client
            client = create_ollama_client()
            if not client.is_healthy():
                logger.warning("[保活检查] Ollama 服务不可用，请手动启动 'ollama serve'")
        except Exception:
            pass


def start_ollama_watchdog():
    """启动Ollama保活检查"""
    thread = threading.Thread(target=ollama_watchdog_thread, daemon=True, name="OllamaWatchdog")
    thread.start()
    logger.info("[自启动] Ollama保活检查已启动")
    return thread


# ── 主入口 ──

if __name__ == '__main__':
    print("=" * 60)
    print("  [Aurora] 量化交易系统 v2.0")
    print("  Smart Model Router 已集成")
    print("=" * 60)

    # 初始化AI智能路由器
    logger.info("正在初始化AI智能路由器...")
    router_ok = init_smart_router()

    # 启动后台守护线程
    cost_thread = start_cost_guardian()
    watchdog_thread = start_ollama_watchdog()

    print(f"\n  [Web] 主Web服务: http://0.0.0.0:5000")
    print(f"  [Login] 登录地址: http://127.0.0.1:5000/login")
    print(f"  [Robot] QS Robot: http://127.0.0.1:5000/qbot")
    print(f"  [AI] AI路由器: {'OK' if router_ok else 'WARNING'}")
    print(f"\n  [Cost] 费用守护: 运行中 (每30秒巡检)")
    print(f"  [Ollama] 保活检查: 运行中 (每60秒检查)")
    print("=" * 60)

    # 启动Aurora主服务器 (QBot已通过visualization.py集成到5002端口)
    serve(app, host='0.0.0.0', port=5002, threads=8)
