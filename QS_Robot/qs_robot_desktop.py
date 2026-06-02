#!/usr/bin/env python3
"""
QS Robot - Aurora 量化系统桌面智能助手
独立的桌面应用程序，提供系统级智能助手功能

功能特性：
- 独立运行，不依赖浏览器
- 悬浮球快捷入口（可配置位置）
- 全屏模式支持
- 系统托盘最小化
- 任务栏固定支持
- 多用户远程登录支持
- Aurora 风格界面设计
"""

import sys
import os
import json
import requests
import threading
import socket
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QPushButton, QLabel, QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect, QMenu, QAction,
    QSystemTrayIcon, QScrollArea, QFrame, QCheckBox, QDialog,
    QFormLayout, QGroupBox, QMessageBox, QSpacerItem, QSizePolicy,
    QProgressBar
)
from PyQt5.QtCore import (
    Qt, QPoint, QRect, pyqtSignal, QTimer, QObject, QSize,
    QEasingCurve, QThread, pyqtSlot, QPropertyAnimation
)
from PyQt5.QtGui import (
    QFont, QColor, QPalette, QIcon, QPainter, QBrush, QPen,
    QLinearGradient, QRadialGradient
)

# Aurora 主题颜色
AURORA_COLORS = {
    'primary': '#00D4AA',
    'secondary': '#0A84FF',
    'background': '#0D1117',
    'surface': '#161B22',
    'surface_light': '#21262D',
    'border': '#30363D',
    'text': '#E6EDF3',
    'text_secondary': '#8B949E',
    'accent': '#58A6FF',
    'success': '#3FB950',
    'warning': '#D29922',
    'error': '#F85149'
}

# 配置文件路径
CONFIG_FILE = os.path.join(os.path.expanduser('~'), '.qs_robot_config.json')


def load_config():
    """加载配置文件"""
    default_config = {
        'auto_start': False,
        'float_ball_position': 'top_right',  # top_left, top_right, bottom_left, bottom_right
        'window_geometry': {'x': 100, 'y': 100, 'width': 400, 'height': 600},
        'fullscreen': False,
        'remote_host': '127.0.0.1',
        'remote_port': 5000,
        'remember_login': False,
        'saved_credentials': {'username': '', 'password': ''}
    }
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                # 合并新配置项
                for key, value in default_config.items():
                    if key not in config:
                        config[key] = value
                return config
    except Exception:
        pass
    return default_config


def save_config(config):
    """保存配置文件"""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False


class LoginDialog(QDialog):
    """登录对话框"""
    
    login_success = pyqtSignal(str, str)
    login_canceled = pyqtSignal()
    
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("QS Robot - 用户登录")
        self.setFixedSize(380, 300)
        self.setStyleSheet(f"""
            QDialog {{
                background: {AURORA_COLORS['background']};
                border-radius: 12px;
            }}
        """)
        self.setup_ui()
    
    def setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        
        # Logo 和标题
        logo_label = QLabel("🤖")
        logo_label.setStyleSheet("""
            QLabel {
                font-size: 48px;
                text-align: center;
            }
        """)
        title_label = QLabel("QS Robot")
        title_label.setStyleSheet(f"""
            QLabel {{
                color: {AURORA_COLORS['text']};
                font-size: 24px;
                font-weight: bold;
                text-align: center;
            }}
        """)
        subtitle_label = QLabel("Aurora 量化系统智能助手")
        subtitle_label.setStyleSheet(f"""
            QLabel {{
                color: {AURORA_COLORS['text_secondary']};
                font-size: 14px;
                text-align: center;
            }}
        """)
        
        logo_layout = QVBoxLayout()
        logo_layout.addWidget(logo_label)
        logo_layout.addWidget(title_label)
        logo_layout.addWidget(subtitle_label)
        
        # 表单区域
        form_group = QGroupBox()
        form_group.setStyleSheet(f"""
            QGroupBox {{
                border: 1px solid {AURORA_COLORS['border']};
                border-radius: 8px;
                background: {AURORA_COLORS['surface']};
            }}
        """)
        form_layout = QFormLayout(form_group)
        form_layout.setContentsMargins(20, 15, 20, 15)
        form_layout.setSpacing(15)
        
        # 用户名
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("请输入用户名")
        self.username_input.setStyleSheet(f"""
            QLineEdit {{
                background: {AURORA_COLORS['surface_light']};
                border: 1px solid {AURORA_COLORS['border']};
                border-radius: 8px;
                padding: 10px;
                color: {AURORA_COLORS['text']};
                font-size: 14px;
            }}
            QLineEdit:focus {{
                border-color: {AURORA_COLORS['primary']};
            }}
        """)
        if self.config.get('remember_login') and self.config['saved_credentials']['username']:
            self.username_input.setText(self.config['saved_credentials']['username'])
        
        # 密码
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("请输入密码")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setStyleSheet(self.username_input.styleSheet())
        if self.config.get('remember_login') and self.config['saved_credentials']['password']:
            self.password_input.setText(self.config['saved_credentials']['password'])
        
        # 记住密码
        self.remember_check = QCheckBox("记住密码")
        self.remember_check.setChecked(self.config.get('remember_login', False))
        self.remember_check.setStyleSheet(f"""
            QCheckBox {{
                color: {AURORA_COLORS['text_secondary']};
                font-size: 13px;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
            }}
            QCheckBox::indicator:checked {{
                background: {AURORA_COLORS['primary']};
            }}
        """)
        
        # 远程连接选项
        self.remote_check = QCheckBox("远程连接")
        self.remote_check.setStyleSheet(self.remember_check.styleSheet())
        
        form_layout.addRow(QLabel("用户名"), self.username_input)
        form_layout.addRow(QLabel("密码"), self.password_input)
        form_layout.addRow(self.remember_check)
        form_layout.addRow(self.remote_check)
        
        # 按钮区域
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setFixedHeight(40)
        self.cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: {AURORA_COLORS['surface_light']};
                border: 1px solid {AURORA_COLORS['border']};
                border-radius: 8px;
                padding: 10px 25px;
                color: {AURORA_COLORS['text']};
                font-size: 14px;
            }}
            QPushButton:hover {{
                background: {AURORA_COLORS['border']};
            }}
        """)
        self.cancel_btn.clicked.connect(self.on_cancel)
        
        self.login_btn = QPushButton("登录")
        self.login_btn.setFixedHeight(40)
        self.login_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {AURORA_COLORS['secondary']},
                    stop:1 {AURORA_COLORS['primary']});
                border: none;
                border-radius: 8px;
                padding: 10px 30px;
                color: white;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                box-shadow: 0 4px 12px rgba(0, 212, 170, 0.4);
            }}
        """)
        self.login_btn.clicked.connect(self.on_login)
        
        button_layout.addWidget(self.cancel_btn)
        button_layout.addWidget(self.login_btn)
        
        layout.addLayout(logo_layout)
        layout.addWidget(form_group)
        layout.addLayout(button_layout)
    
    def on_login(self):
        """处理登录"""
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()
        
        if not username or not password:
            QMessageBox.warning(self, "警告", "请输入用户名和密码")
            return
        
        # 保存配置
        if self.remember_check.isChecked():
            self.config['remember_login'] = True
            self.config['saved_credentials'] = {'username': username, 'password': password}
        else:
            self.config['remember_login'] = False
            self.config['saved_credentials'] = {'username': '', 'password': ''}
        save_config(self.config)
        
        self.login_success.emit(username, password)
        self.accept()
    
    def on_cancel(self):
        """处理取消"""
        self.login_canceled.emit()
        self.reject()


class ChatMessage:
    """聊天消息"""
    def __init__(self, content, is_user=False, timestamp=None):
        self.content = content
        self.is_user = is_user
        self.timestamp = timestamp or datetime.now()


class AuroraAPIClient:
    """Aurora 系统 API 客户端"""
    
    def __init__(self, base_url='http://127.0.0.1:5000'):
        self.base_url = base_url
        self.session_id = None
        self.username = None
    
    def set_server(self, host, port):
        """设置服务器地址"""
        self.base_url = f'http://{host}:{port}'
    
    def login(self, username='admin', password='admin123'):
        """登录 Aurora 系统"""
        try:
            response = requests.post(
                f'{self.base_url}/api/auth/login',
                json={'username': username, 'password': password},
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    self.session_id = data.get('session_id')
                    self.username = username
                    return True, data.get('message', '登录成功')
            return False, '登录失败'
        except Exception as e:
            return False, f'连接错误: {str(e)}'
    
    def chat(self, message):
        """发送聊天消息"""
        try:
            response = requests.post(
                f'{self.base_url}/api/deepseek/chat',
                json={'message': message},
                timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    return True, data.get('response', ''), data.get('source', 'unknown')
            return False, '发送失败', 'error'
        except Exception as e:
            return False, f'连接错误: {str(e)}', 'error'
    
    def get_system_status(self):
        """获取系统状态"""
        return {
            'status': 'running',
            'location': '烟台',
            'network': 'connected',
            'modules': {
                'strategy_engine': 'running',
                'data_collection': 'running',
                'backtest': 'ready',
                'risk_control': 'running'
            }
        }
    
    def test_connection(self):
        """测试服务器连接"""
        try:
            response = requests.get(f'{self.base_url}/api/system/health', timeout=5)
            return response.status_code == 200
        except Exception:
            return False


class MessageBubble(QFrame):
    """消息气泡组件"""
    
    def __init__(self, message, parent=None):
        super().__init__(parent)
        self.message = message
        self.setup_ui()
    
    def setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        content_label = QLabel(self.message.content)
        content_label.setWordWrap(True)
        content_label.setTextFormat(Qt.RichText)
        content_label.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 14px;
                line-height: 1.5;
                background: transparent;
            }
        """)
        
        time_label = QLabel(self.message.timestamp.strftime('%H:%M'))
        time_label.setStyleSheet(f"""
            QLabel {{
                color: {AURORA_COLORS['text_secondary']};
                font-size: 11px;
                background: transparent;
            }}
        """)
        
        if self.message.is_user:
            content_label.setAlignment(Qt.AlignRight)
            time_label.setAlignment(Qt.AlignRight)
            bubble_style = f"""
                QFrame {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 {AURORA_COLORS['secondary']},
                        stop:1 {AURORA_COLORS['primary']});
                    border-radius: 16px;
                    padding: 10px 14px;
                    border-bottom-right-radius: 4px;
                    max-width: 300px;
                }}
            """
        else:
            content_label.setAlignment(Qt.AlignLeft)
            time_label.setAlignment(Qt.AlignLeft)
            bubble_style = f"""
                QFrame {{
                    background: {AURORA_COLORS['surface_light']};
                    border-radius: 16px;
                    padding: 10px 14px;
                    border-bottom-left-radius: 4px;
                    border: 1px solid {AURORA_COLORS['border']};
                    max-width: 350px;
                }}
            """
        
        self.setStyleSheet(bubble_style)
        layout.addWidget(content_label)
        layout.addWidget(time_label)


from qs_robot_core import QSRobotCore, AuroraSystemIntegration

class QSChatWidget(QWidget):
    """QS Robot 聊天组件"""
    
    def __init__(self, api_client, parent=None):
        super().__init__(parent)
        self.messages = []
        self.api_client = api_client
        # 使用共享的AuroraSystemIntegration
        self.robot_core = QSRobotCore(AuroraSystemIntegration())
        self.setup_ui()
    
    def setup_ui(self):
        """设置UI"""
        self.setStyleSheet(f"""
        QWidget {{
            background: {AURORA_COLORS['background']};
            border: none;
        }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 标题栏
        title_bar = QFrame()
        title_bar.setFixedHeight(50)
        title_bar.setStyleSheet(f"""
            QFrame {{
                background: {AURORA_COLORS['surface']};
                border-bottom: 1px solid {AURORA_COLORS['border']};
            }}
        """)
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(16, 0, 8, 0)
        
        avatar = QLabel("🤖")
        avatar.setStyleSheet("""
            QLabel {
                font-size: 24px;
                background: transparent;
            }
        """)
        
        title_info = QVBoxLayout()
        title_label = QLabel("QS Robot")
        title_label.setStyleSheet(f"""
            QLabel {{
                color: {AURORA_COLORS['text']};
                font-size: 16px;
                font-weight: bold;
                background: transparent;
            }}
        """)
        status_label = QLabel("量化系统智能助手")
        status_label.setStyleSheet(f"""
            QLabel {{
                color: {AURORA_COLORS['text_secondary']};
                font-size: 12px;
                background: transparent;
            }}
        """)
        title_info.addWidget(title_label)
        title_info.addWidget(status_label)
        title_info.addStretch()
        
        # 快捷按钮
        quick_layout = QHBoxLayout()
        quick_layout.setSpacing(8)
        quick_buttons = [
            ("系统状态", "status"),
            ("策略列表", "strategy"),
            ("优化策略", "optimize"),
            ("健康检查", "health")
        ]
        for text, action in quick_buttons:
            btn = QPushButton(text)
            btn.setFixedSize(70, 28)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: rgba(0, 212, 170, 0.1);
                    border: 1px solid rgba(0, 212, 170, 0.3);
                    border-radius: 14px;
                    color: {AURORA_COLORS['primary']};
                    font-size: 11px;
                }}
                QPushButton:hover {{
                    background: rgba(0, 212, 170, 0.2);
                }}
            """)
            btn.clicked.connect(lambda checked, a=action: self.handle_quick_action(a))
            quick_layout.addWidget(btn)
        
        title_layout.addWidget(avatar)
        title_layout.addLayout(title_info)
        title_layout.addStretch()
        title_layout.addLayout(quick_layout)
        
        # 聊天区域
        self.chat_area = QScrollArea()
        self.chat_area.setWidgetResizable(True)
        self.chat_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.chat_area.setStyleSheet(f"""
            QScrollArea {{
                background: {AURORA_COLORS['background']};
                border: none;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 6px;
            }}
            QScrollBar::handle:vertical {{
                background: {AURORA_COLORS['border']};
                border-radius: 3px;
            }}
        """)
        
        self.chat_container = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setContentsMargins(16, 16, 16, 16)
        self.chat_layout.setSpacing(12)
        self.chat_layout.addStretch()
        
        self.chat_area.setWidget(self.chat_container)
        
        # 输入区域
        input_frame = QFrame()
        input_frame.setStyleSheet(f"""
            QFrame {{
                background: {AURORA_COLORS['surface']};
                border-top: 1px solid {AURORA_COLORS['border']};
            }}
        """)
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(12, 12, 12, 12)
        input_layout.setSpacing(8)
        
        self.voice_btn = QPushButton("🎤")
        self.voice_btn.setFixedSize(40, 40)
        self.voice_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                font-size: 20px;
            }}
        """)
        
        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("输入问题或指令...")
        self.input_box.setStyleSheet(f"""
            QLineEdit {{
                background: {AURORA_COLORS['surface_light']};
                border: 1px solid {AURORA_COLORS['border']};
                border-radius: 20px;
                padding: 10px 16px;
                color: {AURORA_COLORS['text']};
                font-size: 14px;
            }}
            QLineEdit:focus {{
                border-color: {AURORA_COLORS['primary']};
                background: {AURORA_COLORS['surface']};
            }}
        """)
        self.input_box.setFixedHeight(40)
        self.input_box.returnPressed.connect(self.send_message)
        
        self.send_btn = QPushButton("发送")
        self.send_btn.setFixedSize(60, 40)
        self.send_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {AURORA_COLORS['secondary']},
                    stop:1 {AURORA_COLORS['primary']});
                border: none;
                border-radius: 20px;
                padding: 10px 20px;
                color: white;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                box-shadow: 0 4px 12px rgba(0, 212, 170, 0.4);
            }}
        """)
        self.send_btn.clicked.connect(self.send_message)
        
        self.tts_btn = QPushButton("🔊")
        self.tts_btn.setFixedSize(40, 40)
        self.tts_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                font-size: 20px;
            }}
        """)
        
        input_layout.addWidget(self.voice_btn)
        input_layout.addWidget(self.input_box)
        input_layout.addWidget(self.send_btn)
        input_layout.addWidget(self.tts_btn)
        
        layout.addWidget(title_bar)
        layout.addWidget(self.chat_area, 1)
        layout.addWidget(input_frame)
        
        # 添加欢迎消息
        self.add_welcome_message()
    
    def add_welcome_message(self):
        """添加欢迎消息"""
        welcome = ChatMessage(
            """👋 您好！我是 QS Robot，您的 Aurora 量化系统智能助手。

我可以帮您：
• 查询系统状态与策略信息
• 优化策略参数
• 运行回测与分析
• 风控监控与预警

💡 快捷命令：
• <b>系统状态</b> - 查看系统运行状态
• <b>策略列表</b> - 列出所有可用策略
• <b>优化策略</b> - 优化策略参数
• <b>健康检查</b> - 系统健康检查

请问有什么可以帮您的？""",
            is_user=False
        )
        self.add_message(welcome)
    
    def add_message(self, message):
        """添加消息"""
        self.messages.append(message)
        bubble = MessageBubble(message)
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, bubble)
        QTimer.singleShot(100, self.scroll_to_bottom)
    
    def scroll_to_bottom(self):
        """滚动到底部"""
        self.chat_area.verticalScrollBar().setValue(
            self.chat_area.verticalScrollBar().maximum()
        )
    
    def send_message(self):
        """发送消息"""
        text = self.input_box.text().strip()
        if not text:
            return
        
        user_msg = ChatMessage(text, is_user=True)
        self.add_message(user_msg)
        self.input_box.clear()
        
        threading.Thread(target=self._fetch_response, args=(text,), daemon=True).start()
    
    def _fetch_response(self, message):
        """获取响应 - 先尝试系统命令，再回退到LLM"""
        # 先尝试处理系统命令
        try:
            response = self.robot_core.process_command(message)
            if response:
                response_msg = ChatMessage(response, is_user=False)
                QTimer.singleShot(100, lambda: self.add_message(response_msg))
                return
        except Exception as e:
            pass
        
        # 回退到LLM聊天
        success, response, source = self.api_client.chat(message)
        
        if success:
            response_msg = ChatMessage(response, is_user=False)
        else:
            response_msg = ChatMessage(
                f"抱歉，{response}\n\n请检查 Aurora 系统是否运行。",
                is_user=False
            )
        
        QTimer.singleShot(100, lambda: self.add_message(response_msg))
    
    def handle_quick_action(self, action):
        """处理快捷操作"""
        commands = {
            'status': '系统状态',
            'strategy': '策略列表',
            'optimize': '优化策略',
            'health': '健康检查'
        }
        if action in commands:
            self.input_box.setText(commands[action])
            self.send_message()


class QSFloatBall(QWidget):
    """QS Robot 悬浮球"""
    
    clicked = pyqtSignal()
    mouse_moved = pyqtSignal(QPoint)
    
    def __init__(self, position='top_right', parent=None):
        super().__init__(parent)
        self.position = position
        self.is_expanded = False
        self.dragging = False
        self.drag_position = QPoint()
        self.setup_ui()
        self.start_pulse_animation()
    
    def setup_ui(self):
        """设置UI"""
        self.setFixedSize(60, 60)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # 根据配置设置位置
        screen = QApplication.desktop().screenGeometry()
        if self.position == 'top_right':
            self.move(screen.width() - 80, 20)
        elif self.position == 'top_left':
            self.move(20, 20)
        elif self.position == 'bottom_right':
            self.move(screen.width() - 80, screen.height() - 100)
        elif self.position == 'bottom_left':
            self.move(20, screen.height() - 100)
    
    def paintEvent(self, event):
        """绘制悬浮球"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        gradient = QRadialGradient(
            self.width() / 2, self.height() / 2, 30,
            self.width() / 2, self.height() / 2
        )
        gradient.setColorAt(0, QColor('#0A84FF'))
        gradient.setColorAt(1, QColor('#00D4AA'))
        
        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(self.rect())
        
        painter.setPen(QPen(QColor('white'), 2))
        font = QFont("Segoe UI Emoji", 28)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignCenter, "🤖")
    
    def mousePressEvent(self, event):
        """鼠标按下"""
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()
    
    def mouseMoveEvent(self, event):
        """鼠标移动"""
        if event.buttons() == Qt.LeftButton and self.dragging:
            new_pos = event.globalPos() - self.drag_position
            self.move(new_pos)
            self.mouse_moved.emit(self.pos())
            event.accept()
    
    def mouseReleaseEvent(self, event):
        """鼠标释放"""
        if event.button() == Qt.LeftButton:
            if not self.dragging:
                self.clicked.emit()
            self.dragging = False
    
    def start_pulse_animation(self):
        """启动脉冲动画"""
        self.opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity)
        
        self.animation = QPropertyAnimation(self.opacity, b"opacity")
        self.animation.setDuration(1500)
        self.animation.setStartValue(1.0)
        self.animation.setEndValue(0.6)
        self.animation.setEasingCurve(QEasingCurve.InOutQuad)
        self.animation.setLoopCount(-1)
        self.animation.setDirection(QPropertyAnimation.Alternate)
        self.animation.start()


class QSMainWindow(QWidget):
    """QS Robot 主窗口"""
    
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.float_ball = None
        self.tray = None
        self.is_visible = False
        self.is_fullscreen = False
        self.api_client = AuroraAPIClient()
        self.setup_ui()
        self.setup_tray()
        self.hide()
    
    def setup_ui(self):
        """设置UI"""
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # 从配置恢复窗口位置和大小
        geom = self.config.get('window_geometry', {'x': 100, 'y': 100, 'width': 400, 'height': 600})
        self.resize(geom['width'], geom['height'])
        self.move(geom['x'], geom['y'])
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        shadow_layout = QVBoxLayout()
        shadow_layout.setContentsMargins(15, 15, 15, 15)
        
        content_frame = QFrame()
        content_frame.setStyleSheet(f"""
            QFrame {{
                background: {AURORA_COLORS['background']};
                border-radius: 12px;
                border: 1px solid {AURORA_COLORS['border']};
            }}
        """)
        
        shadow = QGraphicsDropShadowEffect(content_frame)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 100))
        shadow.setOffset(0, 4)
        content_frame.setGraphicsEffect(shadow)
        
        content_layout = QVBoxLayout(content_frame)
        content_layout.setContentsMargins(0, 0, 0, 0)
        
        title_bar = self.create_title_bar()
        content_layout.addWidget(title_bar)
        
        self.chat_widget = QSChatWidget(self.api_client)
        content_layout.addWidget(self.chat_widget, 1)
        
        shadow_layout.addWidget(content_frame)
        layout.addLayout(shadow_layout)
    
    def create_title_bar(self):
        """创建标题栏"""
        title_bar = QFrame()
        title_bar.setFixedHeight(40)
        title_bar.setStyleSheet(f"""
            QFrame {{
                background: {AURORA_COLORS['surface']};
                border-radius: 12px 12px 0 0;
                border-bottom: 1px solid {AURORA_COLORS['border']};
            }}
        """)
        
        layout = QHBoxLayout(title_bar)
        layout.setContentsMargins(16, 0, 8, 0)
        
        title = QLabel("QS Robot - Aurora 智能助手")
        title.setStyleSheet(f"""
            QLabel {{
                color: {AURORA_COLORS['text']};
                font-size: 14px;
                font-weight: bold;
                background: transparent;
            }}
        """)
        
        layout.addWidget(title)
        layout.addStretch()
        
        # 全屏按钮
        fullscreen_btn = QPushButton("⛶")
        fullscreen_btn.setFixedSize(30, 30)
        fullscreen_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: {AURORA_COLORS['text_secondary']};
                font-size: 14px;
            }}
            QPushButton:hover {{
                color: {AURORA_COLORS['text']};
            }}
        """)
        fullscreen_btn.clicked.connect(self.toggle_fullscreen)
        
        # 最小化按钮
        minimize_btn = QPushButton("─")
        minimize_btn.setFixedSize(30, 30)
        minimize_btn.setStyleSheet(fullscreen_btn.styleSheet())
        minimize_btn.clicked.connect(self.hide_window)
        
        # 关闭按钮
        close_btn = QPushButton("×")
        close_btn.setFixedSize(30, 30)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: {AURORA_COLORS['text_secondary']};
                font-size: 20px;
            }}
            QPushButton:hover {{
                color: {AURORA_COLORS['error']};
            }}
        """)
        close_btn.clicked.connect(self.hide_window)
        
        layout.addWidget(fullscreen_btn)
        layout.addWidget(minimize_btn)
        layout.addWidget(close_btn)
        
        return title_bar
    
    def setup_tray(self):
        """设置系统托盘"""
        self.tray = QSystemTrayIcon(self)
        
        # 创建托盘图标 (使用绘制的图标)
        from PyQt5.QtGui import QPixmap, QPainter, QFont
        icon_pixmap = QPixmap(32, 32)
        icon_pixmap.fill(Qt.transparent)
        painter = QPainter(icon_pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 绘制渐变圆形
        gradient = QRadialGradient(16, 16, 14, 16, 16)
        gradient.setColorAt(0, QColor('#0A84FF'))
        gradient.setColorAt(1, QColor('#00D4AA'))
        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(0, 0, 32, 32)
        
        # 绘制机器人文字
        painter.setPen(QPen(QColor('white'), 2))
        eye_font = QFont("Segoe UI", 12, QFont.Bold)
        painter.setFont(eye_font)
        painter.drawText(icon_pixmap.rect(), Qt.AlignCenter, "Q")
        painter.end()
        
        tray_icon = QIcon(icon_pixmap)
        self.tray.setIcon(tray_icon)
        
        menu = QMenu()
        
        show_action = QAction("显示主界面", self)
        show_action.triggered.connect(self.show_window)
        menu.addAction(show_action)
        
        fullscreen_action = QAction("全屏模式", self)
        fullscreen_action.triggered.connect(self.toggle_fullscreen)
        menu.addAction(fullscreen_action)
        
        menu.addSeparator()
        
        status_action = QAction("系统状态", self)
        status_action.triggered.connect(self.show_status)
        menu.addAction(status_action)
        
        menu.addSeparator()
        
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self.quit_app)
        menu.addAction(quit_action)
        
        self.tray.setContextMenu(menu)
        self.tray.setToolTip("QS Robot - Aurora 量化系统智能助手")
        self.tray.activated.connect(self.on_tray_activated)
        self.tray.show()
    
    def on_tray_activated(self, reason):
        """托盘图标被激活"""
        if reason == QSystemTrayIcon.Trigger:
            self.toggle_window()
    
    def toggle_window(self):
        """切换窗口显示"""
        if self.is_visible:
            self.hide_window()
        else:
            self.show_window()
    
    def show_window(self):
        """显示窗口"""
        self.show()
        self.is_visible = True
        self.activateWindow()
        self.raise_()
    
    def hide_window(self):
        """隐藏窗口"""
        self.save_window_geometry()
        self.hide()
        self.is_visible = False
    
    def toggle_fullscreen(self):
        """切换全屏模式"""
        if self.is_fullscreen:
            self.showNormal()
            self.setStyleSheet("")
            self.is_fullscreen = False
        else:
            self.showFullScreen()
            self.setStyleSheet(f"""
                QWidget {{
                    background: {AURORA_COLORS['background']};
                }}
            """)
            self.is_fullscreen = True
    
    def save_window_geometry(self):
        """保存窗口位置和大小"""
        geom = {
            'x': self.pos().x(),
            'y': self.pos().y(),
            'width': self.width(),
            'height': self.height()
        }
        self.config['window_geometry'] = geom
        save_config(self.config)
    
    def show_status(self):
        """显示状态"""
        self.tray.showMessage(
            "QS Robot",
            "Aurora 量化系统运行正常",
            QSystemTrayIcon.Information,
            3000
        )
    
    def quit_app(self):
        """退出应用"""
        self.save_window_geometry()
        QApplication.quit()
    
    def mousePressEvent(self, event):
        """鼠标按下事件"""
        if event.button() == Qt.LeftButton:
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()
    
    def mouseMoveEvent(self, event):
        """鼠标移动事件"""
        if event.buttons() == Qt.LeftButton:
            self.move(event.globalPos() - self.drag_position)
            event.accept()
    
    def closeEvent(self, event):
        """关闭事件"""
        event.ignore()
        self.hide_window()
    
    def set_api_client(self, client):
        """设置API客户端"""
        self.api_client = client
        self.chat_widget.api_client = client


class QSApplication:
    """QS Robot 应用程序"""
    
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        
        # 加载配置
        self.config = load_config()
        
        # 设置应用程序
        self.setup_application()
        
        # 创建登录对话框
        self.login_dialog = LoginDialog(self.config)
        self.login_dialog.login_success.connect(self.on_login_success)
        self.login_dialog.login_canceled.connect(self.on_login_canceled)
        
        # 显示登录对话框
        if self.login_dialog.exec_() != QDialog.Accepted:
            sys.exit(0)
        
        # 创建主窗口和悬浮球
        self.main_window = QSMainWindow(self.config)
        self.create_float_ball()
    
    def setup_application(self):
        """设置应用程序"""
        self.app.setApplicationName("QS Robot")
        self.app.setApplicationVersion("1.0.0")
        self.app.setOrganizationName("Aurora")
        
        self.app.setStyle('Fusion')
        
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(AURORA_COLORS['background']))
        palette.setColor(QPalette.WindowText, QColor(AURORA_COLORS['text']))
        self.app.setPalette(palette)
    
    def create_float_ball(self):
        """创建悬浮球"""
        position = self.config.get('float_ball_position', 'top_right')
        self.float_ball = QSFloatBall(position)
        self.float_ball.clicked.connect(self.main_window.toggle_window)
        self.float_ball.mouse_moved.connect(self.on_float_ball_moved)
        self.float_ball.show()
    
    def on_login_success(self, username, password):
        """登录成功"""
        # 测试连接
        server_host = self.config.get('remote_host', '127.0.0.1')
        server_port = self.config.get('remote_port', 5000)
        
        # 设置API客户端
        self.main_window.api_client.set_server(server_host, server_port)
        success, message = self.main_window.api_client.login(username, password)
        
        # 同时设置机器人核心的服务器地址
        self.main_window.chat_widget.robot_core.set_server(server_host, server_port)
        
        if not success:
            QMessageBox.warning(None, "登录失败", message)
            sys.exit(1)
    
    def on_login_canceled(self):
        """登录取消"""
        sys.exit(0)
    
    def on_float_ball_moved(self, pos):
        """悬浮球位置变化"""
        screen = QApplication.desktop().screenGeometry()
        x, y = pos.x(), pos.y()
        
        if x < screen.width() / 2:
            if y < screen.height() / 2:
                self.config['float_ball_position'] = 'top_left'
            else:
                self.config['float_ball_position'] = 'bottom_left'
        else:
            if y < screen.height() / 2:
                self.config['float_ball_position'] = 'top_right'
            else:
                self.config['float_ball_position'] = 'bottom_right'
        save_config(self.config)
    
    def run(self):
        """运行应用程序"""
        sys.exit(self.app.exec_())


def main():
    """主函数"""
    qs_app = QSApplication()
    qs_app.run()


if __name__ == '__main__':
    main()
