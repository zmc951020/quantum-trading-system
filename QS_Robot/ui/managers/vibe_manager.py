# -*- coding: utf-8 -*-
"""Vibe-Trading 子进程管理"""
import os
import sys
import subprocess
import time
import urllib.request

_VIBE_API_PORT = 5004
_VIBE_MCP_PORT = 5005
_vibe_api_process = None
_vibe_mcp_process = None
_VIBE_SITE_PACKAGES = os.path.dirname(os.path.dirname(sys.executable)) + "\\Lib\\site-packages"


def start_vibe_api():
    """启动 Vibe-Trading FastAPI API Server"""
    global _vibe_api_process
    if _vibe_api_process and _vibe_api_process.poll() is None:
        return {"success": True, "port": _VIBE_API_PORT, "status": "already_running",
                "url": f"http://127.0.0.1:{_VIBE_API_PORT}", "docs": f"http://127.0.0.1:{_VIBE_API_PORT}/docs"}

    api_server = os.path.join(_VIBE_SITE_PACKAGES, "api_server.py")
    if not os.path.exists(api_server):
        return {"success": False, "error": f"api_server.py 未找到: {api_server}"}

    env = os.environ.copy()
    env["PYTHONPATH"] = _VIBE_SITE_PACKAGES + os.pathsep + env.get("PYTHONPATH", "")

    _vibe_api_process = subprocess.Popen(
        [sys.executable, api_server, "--port", str(_VIBE_API_PORT), "--host", "127.0.0.1"],
        cwd=_VIBE_SITE_PACKAGES,
        env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    time.sleep(3)
    if _vibe_api_process.poll() is not None:
        stderr = _vibe_api_process.stderr.read().decode("utf-8", errors="replace")[:500]
        _vibe_api_process = None
        return {"success": False, "error": f"进程启动失败，stderr: {stderr}"}

    return {"success": True, "port": _VIBE_API_PORT,
            "url": f"http://127.0.0.1:{_VIBE_API_PORT}",
            "docs": f"http://127.0.0.1:{_VIBE_API_PORT}/docs"}


def get_vibe_api_status():
    """Vibe-Trading FastAPI 状态查询"""
    running = _vibe_api_process is not None and _vibe_api_process.poll() is None
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{_VIBE_API_PORT}/docs", method="HEAD")
        urllib.request.urlopen(req, timeout=2)
        api_healthy = True
    except Exception:
        api_healthy = False

    return {
        "success": True,
        "running": running,
        "api_healthy": api_healthy,
        "port": _VIBE_API_PORT,
        "url": f"http://127.0.0.1:{_VIBE_API_PORT}" if running else None,
        "docs": f"http://127.0.0.1:{_VIBE_API_PORT}/docs" if running else None,
    }


def stop_vibe_api():
    """停止 Vibe-Trading FastAPI"""
    global _vibe_api_process
    if _vibe_api_process and _vibe_api_process.poll() is None:
        _vibe_api_process.terminate()
        try:
            _vibe_api_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _vibe_api_process.kill()
        _vibe_api_process = None
        return {"success": True, "status": "stopped"}
    return {"success": True, "status": "not_running"}


def start_vibe_mcp():
    """启动 Vibe-Trading MCP Server"""
    global _vibe_mcp_process
    if _vibe_mcp_process and _vibe_mcp_process.poll() is None:
        return {"success": True, "port": _VIBE_MCP_PORT, "status": "already_running"}

    mcp_server = os.path.join(_VIBE_SITE_PACKAGES, "mcp_server.py")
    if not os.path.exists(mcp_server):
        return {"success": False, "error": f"mcp_server.py 未找到: {mcp_server}"}

    env = os.environ.copy()
    env["PYTHONPATH"] = _VIBE_SITE_PACKAGES + os.pathsep + env.get("PYTHONPATH", "")

    _vibe_mcp_process = subprocess.Popen(
        [sys.executable, mcp_server, "--transport", "sse", "--port", str(_VIBE_MCP_PORT)],
        cwd=_VIBE_SITE_PACKAGES,
        env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    time.sleep(2)
    if _vibe_mcp_process.poll() is not None:
        stderr = _vibe_mcp_process.stderr.read().decode("utf-8", errors="replace")[:500]
        _vibe_mcp_process = None
        return {"success": False, "error": f"MCP启动失败: {stderr}"}

    return {"success": True, "port": _VIBE_MCP_PORT,
            "sse_url": f"http://127.0.0.1:{_VIBE_MCP_PORT}/sse"}


def get_vibe_mcp_status():
    """Vibe-Trading MCP Server 状态查询"""
    running = _vibe_mcp_process is not None and _vibe_mcp_process.poll() is None
    return {
        "success": True,
        "running": running,
        "port": _VIBE_MCP_PORT,
        "sse_url": f"http://127.0.0.1:{_VIBE_MCP_PORT}/sse" if running else None,
    }


def stop_vibe_mcp():
    """停止 Vibe-Trading MCP Server"""
    global _vibe_mcp_process
    if _vibe_mcp_process and _vibe_mcp_process.poll() is None:
        _vibe_mcp_process.terminate()
        try:
            _vibe_mcp_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _vibe_mcp_process.kill()
        _vibe_mcp_process = None
        return {"success": True, "status": "stopped"}
    return {"success": True, "status": "not_running"}


def stop_vibe_services():
    """清理所有 Vibe-Trading 子进程"""
    global _vibe_api_process, _vibe_mcp_process
    for proc, name in [(_vibe_api_process, "FastAPI"), (_vibe_mcp_process, "MCP")]:
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
    _vibe_api_process = None
    _vibe_mcp_process = None
