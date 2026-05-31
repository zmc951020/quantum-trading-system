#!/usr/bin/env python3
"""
QS Robot 系统托盘模块
支持最小化到托盘、右键菜单恢复/退出
"""
import pystray
import threading
import webbrowser
from PIL import Image, ImageDraw


def create_tray_icon():
    """创建一个 64x64 的机器人图标 (蓝色Q字形)"""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # 圆形背景
    draw.ellipse([4, 4, 60, 60], fill=(22, 27, 34, 255), outline=(88, 166, 255, 255), width=2)
    # 字母 "Q"
    draw.text((18, 10), "Q", fill=(88, 166, 255, 255))
    # 小标记 "S"
    draw.text((36, 34), "S", fill=(63, 185, 80, 255))
    return img


class QBotTray:
    """QS Robot 系统托盘管理器"""

    def __init__(self, app_host="127.0.0.1", app_port=5001, on_restore=None, on_quit=None):
        self.app_host = app_host
        self.app_port = app_port
        self.app_url = f"http://{app_host}:{app_port}"
        self._on_restore = on_restore
        self._on_quit = on_quit
        self._tray = None
        self._icon = create_tray_icon()

    def _open_panel(self, icon, item):
        """打开 Web 控制面板"""
        webbrowser.open(self.app_url)

    def _restore(self, icon, item):
        """恢复窗口"""
        if self._on_restore:
            self._on_restore()

    def _quit(self, icon, item):
        """退出"""
        icon.stop()
        if self._on_quit:
            self._on_quit()

    def _setup_menu(self):
        """构建托盘右键菜单"""
        menu = (
            pystray.MenuItem("🧠 打开控制面板", self._open_panel, default=True),
            pystray.MenuItem("🔄 显示窗口", self._restore),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("❌ 退出", self._quit),
        )
        return menu

    def run(self):
        """启动托盘图标"""
        self._tray = pystray.Icon(
            "qs_robot",
            self._icon,
            f"QS Robot — 量化交易助手 ({self.app_port})",
            menu=self._setup_menu(),
        )
        self._tray.run()

    def run_in_thread(self):
        """在后台线程启动托盘"""
        t = threading.Thread(target=self.run, daemon=True, name="QBot-Tray")
        t.start()
        return t

    def stop(self):
        """停止托盘"""
        if self._tray:
            self._tray.stop()


if __name__ == "__main__":
    # 测试托盘
    tray = QBotTray(app_port=5001)
    tray.run()