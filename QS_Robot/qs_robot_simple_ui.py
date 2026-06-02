#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QS Robot - Aurora 量化系统智能助手
启动器 - 修复按钮功能
"""

import sys
import os
import subprocess
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QPushButton,
    QMessageBox, QHBoxLayout
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QPalette, QColor

# Aurora系统地址
AURORA_URL = "http://127.0.0.1:5000"
DEEPSEEK_URL = f"{AURORA_URL}/deepseek"

class QSLoginWindow(QWidget):
    """QS Robot 登录窗口 - 简洁版"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("QS Robot - Aurora 量化系统")
        self.setFixedSize(500, 350)
        self.setup_ui()
    
    def setup_ui(self):
        """设置UI"""
        self.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #0D1117, stop:1 #161B22);
            }
        """)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)
        
        # 标题
        title = QLabel("QS Robot")
        title.setFont(QFont("Microsoft YaHei", 28, QFont.Bold))
        title.setStyleSheet("color: #00D4AA; background: transparent;")
        title.setAlignment(Qt.AlignCenter)
        
        # 副标题
        subtitle = QLabel("Aurora 量化系统智能助手")
        subtitle.setFont(QFont("Microsoft YaHei", 12))
        subtitle.setStyleSheet("color: #8B949E; background: transparent;")
        subtitle.setAlignment(Qt.AlignCenter)
        
        # 说明
        description = QLabel(
            "欢迎使用 QS Robot 智能助手\n"
            "系统将打开 Aurora 登录页面\n"
            "请使用系统账号登录"
        )
        description.setFont(QFont("Microsoft YaHei", 10))
        description.setStyleSheet("color: #E6EDF3; background: transparent;")
        description.setAlignment(Qt.AlignCenter)
        
        # 按钮区域
        button_layout = QHBoxLayout()
        button_layout.setSpacing(20)
        
        # 打开登录页面按钮
        login_btn = QPushButton("打开 Aurora 登录页面")
        login_btn.setFixedHeight(45)
        login_btn.setFont(QFont("Microsoft YaHei", 11))
        login_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00D4AA, stop:1 #0A84FF);
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px 25px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00E4BA, stop:1 #1A94FF);
            }
        """)
        login_btn.clicked.connect(self.open_login_page)
        
        # 直接进入按钮
        enter_btn = QPushButton("直接进入系统")
        enter_btn.setFixedHeight(45)
        enter_btn.setFont(QFont("Microsoft YaHei", 11))
        enter_btn.setStyleSheet("""
            QPushButton {
                background: rgba(0, 212, 170, 0.1);
                color: #00D4AA;
                border: 1px solid #00D4AA;
                border-radius: 8px;
                padding: 10px 25px;
            }
            QPushButton:hover {
                background: rgba(0, 212, 170, 0.2);
            }
        """)
        enter_btn.clicked.connect(self.open_deepseek_page)
        
        button_layout.addWidget(login_btn)
        button_layout.addWidget(enter_btn)
        
        # 提示信息
        hint = QLabel("提示：登录后将自动打开 QS Robot 聊天功能")
        hint.setFont(QFont("Microsoft YaHei", 9))
        hint.setStyleSheet("color: #8B949E; background: transparent;")
        hint.setAlignment(Qt.AlignCenter)
        
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(20)
        layout.addWidget(description)
        layout.addSpacing(20)
        layout.addLayout(button_layout)
        layout.addSpacing(15)
        layout.addWidget(hint)
        
        self.setLayout(layout)
    
    def open_login_page(self):
        """打开Aurora登录页面"""
        try:
            # 使用start命令打开浏览器
            subprocess.Popen(['start', AURORA_URL + '/login'], shell=True)
            QMessageBox.information(
                self,
                "提示",
                "Aurora 登录页面已在浏览器中打开\n请使用 admin / admin123 登录"
            )
        except Exception as e:
            QMessageBox.warning(
                self,
                "警告",
                f"无法打开浏览器: {str(e)}\n\n请手动访问:\n{AURORA_URL}/login"
            )
    
    def open_deepseek_page(self):
        """直接打开DeepSeek页面"""
        try:
            subprocess.Popen(['start', DEEPSEEK_URL], shell=True)
            QMessageBox.information(
                self,
                "提示",
                "Aurora 系统已在浏览器中打开\n请在浏览器右下角找到 QS Robot 悬浮球"
            )
            self.close()
        except Exception as e:
            QMessageBox.warning(
                self,
                "警告",
                f"无法打开浏览器: {str(e)}\n\n请手动访问:\n{DEEPSEEK_URL}"
            )

def main():
    app = QApplication(sys.argv)
    
    # 设置Fusion风格
    app.setStyle('Fusion')
    
    # 设置深色主题
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor('#0D1117'))
    palette.setColor(QPalette.WindowText, QColor('#E6EDF3'))
    palette.setColor(QPalette.Base, QColor('#161B22'))
    palette.setColor(QPalette.AlternateBase, QColor('#21262D'))
    palette.setColor(QPalette.ToolTipBase, QColor('#00D4AA'))
    palette.setColor(QPalette.ToolTipText, QColor('#FFFFFF'))
    palette.setColor(QPalette.Text, QColor('#E6EDF3'))
    palette.setColor(QPalette.Button, QColor('#21262D'))
    palette.setColor(QPalette.ButtonText, QColor('#E6EDF3'))
    palette.setColor(QPalette.BrightText, QColor('#FF0000'))
    palette.setColor(QPalette.Highlight, QColor('#00D4AA'))
    palette.setColor(QPalette.HighlightedText, QColor('#000000'))
    app.setPalette(palette)
    
    window = QSLoginWindow()
    window.show()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
