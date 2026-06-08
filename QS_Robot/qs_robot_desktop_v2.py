#!/usr/bin/env python3
"""
QS Robot 桌面应用 V2.0 - 策略管理平台升级版
=============================================
整合 Aurora DeepSeek 引擎 + QS Robot 本地智能体。

新特性（V2.0 vs V1.0）：
  ✅ 双核统一：Aurora在线→双核联动；Aurora离线→模拟降级
  ✅ 完整策略管理：列表/启动/停止/回测/优化/对比
  ✅ 系统健康仪表盘：CPU/内存/磁盘/Aurora状态实时显示
  ✅ 5大增益模块状态监控
  ✅ 系统托盘悬浮球（一键唤出/最小化）
  ✅ 实时交易信号通知
  ✅ 策略历史对比图表

启动方式:
  1. 双击 启动QS机器人.bat
  2. python qs_robot_desktop_v2.py
  3. 在V1.0桌面版中 import qs_robot_desktop_v2 升级
"""

import sys
import os
import json
import time
import threading
import traceback
from datetime import datetime
from typing import Dict, List, Optional, Any

# ============================================================
# Windows控制台UTF-8编码补丁 (解决'gbk' codec无法编码emoji的问题)
# ============================================================
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 添加QS Robot路径
QS_ROBOT_PATH = os.path.dirname(os.path.abspath(__file__))
if QS_ROBOT_PATH not in sys.path:
    sys.path.insert(0, QS_ROBOT_PATH)

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, font
import requests

# ---- 导入增强型策略管理器 ----
try:
    from core.enhanced_strategy_manager import (
        EnhancedStrategyManager, get_strategy_manager,
        SystemMode, StrategyStatus, BacktestResult, SystemHealth
    )
    STRATEGY_MANAGER_AVAILABLE = True
except ImportError:
    STRATEGY_MANAGER_AVAILABLE = False
    print("[WARNING] enhanced_strategy_manager 不可用，使用基础模式")


# ============================================================
# 系统托盘悬浮球 (TrayBall)
# ============================================================

class TrayBall:
    """系统托盘悬浮球 - 最小化后显示状态"""

    def __init__(self, parent):
        self.parent = parent
        self.window = None
        self._running = False
        self._update_thread = None

    def show(self):
        """显示悬浮球"""
        if self.window:
            return

        self.window = tk.Toplevel(self.parent)
        self.window.title("QS Robot")
        self.window.geometry("80x80+{}+{}".format(
            self.parent.winfo_screenwidth() - 100,
            self.parent.winfo_screenheight() - 120
        ))
        self.window.overrideredirect(True)
        self.window.attributes('-topmost', True)
        self.window.attributes('-alpha', 0.85)
        self.window.configure(bg='#1a1a2e')

        # 状态圆点
        self.canvas = tk.Canvas(self.window, width=80, height=80,
                                bg='#1a1a2e', highlightthickness=0)
        self.canvas.pack()
        self.ball = self.canvas.create_oval(10, 10, 70, 70,
                                            fill='#00ff88', outline='#00cc66', width=2)
        self.text = self.canvas.create_text(40, 40, text="QS", fill='#1a1a2e',
                                            font=('Arial', 14, 'bold'))

        # 双击还原
        self.canvas.bind('<Double-Button-1>', self._on_double_click)
        self.canvas.bind('<Button-1>', self._start_move)
        self.canvas.bind('<B1-Motion>', self._on_move)

        self._running = True
        self._update_thread = threading.Thread(target=self._update_status, daemon=True)
        self._update_thread.start()

    def hide(self):
        """隐藏悬浮球"""
        self._running = False
        if self.window:
            self.window.destroy()
            self.window = None

    def _update_status(self):
        """更新悬浮球状态（根据Aurora连接状态变色）"""
        colors = {
            'aurora_live': '#00ff88',    # 绿色 - 双核联动
            'fallback': '#ffaa00',        # 橙色 - 模拟降级
            'standalone': '#ff4444'       # 红色 - 独立模式
        }
        while self._running:
            try:
                if hasattr(self.parent, 'strategy_mgr') and self.parent.strategy_mgr:
                    mode = self.parent.strategy_mgr.get_mode().value
                    color = colors.get(mode, '#ff4444')
                    self.canvas.itemconfig(self.ball, fill=color)
                    self.canvas.itemconfig(self.text, text=mode[:2].upper())
            except Exception:
                pass
            time.sleep(5)

    def _on_double_click(self, event):
        """双击还原主窗口"""
        self.parent.deiconify()
        self.parent.lift()
        self.parent.focus_force()

    def _start_move(self, event):
        self._x = event.x
        self._y = event.y

    def _on_move(self, event):
        deltax = event.x - self._x
        deltay = event.y - self._y
        x = self.window.winfo_x() + deltax
        y = self.window.winfo_y() + deltay
        self.window.geometry(f"+{x}+{y}")


# ============================================================
# 主应用窗口
# ============================================================

class QSRobotDesktopV2:
    """QS Robot 桌面应用 V2.0 主窗口"""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("QS Robot V2.0 - 量化策略管理平台")
        self.root.geometry("1200x800")
        self.root.minsize(900, 600)

        # 样式
        self._setup_style()

        # 策略管理器
        self.strategy_mgr = None
        if STRATEGY_MANAGER_AVAILABLE:
            self.strategy_mgr = get_strategy_manager()
        else:
            print("[WARNING] 策略管理器不可用")

        # 韬定律优化状态缓存：{strategy_name: "最佳评分/状态"}
        self._tau_cache = {}

        # 悬浮球
        self.tray_ball = TrayBall(self.root)

        # 状态变量
        self._status_var = tk.StringVar(value="就绪")
        self._mode_var = tk.StringVar(value="检测中...")
        self._aurora_var = tk.StringVar(value="检测中...")
        self._cpu_var = tk.StringVar(value="--")
        self._mem_var = tk.StringVar(value="--")
        self._disk_var = tk.StringVar(value="--")
        self._strategy_count_var = tk.StringVar(value="--")
        self._active_count_var = tk.StringVar(value="0")
        self._backtest_count_var = tk.StringVar(value="0")
        self._auto_refresh = tk.BooleanVar(value=True)

        # 构建UI
        self._build_ui()

        # 启动后台线程
        self._running = True
        self._refresh_thread = threading.Thread(target=self._auto_refresh_loop, daemon=True)
        self._refresh_thread.start()

        # 窗口关闭时最小化到托盘
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # 初始化刷新
        self._refresh_all()

    # ---- 样式设置 ----

    def _setup_style(self):
        """配置ttk样式（深色主题）"""
        style = ttk.Style()
        style.theme_use('clam')

        bg = '#1a1a2e'
        fg = '#e0e0e0'
        accent = '#00d4ff'
        accent2 = '#00ff88'
        warning = '#ffaa00'
        danger = '#ff4444'

        style.configure('TFrame', background=bg)
        style.configure('TLabel', background=bg, foreground=fg, font=('Microsoft YaHei', 10))
        style.configure('TButton', background='#16213e', foreground=fg,
                        font=('Microsoft YaHei', 10), padding=6)
        style.map('TButton', background=[('active', '#0f3460')])
        style.configure('Accent.TButton', background=accent, foreground='#1a1a2e',
                        font=('Microsoft YaHei', 10, 'bold'), padding=8)
        style.configure('Green.TButton', background='#00cc66', foreground='#1a1a2e',
                        font=('Microsoft YaHei', 10, 'bold'), padding=8)
        style.configure('Red.TButton', background=danger, foreground='white',
                        font=('Microsoft YaHei', 10, 'bold'), padding=8)
        style.configure('TNotebook', background=bg, borderwidth=0)
        style.configure('TNotebook.Tab', background='#16213e', foreground=fg,
                        padding=[15, 8], font=('Microsoft YaHei', 10))
        style.map('TNotebook.Tab', background=[('selected', '#0f3460')])
        style.configure('Treeview', background='#16213e', foreground=fg,
                        fieldbackground='#16213e', font=('Microsoft YaHei', 9))
        style.configure('Treeview.Heading', background='#0f3460', foreground=fg,
                        font=('Microsoft YaHei', 9, 'bold'))
        style.configure('TProgressbar', thickness=8)

        self.root.configure(bg=bg)

    # ---- UI构建 ----

    def _build_ui(self):
        """构建完整UI"""
        # 顶部状态栏
        self._build_status_bar()

        # 主内容区（Notebook标签页）
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill='both', expand=True, padx=5, pady=5)

        # 标签1: 仪表盘
        self._build_dashboard_tab(notebook)

        # 标签2: 策略管理
        self._build_strategy_tab(notebook)

        # 标签3: 回测中心
        self._build_backtest_tab(notebook)

        # 标签4: 优化器
        self._build_optimizer_tab(notebook)

        # 标签5: 技术分析
        self._build_technical_analysis_tab(notebook)

        # 标签6: 股票池
        self._build_stock_pool_tab(notebook)

        # 标签7: 系统监控
        self._build_monitor_tab(notebook)

        # 标签8: Cline智能体
        self._build_cline_agent_tab(notebook)

        # 底部操作栏
        self._build_action_bar()

    def _build_status_bar(self):
        """顶部状态栏"""
        frame = ttk.Frame(self.root)
        frame.pack(fill='x', padx=5, pady=(5, 0))

        # 模式指示器
        mode_frame = ttk.Frame(frame)
        mode_frame.pack(side='left', padx=5)

        self._mode_indicator = tk.Canvas(mode_frame, width=12, height=12,
                                         bg='#1a1a2e', highlightthickness=0)
        self._mode_indicator.pack(side='left', padx=(0, 5))
        self._mode_dot = self._mode_indicator.create_oval(1, 1, 11, 11, fill='#888888')

        ttk.Label(mode_frame, textvariable=self._mode_var, font=('Microsoft YaHei', 10, 'bold')).pack(side='left')
        ttk.Label(mode_frame, text=" | Aurora:", font=('Microsoft YaHei', 9)).pack(side='left', padx=(10, 2))
        ttk.Label(mode_frame, textvariable=self._aurora_var,
                  font=('Microsoft YaHei', 10, 'bold')).pack(side='left')

        # CPU/内存/磁盘
        ttk.Label(frame, text="CPU:", font=('Microsoft YaHei', 9)).pack(side='left', padx=(20, 2))
        ttk.Label(frame, textvariable=self._cpu_var, font=('Microsoft YaHei', 9, 'bold'),
                  foreground='#00d4ff').pack(side='left')
        ttk.Label(frame, text="MEM:", font=('Microsoft YaHei', 9)).pack(side='left', padx=(10, 2))
        ttk.Label(frame, textvariable=self._mem_var, font=('Microsoft YaHei', 9, 'bold'),
                  foreground='#00ff88').pack(side='left')
        ttk.Label(frame, text="DISK:", font=('Microsoft YaHei', 9)).pack(side='left', padx=(10, 2))
        ttk.Label(frame, textvariable=self._disk_var, font=('Microsoft YaHei', 9, 'bold'),
                  foreground='#ffaa00').pack(side='left')

        # 状态文字
        ttk.Label(frame, textvariable=self._status_var,
                  font=('Microsoft YaHei', 9)).pack(side='right', padx=10)

    def _build_dashboard_tab(self, notebook):
        """仪表盘标签页"""
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="📊 仪表盘")

        # 左右分栏
        left = ttk.Frame(tab)
        left.pack(side='left', fill='both', expand=True, padx=5, pady=5)
        right = ttk.Frame(tab)
        right.pack(side='right', fill='both', expand=True, padx=5, pady=5)

        # 左侧：策略概览
        ttk.Label(left, text="策略概览", font=('Microsoft YaHei', 12, 'bold')).pack(anchor='w', pady=(0, 10))

        cards = ttk.Frame(left)
        cards.pack(fill='x')

        for label, var, color in [
            ("可用策略", self._strategy_count_var, '#00d4ff'),
            ("活跃策略", self._active_count_var, '#00ff88'),
            ("回测记录", self._backtest_count_var, '#ffaa00'),
        ]:
            card = tk.Frame(cards, bg='#16213e', width=160, height=80)
            card.pack(side='left', padx=5, pady=5, fill='x', expand=True)
            card.pack_propagate(False)
            tk.Label(card, text=label, bg='#16213e', fg='#888888',
                     font=('Microsoft YaHei', 9)).pack(pady=(10, 0))
            tk.Label(card, textvariable=var, bg='#16213e', fg=color,
                     font=('Arial', 24, 'bold')).pack()

        # 快操作
        ttk.Label(left, text="快捷操作", font=('Microsoft YaHei', 12, 'bold')).pack(anchor='w', pady=(15, 5))
        ops_frame = ttk.Frame(left)
        ops_frame.pack(fill='x')
        ttk.Button(ops_frame, text="🔄 刷新全部", command=self._refresh_all).pack(side='left', padx=5)
        ttk.Button(ops_frame, text="📊 批量回测TOP5", command=self._quick_backtest).pack(side='left', padx=5)
        ttk.Button(ops_frame, text="📋 导出状态", command=self._export_status).pack(side='left', padx=5)

        # 右侧：日志
        ttk.Label(right, text="实时日志", font=('Microsoft YaHei', 12, 'bold')).pack(anchor='w', pady=(0, 10))
        self._log_text = scrolledtext.ScrolledText(
            right, height=20, bg='#0f0f1a', fg='#00ff88',
            font=('Consolas', 9), wrap='word', state='disabled'
        )
        self._log_text.pack(fill='both', expand=True)

    def _build_strategy_tab(self, notebook):
        """策略管理标签页"""
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="📈 策略管理")

        # 工具栏
        toolbar = ttk.Frame(tab)
        toolbar.pack(fill='x', padx=5, pady=5)
        ttk.Button(toolbar, text="🔄 刷新列表", command=self._refresh_strategies).pack(side='left', padx=2)
        ttk.Button(toolbar, text="▶ 启动选中", command=self._start_selected, style='Green.TButton').pack(side='left', padx=5)
        ttk.Button(toolbar, text="⏹ 停止全部", command=self._stop_all, style='Red.TButton').pack(side='left', padx=2)
        ttk.Separator(toolbar, orient='vertical').pack(side='left', fill='y', padx=5)
        ttk.Button(toolbar, text="🔬 韬定律优化",
                   command=self._tau_optimize_selected, style='Accent.TButton').pack(side='left', padx=2)
        ttk.Button(toolbar, text="🔬 批量韬定律优化",
                   command=self._tau_optimize_batch).pack(side='left', padx=2)
        ttk.Label(toolbar, text="双击行查看详情 | 韬定律按钮针对选中策略执行", font=('Microsoft YaHei', 9),
                  foreground='#888888').pack(side='right', padx=10)

        # 策略列表
        columns = ('name', 'category', 'label', 'status', 'tau')
        self._strategy_tree = ttk.Treeview(tab, columns=columns, show='headings', height=15)
        self._strategy_tree.heading('name', text='策略名称')
        self._strategy_tree.heading('category', text='分类')
        self._strategy_tree.heading('label', text='标签')
        self._strategy_tree.heading('status', text='状态')
        self._strategy_tree.heading('tau', text='韬定律优化')
        self._strategy_tree.column('name', width=250)
        self._strategy_tree.column('category', width=80)
        self._strategy_tree.column('label', width=180)
        self._strategy_tree.column('status', width=80)
        self._strategy_tree.column('tau', width=120)
        self._strategy_tree.pack(fill='both', expand=True, padx=5)

        self._strategy_tree.bind('<Double-1>', self._on_strategy_double_click)

        # 详情面板
        detail_frame = ttk.Frame(tab)
        detail_frame.pack(fill='x', padx=5, pady=5)

        ttk.Label(detail_frame, text="选中策略:", font=('Microsoft YaHei', 9, 'bold')).grid(row=0, column=0, sticky='w')
        self._detail_name = tk.StringVar(value="--")
        ttk.Label(detail_frame, textvariable=self._detail_name,
                  font=('Microsoft YaHei', 10)).grid(row=0, column=1, sticky='w', padx=10)

        ttk.Label(detail_frame, text="分类:", font=('Microsoft YaHei', 9)).grid(row=1, column=0, sticky='w')
        self._detail_cat = tk.StringVar(value="--")
        ttk.Label(detail_frame, textvariable=self._detail_cat).grid(row=1, column=1, sticky='w', padx=10)

        ttk.Label(detail_frame, text="描述:", font=('Microsoft YaHei', 9)).grid(row=2, column=0, sticky='w')
        self._detail_desc = tk.StringVar(value="--")
        ttk.Label(detail_frame, textvariable=self._detail_desc,
                  font=('Microsoft YaHei', 9), foreground='#888888').grid(row=2, column=1, sticky='w', padx=10)

    def _build_backtest_tab(self, notebook):
        """回测中心标签页（增强版）"""
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="🧪 回测中心")

        # 回测结果存储
        self._last_backtest_result = None

        # 控制面板
        ctrl = ttk.Frame(tab)
        ctrl.pack(fill='x', padx=5, pady=5)

        ttk.Label(ctrl, text="策略:").pack(side='left', padx=(0, 5))
        self._bt_strategy = ttk.Combobox(ctrl, width=25, state='readonly')
        self._bt_strategy.pack(side='left', padx=5)

        ttk.Label(ctrl, text="天数:").pack(side='left', padx=(10, 5))
        self._bt_days = ttk.Spinbox(ctrl, from_=7, to=365, width=5)
        self._bt_days.set(30)
        self._bt_days.pack(side='left', padx=5)

        ttk.Label(ctrl, text="初始资金:").pack(side='left', padx=(10, 5))
        self._bt_balance = ttk.Entry(ctrl, width=12)
        self._bt_balance.insert(0, '100000')
        self._bt_balance.pack(side='left', padx=5)

        ttk.Button(ctrl, text="🚀 开始回测", command=self._run_backtest,
                   style='Accent.TButton').pack(side='left', padx=10)
        ttk.Button(ctrl, text="📊 对比TOP3", command=self._compare_top3).pack(side='left', padx=5)
        ttk.Button(ctrl, text="📈 查看详情", command=self._show_backtest_details,
                   state='disabled').pack(side='left', padx=5)
        self._bt_detail_btn = ctrl.winfo_children()[-1]

        # 主内容区（上下分栏）
        top_frame = ttk.Frame(tab)
        top_frame.pack(fill='both', expand=True, padx=5, pady=5)
        bottom_frame = ttk.Frame(tab)
        bottom_frame.pack(fill='both', expand=True, padx=5, pady=5)

        # 上部分：结果列表 + 绩效指标
        left_top = ttk.Frame(top_frame)
        left_top.pack(side='left', fill='both', expand=True, padx=5)
        right_top = ttk.Frame(top_frame)
        right_top.pack(side='right', fill='both', expand=True, padx=5)

        # 结果列表
        columns = ('strategy', 'return', 'sharpe', 'drawdown', 'winrate', 'trades')
        self._bt_tree = ttk.Treeview(left_top, columns=columns, show='headings', height=12)
        self._bt_tree.heading('strategy', text='策略')
        self._bt_tree.heading('return', text='收益%')
        self._bt_tree.heading('sharpe', text='夏普')
        self._bt_tree.heading('drawdown', text='回撤%')
        self._bt_tree.heading('winrate', text='胜率%')
        self._bt_tree.heading('trades', text='交易次数')
        self._bt_tree.column('strategy', width=150)
        self._bt_tree.column('return', width=70)
        self._bt_tree.column('sharpe', width=70)
        self._bt_tree.column('drawdown', width=70)
        self._bt_tree.column('winrate', width=70)
        self._bt_tree.column('trades', width=70)
        self._bt_tree.pack(fill='both', expand=True)

        # 绩效指标面板
        ttk.Label(right_top, text="📊 绩效指标", font=('Microsoft YaHei', 11, 'bold')).pack(anchor='w')
        self._bt_metrics = scrolledtext.ScrolledText(right_top, height=12, bg='#0f0f1a',
                                                     fg='#00d4ff', font=('Consolas', 9))
        self._bt_metrics.pack(fill='both', expand=True)
        self._bt_metrics.insert('end', "等待回测...\n\n")

        # 下部分：收益曲线 + 回撤曲线 + 回测日志
        left_bottom = ttk.Frame(bottom_frame)
        left_bottom.pack(side='left', fill='both', expand=True, padx=5)
        middle_bottom = ttk.Frame(bottom_frame)
        middle_bottom.pack(side='left', fill='both', expand=True, padx=5)
        right_bottom = ttk.Frame(bottom_frame)
        right_bottom.pack(side='right', fill='both', expand=True, padx=5)

        # 收益曲线
        ttk.Label(left_bottom, text="📈 收益曲线", font=('Microsoft YaHei', 11, 'bold')).pack(anchor='w')
        self._bt_equity = scrolledtext.ScrolledText(left_bottom, height=8, bg='#0f0f1a',
                                                    fg='#00ff88', font=('Consolas', 8))
        self._bt_equity.pack(fill='both', expand=True)
        self._bt_equity.insert('end', "等待回测...\n")

        # 回撤曲线
        ttk.Label(middle_bottom, text="📉 回撤曲线", font=('Microsoft YaHei', 11, 'bold')).pack(anchor='w')
        self._bt_drawdown = scrolledtext.ScrolledText(middle_bottom, height=8, bg='#0f0f1a',
                                                     fg='#ff6b6b', font=('Consolas', 8))
        self._bt_drawdown.pack(fill='both', expand=True)
        self._bt_drawdown.insert('end', "等待回测...\n")

        # 回测日志
        ttk.Label(right_bottom, text="📋 回测日志", font=('Microsoft YaHei', 11, 'bold')).pack(anchor='w')
        self._bt_log = scrolledtext.ScrolledText(right_bottom, height=8, bg='#0f0f1a',
                                                 fg='#00ff88', font=('Consolas', 9))
        self._bt_log.pack(fill='both', expand=True)

    def _build_optimizer_tab(self, notebook):
        """优化器标签页"""
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="⚡ 优化器")

        # 控制面板
        ctrl = ttk.Frame(tab)
        ctrl.pack(fill='x', padx=5, pady=5)

        ttk.Label(ctrl, text="策略:").pack(side='left', padx=(0, 5))
        self._opt_strategy = ttk.Combobox(ctrl, width=25, state='readonly')
        self._opt_strategy.pack(side='left', padx=5)

        ttk.Label(ctrl, text="迭代:").pack(side='left', padx=(10, 5))
        self._opt_iterations = ttk.Spinbox(ctrl, from_=10, to=500, width=5)
        self._opt_iterations.set(50)
        self._opt_iterations.pack(side='left', padx=5)

        ttk.Label(ctrl, text="目标:").pack(side='left', padx=(10, 5))
        self._opt_target = ttk.Combobox(ctrl, values=['sharpe_ratio', 'total_return', 'sortino_ratio'],
                                        width=15, state='readonly')
        self._opt_target.set('sharpe_ratio')
        self._opt_target.pack(side='left', padx=5)

        ttk.Button(ctrl, text="⚡ 开始优化", command=self._run_optimization,
                   style='Accent.TButton').pack(side='left', padx=10)

        # 优化结果
        columns = ('iteration', 'score', 'params')
        self._opt_tree = ttk.Treeview(tab, columns=columns, show='headings', height=10)
        self._opt_tree.heading('iteration', text='迭代')
        self._opt_tree.heading('score', text='评分')
        self._opt_tree.heading('params', text='参数')
        self._opt_tree.column('iteration', width=80)
        self._opt_tree.column('score', width=100)
        self._opt_tree.column('params', width=400)
        self._opt_tree.pack(fill='both', expand=True, padx=5)

        # 最佳参数
        best_frame = ttk.Frame(tab)
        best_frame.pack(fill='x', padx=5, pady=5)
        ttk.Label(best_frame, text="最佳参数:", font=('Microsoft YaHei', 10, 'bold')).pack(anchor='w')
        self._opt_best = scrolledtext.ScrolledText(best_frame, height=4, bg='#0f0f1a',
                                                    fg='#00ff88', font=('Consolas', 9))
        self._opt_best.pack(fill='x')

        # 牧羊人优化器
        shepherd_frame = ttk.Frame(tab)
        shepherd_frame.pack(fill='x', padx=5, pady=5)
        ttk.Label(shepherd_frame, text="牧羊人五行优化器 (自带安全校验)",
                  font=('Microsoft YaHei', 10, 'bold')).pack(anchor='w')
        ttk.Button(shepherd_frame, text="🐑 启动牧羊人优化",
                   command=self._run_shepherd, style='Green.TButton').pack(side='left', padx=5)
        self._shepherd_status = tk.StringVar(value="就绪")
        ttk.Label(shepherd_frame, textvariable=self._shepherd_status,
                  font=('Microsoft YaHei', 9)).pack(side='left', padx=10)

        # 韬定律策略优化器集群
        tau_frame = ttk.Frame(tab)
        tau_frame.pack(fill='x', padx=5, pady=10)
        ttk.Label(tau_frame, text="韬定律策略优化器集群 (相似缓存 + 空间折叠 + 增量计算)",
                  font=('Microsoft YaHei', 10, 'bold')).pack(anchor='w')

        tau_ctrl = ttk.Frame(tau_frame)
        tau_ctrl.pack(fill='x', pady=5)

        ttk.Label(tau_ctrl, text="粗筛点数:").pack(side='left', padx=(0, 5))
        self._tau_coarse = ttk.Spinbox(tau_ctrl, from_=10, to=200, width=5)
        self._tau_coarse.set(30)
        self._tau_coarse.pack(side='left', padx=5)

        ttk.Label(tau_ctrl, text="精搜点数:").pack(side='left', padx=(10, 5))
        self._tau_refined = ttk.Spinbox(tau_ctrl, from_=10, to=200, width=5)
        self._tau_refined.set(50)
        self._tau_refined.pack(side='left', padx=5)

        ttk.Label(tau_ctrl, text="目标:").pack(side='left', padx=(10, 5))
        self._tau_target = ttk.Combobox(tau_ctrl, values=['sharpe_ratio', 'total_return', 'sortino_ratio'],
                                         width=15, state='readonly')
        self._tau_target.set('sharpe_ratio')
        self._tau_target.pack(side='left', padx=5)

        ttk.Button(tau_ctrl, text="🚀 启动韬定律集群优化",
                   command=self._run_tau_cluster, style='Accent.TButton').pack(side='left', padx=10)

        self._tau_status = tk.StringVar(value="就绪")
        ttk.Label(tau_ctrl, textvariable=self._tau_status,
                  font=('Microsoft YaHei', 9), foreground='#00d4ff').pack(side='left', padx=10)

        # 韬定律结果显示
        tau_result_frame = ttk.Frame(tau_frame)
        tau_result_frame.pack(fill='x', pady=5)
        ttk.Label(tau_result_frame, text="最佳参数:", font=('Microsoft YaHei', 9, 'bold')).pack(anchor='w')
        self._tau_best = scrolledtext.ScrolledText(tau_result_frame, height=4, bg='#0f0f1a',
                                                    fg='#00d4ff', font=('Consolas', 9))
        self._tau_best.pack(fill='x')

        ttk.Label(tau_result_frame, text="运行统计:", font=('Microsoft YaHei', 9, 'bold')).pack(anchor='w', pady=(5, 0))
        self._tau_stats = tk.StringVar(value="--")
        ttk.Label(tau_result_frame, textvariable=self._tau_stats,
                  font=('Consolas', 9), foreground='#00ff88').pack(anchor='w')

        # 模式分析报告显示区（新增）
        ttk.Label(tau_result_frame, text="🔍 模式分析报告 (坏参数模式/范围收缩建议/参数锁定建议/策略改进方向):",
                  font=('Microsoft YaHei', 9, 'bold')).pack(anchor='w', pady=(8, 0))
        self._tau_pattern = scrolledtext.ScrolledText(tau_result_frame, height=12, bg='#0f0f1a',
                                                       fg='#ffd700', font=('Consolas', 9))
        self._tau_pattern.pack(fill='x')

        # 智能标的轮动68因子优化
        tau_shepherd_frame = ttk.Frame(tab)
        tau_shepherd_frame.pack(fill='x', padx=5, pady=10)
        ttk.Label(tau_shepherd_frame, text="智能标的轮动68因子优化 (68因子分层搜索)",
                  font=('Microsoft YaHei', 10, 'bold')).pack(anchor='w')

        tau_shepherd_ctrl = ttk.Frame(tau_shepherd_frame)
        tau_shepherd_ctrl.pack(fill='x', pady=5)

        ttk.Label(tau_shepherd_ctrl, text="策略:").pack(side='left', padx=(0, 5))
        self._tau_shepherd_strategy = ttk.Combobox(tau_shepherd_ctrl, width=25, state='readonly')
        self._tau_shepherd_strategy.pack(side='left', padx=5)

        ttk.Label(tau_shepherd_ctrl, text="粗筛点数:").pack(side='left', padx=(10, 5))
        self._tau_shepherd_coarse = ttk.Spinbox(tau_shepherd_ctrl, from_=10, to=200, width=5)
        self._tau_shepherd_coarse.set(35)
        self._tau_shepherd_coarse.pack(side='left', padx=5)

        ttk.Label(tau_shepherd_ctrl, text="精搜点数:").pack(side='left', padx=(10, 5))
        self._tau_shepherd_refined = ttk.Spinbox(tau_shepherd_ctrl, from_=5, to=100, width=5)
        self._tau_shepherd_refined.set(15)
        self._tau_shepherd_refined.pack(side='left', padx=5)

        ttk.Button(tau_shepherd_ctrl, text="🚀 启动标的轮动优化",
                   command=self._run_tau_shepherd_ui, style='Accent.TButton').pack(side='left', padx=10)

        self._tau_shepherd_status = tk.StringVar(value="就绪")
        ttk.Label(tau_shepherd_ctrl, textvariable=self._tau_shepherd_status,
                  font=('Microsoft YaHei', 9), foreground='#ffaa00').pack(side='left', padx=10)

        # 智能标的轮动结果显示
        tau_shepherd_result = ttk.Frame(tau_shepherd_frame)
        tau_shepherd_result.pack(fill='x', pady=5)
        ttk.Label(tau_shepherd_result, text="最佳参数:", font=('Microsoft YaHei', 9, 'bold')).pack(anchor='w')
        self._tau_shepherd_best = scrolledtext.ScrolledText(tau_shepherd_result, height=4, bg='#0f0f1a',
                                                         fg='#ffaa00', font=('Consolas', 9))
        self._tau_shepherd_best.pack(fill='x')

        ttk.Label(tau_shepherd_result, text="运行统计:", font=('Microsoft YaHei', 9, 'bold')).pack(anchor='w', pady=(5, 0))
        self._tau_shepherd_stats = tk.StringVar(value="--")
        ttk.Label(tau_shepherd_result, textvariable=self._tau_shepherd_stats,
                  font=('Consolas', 9), foreground='#ffaa00').pack(anchor='w')

        # ==================== 韬定律自动集成总线 ====================
        auto_frame = ttk.Frame(tab)
        auto_frame.pack(fill='x', padx=5, pady=15)
        ttk.Label(auto_frame, text="🔗 韬定律自动集成总线 (策略→优化→股票池→交易配置)",
                  font=('Microsoft YaHei', 10, 'bold')).pack(anchor='w')

        auto_ctrl = ttk.Frame(auto_frame)
        auto_ctrl.pack(fill='x', pady=5)

        ttk.Button(auto_ctrl, text="⚡ 完整自动化流程",
                   command=self._run_auto_full_workflow, style='Accent.TButton').pack(side='left', padx=5)
        ttk.Button(auto_ctrl, text="📊 批量优化所有策略",
                   command=self._run_batch_optimize).pack(side='left', padx=5)
        ttk.Button(auto_ctrl, text="💹 策略-股票池匹配",
                   command=self._run_stock_pool_match).pack(side='left', padx=5)
        ttk.Button(auto_ctrl, text="📋 集成状态报告",
                   command=self._show_integration_report).pack(side='left', padx=5)

        self._auto_status = tk.StringVar(value="就绪 - 选择策略后点击按钮启动自动化流程")
        ttk.Label(auto_frame, textvariable=self._auto_status,
                  font=('Microsoft YaHei', 9)).pack(anchor='w', pady=5)

        # 自动化结果显示
        auto_result_frame = ttk.Frame(auto_frame)
        auto_result_frame.pack(fill='both', expand=True, pady=5)
        self._auto_log = scrolledtext.ScrolledText(auto_result_frame, height=10, bg='#0f0f1a',
                                                    fg='#00d4ff', font=('Consolas', 9))
        self._auto_log.pack(fill='both', expand=True)

    def _run_tau_cluster(self):
        """运行韬定律集群优化"""
        strategy = self._opt_strategy.get()
        if not strategy:
            messagebox.showinfo("提示", "请先选择策略")
            return

        self._tau_status.set(f"优化中: {strategy}...")
        self._tau_best.delete('1.0', 'end')

        def run_thread():
            try:
                if not self.strategy_mgr:
                    raise Exception("策略管理器不可用")

                result = self.strategy_mgr.run_tau_cluster_optimization(
                    strategy_name=strategy,
                    coarse_points=int(self._tau_coarse.get()),
                    refined_points=int(self._tau_refined.get()),
                    target=self._tau_target.get()
                )

                if result.get('success'):
                    data = result.get('data', {})
                    best_params = data.get('best_params', {})
                    status = data.get('cluster_status', {})

                    # 显示最佳参数
                    self._tau_best.insert('end', json.dumps(best_params, indent=2, ensure_ascii=False))

                    # 显示统计信息
                    total = status.get('total_requests', data.get('total_evals', 0))
                    cache_hit = status.get('cache', {}).get('hit_rate', 0) \
                        if isinstance(status, dict) else 0
                    score = data.get('best_score', 0)
                    ret = data.get('best_return', 0)
                    elapsed = data.get('time_elapsed', 0)

                    stats_text = (
                        f"最佳评分: {score:.4f}  |  "
                        f"最佳收益: {ret:.2f}%  |  "
                        f"评估总数: {total}  |  "
                        f"缓存命中率: {cache_hit*100:.1f}%  |  "
                        f"耗时: {elapsed:.2f}s"
                    )
                    self._tau_stats.set(stats_text)
                    self._tau_status.set(f"✅ 完成: {strategy}")

                    # 显示模式分析报告（新增）
                    self._tau_pattern.delete('1.0', 'end')
                    pa = data.get('pattern_analysis')
                    if pa:
                        pa_lines = []
                        pa_lines.append("=" * 60)
                        pa_lines.append(f" 评估点数: {pa.get('num_points', 0)}    评分范围: {pa.get('score_range', ['-','-'])}")
                        pa_lines.append("")
                        rcs = pa.get('range_contract_suggestions', [])
                        pa_lines.append(f" ── 范围收缩建议 ({len(rcs)} 项)")
                        if rcs:
                            for r in rcs:
                                pa_lines.append(f"   📏 {r['param']}: {r.get('original_range', [])} → "
                                               f"{r.get('suggested_range', [])} (收缩 {int(r.get('contraction_ratio',0)*100)}%)")
                        else:
                            pa_lines.append("   ⚪ 暂无可收缩的参数 (好/坏参数取值无显著差异)")
                        pa_lines.append("")
                        locks = pa.get('lock_suggestions', [])
                        pa_lines.append(f" ── 参数锁定建议 ({len(locks)} 项)")
                        if locks:
                            for l in locks:
                                pa_lines.append(f"   🔒 {l['param']}: 建议锁定为 {l.get('suggested_value','?')} "
                                               f"(相关性 {l.get('correlation','?')}, 好坏差异 {l.get('norm_diff','?')})")
                                pa_lines.append(f"       → 从优化变量中移除此参数，降低搜索维度")
                        else:
                            pa_lines.append("   ⚪ 所有参数对评分都有显著影响，暂不建议锁定")
                        pa_lines.append("")
                        arcs = pa.get('architecture_suggestions', [])
                        pa_lines.append(f" ── 策略改进方向提示 ({len(arcs)} 项)")
                        if arcs:
                            for a in arcs:
                                pa_lines.append(f"   💡 {a.get('category','建议')}:")
                                pa_lines.append(f"       观察: {a.get('short_text', '')}")
                                pa_lines.append(f"       建议: {a.get('action_suggestion', '')}")
                                pa_lines.append("")
                        else:
                            pa_lines.append("   ⚪ 暂未检测到需要架构级修改的参数模式")
                        pa_lines.append("=" * 60)
                        self._tau_pattern.insert('end', "\n".join(pa_lines))
                    else:
                        self._tau_pattern.insert('end', "(本次优化无模式分析数据 - 可能是评估点不足，需 ≥ 10 个评估点)")

                    # 自动刷新策略列表，显示最新优化状态
                    try:
                        self.strategy_mgr.apply_optimized_params(strategy)
                    except Exception:
                        pass
                    self.root.after(0, self._refresh_strategies)
                else:
                    self._tau_status.set(f"❌ 失败: {result.get('error', '未知错误')}")
            except Exception as e:
                self._tau_status.set(f"❌ 异常: {str(e)}")

        threading.Thread(target=run_thread, daemon=True).start()

    def _run_tau_shepherd_ui(self):
        """运行智能标的轮动68因子优化"""
        strategy = self._tau_shepherd_strategy.get() or self._opt_strategy.get()
        if not strategy:
            messagebox.showinfo("提示", "请先选择策略")
            return

        self._tau_shepherd_status.set(f"优化中: {strategy}...")
        self._tau_shepherd_best.delete('1.0', 'end')

        def run_thread():
            try:
                if not self.strategy_mgr:
                    raise Exception("策略管理器不可用")
                result = self.strategy_mgr.run_tau_shepherd_optimization(
                    strategy_name=strategy,
                    coarse_points=int(self._tau_shepherd_coarse.get()),
                    refined_per_group=int(self._tau_shepherd_refined.get()),
                )

                if result.get('success'):
                    data = result.get('data', {})
                    best_params = data.get('best_params', {})
                    cluster_status = data.get('cluster_status', {})

                    self._tau_shepherd_best.insert('end', json.dumps(best_params, indent=2, ensure_ascii=False))

                    total = cluster_status.get('total_requests', data.get('total_evals', 0))
                    cache_hit = cluster_status.get('cache', {}).get('hit_rate', 0) \
                        if isinstance(cluster_status, dict) else 0
                    score = data.get('best_score', 0)
                    ret = data.get('best_return', 0)
                    elapsed = data.get('time_elapsed', 0)

                    stats_text = (
                        f"最佳评分: {score:.4f}  |  "
                        f"最佳收益: {ret:.2f}%  |  "
                        f"评估总数: {total}  |  "
                        f"缓存命中率: {cache_hit*100:.1f}%  |  "
                        f"耗时: {elapsed:.2f}s"
                    )
                    self._tau_shepherd_stats.set(stats_text)
                    self._tau_shepherd_status.set(f"✅ 完成: {strategy}")

                    # 自动刷新策略列表，显示最新优化状态
                    try:
                        self.strategy_mgr.apply_optimized_params(strategy)
                    except Exception:
                        pass
                    self.root.after(0, self._refresh_strategies)
                else:
                    self._tau_shepherd_status.set(f"❌ 失败: {result.get('error', '未知错误')}")
            except Exception as e:
                self._tau_shepherd_status.set(f"❌ 异常: {str(e)}")

        threading.Thread(target=run_thread, daemon=True).start()

    def _build_technical_analysis_tab(self, notebook):
        """技术分析标签页"""
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="📈 技术分析")

        # 技术分析引擎
        self._ta_engine = None
        self._factor_engine = None
        self._vibe_integration = None
        try:
            from core.technical_analysis import get_ta_engine, get_factor_engine
            from core.vibe_integration import get_vibe_integration
            self._ta_engine = get_ta_engine()
            self._factor_engine = get_factor_engine()
            self._vibe_integration = get_vibe_integration()
        except Exception as e:
            print(f"[WARNING] 技术分析模块不可用: {e}")

        # 顶部工具栏
        toolbar = ttk.Frame(tab)
        toolbar.pack(fill='x', padx=5, pady=5)

        ttk.Label(toolbar, text="股票代码:").pack(side='left', padx=(0, 5))
        self._ta_symbol = ttk.Entry(toolbar, width=12)
        self._ta_symbol.insert(0, '000001')
        self._ta_symbol.pack(side='left', padx=5)

        ttk.Label(toolbar, text="天数:").pack(side='left', padx=(10, 5))
        self._ta_days = ttk.Spinbox(toolbar, from_=30, to=500, width=5)
        self._ta_days.set(100)
        self._ta_days.pack(side='left', padx=5)

        ttk.Button(toolbar, text="🔍 开始分析", command=self._run_technical_analysis,
                   style='Accent.TButton').pack(side='left', padx=10)
        ttk.Button(toolbar, text="🤖 AI智能分析", command=self._run_ai_analysis).pack(side='left', padx=5)
        ttk.Button(toolbar, text="🏛️ 港大智能体", command=self._run_hku_vibe_analysis,
                   style='Accent.TButton').pack(side='left', padx=10)
        ttk.Button(toolbar, text="🎯 增强版分析", 
                   command=self._run_hku_vibe_enhanced_analysis).pack(side='left', padx=5)
        ttk.Button(toolbar, text="🚀 强强联合流程", 
                   command=self._run_hybrid_power_flow,
                   style='Accent.TButton').pack(side='left', padx=10)

        # 主内容区（上下分栏）
        top = ttk.Frame(tab)
        top.pack(fill='both', expand=True, padx=5, pady=5)
        bottom = ttk.Frame(tab)
        bottom.pack(fill='both', expand=True, padx=5, pady=5)

        # 上部分：指标面板（左右分栏）
        left_top = ttk.Frame(top)
        left_top.pack(side='left', fill='both', expand=True, padx=5)
        right_top = ttk.Frame(top)
        right_top.pack(side='right', fill='both', expand=True, padx=5)

        # 左侧：技术指标
        ttk.Label(left_top, text="技术指标", font=('Microsoft YaHei', 11, 'bold')).pack(anchor='w')

        self._ta_indicators = scrolledtext.ScrolledText(left_top, height=10, bg='#0f0f1a',
                                                        fg='#00d4ff', font=('Consolas', 9))
        self._ta_indicators.pack(fill='both', expand=True)

        # 右侧：交易信号
        ttk.Label(right_top, text="交易信号", font=('Microsoft YaHei', 11, 'bold')).pack(anchor='w')

        self._ta_signals = scrolledtext.ScrolledText(right_top, height=10, bg='#0f0f1a',
                                                     fg='#00ff88', font=('Consolas', 9))
        self._ta_signals.pack(fill='both', expand=True)

        # 下部分：因子分析和AI分析（左右分栏）
        left_bottom = ttk.Frame(bottom)
        left_bottom.pack(side='left', fill='both', expand=True, padx=5)
        right_bottom = ttk.Frame(bottom)
        right_bottom.pack(side='right', fill='both', expand=True, padx=5)

        # 左侧：因子分析
        ttk.Label(left_bottom, text="因子分析", font=('Microsoft YaHei', 11, 'bold')).pack(anchor='w')

        columns = ('factor', 'value', 'description')
        self._factor_tree = ttk.Treeview(left_bottom, columns=columns, show='headings', height=8)
        self._factor_tree.heading('factor', text='因子')
        self._factor_tree.heading('value', text='值')
        self._factor_tree.heading('description', text='描述')
        self._factor_tree.column('factor', width=100)
        self._factor_tree.column('value', width=80)
        self._factor_tree.column('description', width=150)
        self._factor_tree.pack(fill='both', expand=True)

        # 右侧：AI分析结果
        ttk.Label(right_bottom, text="AI智能分析", font=('Microsoft YaHei', 11, 'bold')).pack(anchor='w')

        self._ai_analysis = scrolledtext.ScrolledText(right_bottom, height=8, bg='#0f0f1a',
                                                     fg='#ffd700', font=('Consolas', 9))
        self._ai_analysis.pack(fill='both', expand=True)

        # 初始化示例数据
        self._load_sample_ta_data()

    def _load_sample_ta_data(self):
        """加载示例技术分析数据"""
        import random
        
        indicators = """【均线系统】
MA5:    11.25
MA10:   10.98
MA20:   10.75
MA60:   10.50

【震荡指标】
RSI(14): 58.75
KDJ:     K=62.3, D=58.5, J=70.1
CCI:     85.32

【趋势指标】
MACD:    0.25 (信号线: 0.18)
ATR:     0.35
ADX:     28.5

【波动率】
布林带宽度: 15.3%
HV20:    22.5%

【量能】
OBV:     1250000
量比:    1.25
"""
        self._ta_indicators.insert('end', indicators)

        signals = """📈 多头信号:
  [买入] MA: 均线多头排列，趋势向上
  [买入] RSI: RSI处于正常区间(58.75)

📊 中性信号:
  [info] BOLL: 布林带宽度: 15.3%

⚠️ 预警信号:
  暂无

📉 空头信号:
  暂无
"""
        self._ta_signals.insert('end', signals)

        self._factor_tree.delete(*self._factor_tree.get_children())
        factors = [
            ('momentum_1d', '2.35', '1日动量'),
            ('momentum_5d', '8.72', '5日动量'),
            ('momentum_20d', '15.32', '20日动量'),
            ('volatility_20d', '18.56', '20日波动率'),
            ('rsi_14d', '58.75', 'RSI(14)'),
            ('bollinger_width', '15.32', '布林带宽度'),
            ('macd_signal', '0.07', 'MACD信号'),
            ('atr_ratio', '3.12', 'ATR比率'),
        ]
        for f, v, d in factors:
            self._factor_tree.insert('', 'end', values=(f, v, d))

        ai_analysis = """🤖 AI智能分析报告

【技术面】
趋势判断: 上升趋势
支撑位:    10.80
阻力位:    12.50
建议:      建议持有

【基本面】
PE:       12.5
PB:       1.8
EPS:      0.85
评级:      增持

【舆情】
情绪分数:  0.35
正面比例:  58%
市场情绪:  中性

【风控】
风险评分:  45.5
最大回撤:  12.5%
波动率:    18.5%
"""
        self._ai_analysis.insert('end', ai_analysis)

    def _run_technical_analysis(self):
        """执行技术分析（通过统一数据总线获取数据）"""
        symbol = self._ta_symbol.get().strip()
        if not symbol:
            messagebox.showwarning("提示", "请输入股票代码")
            return

        try:
            days = int(self._ta_days.get())
        except ValueError:
            messagebox.showerror("错误", "天数必须为数字")
            return

        if not self._ta_engine:
            messagebox.showerror("错误", "技术分析引擎不可用")
            return

        # 显示加载状态
        self._ta_indicators.delete('1.0', 'end')
        self._ta_indicators.insert('end', f"🔄 正在从数据总线获取 {symbol} 数据...\n")
        self.root.update()

        def run_thread():
            """子线程：从总线获取数据并分析"""
            try:
                # 1. 通过数据总线获取数据
                result = self._ta_engine.analyze_from_bus(symbol, period="daily", days=days)

                # 回到主线程更新UI
                self.root.after(0, lambda: self._update_ta_ui(symbol, result))

            except Exception as e:
                error_msg = f"分析失败: {e}"
                self.root.after(0, lambda: self._ta_indicators.insert('end', error_msg + "\n"))

        import threading
        threading.Thread(target=run_thread, daemon=True).start()

    def _update_ta_ui(self, symbol: str, result: Dict):
        """更新技术分析UI显示"""
        if not result.get("success"):
            msg = f"❌ {result.get('error', '未知错误')}"
            self._ta_indicators.delete('1.0', 'end')
            self._ta_indicators.insert('end', msg + "\n")
            return

        data_source = result.get("data_source", "未知")
        data_count = result.get("data_count", 0)
        raw_data = result.get("raw_data", {})

        # 从总线获取数据
        closes = [float(c) for c in raw_data.get("closes", [])]
        volumes_raw = raw_data.get("volumes", [])
        if volumes_raw:
            volumes = [float(v) for v in volumes_raw]
        else:
            volumes = None

        # 执行技术分析（只做一次）
        analysis = self._ta_engine.analyze_stock(symbol, closes, volumes)

        # 显示数据源信息 + 技术指标
        self._ta_indicators.delete('1.0', 'end')
        self._ta_indicators.insert(
            'end',
            f"[数据源] {data_source} | 数据点: {data_count}个\n"
            f"[股票] {symbol} | {raw_data.get('name', symbol)}\n"
            f"[最新价] {closes[-1]:.2f}\n\n"
        )

        indicators = analysis['indicators']
        
        result = "【均线系统】\n"
        for ma_name in ['MA5', 'MA10', 'MA20', 'MA60']:
            if ma_name in indicators and indicators[ma_name].values:
                val = indicators[ma_name].values[-1]
                result += f"{ma_name}:   {val:.2f}\n"
        result += "\n"

        result += "【震荡指标】\n"
        if 'RSI' in indicators and indicators['RSI'].values:
            rsi = indicators['RSI'].values[-1]
            result += f"RSI(14): {rsi:.2f}\n"
        if 'KDJ' in indicators and indicators['KDJ'].values:
            kdj = indicators['KDJ'].values[-1]
            if kdj[0] is not None:
                result += f"KDJ:     K={kdj[0]:.1f}, D={kdj[1]:.1f}, J={kdj[2]:.1f}\n"
        result += "\n"

        result += "【趋势指标】\n"
        if 'MACD' in indicators and indicators['MACD'].values:
            macd = indicators['MACD'].values[-1]
            if macd[0] is not None:
                result += f"MACD:    {macd[0]:.2f} (信号线: {macd[1]:.2f})\n"
        if 'ATR' in indicators and indicators['ATR'].values:
            atr = indicators['ATR'].values[-1]
            if atr:
                result += f"ATR:     {atr:.2f}\n"
        result += "\n"

        result += "【波动率】\n"
        if 'BOLL' in indicators and indicators['BOLL'].values:
            boll = indicators['BOLL'].values[-1]
            if boll[0] is not None:
                width = (boll[2] - boll[0]) / boll[1] * 100
                result += f"布林带宽度: {width:.1f}%\n"
        result += f"H V20:    {analysis['stats']['volatility']:.1f}%\n"

        self._ta_indicators.insert('end', result)

        # 显示信号
        self._ta_signals.delete('1.0', 'end')
        signals = analysis['signals']
        
        result = "📈 多头信号:\n"
        buy_signals = [s for s in signals if s['type'] == 'buy']
        if buy_signals:
            for sig in buy_signals:
                result += f"  [{sig['type']}] {sig['indicator']}: {sig['reason']}\n"
        else:
            result += "  暂无\n"
        result += "\n"

        result += "📊 中性信号:\n"
        info_signals = [s for s in signals if s['type'] == 'info']
        if info_signals:
            for sig in info_signals:
                result += f"  [{sig['type']}] {sig['indicator']}: {sig['reason']}\n"
        else:
            result += "  暂无\n"
        result += "\n"

        result += "⚠️ 预警信号:\n"
        result += "  暂无\n\n"

        result += "📉 空头信号:\n"
        sell_signals = [s for s in signals if s['type'] == 'sell']
        if sell_signals:
            for sig in sell_signals:
                result += f"  [{sig['type']}] {sig['indicator']}: {sig['reason']}\n"
        else:
            result += "  暂无\n"

        self._ta_signals.insert('end', result)

        # 显示因子
        self._factor_tree.delete(*self._factor_tree.get_children())
        if self._factor_engine:
            factors = self._factor_engine.calculate_factor(symbol, closes, volumes)
            desc = self._factor_engine.get_factor_descriptions()
            for name, value in factors.items():
                self._factor_tree.insert('', 'end', values=(name, f"{value:.2f}", desc.get(name, name)))

        messagebox.showinfo("完成", f"已完成 {symbol} 的技术分析\n数据源: {data_source}")

    def _run_ai_analysis(self):
        """执行AI智能分析"""
        symbol = self._ta_symbol.get().strip()
        if not symbol:
            messagebox.showwarning("提示", "请输入股票代码")
            return

        if not self._vibe_integration:
            messagebox.showerror("错误", "AI分析引擎不可用")
            return

        self._ai_analysis.delete('1.0', 'end')
        self._ai_analysis.insert('end', "🤖 正在进行AI分析...\n")
        self.root.update()

        def run_thread():
            try:
                result = self._vibe_integration.analyze_stock(symbol)
                
                tech = result.get('technical', {})
                fund = result.get('fundamental', {})
                sent = result.get('sentiment', {})
                risk = result.get('risk', {})

                report = f"🤖 AI智能分析报告 ({'模拟模式' if result.get('mock_mode') else '真实AI'})\n\n"
                
                report += "【技术面】\n"
                report += f"趋势判断: {tech.get('trend', '未知')}\n"
                report += f"支撑位:    {tech.get('support', '--')}\n"
                report += f"阻力位:    {tech.get('resistance', '--')}\n"
                report += f"RSI:       {tech.get('rsi', '--')}\n"
                report += f"MACD信号:  {tech.get('macd_signal', '--')}\n"
                report += f"建议:      {tech.get('suggestion', '--')}\n\n"

                report += "【基本面】\n"
                report += f"PE:        {fund.get('pe', '--')}\n"
                report += f"PB:        {fund.get('pb', '--')}\n"
                report += f"EPS:       {fund.get('eps', '--')}\n"
                report += f"ROE:       {fund.get('roe', '--')}%\n"
                report += f"行业排名:   {fund.get('industry_rank', '--')}\n"
                report += f"评级:      {fund.get('rating', '--')}\n\n"

                report += "【舆情】\n"
                report += f"情绪分数:  {sent.get('sentiment_score', '--')}\n"
                report += f"正面比例:  {sent.get('positive_ratio', '--')}%\n"
                report += f"市场情绪:  {sent.get('market_sentiment', '--')}\n\n"

                report += "【风控】\n"
                report += f"风险评分:  {risk.get('risk_score', '--')}\n"
                report += f"最大回撤:  {risk.get('max_drawdown', '--')}%\n"
                report += f"波动率:    {risk.get('volatility', '--')}%\n"

                self._ai_analysis.delete('1.0', 'end')
                self._ai_analysis.insert('end', report)

                if result.get('warning'):
                    self._log(f"[AI分析警告] {result['warning']}")

            except Exception as e:
                self._ai_analysis.delete('1.0', 'end')
                self._ai_analysis.insert('end', f"❌ AI分析失败: {e}")

    def _run_hku_vibe_analysis(self):
        """启动港大Vibe-Trading智能体分析"""
        symbol = self._ta_symbol.get().strip()
        if not symbol:
            messagebox.showwarning("提示", "请输入股票代码")
            return

        if not self._vibe_integration:
            messagebox.showerror("错误", "Vibe-Trading引擎不可用")
            return

        # 创建港大智能体分析对话框
        vibe_win = tk.Toplevel(self.root)
        vibe_win.title("🏛️ 港大Vibe-Trading智能体分析")
        vibe_win.geometry("1000x700")
        vibe_win.iconbitmap(default=None)

        # 顶部标题栏
        header = ttk.Frame(vibe_win)
        header.pack(fill='x', padx=10, pady=10)
        ttk.Label(header, text=f"Vibe-Trading AI 多智能体投研系统", 
                  font=('Microsoft YaHei', 14, 'bold')).pack(side='left')
        
        # 获取智能体信息
        agent_info = self._vibe_integration.get_agent_info()
        status_text = "✅ Vibe-Trading已安装" if agent_info['available'] else "⚠️ 模拟模式"
        ttk.Label(header, text=status_text, 
                  foreground='green' if agent_info['available'] else 'orange').pack(side='right')

        # 创建笔记本用于多个智能体分析标签
        notebook = ttk.Notebook(vibe_win)
        notebook.pack(fill='both', expand=True, padx=10, pady=10)

        # ==================== 标签1: 技术分析师 ====================
        tech_tab = ttk.Frame(notebook)
        notebook.add(tech_tab, text="📈 技术分析师")
        
        tech_text = scrolledtext.ScrolledText(tech_tab, bg='#0f0f1a', fg='#00ff88', font=('Consolas', 9))
        tech_text.pack(fill='both', expand=True, padx=5, pady=5)
        tech_text.insert('end', "正在分析技术面...")

        # ==================== 标签2: 基本面分析师 ====================
        fund_tab = ttk.Frame(notebook)
        notebook.add(fund_tab, text="📊 基本面分析师")
        
        fund_text = scrolledtext.ScrolledText(fund_tab, bg='#0f0f1a', fg='#00d4ff', font=('Consolas', 9))
        fund_text.pack(fill='both', expand=True, padx=5, pady=5)
        fund_text.insert('end', "正在分析基本面...")

        # ==================== 标签3: 舆情分析师 ====================
        sentiment_tab = ttk.Frame(notebook)
        notebook.add(sentiment_tab, text="💬 舆情分析师")
        
        sentiment_text = scrolledtext.ScrolledText(sentiment_tab, bg='#0f0f1a', fg='#ffd700', font=('Consolas', 9))
        sentiment_text.pack(fill='both', expand=True, padx=5, pady=5)
        sentiment_text.insert('end', "正在分析舆情...")

        # ==================== 标签4: 风控智能体 ====================
        risk_tab = ttk.Frame(notebook)
        notebook.add(risk_tab, text="🛡️ 风控智能体")
        
        risk_text = scrolledtext.ScrolledText(risk_tab, bg='#0f0f1a', fg='#ff6b6b', font=('Consolas', 9))
        risk_text.pack(fill='both', expand=True, padx=5, pady=5)
        risk_text.insert('end', "正在评估风险...")

        # ==================== 标签5: 策略代码生成 ====================
        code_tab = ttk.Frame(notebook)
        notebook.add(code_tab, text="💻 策略代码")
        
        code_text = scrolledtext.ScrolledText(code_tab, bg='#0f0f1a', fg='#c0c0c0', font=('Consolas', 9))
        code_text.pack(fill='both', expand=True, padx=5, pady=5)
        code_text.insert('end', "正在生成策略代码...")

        # ==================== 标签6: 回测报告 ====================
        backtest_tab = ttk.Frame(notebook)
        notebook.add(backtest_tab, text="📋 回测报告")
        
        backtest_text = scrolledtext.ScrolledText(backtest_tab, bg='#0f0f1a', fg='#e0e0e0', font=('Consolas', 9))
        backtest_text.pack(fill='both', expand=True, padx=5, pady=5)
        backtest_text.insert('end', "正在生成回测报告...")

        # 底部按钮栏
        footer = ttk.Frame(vibe_win)
        footer.pack(fill='x', padx=10, pady=10)
        
        # 输入提示框
        ttk.Label(footer, text="分析提示:").pack(side='left', padx=(0, 5))
        prompt_entry = ttk.Entry(footer, width=50)
        prompt_entry.insert(0, f"分析股票{symbol}的技术面、基本面和交易机会")
        prompt_entry.pack(side='left', padx=5)
        
        def run_analysis():
            """执行多智能体分析"""
            prompt = prompt_entry.get()
            
            # 清空所有标签
            tech_text.delete('1.0', 'end')
            fund_text.delete('1.0', 'end')
            sentiment_text.delete('1.0', 'end')
            risk_text.delete('1.0', 'end')
            code_text.delete('1.0', 'end')
            backtest_text.delete('1.0', 'end')

            tech_text.insert('end', "🤖 技术分析师正在分析...\n")
            fund_text.insert('end', "📊 基本面分析师正在分析...\n")
            sentiment_text.insert('end', "💬 舆情分析师正在分析...\n")
            risk_text.insert('end', "🛡️ 风控智能体正在评估...\n")
            vibe_win.update()

            def analysis_thread():
                try:
                    result = self._vibe_integration.analyze_stock(symbol, prompt)

                    # 更新技术分析
                    tech = result.get('technical', {})
                    tech_report = f"🏛️ Vibe-Trading 技术分析报告\n"
                    tech_report += "=" * 50 + "\n\n"
                    tech_report += f"📊 标的: {symbol}\n"
                    tech_report += f"⏰ 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                    tech_report += "【趋势分析】\n"
                    tech_report += f"  趋势判断: {tech.get('trend', '未知')}\n"
                    tech_report += f"  支撑位:   {tech.get('support', '--')}\n"
                    tech_report += f"  阻力位:   {tech.get('resistance', '--')}\n\n"
                    tech_report += "【指标分析】\n"
                    tech_report += f"  RSI(14):  {tech.get('rsi', '--')}\n"
                    tech_report += f"  MACD信号: {tech.get('macd_signal', '--')}\n"
                    tech_report += f"  布林带位置: {tech.get('bollinger_position', '--')}\n"
                    tech_report += f"  量价分析: {tech.get('volume_analysis', '--')}\n\n"
                    tech_report += "【操作建议】\n"
                    tech_report += f"  {tech.get('suggestion', '--')}\n"
                    
                    vibe_win.after(0, lambda: tech_text.delete('1.0', 'end'))
                    vibe_win.after(0, lambda: tech_text.insert('end', tech_report))

                    # 更新基本面分析
                    fund = result.get('fundamental', {})
                    fund_report = f"🏛️ Vibe-Trading 基本面分析报告\n"
                    fund_report += "=" * 50 + "\n\n"
                    fund_report += f"📊 标的: {symbol}\n\n"
                    fund_report += "【估值指标】\n"
                    fund_report += f"  PE:        {fund.get('pe', '--')}\n"
                    fund_report += f"  PB:        {fund.get('pb', '--')}\n"
                    fund_report += f"  EPS:       {fund.get('eps', '--')}\n"
                    fund_report += f"  ROE:       {fund.get('roe', '--')}%\n\n"
                    fund_report += "【成长能力】\n"
                    fund_report += f"  营收增长率: {fund.get('revenue_growth', '--')}%\n"
                    fund_report += f"  净利润增长: {fund.get('profit_growth', '--')}%\n\n"
                    fund_report += "【行业对比】\n"
                    fund_report += f"  行业排名:   {fund.get('industry_rank', '--')}\n"
                    fund_report += f"  投资评级:   {fund.get('rating', '--')}\n"
                    
                    vibe_win.after(0, lambda: fund_text.delete('1.0', 'end'))
                    vibe_win.after(0, lambda: fund_text.insert('end', fund_report))

                    # 更新舆情分析
                    sent = result.get('sentiment', {})
                    sent_report = f"🏛️ Vibe-Trading 舆情分析报告\n"
                    sent_report += "=" * 50 + "\n\n"
                    sent_report += f"📊 标的: {symbol}\n\n"
                    sent_report += "【舆情概览】\n"
                    sent_report += f"  情绪分数:   {sent.get('sentiment_score', '--')} (-1~1)\n"
                    sent_report += f"  新闻数量:   {sent.get('news_count', '--')} 条\n"
                    sent_report += f"  正面比例:   {sent.get('positive_ratio', '--')}%\n"
                    sent_report += f"  市场情绪:   {sent.get('market_sentiment', '--')}\n\n"
                    sent_report += "【热门话题】\n"
                    for topic in sent.get('key_topics', []):
                        sent_report += f"  • {topic}\n"
                    
                    vibe_win.after(0, lambda: sentiment_text.delete('1.0', 'end'))
                    vibe_win.after(0, lambda: sentiment_text.insert('end', sent_report))

                    # 更新风控分析
                    risk = result.get('risk', {})
                    risk_report = f"🏛️ Vibe-Trading 风险评估报告\n"
                    risk_report += "=" * 50 + "\n\n"
                    risk_report += f"📊 标的: {symbol}\n\n"
                    risk_report += "【风险评分】\n"
                    risk_report += f"  综合评分:   {risk.get('risk_score', '--')} (0-100)\n"
                    risk_report += f"  最大回撤:   {risk.get('max_drawdown', '--')}%\n"
                    risk_report += f"  波动率:     {risk.get('volatility', '--')}%\n\n"
                    risk_report += "【风险类型】\n"
                    risk_report += f"  流动性风险: {risk.get('liquidity_risk', '--')}\n"
                    risk_report += f"  集中度风险: {risk.get('concentration_risk', '--')}\n\n"
                    risk_report += "【风险因子】\n"
                    for factor in risk.get('risk_factors', []):
                        risk_report += f"  • {factor}\n"
                    
                    vibe_win.after(0, lambda: risk_text.delete('1.0', 'end'))
                    vibe_win.after(0, lambda: risk_text.insert('end', risk_report))

                    # 更新策略代码
                    code = result.get('strategy_code', '')
                    vibe_win.after(0, lambda: code_text.delete('1.0', 'end'))
                    vibe_win.after(0, lambda: code_text.insert('end', code))

                    # 更新回测报告
                    bt = result.get('backtest', {})
                    bt_report = f"🏛️ Vibe-Trading 回测报告\n"
                    bt_report += "=" * 50 + "\n\n"
                    bt_report += f"📊 策略: {bt.get('strategy', 'Generated')}\n\n"
                    bt_report += "【绩效指标】\n"
                    bt_report += f"  总收益率:   {bt.get('total_return', '--')}%\n"
                    bt_report += f"  年化收益率: {bt.get('annual_return', '--')}%\n"
                    bt_report += f"  夏普比率:   {bt.get('sharpe_ratio', '--')}\n"
                    bt_report += f"  最大回撤:   {bt.get('max_drawdown', '--')}%\n\n"
                    bt_report += "【交易统计】\n"
                    bt_report += f"  胜率:       {bt.get('win_rate', '--')}%\n"
                    bt_report += f"  盈亏比:     {bt.get('profit_factor', '--')}\n"
                    bt_report += f"  交易次数:   {bt.get('total_trades', '--')}\n\n"
                    bt_report += "【总结】\n"
                    bt_report += f"  {bt.get('summary', '--')}\n"
                    
                    vibe_win.after(0, lambda: backtest_text.delete('1.0', 'end'))
                    vibe_win.after(0, lambda: backtest_text.insert('end', bt_report))

                    if result.get('warning'):
                        print(f"[Vibe警告] {result['warning']}")

                except Exception as e:
                    vibe_win.after(0, lambda: tech_text.insert('end', f"❌ 分析失败: {e}"))

            threading.Thread(target=analysis_thread, daemon=True).start()

        ttk.Button(footer, text="🚀 开始多智能体分析", command=run_analysis,
                   style='Accent.TButton').pack(side='right', padx=10)
        ttk.Button(footer, text="🗑 关闭", command=vibe_win.destroy).pack(side='right')

        # 自动开始分析
        run_analysis()

    def _run_hku_vibe_enhanced_analysis(self):
        """启动港大Vibe增强版分析（含综合评分+股票池推荐）"""
        symbol = self._ta_symbol.get().strip()
        if not symbol:
            messagebox.showwarning("提示", "请输入股票代码")
            return

        if not self._vibe_integration:
            messagebox.showerror("错误", "Vibe-Trading引擎不可用")
            return

        # 创建增强版分析窗口
        win = tk.Toplevel(self.root)
        win.title("🏛️ 港大Vibe增强版分析 - 综合评分+股票池推荐")
        win.geometry("950x700")

        # 主面板
        main_frame = ttk.Frame(win)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)

        # 顶部控制栏
        ctrl = ttk.Frame(main_frame)
        ctrl.pack(fill='x')
        ttk.Label(ctrl, text=f"分析标的: {symbol}", 
                  font=('Microsoft YaHei', 12, 'bold')).pack(side='left')
        
        status_label = ttk.Label(ctrl, text="🔄 正在分析...", foreground='orange')
        status_label.pack(side='right')

        # 创建笔记本
        nb = ttk.Notebook(main_frame)
        nb.pack(fill='both', expand=True, pady=10)

        # ========== 标签1: 综合评分仪表 ==========
        score_tab = ttk.Frame(nb)
        nb.add(score_tab, text="📊 综合评分")
        
        score_text = scrolledtext.ScrolledText(score_tab, bg='#0f0f1a', fg='#ffd700', 
                                               font=('Consolas', 10))
        score_text.pack(fill='both', expand=True, padx=5, pady=5)
        score_text.insert('end', "正在计算综合评分...")

        # ========== 标签2: 股票池推荐 ==========
        pool_tab = ttk.Frame(nb)
        nb.add(pool_tab, text="📦 股票池推荐")
        
        pool_text = scrolledtext.ScrolledText(pool_tab, bg='#0f0f1a', fg='#00ff88', 
                                              font=('Consolas', 10))
        pool_text.pack(fill='both', expand=True, padx=5, pady=5)
        pool_text.insert('end', "正在生成股票池推荐...")

        # ========== 标签3: 详细报告 ==========
        detail_tab = ttk.Frame(nb)
        nb.add(detail_tab, text="📝 详细报告")
        
        detail_text = scrolledtext.ScrolledText(detail_tab, bg='#0f0f1a', fg='#c0c0c0', 
                                               font=('Consolas', 9))
        detail_text.pack(fill='both', expand=True, padx=5, pady=5)
        detail_text.insert('end', "正在生成详细报告...")

        # ========== 标签4: 各维度评分雷达 ==========
        radar_tab = ttk.Frame(nb)
        nb.add(radar_tab, text="🎯 各维度评分")
        
        radar_text = scrolledtext.ScrolledText(radar_tab, bg='#0f0f1a', fg='#00d4ff', 
                                               font=('Consolas', 10))
        radar_text.pack(fill='both', expand=True, padx=5, pady=5)
        radar_text.insert('end', "正在分析各维度...")

        def do_analysis():
            try:
                # 调用增强版分析
                result = self._vibe_integration.analyze_stock_enhanced(symbol, f"深度分析股票{symbol}")
                
                if not result.get('enhanced_analysis'):
                    win.after(0, lambda: status_label.config(text="❌ 分析失败", foreground='red'))
                    return

                enhanced = result['enhanced_analysis']
                
                # 更新综合评分
                win.after(0, lambda: score_text.delete('1.0', 'end'))
                score_report = f"🏛️ Vibe-Trading 综合评分报告\n"
                score_report += "=" * 60 + "\n\n"
                score_report += f"📊 标的: {symbol}\n"
                score_report += f"⏰ 分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                score_report += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                score_report += f"🎯 综合评分: {enhanced['comprehensive_score']:.1f} / 100\n"
                score_report += f"🔒 可信度: {enhanced['confidence_level']}\n"
                score_report += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                
                # 评分等级
                if enhanced['comprehensive_score'] >= 80:
                    grade = "🏆 优秀（强烈推荐）"
                elif enhanced['comprehensive_score'] >= 65:
                    grade = "👍 良好（建议关注）"
                elif enhanced['comprehensive_score'] >= 50:
                    grade = "👀 中等（观望）"
                elif enhanced['comprehensive_score'] >= 35:
                    grade = "⚠️ 偏低（谨慎）"
                else:
                    grade = "❌ 不推荐"
                
                score_report += f"📈 评级: {grade}\n\n"
                score_report += f"💡 推荐操作: {enhanced['recommended_action']}\n\n"
                
                win.after(0, lambda: score_text.insert('end', score_report))

                # 更新股票池推荐
                win.after(0, lambda: pool_text.delete('1.0', 'end'))
                pool_report = f"📦 股票池推荐分析\n"
                pool_report += "=" * 60 + "\n\n"
                pool_report += f"🎯 推荐进入层级: {enhanced['pool_recommendation']}\n\n"
                pool_report += "【股票池层级说明】\n"
                pool_report += "  🏆 实盘池:   评分>=90，经过所有测试，可实盘交易\n"
                pool_report += "  ⚡ 预实盘池: 评分>=80，通过测试筛选，准备进入实盘\n"
                pool_report += "  🔬 测试池:   评分>=65，需经过我们的策略回测验证\n"
                pool_report += "  📋 候选池:   评分>=50，关注观察\n"
                pool_report += "  👀 观察池:   评分>=35，低优先级关注\n"
                pool_report += "  ❌ 不推荐:   评分<35，暂不纳入股票池\n\n"
                
                if enhanced['pool_recommendation'] in ["观察池", "候选池", "测试池", "预实盘池"]:
                    pool_report += f"✅ 该股票符合 {enhanced['pool_recommendation']} 标准\n"
                    pool_report += f"   已自动进入股票池，等待后续流程筛选\n"
                else:
                    pool_report += "⚠️ 该股票暂不满足股票池条件\n"
                    pool_report += "   建议继续观察或寻找其他标的\n"
                
                win.after(0, lambda: pool_text.insert('end', pool_report))

                # 更新各维度评分
                win.after(0, lambda: radar_text.delete('1.0', 'end'))
                radar_report = f"🎯 各维度评分详情\n\n"
                scores = [
                    ("📈 技术面", enhanced['technical_score']),
                    ("💼 基本面", enhanced['fundamental_score']),
                    ("💬 舆情面", enhanced['sentiment_score']),
                    ("🛡️ 风控面", enhanced['risk_score']),
                ]
                
                for name, score in scores:
                    # ASCII条形图
                    bar = '█' * int(score / 5) + '░' * (20 - int(score / 5))
                    color = "🟢" if score >= 65 else ("🟡" if score >= 40 else "🔴")
                    radar_report += f"{name}: {score:5.1f} |{bar}| {color}\n"
                
                radar_report += "\n【评分说明】\n"
                radar_report += "  🟢 65-100: 优秀\n"
                radar_report += "  🟡 40-64:  中等\n"
                radar_report += "  🔴 0-39:   偏低\n"
                
                win.after(0, lambda: radar_text.insert('end', radar_report))

                # 更新详细报告
                win.after(0, lambda: detail_text.delete('1.0', 'end'))
                
                # 技术分析详情
                tech = result.get('technical', {})
                fund = result.get('fundamental', {})
                sent = result.get('sentiment', {})
                risk = result.get('risk', {})
                
                full_report = f"📝 Vibe-Trading 完整分析报告\n"
                full_report += "=" * 60 + "\n\n"
                full_report += "【技术分析】\n"
                full_report += f"  趋势判断: {tech.get('trend', '未知')}\n"
                full_report += f"  支撑位:   {tech.get('support', '--')}\n"
                full_report += f"  阻力位:   {tech.get('resistance', '--')}\n"
                full_report += f"  RSI:      {tech.get('rsi', '--')}\n"
                full_report += f"  MACD:     {tech.get('macd_signal', '--')}\n\n"
                
                full_report += "【基本面分析】\n"
                full_report += f"  PE:       {fund.get('pe', '--')}\n"
                full_report += f"  PB:       {fund.get('pb', '--')}\n"
                full_report += f"  ROE:      {fund.get('roe', '--')}%\n"
                full_report += f"  营收增长: {fund.get('revenue_growth', '--')}%\n\n"
                
                full_report += "【舆情分析】\n"
                full_report += f"  情绪分数: {sent.get('sentiment_score', '--')}\n"
                full_report += f"  正面比例: {sent.get('positive_ratio', '--')}%\n"
                full_report += f"  市场情绪: {sent.get('market_sentiment', '--')}\n\n"
                
                full_report += "【风控分析】\n"
                full_report += f"  风险评分: {risk.get('risk_score', '--')}\n"
                full_report += f"  最大回撤: {risk.get('max_drawdown', '--')}%\n"
                full_report += f"  波动率:   {risk.get('volatility', '--')}%\n\n"
                
                full_report += "【综合建议】\n"
                full_report += f"  操作建议: {enhanced['recommended_action']}\n"
                full_report += f"  股票池层级: {enhanced['pool_recommendation']}\n"
                full_report += f"  综合评分: {enhanced['comprehensive_score']:.1f}\n"
                
                win.after(0, lambda: detail_text.insert('end', full_report))
                
                win.after(0, lambda: status_label.config(text="✅ 分析完成", foreground='green'))

            except Exception as e:
                win.after(0, lambda: status_label.config(text=f"❌ 失败: {e}", foreground='red'))

        threading.Thread(target=do_analysis, daemon=True).start()

    def _run_hybrid_power_flow(self):
        """启动强强联合流程（韬定律+港大+股票池+风控）"""
        selected = self._get_selected_strategy()
        if not selected:
            messagebox.showinfo("提示", "请先在策略列表中选中一个策略")
            return

        # 创建流程窗口
        win = tk.Toplevel(self.root)
        win.title("🚀 强强联合流程 - 韬定律优化 + 港大分析 + 股票池 + 风控")
        win.geometry("900x600")

        main_frame = ttk.Frame(win)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)

        ctrl = ttk.Frame(main_frame)
        ctrl.pack(fill='x')
        ttk.Label(ctrl, text=f"运行策略: {selected}", 
                  font=('Microsoft YaHei', 12, 'bold')).pack(side='left')
        status_label = ttk.Label(ctrl, text="🔄 运行中...", foreground='orange')
        status_label.pack(side='right')

        report_text = scrolledtext.ScrolledText(main_frame, bg='#0f0f1a', fg='#00ff88',
                                               font=('Consolas', 10))
        report_text.pack(fill='both', expand=True, pady=10)
        report_text.insert('end', "正在执行强强联合流程...\n\n")

        def run_flow():
            try:
                from core.integration_bus import get_integration_bus
                bus = get_integration_bus()
                
                result = bus.auto_hybrid_power_flow(selected)
                
                if result.get('success'):
                    report_str = result.get('report', '✅ 流程完成')
                    win.after(0, lambda: report_text.delete('1.0', 'end'))
                    win.after(0, lambda: report_text.insert('end', report_str))
                    win.after(0, lambda: status_label.config(text="✅ 流程完成", foreground='green'))
                else:
                    err = result.get('error', '未知错误')
                    win.after(0, lambda: report_text.insert('end', f"\n❌ 失败: {err}"))
                    win.after(0, lambda: status_label.config(text="❌ 失败", foreground='red'))
            except Exception as e:
                win.after(0, lambda: report_text.insert('end', f"\n❌ 异常: {e}"))
                win.after(0, lambda: status_label.config(text="❌ 异常", foreground='red'))

        threading.Thread(target=run_flow, daemon=True).start()

    def _build_stock_pool_tab(self, notebook):
        """股票池管理标签页"""
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="📦 股票池")

        # 股票池管理器
        self._stock_pool_mgr = None
        self._integration_bus = None
        try:
            from core.stock_pool import get_stock_pool_manager
            from core.integration_bus import get_integration_bus
            self._stock_pool_mgr = get_stock_pool_manager()
            self._integration_bus = get_integration_bus()
        except Exception as e:
            print(f"[WARNING] 股票池模块不可用: {e}")

        # 顶部工具栏
        toolbar = ttk.Frame(tab)
        toolbar.pack(fill='x', padx=5, pady=5)

        ttk.Button(toolbar, text="🔄 刷新股票池", command=self._refresh_stock_pool).pack(side='left', padx=2)
        ttk.Button(toolbar, text="➕ 添加股票", command=self._show_add_stock_dialog).pack(side='left', padx=2)
        ttk.Button(toolbar, text="⬆️ 批量升级", command=self._batch_promote_stocks).pack(side='left', padx=2)
        ttk.Button(toolbar, text="🗑️ 移除选中", command=self._remove_selected_stock).pack(side='left', padx=2)
        ttk.Separator(toolbar, orient='vertical').pack(side='left', fill='y', padx=5)
        ttk.Button(toolbar, text="🚀 执行股票池流程", command=self._run_stock_pool_flow, style='Accent.TButton').pack(side='left', padx=5)

        # 左右分栏
        left = ttk.Frame(tab)
        left.pack(side='left', fill='both', expand=True, padx=5, pady=(0, 5))
        right = ttk.Frame(tab)
        right.pack(side='right', fill='both', expand=True, padx=5, pady=(0, 5))

        # 左侧：股票池统计卡片
        stats_frame = ttk.Frame(left)
        stats_frame.pack(fill='x', pady=(0, 5))
        ttk.Label(stats_frame, text="股票池统计", font=('Microsoft YaHei', 11, 'bold')).pack(anchor='w')

        # 5个池的统计
        pool_stats = ttk.Frame(stats_frame)
        pool_stats.pack(fill='x', pady=5)

        self._pool_watchlist = tk.StringVar(value="0")
        self._pool_candidate = tk.StringVar(value="0")
        self._pool_testing = tk.StringVar(value="0")
        self._pool_prelive = tk.StringVar(value="0")
        self._pool_live = tk.StringVar(value="0")

        pool_config = [
            ("观察池", self._pool_watchlist, '#888888', 'watchlist'),
            ("候选池", self._pool_candidate, '#00d4ff', 'candidate'),
            ("测试池", self._pool_testing, '#ffaa00', 'testing'),
            ("预实盘池", self._pool_prelive, '#00ff88', 'prelive'),
            ("实盘池", self._pool_live, '#ff4444', 'live'),
        ]

        for label, var, color, level in pool_config:
            card = tk.Frame(pool_stats, bg='#16213e', width=100, height=65)
            card.pack(side='left', padx=3, fill='x', expand=True)
            card.pack_propagate(False)
            tk.Label(card, text=label, bg='#16213e', fg='#888888', font=('Microsoft YaHei', 8)).pack(pady=(8, 0))
            tk.Label(card, textvariable=var, bg='#16213e', fg=color, font=('Arial', 18, 'bold')).pack()

        # 股票列表
        ttk.Label(left, text="股票列表", font=('Microsoft YaHei', 11, 'bold')).pack(anchor='w', pady=(10, 5))

        columns = ('symbol', 'name', 'level', 'score', 'risk')
        self._stock_tree = ttk.Treeview(left, columns=columns, show='headings', height=15)
        self._stock_tree.heading('symbol', text='代码')
        self._stock_tree.heading('name', text='名称')
        self._stock_tree.heading('level', text='池')
        self._stock_tree.heading('score', text='评分')
        self._stock_tree.heading('risk', text='风控')
        self._stock_tree.column('symbol', width=80)
        self._stock_tree.column('name', width=120)
        self._stock_tree.column('level', width=80)
        self._stock_tree.column('score', width=80)
        self._stock_tree.column('risk', width=80)
        self._stock_tree.pack(fill='both', expand=True)

        self._stock_tree.bind('<Double-1>', self._on_stock_double_click)

        # 右侧：股票详情和操作
        ttk.Label(right, text="股票详情", font=('Microsoft YaHei', 11, 'bold')).pack(anchor='w')

        detail_frame = ttk.Frame(right)
        detail_frame.pack(fill='x', pady=5)

        ttk.Label(detail_frame, text="代码:", font=('Microsoft YaHei', 9)).grid(row=0, column=0, sticky='w')
        self._stock_detail_symbol = tk.StringVar(value="--")
        ttk.Label(detail_frame, textvariable=self._stock_detail_symbol, font=('Microsoft YaHei', 10)).grid(row=0, column=1, sticky='w', padx=10)

        ttk.Label(detail_frame, text="名称:", font=('Microsoft YaHei', 9)).grid(row=1, column=0, sticky='w')
        self._stock_detail_name = tk.StringVar(value="--")
        ttk.Label(detail_frame, textvariable=self._stock_detail_name).grid(row=1, column=1, sticky='w', padx=10)

        ttk.Label(detail_frame, text="当前池:", font=('Microsoft YaHei', 9)).grid(row=2, column=0, sticky='w')
        self._stock_detail_level = tk.StringVar(value="--")
        ttk.Label(detail_frame, textvariable=self._stock_detail_level).grid(row=2, column=1, sticky='w', padx=10)

        ttk.Label(detail_frame, text="风控评分:", font=('Microsoft YaHei', 9)).grid(row=3, column=0, sticky='w')
        self._stock_detail_risk = tk.StringVar(value="--")
        ttk.Label(detail_frame, textvariable=self._stock_detail_risk).grid(row=3, column=1, sticky='w', padx=10)

        # 升级操作
        ttk.Label(right, text="升级操作", font=('Microsoft YaHei', 11, 'bold')).pack(anchor='w', pady=(10, 5))
        level_buttons = ttk.Frame(right)
        level_buttons.pack(fill='x')

        ttk.Button(level_buttons, text="→ 候选池", command=lambda: self._promote_to('candidate')).pack(side='left', padx=2)
        ttk.Button(level_buttons, text="→ 测试池", command=lambda: self._promote_to('testing')).pack(side='left', padx=2)
        ttk.Button(level_buttons, text="→ 预实盘", command=lambda: self._promote_to('prelive')).pack(side='left', padx=2)
        ttk.Button(level_buttons, text="→ 实盘", command=lambda: self._promote_to('live')).pack(side='left', padx=2)

        # 流程日志
        ttk.Label(right, text="流程日志", font=('Microsoft YaHei', 11, 'bold')).pack(anchor='w', pady=(10, 5))
        self._stock_pool_log = scrolledtext.ScrolledText(right, height=8, bg='#0f0f1a', fg='#00ff88', font=('Consolas', 9))
        self._stock_pool_log.pack(fill='both', expand=True)

        # 初始化刷新
        self._refresh_stock_pool()

    def _refresh_stock_pool(self):
        """刷新股票池列表"""
        if not self._stock_pool_mgr:
            return

        try:
            summary = self._stock_pool_mgr.get_pool_summary()
            self._pool_watchlist.set(summary.get('watchlist', 0))
            self._pool_candidate.set(summary.get('candidate', 0))
            self._pool_testing.set(summary.get('testing', 0))
            self._pool_prelive.set(summary.get('prelive', 0))
            self._pool_live.set(summary.get('live', 0))

            self._stock_tree.delete(*self._stock_tree.get_children())
            all_stocks = self._stock_pool_mgr.get_all_stocks()

            level_names = {
                'watchlist': '观察',
                'candidate': '候选',
                'testing': '测试',
                'prelive': '预实盘',
                'live': '实盘'
            }

            for stock in all_stocks:
                level = stock.level.value if hasattr(stock.level, 'value') else stock.level
                self._stock_tree.insert('', 'end', values=(
                    stock.symbol,
                    stock.name,
                    level_names.get(level, level),
                    stock.metadata.get('score', '--'),
                    f"{stock.risk_score:.1f}" if stock.risk_score > 0 else '--'
                ))

        except Exception as e:
            self._log(f"[ERROR] 刷新股票池失败: {e}")

    def _show_add_stock_dialog(self):
        """显示添加股票对话框"""
        dialog = tk.Toplevel(self.root)
        dialog.title("添加股票")
        dialog.geometry("350x200")
        dialog.resizable(False, False)

        ttk.Label(dialog, text="股票代码:").grid(row=0, column=0, padx=10, pady=10, sticky='w')
        symbol_entry = ttk.Entry(dialog, width=20)
        symbol_entry.grid(row=0, column=1, padx=10, pady=10)

        ttk.Label(dialog, text="股票名称:").grid(row=1, column=0, padx=10, pady=10, sticky='w')
        name_entry = ttk.Entry(dialog, width=20)
        name_entry.grid(row=1, column=1, padx=10, pady=10)

        def add_stock():
            symbol = symbol_entry.get().strip()
            name = name_entry.get().strip()
            if not symbol:
                messagebox.showwarning("提示", "请输入股票代码")
                return

            if not name:
                name = symbol

            if self._stock_pool_mgr:
                result = self._stock_pool_mgr.add_stock(symbol, name)
                if result['success']:
                    messagebox.showinfo("成功", f"已添加 {symbol} {name} 到观察池")
                    self._refresh_stock_pool()
                else:
                    messagebox.showwarning("提示", result.get('error', '添加失败'))
            dialog.destroy()

        ttk.Button(dialog, text="确定", command=add_stock, style='Accent.TButton').grid(row=2, column=0, padx=10, pady=10)
        ttk.Button(dialog, text="取消", command=dialog.destroy).grid(row=2, column=1, padx=10, pady=10)

    def _remove_selected_stock(self):
        """移除选中的股票"""
        selection = self._stock_tree.selection()
        if not selection:
            messagebox.showwarning("提示", "请先选中股票")
            return

        symbol = self._stock_tree.item(selection[0], 'values')[0]
        name = self._stock_tree.item(selection[0], 'values')[1]

        if messagebox.askyesno("确认", f"确定要移除 {symbol} {name} 吗？"):
            if self._stock_pool_mgr:
                result = self._stock_pool_mgr.remove_stock(symbol)
                if result['success']:
                    self._log(f"已移除股票: {symbol}")
                    self._refresh_stock_pool()
                else:
                    messagebox.showwarning("提示", result.get('error', '移除失败'))

    def _promote_to(self, target_level):
        """升级选中股票到目标池"""
        selection = self._stock_tree.selection()
        if not selection:
            messagebox.showwarning("提示", "请先选中股票")
            return

        symbol = self._stock_tree.item(selection[0], 'values')[0]

        if self._stock_pool_mgr:
            from core.stock_pool import PoolLevel
            try:
                level = PoolLevel(target_level)
                result = self._stock_pool_mgr.promote(symbol, level)
                if result['success']:
                    messagebox.showinfo("成功", result['message'])
                    self._refresh_stock_pool()
                else:
                    messagebox.showwarning("提示", result.get('error', '升级失败'))
            except ValueError:
                messagebox.showerror("错误", "无效的目标池")

    def _batch_promote_stocks(self):
        """批量升级所有可升级的股票"""
        if not self._stock_pool_mgr:
            return

        results = self._stock_pool_mgr.auto_promote_all()
        success_count = sum(1 for r in results if r.get('success'))
        self._log(f"批量升级完成: 成功 {success_count}/{len(results)}")
        self._refresh_stock_pool()
        messagebox.showinfo("完成", f"批量升级完成: 成功 {success_count}/{len(results)}")

    def _on_stock_double_click(self, event):
        """双击股票查看详情"""
        selection = self._stock_tree.selection()
        if not selection:
            return

        symbol = self._stock_tree.item(selection[0], 'values')[0]
        name = self._stock_tree.item(selection[0], 'values')[1]
        level = self._stock_tree.item(selection[0], 'values')[2]
        risk = self._stock_tree.item(selection[0], 'values')[4]

        self._stock_detail_symbol.set(symbol)
        self._stock_detail_name.set(name)
        self._stock_detail_level.set(level)
        self._stock_detail_risk.set(risk)

    def _run_stock_pool_flow(self):
        """执行股票池完整流程"""
        if not self._integration_bus:
            messagebox.showerror("错误", "集成总线不可用")
            return

        self._stock_pool_log.delete('1.0', 'end')
        self._stock_pool_log.insert('end', f"[{datetime.now().strftime('%H:%M:%S')}] 开始执行股票池流程...\n")
        self.root.update()

        def run_thread():
            try:
                report = self._integration_bus.auto_stock_pool_flow_for_strategy("伯努利-康达策略")
                self._stock_pool_log.insert('end', f"[{datetime.now().strftime('%H:%M:%S')}] 流程完成\n")
                self._stock_pool_log.insert('end', f"  处理股票数: {report.get('processed_stocks', 0)}\n")
                self._stock_pool_log.insert('end', f"  候选池: {report.get('candidate_count', 0)}\n")
                self._stock_pool_log.insert('end', f"  测试池: {report.get('testing_count', 0)}\n")
                self._stock_pool_log.insert('end', f"  预实盘池: {report.get('prelive_count', 0)}\n")

                details = report.get('details', [])
                for detail in details:
                    status = "✅" if detail.get('status') == 'passed' else "❌"
                    self._stock_pool_log.insert('end', f"  {status} {detail.get('symbol')} {detail.get('name')}: {detail.get('new_level') or detail.get('reason')}\n")

                self.root.after(0, self._refresh_stock_pool)
            except Exception as e:
                self._stock_pool_log.insert('end', f"[{datetime.now().strftime('%H:%M:%S')}] ❌ 失败: {e}\n")

        threading.Thread(target=run_thread, daemon=True).start()

    def _build_monitor_tab(self, notebook):
        """系统监控标签页（增强版）"""
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="🔍 系统监控")

        # 创建笔记本用于标签切换
        monitor_notebook = ttk.Notebook(tab)
        monitor_notebook.pack(fill='both', expand=True, padx=5, pady=5)

        # 标签1: 系统状态
        status_tab = ttk.Frame(monitor_notebook)
        monitor_notebook.add(status_tab, text="🖥️ 系统状态")

        # 健康状态
        health_frame = ttk.Frame(status_tab)
        health_frame.pack(fill='x', padx=5, pady=5)

        ttk.Label(health_frame, text="系统健康状态",
                  font=('Microsoft YaHei', 12, 'bold')).pack(anchor='w')

        self._health_text = scrolledtext.ScrolledText(
            health_frame, height=8, bg='#0f0f1a', fg='#e0e0e0',
            font=('Consolas', 9), state='disabled'
        )
        self._health_text.pack(fill='x', pady=5)

        # 增益模块
        gain_frame = ttk.Frame(status_tab)
        gain_frame.pack(fill='x', padx=5, pady=5)
        ttk.Label(gain_frame, text="5大增益模块状态",
                  font=('Microsoft YaHei', 12, 'bold')).pack(anchor='w')

        columns = ('module', 'status', 'metrics')
        self._gain_tree = ttk.Treeview(gain_frame, columns=columns, show='headings', height=6)
        self._gain_tree.heading('module', text='模块')
        self._gain_tree.heading('status', text='状态')
        self._gain_tree.heading('metrics', text='指标')
        self._gain_tree.column('module', width=150)
        self._gain_tree.column('status', width=80)
        self._gain_tree.column('metrics', width=300)
        self._gain_tree.pack(fill='x', pady=5)

        # 风险状态
        risk_frame = ttk.Frame(status_tab)
        risk_frame.pack(fill='x', padx=5, pady=5)
        ttk.Label(risk_frame, text="风险控制状态",
                  font=('Microsoft YaHei', 12, 'bold')).pack(anchor='w')
        self._risk_text = scrolledtext.ScrolledText(
            risk_frame, height=8, bg='#0f0f1a', fg='#e0e0e0',
            font=('Consolas', 9), state='disabled'
        )
        self._risk_text.pack(fill='x', pady=5)

        # 标签2: 任务调度器
        scheduler_tab = ttk.Frame(monitor_notebook)
        monitor_notebook.add(scheduler_tab, text="📋 任务调度")

        # 控制面板
        ctrl = ttk.Frame(scheduler_tab)
        ctrl.pack(fill='x', padx=5, pady=5)

        ttk.Button(ctrl, text="▶ 启动调度器", command=self._start_scheduler,
                   style='Accent.TButton').pack(side='left', padx=5)
        ttk.Button(ctrl, text="⏹ 停止调度器", command=self._stop_scheduler).pack(side='left', padx=5)
        ttk.Button(ctrl, text="➕ 添加任务", command=self._add_scheduler_task).pack(side='left', padx=5)
        ttk.Label(ctrl, text="状态: ").pack(side='left', padx=(10, 0))
        self._scheduler_status = ttk.Label(ctrl, text="未启动", foreground='red')
        self._scheduler_status.pack(side='left', padx=5)

        # 任务列表
        task_columns = ('id', 'name', 'type', 'status', 'next_run', 'run_count')
        self._task_tree = ttk.Treeview(scheduler_tab, columns=task_columns, show='headings', height=8)
        self._task_tree.heading('id', text='ID')
        self._task_tree.heading('name', text='名称')
        self._task_tree.heading('type', text='类型')
        self._task_tree.heading('status', text='状态')
        self._task_tree.heading('next_run', text='下次运行')
        self._task_tree.heading('run_count', text='运行次数')
        self._task_tree.column('id', width=80)
        self._task_tree.column('name', width=150)
        self._task_tree.column('type', width=80)
        self._task_tree.column('status', width=80)
        self._task_tree.column('next_run', width=100)
        self._task_tree.column('run_count', width=80)
        self._task_tree.pack(fill='x', padx=5)

        # 任务操作
        action_frame = ttk.Frame(scheduler_tab)
        action_frame.pack(fill='x', padx=5, pady=5)
        ttk.Button(action_frame, text="▶ 立即执行", command=self._run_task_now).pack(side='left', padx=5)
        ttk.Button(action_frame, text="⏸ 暂停", command=self._pause_task).pack(side='left', padx=5)
        ttk.Button(action_frame, text="▶ 恢复", command=self._resume_task).pack(side='left', padx=5)
        ttk.Button(action_frame, text="🗑 删除", command=self._delete_task).pack(side='left', padx=5)

        # 任务日志
        ttk.Label(scheduler_tab, text="📝 任务日志", font=('Microsoft YaHei', 11, 'bold')).pack(anchor='w', padx=5)
        self._task_log = scrolledtext.ScrolledText(scheduler_tab, height=6, bg='#0f0f1a',
                                                  fg='#00ff88', font=('Consolas', 9))
        self._task_log.pack(fill='both', expand=True, padx=5)

        # 标签3: 实时行情
        realtime_tab = ttk.Frame(monitor_notebook)
        monitor_notebook.add(realtime_tab, text="📡 实时行情")

        # 控制面板
        realtime_ctrl = ttk.Frame(realtime_tab)
        realtime_ctrl.pack(fill='x', padx=5, pady=5)

        ttk.Entry(realtime_ctrl, width=12, textvariable=tk.StringVar(value="000001")).pack(side='left', padx=5)
        ttk.Button(realtime_ctrl, text="➕ 订阅", command=self._subscribe_realtime).pack(side='left', padx=5)
        ttk.Button(realtime_ctrl, text="▶ 开始轮询", command=self._start_realtime_polling,
                   style='Accent.TButton').pack(side='left', padx=5)
        ttk.Button(realtime_ctrl, text="⏹ 停止轮询", command=self._stop_realtime_polling).pack(side='left', padx=5)
        ttk.Label(realtime_ctrl, text="状态: ").pack(side='left', padx=(10, 0))
        self._realtime_status = ttk.Label(realtime_ctrl, text="未启动", foreground='red')
        self._realtime_status.pack(side='left', padx=5)

        # 行情列表
        quote_columns = ('symbol', 'name', 'price', 'change_pct', 'volume', 'update_time')
        self._quote_tree = ttk.Treeview(realtime_tab, columns=quote_columns, show='headings', height=8)
        self._quote_tree.heading('symbol', text='代码')
        self._quote_tree.heading('name', text='名称')
        self._quote_tree.heading('price', text='现价')
        self._quote_tree.heading('change_pct', text='涨跌幅')
        self._quote_tree.heading('volume', text='成交量')
        self._quote_tree.heading('update_time', text='更新时间')
        self._quote_tree.column('symbol', width=80)
        self._quote_tree.column('name', width=100)
        self._quote_tree.column('price', width=80)
        self._quote_tree.column('change_pct', width=80)
        self._quote_tree.column('volume', width=100)
        self._quote_tree.column('update_time', width=100)
        self._quote_tree.pack(fill='x', padx=5)

        # 预警日志
        ttk.Label(realtime_tab, text="⚠️ 预警日志", font=('Microsoft YaHei', 11, 'bold')).pack(anchor='w', padx=5)
        self._alert_log = scrolledtext.ScrolledText(realtime_tab, height=6, bg='#0f0f1a',
                                                   fg='#ff6b6b', font=('Consolas', 9))
        self._alert_log.pack(fill='both', expand=True, padx=5)

    def _build_action_bar(self):
        """底部操作栏 - 增强版：系统切换 + 一键流程自动化 + LLM模型切换"""
        bar = ttk.Frame(self.root)
        bar.pack(fill='x', padx=5, pady=3)

        ttk.Checkbutton(bar, text="自动刷新(30s)", variable=self._auto_refresh).pack(side='left', padx=5)
        ttk.Button(bar, text="🔽 最小化到托盘", command=self._minimize_to_tray).pack(side='left', padx=5)

        # LLM模型切换
        llm_frame = ttk.LabelFrame(bar, text="🤖 LLM模型")
        llm_frame.pack(side='left', padx=10)
        
        # 自动切换开关
        self._auto_switch_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(llm_frame, text="智能切换", variable=self._auto_switch_var,
                        command=self._on_auto_switch_toggle).pack(side='left', padx=3)
        
        # 任务类型选择
        ttk.Label(llm_frame, text="任务:").pack(side='left', padx=5)
        self._llm_task_type = ttk.Combobox(llm_frame, width=15, state='readonly')
        self._llm_task_type.pack(side='left', padx=3)
        self._llm_task_type.bind('<<ComboboxSelected>>', self._on_task_type_change)
        
        ttk.Label(llm_frame, text="提供者:").pack(side='left', padx=5)
        self._llm_provider = ttk.Combobox(llm_frame, width=10, state='readonly')
        self._llm_provider.pack(side='left', padx=3)
        self._llm_provider.bind('<<ComboboxSelected>>', self._on_llm_provider_change)
        
        ttk.Label(llm_frame, text="模型:").pack(side='left', padx=5)
        self._llm_model = ttk.Combobox(llm_frame, width=20, state='readonly')
        self._llm_model.pack(side='left', padx=3)
        self._llm_model.bind('<<ComboboxSelected>>', self._on_llm_model_change)
        
        self._llm_status = ttk.Label(llm_frame, text="✓", foreground='#00ff88')
        self._llm_status.pack(side='left', padx=5)
        
        self._refresh_llm_providers()
        self._refresh_task_types()

        # 系统切换：Web 界面跳转
        web_frame = ttk.LabelFrame(bar, text="🌐 系统切换")
        web_frame.pack(side='left', padx=10)
        ttk.Button(web_frame, text="🎯 主系统",
                   command=lambda: self._open_web_system('main')).pack(side='left', padx=3)
        ttk.Button(web_frame, text="📊 股票池",
                   command=lambda: self._open_web_system('stock_pool')).pack(side='left', padx=3)
        ttk.Button(web_frame, text="📈 技术分析",
                   command=lambda: self._open_web_system('technical_analysis')).pack(side='left', padx=3)

        # 固定流程自动化：一键调用集成总线
        flow_frame = ttk.LabelFrame(bar, text="⚙️ 一键流程自动化")
        flow_frame.pack(side='left', padx=10)
        ttk.Button(flow_frame, text="🎯 韬定律优化→应用",
                   command=lambda: self._run_auto_flow('optimize')).pack(side='left', padx=3)
        ttk.Button(flow_frame, text="📊 股票池自动流转",
                   command=lambda: self._run_auto_flow('stock_pool')).pack(side='left', padx=3)
        ttk.Button(flow_frame, text="🔄 完整工作流",
                   command=lambda: self._run_auto_flow('full')).pack(side='left', padx=3)
        ttk.Button(flow_frame, text="🤖 港大Vibe选股",
                   command=lambda: self._run_auto_flow('vibe')).pack(side='left', padx=3)
        ttk.Button(flow_frame, text="⚡ 强强联合",
                   command=lambda: self._run_auto_flow('hybrid')).pack(side='left', padx=3)

        ttk.Button(bar, text="❌ 退出", command=self._quit_app).pack(side='right', padx=5)

        ttk.Label(bar, text="QS Robot V2.0 | 三系统互通",
                  font=('Microsoft YaHei', 8), foreground='#555555').pack(side='right', padx=20)
    
    def _refresh_llm_providers(self):
        """刷新LLM提供者列表"""
        try:
            from llm_manager import llm_manager
            providers = llm_manager.list_providers()
            self._llm_provider['values'] = providers if providers else ['无可用提供者']
            
            if providers:
                current_provider = llm_manager.active_provider.name if llm_manager.active_provider else providers[0]
                self._llm_provider.set(current_provider)
                self._refresh_llm_models()
        except Exception as e:
            self._llm_provider['values'] = ['LLM未初始化']
            self._llm_status.config(text="✗", foreground='#ff4444')
    
    def _refresh_llm_models(self):
        """刷新当前提供者的模型列表"""
        try:
            from llm_manager import llm_manager
            provider_name = self._llm_provider.get()
            provider = llm_manager.get_provider(provider_name)
            
            if provider:
                models = provider.get_available_models()
                self._llm_model['values'] = models if models else ['获取模型列表失败']
                
                if models:
                    self._llm_model.set(provider.model)
                
                if provider.is_available():
                    self._llm_status.config(text="✓", foreground='#00ff88')
                else:
                    self._llm_status.config(text="⚠", foreground='#ffaa00')
        except Exception as e:
            self._llm_model['values'] = ['加载失败']
            self._llm_status.config(text="✗", foreground='#ff4444')
    
    def _on_llm_provider_change(self, event):
        """切换LLM提供者"""
        try:
            from llm_manager import llm_manager
            provider_name = self._llm_provider.get()
            
            if llm_manager.set_active_provider(provider_name):
                self._log(f"已切换LLM提供者: {provider_name}")
                self._refresh_llm_models()
            else:
                self._log(f"切换LLM提供者失败: {provider_name}")
        except Exception as e:
            self._log(f"LLM提供者切换异常: {str(e)}")
    
    def _on_llm_model_change(self, event):
        """切换LLM模型"""
        try:
            from llm_manager import llm_manager
            model_name = self._llm_model.get()
            
            if llm_manager.set_model(model_name):
                self._log(f"已切换LLM模型: {model_name}")
            else:
                self._log(f"切换LLM模型失败: {model_name}")
        except Exception as e:
            self._log(f"LLM模型切换异常: {str(e)}")
    
    def _refresh_task_types(self):
        """刷新任务类型列表"""
        try:
            from llm_manager import llm_manager
            task_types = llm_manager.get_task_types()
            descriptions = [llm_manager.get_task_type_description(t) for t in task_types]
            self._llm_task_type['values'] = descriptions if descriptions else ['获取任务类型失败']
            if descriptions:
                self._llm_task_type.set(descriptions[0])
        except Exception as e:
            self._llm_task_type['values'] = ['加载失败']
    
    def _on_auto_switch_toggle(self):
        """切换智能自动开关"""
        try:
            from llm_manager import llm_manager
            enabled = self._auto_switch_var.get()
            llm_manager.enable_auto_switch(enabled)
            
            if enabled:
                self._log("已启用智能模型切换")
            else:
                self._log("已禁用智能模型切换")
        except Exception as e:
            self._log(f"智能切换开关异常: {str(e)}")
    
    def _on_task_type_change(self, event):
        """切换任务类型并自动选择最优模型"""
        try:
            from llm_manager import llm_manager
            
            selected_desc = self._llm_task_type.get()
            task_types = llm_manager.get_task_types()
            
            for task_type in task_types:
                if llm_manager.get_task_type_description(task_type) == selected_desc:
                    llm_manager.set_task_type(task_type)
                    
                    if self._auto_switch_var.get():
                        llm_manager.switch_to_best_model(task_type)
                        self._log(f"已切换任务类型: {selected_desc}，自动选择最优模型")
                        self._refresh_llm_providers()
                    else:
                        self._log(f"已设置任务类型: {selected_desc}")
                    break
        except Exception as e:
            self._log(f"任务类型切换异常: {str(e)}")

    # ---- 事件处理 ----

    def _on_close(self):
        """关闭窗口 = 最小化到托盘"""
        if messagebox.askyesno("QS Robot", "是否最小化到系统托盘？\n\n(选择「否」将退出程序)"):
            self._minimize_to_tray()
        else:
            self._quit_app()

    def _minimize_to_tray(self):
        """最小化到系统托盘悬浮球"""
        self.root.withdraw()
        self.tray_ball.show()
        self._log("已最小化到托盘，双击悬浮球还原")

    def _quit_app(self):
        """退出应用"""
        self._running = False
        self.tray_ball.hide()
        self.root.destroy()
        sys.exit(0)

    def _open_aurora(self):
        """打开Aurora Web界面"""
        import webbrowser
        webbrowser.open("http://localhost:5000")
        self._log("已打开Aurora Web界面")

    def _open_web_system(self, system_type: str):
        """打开指定的 Web 系统页面"""
        import webbrowser
        paths = {
            'main': '/',
            'stock_pool': '/stock_pool',
            'technical_analysis': '/technical_analysis',
        }
        url = f"http://localhost:5000{paths.get(system_type, '/')}"
        webbrowser.open(url)
        self._log(f"已打开Web系统: {system_type} -> {url}")

    def _run_auto_flow(self, flow_type: str):
        """执行固定流程自动化（调用集成总线）"""
        # 使用子线程执行，避免阻塞 GUI
        import threading
        flow_descriptions = {
            'optimize': '韬定律优化→回测→应用',
            'stock_pool': '股票池自动流转',
            'full': '完整工作流（优化→股票池→交易配置）',
            'vibe': '港大Vibe智能体选股',
            'hybrid': '强强联合工作流',
            'batch': '批量自动化',
        }
        desc = flow_descriptions.get(flow_type, flow_type)

        # 弹出策略选择对话框
        import tkinter.simpledialog as simpledialog
        strategy = simpledialog.askstring("策略选择",
                                          f"执行流程: {desc}\n\n请输入策略名称:",
                                          initialvalue="GyroStrategyV7",
                                          parent=self.root)
        if not strategy:
            return

        self._set_status(f"执行中: {desc}...", 'orange')
        self._log(f"[自动化] 启动流程: {desc} (策略={strategy})")

        def run_in_thread():
            """子线程执行流程"""
            try:
                # 优先通过集成总线执行（如果可用）
                if hasattr(self, 'strategy_mgr') and self.strategy_mgr:
                    from core.integration_bus import get_integration_bus
                    bus = get_integration_bus()

                    if flow_type == 'optimize' or flow_type == 'full':
                        result = bus.auto_full_workflow(strategy_name=strategy)
                    elif flow_type == 'stock_pool':
                        result = bus.auto_match_stock_pool(strategy_name=strategy)
                    elif flow_type == 'batch':
                        result = bus.auto_batch_optimize([strategy])
                    elif flow_type == 'vibe':
                        result = bus.auto_vibe_stock_selection([strategy])
                    elif flow_type == 'hybrid':
                        result = bus.auto_hybrid_power_flow(strategy_name=strategy)
                    else:
                        result = {"success": False, "message": f"未知流程类型: {flow_type}"}

                    status = "✅ 成功" if result.get('success') else "❌ 失败"
                    msg = result.get('message', result.get('error', ''))
                    self.root.after(0, lambda: self._log(f"[自动化] {desc} - {status} - {msg[:200]}"))
                    self.root.after(0, lambda: self._set_status(f"{status}: {desc}",
                                                                'green' if result.get('success') else 'red'))
                else:
                    # 回退到通过 HTTP API 调用
                    import requests
                    endpoints = {
                        'optimize': '/api/integration/full_workflow',
                        'stock_pool': '/api/integration/stock_pool',
                        'full': '/api/integration/full_workflow',
                        'vibe': '/api/vibe/analyze_enhanced',
                        'hybrid': '/api/integration/hybrid_power',
                        'batch': '/api/integration/batch_optimize',
                    }
                    endpoint = endpoints.get(flow_type, '/api/integration/full_workflow')
                    url = f"http://localhost:5000{endpoint}"

                    try:
                        resp = requests.post(url, json={'strategy': strategy, 'strategy_name': strategy},
                                            timeout=300)
                        data = resp.json()
                        status = "✅ 成功" if data.get('success') else "❌ 失败"
                        msg = data.get('message', data.get('error', ''))
                        self.root.after(0, lambda: self._log(f"[自动化] {desc} - {status} - {msg[:200]}"))
                        self.root.after(0, lambda: self._set_status(f"{status}: {desc}",
                                                                    'green' if data.get('success') else 'red'))
                    except Exception as e:
                        self.root.after(0, lambda: self._log(f"[自动化] {desc} - 调用失败: {e}"))
                        self.root.after(0, lambda: self._set_status(f"❌ 调用失败: {desc}", 'red'))

            except Exception as e:
                self.root.after(0, lambda: self._log(f"[自动化] {desc} - 异常: {e}"))
                self.root.after(0, lambda: self._set_status(f"❌ 异常: {desc}", 'red'))

        threading.Thread(target=run_in_thread, daemon=True).start()

    # ---- 刷新逻辑 ----

    def _auto_refresh_loop(self):
        """自动刷新循环（每30秒）"""
        while self._running:
            try:
                if self._auto_refresh.get():
                    self.root.after(0, self._refresh_all)
            except Exception:
                pass
            time.sleep(30)

    def _refresh_all(self):
        """刷新所有数据"""
        if not self.strategy_mgr:
            self._set_status("策略管理器不可用", 'red')
            return

        try:
            # 更新模式
            mode = self.strategy_mgr.get_mode()
            mode_labels = {
                SystemMode.AURORA_LIVE: "双核联动",
                SystemMode.AURORA_FALLBACK: "模拟降级",
                SystemMode.STANDALONE: "独立运行"
            }
            self._mode_var.set(mode_labels.get(mode, str(mode)))
            self._aurora_var.set("✅ 在线" if mode == SystemMode.AURORA_LIVE else "⚠️ 离线")

            # 模式指示器颜色
            colors = {SystemMode.AURORA_LIVE: '#00ff88', SystemMode.AURORA_FALLBACK: '#ffaa00',
                      SystemMode.STANDALONE: '#ff4444'}
            self._mode_indicator.itemconfig(self._mode_dot, fill=colors.get(mode, '#888888'))

            # 系统资源
            health = self.strategy_mgr.get_system_health()
            self._cpu_var.set(f"{health.cpu_percent:.1f}%")
            self._mem_var.set(f"{health.memory_percent:.1f}%")
            self._disk_var.set(f"{health.disk_percent:.1f}%")

            # 策略计数
            strategies = self.strategy_mgr.get_strategy_list(force=True)
            self._strategy_count_var.set(str(len(strategies)))
            self._active_count_var.set(str(len(self.strategy_mgr._active_strategies)))
            self._backtest_count_var.set(str(len(self.strategy_mgr._backtest_results)))

            self._refresh_strategies()
            self._refresh_backtest_history()
            self._refresh_monitor()

            self._set_status(f"就绪 - {mode_labels.get(mode)}", 'green')

        except Exception as e:
            self._set_status(f"刷新失败: {e}", 'red')
            self._log(f"[ERROR] 刷新失败: {traceback.format_exc()}")

    def _refresh_strategies(self):
        """刷新策略列表（含最新优化状态显示）"""
        if not self.strategy_mgr:
            return
        try:
            strategies = self.strategy_mgr.get_strategy_list(force=True)

            # 查询所有策略的优化状态（从参数存储）
            opt_status = {}
            try:
                from core.tau_optimizer_cluster import get_parameter_store
                _ps = get_parameter_store()
                all_info = _ps.get_all_strategies_info()
                for info in all_info:
                    opt_status[info['name']] = info
            except Exception as _e:
                pass

            self._strategy_tree.delete(*self._strategy_tree.get_children())
            for s in strategies:
                name = s['name']
                status = "运行中" if name in self.strategy_mgr._active_strategies else "停止"

                # 组装韬定律优化状态列：优先显示 score/version，其次缓存值，最后 '--'
                if name in opt_status:
                    info = opt_status[name]
                    v = info.get('current_version', 0)
                    sc = info.get('best_score', 0)
                    tau_status = f"v{v} | {sc:.2f}" if v > 0 else f"未优化 | {sc:.2f}"
                elif name in self._tau_cache and self._tau_cache[name] != '--':
                    tau_status = self._tau_cache[name]
                else:
                    tau_status = "未优化"

                self._strategy_tree.insert('', 'end', values=(
                    name, s.get('category', ''), s.get('label', name), status, tau_status
                ))

            # 更新下拉列表
            names = [s['name'] for s in strategies]
            self._bt_strategy['values'] = names
            self._opt_strategy['values'] = names
            if hasattr(self, '_tau_shepherd_strategy'):
                self._tau_shepherd_strategy['values'] = names
            if names:
                self._bt_strategy.set(names[0])
                self._opt_strategy.set(names[0])
                if hasattr(self, '_tau_shepherd_strategy'):
                    self._tau_shepherd_strategy.set(names[0])

            self._set_status(f"✅ 策略列表已刷新 (共{len(strategies)}个策略，"
                             f"{len(opt_status)}个有优化记录)", 'green')
        except Exception as e:
            self._log(f"[ERROR] 刷新策略失败: {e}")

    def _tau_optimize_selected(self):
        """对选中策略执行韬定律优化"""
        selection = self._strategy_tree.selection()
        if not selection:
            messagebox.showwarning("提示", "请先选中一个策略")
            return
        name = self._strategy_tree.item(selection[0], 'values')[0]
        self._run_tau_for_strategy(name)

    def _tau_optimize_batch(self):
        """批量韬定律优化 - 顺序执行所有策略（避免并发占用CPU）"""
        if not self.strategy_mgr:
            messagebox.showerror("错误", "策略管理器不可用")
            return
        strategies = self.strategy_mgr.get_strategy_list()
        if not strategies:
            messagebox.showwarning("提示", "没有可优化的策略")
            return
        names = [s['name'] for s in strategies]

        def run_thread():
            total = len(names)
            success = 0
            for i, name in enumerate(names, 1):
                try:
                    self._set_status(f"[批量 {i}/{total}] 优化中: {name}...", 'orange')
                    ok, summary = self._run_tau_for_strategy_blocking(name)
                    if ok:
                        success += 1
                        self._log(f"[批量 {i}/{total}] ✅ {name}: {summary}")
                    else:
                        self._log(f"[批量 {i}/{total}] ❌ {name}: {summary}")
                except Exception as e:
                    self._log(f"[批量 {i}/{total}] ❌ {name}: {e}")
            self._set_status(f"批量优化完成 {success}/{total}", 'green')
            self._log(f"[批量优化] 完成 - 成功 {success}/{total}")

        threading.Thread(target=run_thread, daemon=True).start()

    def _run_tau_for_strategy(self, strategy_name: str):
        """对指定策略执行韬定律优化（自动识别类型，后台线程执行）"""
        if not strategy_name:
            messagebox.showwarning("提示", "策略名称为空")
            return
        self._set_status(f"韬定律优化: {strategy_name}...", 'orange')
        self._log(f"[韬定律] 开始优化: {strategy_name}")

        def run_thread():
            try:
                ok, summary = self._run_tau_for_strategy_blocking(strategy_name)
                if ok:
                    self._set_status(f"✅ 韬定律: {strategy_name} - {summary}", 'green')
                    self._log(f"[韬定律] ✅ {strategy_name} - {summary}")
                else:
                    self._set_status(f"❌ 韬定律: {strategy_name} - {summary}", 'red')
                    self._log(f"[韬定律] ❌ {strategy_name} - {summary}")
            except Exception as e:
                self._set_status(f"❌ 韬定律异常: {e}", 'red')
                self._log(f"[韬定律] ❌ {strategy_name}: {traceback.format_exc()}")

        threading.Thread(target=run_thread, daemon=True).start()

    def _run_tau_for_strategy_blocking(self, strategy_name: str):
        """同步执行韬定律优化（由线程调用），返回 (ok, summary_text)"""
        mgr = self.strategy_mgr
        if not mgr:
            try:
                from core.enhanced_strategy_manager import get_strategy_manager
                mgr = get_strategy_manager()
            except Exception as e:
                return False, f"无法获取策略管理器: {e}"

        # 使用 StrategyOptimizerBus 识别策略类型
        try:
            from core.tau_optimizer_cluster import StrategyOptimizerBus
            bus = StrategyOptimizerBus()
            bus.detect_and_init(strategy_name)
            info = bus.get_module_info()
            module_name = info.get('module_name', 'generic')
        except Exception as e:
            module_name = 'generic'
            self._log(f"[韬定律] 类型检测失败（将使用通用模式）: {e}")

        # 根据模块名选择优化路径
        try:
            if 'shepherd' in module_name or 'rotation' in module_name or '轮动' in module_name:
                result = mgr.run_tau_shepherd_optimization(strategy_name=strategy_name)
            elif 'bernoulli' in module_name or 'coanda' in module_name:
                result = mgr.run_tau_bernoulli_optimization(strategy_name=strategy_name)
            else:
                result = mgr.run_tau_cluster_optimization(strategy_name=strategy_name)
        except AttributeError:
            # 回退到通用优化
            try:
                result = mgr.run_tau_cluster_optimization(strategy_name=strategy_name)
            except Exception as e:
                return False, f"优化方法不可用: {e}"
        except Exception as e:
            return False, str(e)

        if not isinstance(result, dict):
            return False, f"返回格式异常: {type(result).__name__}"

        if result.get('success'):
            data = result.get('data', {}) or {}
            best_params = data.get('best_params', {})
            cluster_status = data.get('cluster_status', {}) or {}

            total = 0
            if isinstance(cluster_status, dict):
                total = cluster_status.get('total_requests', 0)
            if not total:
                total = data.get('total_evals', 0)
            cache_hit = 0
            if isinstance(cluster_status, dict):
                cache_hit = cluster_status.get('cache', {}).get('hit_rate', 0) \
                    if isinstance(cluster_status.get('cache'), dict) else 0
            score = data.get('best_score', 0)
            ret = data.get('best_return', 0)
            elapsed = data.get('time_elapsed', 0)

            summary = (
                f"评分={score:.4f} | 收益={ret:.2f}% | 评估={total} | "
                f"缓存={cache_hit*100:.1f}% | 耗时={elapsed:.2f}s"
            )
            # 模式分析摘要（新增）
            pa = data.get('pattern_analysis')
            if pa:
                rcs = pa.get('range_contract_suggestions', [])
                locks = pa.get('lock_suggestions', [])
                arcs = pa.get('architecture_suggestions', [])
                summary += f"\n  📊 模式分析: 范围收缩 {len(rcs)} 项 | 参数锁定 {len(locks)} 项 | 改进方向 {len(arcs)} 项"
                # 输出到日志面板
                if hasattr(self, '_auto_log') and self._auto_log is not None:
                    try:
                        self._auto_log.insert('end', f"\n  [模式分析] {strategy_name}\n")
                        for r in rcs:
                            self._auto_log.insert('end', f"    📏 {r['param']}: 收缩 {int(r.get('contraction_ratio',0)*100)}%\n")
                        for l in locks:
                            self._auto_log.insert('end', f"    🔒 {l['param']}: 锁定为 {l.get('suggested_value','?')}\n")
                        for a in arcs:
                            self._auto_log.insert('end', f"    💡 {a.get('category','建议')}: {a.get('short_text','')}\n")
                    except Exception:
                        pass
            # 更新缓存并刷新显示 + 自动应用最新参数
            self._tau_cache[strategy_name] = f"★{score:.3f}"
            try:
                self.strategy_mgr.apply_optimized_params(strategy_name)
            except Exception:
                pass
            try:
                self.root.after(0, self._refresh_strategies)
            except Exception:
                pass
            return True, summary
        else:
            return False, result.get('error', '未知错误')

    def _refresh_backtest_history(self):
        """刷新回测历史"""
        self._bt_tree.delete(*self._bt_tree.get_children())
        if not self.strategy_mgr:
            return
        for r in self.strategy_mgr._backtest_results[-20:]:
            self._bt_tree.insert('', 'end', values=(
                r.strategy_name, f"{r.total_return_pct:.2f}", f"{r.sharpe_ratio:.4f}",
                f"{r.max_drawdown:.2f}", f"{r.win_rate:.1f}", r.total_trades
            ))

    def _refresh_monitor(self):
        """刷新监控面板"""
        if not self.strategy_mgr:
            return

        try:
            # 健康状态
            health = self.strategy_mgr.get_system_health()
            self._health_text.configure(state='normal')
            self._health_text.delete(1.0, tk.END)
            self._health_text.insert(tk.END, f"系统健康: {health.status}\n")
            self._health_text.insert(tk.END, f"CPU: {health.cpu_percent}% | 内存: {health.memory_percent}% | 磁盘: {health.disk_percent}%\n")
            self._health_text.insert(tk.END, f"组件状态:\n")
            for name, status in health.services.items():
                self._health_text.insert(tk.END, f"  {name}: {status}\n")
            self._health_text.configure(state='disabled')

            # 增益模块
            gain = self.strategy_mgr.get_gain_status()
            self._gain_tree.delete(*self._gain_tree.get_children())
            gain_modules = [
                ("策略优化器", "optimizer", "增强回测+参数优化"),
                ("风险控制", "risk", "实时风控+熔断"),
                ("数据聚合", "data", "4源数据+容灾切换"),
                ("安全审计", "security", "白名单+注入防护"),
                ("性能监控", "performance", "CPU/内存/延迟监控"),
            ]
            for mod, key, desc in gain_modules:
                status = "✅ 在线" if gain.get('success') else "⚠️ 离线"
                self._gain_tree.insert('', 'end', values=(mod, status, desc))

            # 风险状态
            risk = self.strategy_mgr.get_risk_status()
            self._risk_text.configure(state='normal')
            self._risk_text.delete(1.0, tk.END)
            self._risk_text.insert(tk.END, json.dumps(risk, indent=2, ensure_ascii=False))
            self._risk_text.configure(state='disabled')

        except Exception as e:
            self._log(f"[ERROR] 监控刷新失败: {e}")

    # ---- 策略操作 ----

    def _start_selected(self):
        """启动选中策略"""
        if not self.strategy_mgr:
            messagebox.showerror("错误", "策略管理器不可用")
            return
        selection = self._strategy_tree.selection()
        if not selection:
            messagebox.showwarning("提示", "请先选中一个策略")
            return
        name = self._strategy_tree.item(selection[0], 'values')[0]
        ok, msg = self.strategy_mgr.start_strategy(name)
        if ok:
            messagebox.showinfo("成功", msg)
            self._log(f"✅ {msg}")
            self._refresh_strategies()
        else:
            messagebox.showerror("失败", msg)
            self._log(f"❌ {msg}")

    def _stop_all(self):
        """停止所有策略"""
        if not self.strategy_mgr:
            return
        ok, msg = self.strategy_mgr.stop_strategy()
        self._log(f"{'✅' if ok else '❌'} {msg}")
        self._refresh_strategies()

    def _on_strategy_double_click(self, event):
        """双击策略查看详情"""
        selection = self._strategy_tree.selection()
        if not selection:
            return
        name = self._strategy_tree.item(selection[0], 'values')[0]
        cat = self._strategy_tree.item(selection[0], 'values')[1]
        label = self._strategy_tree.item(selection[0], 'values')[2]
        self._detail_name.set(label)
        self._detail_cat.set(cat)

        # 获取详细信息
        desc = "--"
        if self.strategy_mgr:
            strategies = self.strategy_mgr.get_strategy_list()
            for s in strategies:
                if s['name'] == name:
                    desc = s.get('description', desc)
                    break
        self._detail_desc.set(desc)

    # ---- 回测操作 ----

    def _run_backtest(self):
        """执行回测（使用专业回测引擎）"""
        if not self.strategy_mgr:
            messagebox.showerror("错误", "策略管理器不可用")
            return
        name = self._bt_strategy.get()
        if not name:
            messagebox.showwarning("提示", "请选择策略")
            return
        try:
            days = int(self._bt_days.get())
            balance = float(self._bt_balance.get())
        except ValueError:
            messagebox.showerror("错误", "天数和资金必须为数字")
            return

        self._set_status(f"回测中: {name}...", 'orange')
        self._bt_log.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] 开始回测: {name}, {days}天\n")
        self._bt_log.see(tk.END)
        self.root.update()

        try:
            from core.backtest_engine import run_strategy_backtest
            from core.data_bus import get_data_bus

            # 通过数据总线获取K线数据
            bus = get_data_bus()
            kline = bus.get_kline("000001", days=days)  # 使用示例股票
            if not kline or not kline.get("closes"):
                raise Exception("获取K线数据失败")

            prices = kline["closes"]

            # 使用专业回测引擎
            result = run_strategy_backtest(prices, "rsi")

            if result.get("success"):
                self._last_backtest_result = result
                self._bt_detail_btn.config(state='normal')

                # 更新结果列表
                self._bt_tree.insert('', 0, values=(
                    name, f"{result['total_return']:.2f}",
                    f"{result['sharpe_ratio']:.2f}", f"{result['max_drawdown']:.2f}",
                    f"{result['win_rate']:.2f}", result['trades']
                ))

                # 更新绩效指标
                self._bt_metrics.delete('1.0', tk.END)
                metrics_text = f"策略名称: {name}\n"
                metrics_text += f"回测天数: {days}\n"
                metrics_text += f"初始资金: {balance:.0f}\n\n"
                metrics_text += f"📈 收益指标\n"
                metrics_text += f"  总收益率: {result['total_return']:.2f}%\n"
                metrics_text += f"  年化收益率: {result['annual_return']:.2f}%\n"
                metrics_text += f"  夏普比率: {result['sharpe_ratio']:.2f}\n\n"
                metrics_text += f"📉 风险指标\n"
                metrics_text += f"  最大回撤: {result['max_drawdown']:.2f}%\n\n"
                metrics_text += f"📊 交易指标\n"
                metrics_text += f"  胜率: {result['win_rate']:.2f}%\n"
                metrics_text += f"  盈亏比: {result['profit_factor']:.2f}\n"
                metrics_text += f"  交易次数: {result['trades']}\n"
                metrics_text += f"  盈利次数: {result['win_trades']}\n"
                metrics_text += f"  亏损次数: {result['lose_trades']}\n"
                metrics_text += f"  平均盈利: {result['avg_win']:.2f}%\n"
                metrics_text += f"  平均亏损: {result['avg_lose']:.2f}%\n"
                metrics_text += f"\n⏱️ 耗时: {result['elapsed_time']:.2f}秒"
                self._bt_metrics.insert('end', metrics_text)

                # 更新收益曲线
                self._bt_equity.delete('1.0', tk.END)
                equity = result.get('equity_curve', [])
                if equity:
                    # 采样显示
                    sample = equity[::max(1, len(equity) // 30)]
                    self._bt_equity.insert('end', "Day  Value(%)\n")
                    self._bt_equity.insert('end', "-------------\n")
                    for i, val in enumerate(sample):
                        self._bt_equity.insert('end', f"{i:3d}  {val:6.2f}\n")

                # 更新回撤曲线
                self._bt_drawdown.delete('1.0', tk.END)
                drawdown = result.get('drawdown_curve', [])
                if drawdown:
                    sample = drawdown[::max(1, len(drawdown) // 30)]
                    self._bt_drawdown.insert('end', "Day  Drawdown(%)\n")
                    self._bt_drawdown.insert('end', "----------------\n")
                    for i, val in enumerate(sample):
                        self._bt_drawdown.insert('end', f"{i:3d}  {val:6.2f}\n")

                self._bt_log.insert(tk.END,
                    f"[{datetime.now().strftime('%H:%M:%S')}] ✅ 完成: "
                    f"收益={result['total_return']:.2f}%, 夏普={result['sharpe_ratio']:.2f}\n")
                self._bt_log.see(tk.END)
                self._set_status("回测完成", 'green')
            else:
                raise Exception("回测失败")

        except Exception as e:
            self._bt_log.insert(tk.END,
                f"[{datetime.now().strftime('%H:%M:%S')}] ❌ 失败: {e}\n")
            self._bt_log.see(tk.END)
            self._set_status(f"回测失败: {e}", 'red')

    def _show_backtest_details(self):
        """显示回测详情对话框"""
        if not self._last_backtest_result:
            return

        result = self._last_backtest_result

        # 创建详情窗口
        detail_win = tk.Toplevel(self.root)
        detail_win.title("📈 回测详情")
        detail_win.geometry("800x600")

        # 交易日志
        ttk.Label(detail_win, text="📋 交易日志", font=('Microsoft YaHei', 12, 'bold')).pack(anchor='w', padx=10, pady=10)
        log_text = scrolledtext.ScrolledText(detail_win, bg='#0f0f1a', fg='#00ff88', font=('Consolas', 9))
        log_text.pack(fill='both', expand=True, padx=10, pady=5)

        trades = result.get('trading_log', [])
        if trades:
            log_text.insert('end', f"{'日期':<12} {'类型':<6} {'价格':<10} {'数量':<8} {'价值':<12} {'费用':<8} {'利润':<8}\n")
            log_text.insert('end', '-' * 80 + '\n')
            for trade in trades:
                date = trade.get('date', '')[:10]
                trade_type = '买入' if trade.get('type') == 'buy' else '卖出'
                price = trade.get('price', 0)
                qty = trade.get('quantity', 0)
                value = trade.get('value', 0)
                fee = trade.get('fee', 0)
                profit = trade.get('profit', '')

                log_text.insert('end', f"{date:<12} {trade_type:<6} {price:<10.2f} {qty:<8d} {value:<12.2f} {fee:<8.2f} {profit:<8}\n")
        else:
            log_text.insert('end', "无交易记录")

        # 关闭按钮
        ttk.Button(detail_win, text="关闭", command=detail_win.destroy).pack(pady=10)

    def _compare_top3(self):
        """对比TOP3策略"""
        if not self.strategy_mgr:
            return
        strategies = self.strategy_mgr.get_strategy_list()
        names = [s['name'] for s in strategies[:3]]
        if not names:
            return
        self._set_status(f"对比中: {', '.join(names)}...", 'orange')
        self.root.update()

        try:
            result = self.strategy_mgr.compare_strategies(names, days=30)
            self._bt_log.insert(tk.END, f"\n{'='*50}\n")
            self._bt_log.insert(tk.END, f"TOP3策略对比 (30天):\n")
            for name, data in result['comparison'].items():
                self._bt_log.insert(tk.END,
                    f"  {name}: 收益={data['return']:.2f}%, 夏普={data['sharpe']:.4f}\n")
            self._bt_log.insert(tk.END,
                f"最佳策略: {result['best_strategy']} (夏普={result['best_sharpe']:.4f})\n")
            self._bt_log.insert(tk.END, f"{'='*50}\n")
            self._bt_log.see(tk.END)
            self._set_status("对比完成", 'green')
        except Exception as e:
            self._log(f"[ERROR] 对比失败: {e}")

    # ---- 优化操作 ----

    def _run_optimization(self):
        """运行参数优化"""
        if not self.strategy_mgr:
            messagebox.showerror("错误", "策略管理器不可用")
            return
        name = self._opt_strategy.get()
        if not name:
            messagebox.showwarning("提示", "请选择策略")
            return
        try:
            iterations = int(self._opt_iterations.get())
        except ValueError:
            messagebox.showerror("错误", "迭代次数必须为数字")
            return
        target = self._opt_target.get()

        self._set_status(f"优化中: {name} ({iterations}次迭代)...", 'orange')
        self.root.update()

        try:
            result = self.strategy_mgr.run_optimization(name, iterations, target)
            if result.get('success'):
                data = result['data']
                # 清空并显示历史
                self._opt_tree.delete(*self._opt_tree.get_children())
                for h in data.get('history', []):
                    self._opt_tree.insert('', 'end', values=(
                        h['iteration'], h['score'], str(h.get('params', ''))
                    ))
                # 显示最佳参数
                self._opt_best.delete(1.0, tk.END)
                self._opt_best.insert(tk.END, json.dumps({
                    'best_params': data.get('best_params', {}),
                    'best_score': data.get('best_score', 0),
                    'iterations': data.get('iterations', 0)
                }, indent=2, ensure_ascii=False))
                # 保存到参数存储 + 应用最新参数 + 刷新策略列表
                best_params = data.get('best_params', {})
                best_score = data.get('best_score', 0)
                if best_params:
                    try:
                        from core.tau_optimizer_cluster import get_parameter_store
                        _ps = get_parameter_store()
                        _ps.record_optimization(name, best_params, best_score, method='generic')
                        self.strategy_mgr.apply_optimized_params(name)
                    except Exception as _e:
                        pass
                    self.root.after(0, self._refresh_strategies)
                self._set_status(f"优化完成 - 最佳评分: {data.get('best_score', 0):.4f}", 'green')
            else:
                self._set_status(f"优化失败: {result.get('error', '未知错误')}", 'red')
        except Exception as e:
            self._set_status(f"优化失败: {e}", 'red')
            self._log(f"[ERROR] 优化失败: {traceback.format_exc()}")

    def _run_shepherd(self):
        """运行牧羊人优化器"""
        if not self.strategy_mgr:
            messagebox.showerror("错误", "策略管理器不可用")
            return
        name = self._opt_strategy.get()
        if not name:
            messagebox.showwarning("提示", "请先选择策略")
            return

        self._shepherd_status.set("正在启动牧羊人...")
        self._set_status(f"牧羊人优化: {name}...", 'orange')
        self.root.update()

        try:
            if self.strategy_mgr.is_aurora_available():
                result = self.strategy_mgr.aurora.run_shepherd(name)
                if result.get('success'):
                    self._shepherd_status.set(f"完成: {result.get('message', '成功')}")
                    self._set_status("牧羊人优化完成", 'green')
                else:
                    self._shepherd_status.set(f"失败: {result.get('error', '未知')}")
                    self._set_status("牧羊人优化失败", 'red')
            else:
                self._shepherd_status.set("需要Aurora在线")
                self._set_status("牧羊人优化器需要Aurora在线", 'orange')
        except Exception as e:
            self._shepherd_status.set(f"错误: {e}")
            self._log(f"[ERROR] 牧羊人失败: {traceback.format_exc()}")

    # ---- 快捷操作 ----

    def _quick_backtest(self):
        """快速批量回测"""
        if not self.strategy_mgr:
            return
        self._set_status("批量回测TOP5...", 'orange')
        self.root.update()

        try:
            results = self.strategy_mgr.quick_backtest_all(days=14)
            self._bt_tree.delete(*self._bt_tree.get_children())
            for r in results:
                self._bt_tree.insert('', 'end', values=(
                    r.strategy_name, f"{r.total_return_pct:.2f}", f"{r.sharpe_ratio:.4f}",
                    f"{r.max_drawdown:.2f}", f"{r.win_rate:.1f}", r.total_trades
                ))
            self._set_status(f"批量回测完成 ({len(results)}个策略)", 'green')
        except Exception as e:
            self._set_status(f"批量回测失败: {e}", 'red')

    def _export_status(self):
        """导出状态报告"""
        if not self.strategy_mgr:
            return
        try:
            report = {
                "timestamp": datetime.now().isoformat(),
                "mode": self.strategy_mgr.get_mode().value,
                "health": {
                    "cpu": self._cpu_var.get(),
                    "memory": self._mem_var.get(),
                    "disk": self._disk_var.get(),
                },
                "strategies": len(self.strategy_mgr.get_strategy_list()),
                "active": len(self.strategy_mgr._active_strategies),
                "backtests": len(self.strategy_mgr._backtest_results),
            }
            filename = f"qs_robot_status_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            filepath = os.path.join(QS_ROBOT_PATH, filename)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            self._log(f"📋 状态已导出: {filepath}")
            messagebox.showinfo("导出成功", f"状态报告已保存到:\n{filepath}")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    # ---- 工具方法 ----

    def _set_status(self, text: str, color: str = 'white'):
        """设置状态栏文字"""
        self._status_var.set(text)

    def _log(self, text: str):
        """添加日志"""
        try:
            self._log_text.configure(state='normal')
            self._log_text.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] {text}\n")
            self._log_text.see(tk.END)
            self._log_text.configure(state='disabled')
        except Exception:
            print(f"[QS Robot Log] {text}")

    # ---- 启动 ----

    def run(self):
        """启动桌面应用"""
        self._log("🚀 QS Robot V2.0 桌面应用启动...")
        self._log(f"  策略管理器: {'✅ 已加载' if self.strategy_mgr else '⚠️ 不可用'}")
        self._refresh_all()
        self.root.mainloop()

    # ---- 新方法：完整自动化流程 ----
    def _run_auto_full_workflow(self):
        """完整自动化流程：策略→优化→股票池→交易配置"""
        selected = self._get_selected_strategy()
        if not selected:
            messagebox.showinfo("提示", "请先在策略列表中选中一个策略")
            return

        self._auto_status.set(f"🔄 正在执行完整自动化流程: {selected}...")
        self._auto_log.insert('end', f"\n{'='*60}\n")
        self._auto_log.insert('end', f"[{datetime.now().strftime('%H:%M:%S')}] 启动完整自动化流程: {selected}\n")
        self._auto_log.see('end')

        try:
            from core.integration_bus import get_integration_bus
            bus = get_integration_bus()
            result = bus.auto_full_workflow(selected, coarse_points=25, refined_points_per_region=10)

            if result.get('success'):
                opt = result['optimization']
                pool = result['stock_pool']
                config = result['trading_config']

                self._auto_log.insert('end', f"  ✅ 优化完成: 评分 {opt['best_score']:.4f}, 评估{opt['total_evaluations']}次\n")
                self._auto_log.insert('end', f"  ✅ 股票匹配: {pool['total_matched']}只 ({pool['recommendation_mode']})\n")
                self._auto_log.insert('end', f"  ✅ 交易配置: {'就绪' if config['ready_to_trade'] else '未就绪'}\n")
                self._auto_log.insert('end', f"  ✅ 总耗时: {result['total_elapsed_seconds']:.2f}秒\n")

                if pool['matched_stocks']:
                    self._auto_log.insert('end', f"  📋 推荐股票 (Top5):\n")
                    for s in pool['matched_stocks'][:5]:
                        self._auto_log.insert('end', f"     - {s['name']} ({s['code']}) 评分{s.get('score',0):.3f} {s.get('grade','')}\n")

                self._auto_status.set(f"✅ 完成: {selected} 最佳评分 {opt['best_score']:.4f}")

                # 更新策略列表中的韬定律状态列
                self._update_tau_column(selected, f"{opt['best_score']:.4f}")
            else:
                self._auto_log.insert('end', f"  ❌ 流程失败: {result.get('error', '未知错误')}\n")
                self._auto_status.set("❌ 流程失败")

            self._auto_log.see('end')
        except Exception as e:
            self._auto_log.insert('end', f"  ❌ 异常: {str(e)}\n")
            self._auto_status.set(f"❌ 异常: {str(e)[:30]}")
            self._auto_log.see('end')

    def _run_batch_optimize(self):
        """批量优化所有策略"""
        if not hasattr(self, '_strategy_tree'):
            messagebox.showinfo("提示", "策略列表未加载")
            return

        strategies = []
        for item in self._strategy_tree.get_children():
            values = self._strategy_tree.item(item)['values']
            if values and values[0]:
                strategies.append(values[0])

        if not strategies:
            messagebox.showinfo("提示", "没有可优化的策略")
            return

        self._auto_status.set(f"🔄 正在批量优化 {len(strategies)} 个策略...")
        self._auto_log.insert('end', f"\n{'='*60}\n")
        self._auto_log.insert('end', f"[{datetime.now().strftime('%H:%M:%S')}] 批量优化 {len(strategies)} 个策略\n")
        self._auto_log.see('end')

        try:
            from core.integration_bus import get_integration_bus
            bus = get_integration_bus()
            result = bus.auto_batch_optimize(strategies, coarse_points=20, refined_points_per_region=10)

            if result.get('success'):
                self._auto_log.insert('end', f"  ✅ 成功: {result['successful_count']}/{result['total_strategies']} 个策略\n")

                for rank_name, rank_score in result['best_scores_ranking'][:5]:
                    self._auto_log.insert('end', f"     🏆 {rank_name}: {rank_score:.4f}\n")
                    self._update_tau_column(rank_name, f"{rank_score:.4f}")

                self._auto_status.set(f"✅ 批量优化完成: {result['successful_count']}/{result['total_strategies']}")
            self._auto_log.see('end')
        except Exception as e:
            self._auto_log.insert('end', f"  ❌ 批量优化异常: {str(e)}\n")
            self._auto_status.set(f"❌ 异常")

    def _run_stock_pool_match(self):
        """策略-股票池匹配"""
        selected = self._get_selected_strategy()
        if not selected:
            messagebox.showinfo("提示", "请先在策略列表中选中一个策略")
            return

        self._auto_status.set(f"💹 正在匹配股票池: {selected}...")

        try:
            from core.integration_bus import get_integration_bus
            bus = get_integration_bus()
            result = bus.auto_match_stock_pool(selected, stock_count=15)

            self._auto_log.insert('end', f"\n{'='*60}\n")
            self._auto_log.insert('end', f"[{datetime.now().strftime('%H:%M:%S')}] 股票池匹配: {selected}\n")
            self._auto_log.insert('end', f"  策略画像: {result['factor_profile']['name']}\n")
            self._auto_log.insert('end', f"  关键因子: {', '.join(result['factor_profile']['key_factors'][:5])}\n")
            self._auto_log.insert('end', f"  匹配股票数: {result['total_matched']}\n")
            self._auto_log.insert('end', f"  推荐模式: {result['recommendation_mode']}\n")

            for stock in result['matched_stocks'][:10]:
                self._auto_log.insert('end', f"     - {stock['name']} ({stock['code']}) "
                                            f"{stock.get('grade','')} 评分{stock.get('score', 0):.3f}\n")

            self._auto_status.set(f"💹 匹配完成: {result['total_matched']} 只股票")
            self._auto_log.see('end')
        except Exception as e:
            self._auto_log.insert('end', f"  ❌ 异常: {str(e)}\n")
            self._auto_status.set(f"❌ 异常")

    def _show_integration_report(self):
        """显示集成总线状态报告"""
        try:
            from core.integration_bus import get_integration_bus
            bus = get_integration_bus()
            report = bus.get_workflow_report()

            self._auto_log.insert('end', f"\n{'='*60}\n")
            self._auto_log.insert('end', f"[{datetime.now().strftime('%H:%M:%S')}] 集成总线状态报告\n")
            self._auto_log.insert('end', f"  总执行流程数: {report['total_workflows_executed']}\n")
            self._auto_log.insert('end', f"  已优化策略数: {report['optimized_strategies_count']}\n")

            modules = report['modules_available']
            self._auto_log.insert('end', f"  可用模块:\n")
            for mod_name, available in modules.items():
                status = "✅" if available else "⚠️"
                self._auto_log.insert('end', f"    {status} {mod_name}\n")

            self._auto_log.insert('end', f"  已优化策略列表:\n")
            for strat in report['optimized_strategies'][:10]:
                self._auto_log.insert('end', f"    - {strat['name']}: 评分{strat['best_score']:.4f}\n")

            self._auto_log.insert('end', f"\n  支持的自动化流程:\n")
            for wf in report['supported_workflows']:
                self._auto_log.insert('end', f"    • {wf}\n")

            self._auto_status.set("📋 状态报告已生成")
            self._auto_log.see('end')
        except Exception as e:
            self._auto_log.insert('end', f"  ❌ 获取报告异常: {str(e)}\n")

    def _update_tau_column(self, strategy_name: str, tau_value: str):
        """更新策略列表中的韬定律状态列"""
        if not hasattr(self, '_strategy_tree'):
            return

        for item in self._strategy_tree.get_children():
            values = self._strategy_tree.item(item)['values']
            if values and values[0] == strategy_name:
                new_values = list(values)
                new_values[4] = tau_value  # tau列是第5列（index=4）
                self._strategy_tree.item(item, values=new_values)
                break

    def _get_selected_strategy(self) -> str:
        """获取当前选中的策略名称"""
        if not hasattr(self, '_strategy_tree'):
            return ""

        selected = self._strategy_tree.selection()
        if not selected:
            return ""

        values = self._strategy_tree.item(selected[0])['values']
        if values and len(values) > 0:
            return str(values[0])
        return ""


# ============================================================
# 入口
    # ---- 任务调度器操作 ----

    def _start_scheduler(self):
        """启动任务调度器"""
        try:
            from core.task_scheduler import get_task_scheduler, TaskType
            scheduler = get_task_scheduler()
            self._scheduler_status.config(text="运行中", foreground='green')
            self._task_log.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] ✅ 任务调度器已启动\n")
            self._task_log.see(tk.END)

            # 刷新任务列表
            self._refresh_tasks()

            # 添加示例任务（首次启动时）
            tasks = scheduler.list_tasks()
            if len(tasks) == 0:
                scheduler.schedule_interval_task(
                    name="数据更新任务",
                    task_type=TaskType.DATA_UPDATE,
                    func=self._sample_data_task,
                    minutes=60
                )
                self._task_log.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] 添加示例任务\n")
                self._task_log.see(tk.END)
                self._refresh_tasks()

        except Exception as e:
            self._task_log.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] ❌ 启动失败: {e}\n")
            self._task_log.see(tk.END)

    def _stop_scheduler(self):
        """停止任务调度器"""
        self._scheduler_status.config(text="已停止", foreground='red')
        self._task_log.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] ⏹ 任务调度器已停止\n")
        self._task_log.see(tk.END)

    def _add_scheduler_task(self):
        """添加任务对话框"""
        dialog = tk.Toplevel(self.root)
        dialog.title("添加任务")
        dialog.geometry("350x200")

        ttk.Label(dialog, text="任务名称:").grid(row=0, column=0, padx=10, pady=5, sticky='w')
        name_entry = ttk.Entry(dialog, width=25)
        name_entry.grid(row=0, column=1, padx=10, pady=5)

        ttk.Label(dialog, text="任务类型:").grid(row=1, column=0, padx=10, pady=5, sticky='w')
        type_combo = ttk.Combobox(dialog, values=["data_update", "backtest", "optimization"], width=22)
        type_combo.grid(row=1, column=1, padx=10, pady=5)

        ttk.Label(dialog, text="间隔(分钟):").grid(row=2, column=0, padx=10, pady=5, sticky='w')
        interval_entry = ttk.Entry(dialog, width=10)
        interval_entry.insert(0, "60")
        interval_entry.grid(row=2, column=1, padx=10, pady=5)

        def confirm():
            from core.task_scheduler import get_task_scheduler, TaskType
            scheduler = get_task_scheduler()
            name = name_entry.get()
            task_type = type_combo.get()
            interval = int(interval_entry.get())

            scheduler.schedule_interval_task(
                name=name,
                task_type=TaskType(task_type),
                func=self._sample_data_task,
                minutes=interval
            )

            self._task_log.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] ➕ 添加任务: {name}\n")
            self._task_log.see(tk.END)
            self._refresh_tasks()
            dialog.destroy()

        ttk.Button(dialog, text="确定", command=confirm).grid(row=3, column=0, padx=10, pady=10)
        ttk.Button(dialog, text="取消", command=dialog.destroy).grid(row=3, column=1, padx=10, pady=10)

    def _refresh_tasks(self):
        """刷新任务列表"""
        try:
            from core.task_scheduler import get_task_scheduler
            scheduler = get_task_scheduler()
            tasks = scheduler.list_tasks()

            for item in self._task_tree.get_children():
                self._task_tree.delete(item)

            for task in tasks:
                next_run = task.next_run.strftime('%H:%M') if task.next_run else '--'
                self._task_tree.insert('', 'end', values=(
                    task.id[-8:],
                    task.name,
                    task.task_type.value,
                    task.status.value,
                    next_run,
                    task.run_count
                ))
        except Exception as e:
            pass

    def _run_task_now(self):
        """立即执行选中的任务"""
        selection = self._task_tree.selection()
        if not selection:
            messagebox.showwarning("提示", "请选择任务")
            return

        task_id = self._task_tree.item(selection[0], 'values')[0]

        try:
            from core.task_scheduler import get_task_scheduler
            scheduler = get_task_scheduler()

            full_id = [t.id for t in scheduler.list_tasks() if t.id.endswith(task_id)]
            if full_id:
                scheduler.run_task_now(full_id[0])
                self._task_log.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] ▶ 立即执行任务: {task_id}\n")
                self._task_log.see(tk.END)
                self._refresh_tasks()
        except Exception as e:
            self._task_log.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] ❌ 执行失败: {e}\n")
            self._task_log.see(tk.END)

    def _pause_task(self):
        """暂停选中的任务"""
        selection = self._task_tree.selection()
        if not selection:
            return

        task_id = self._task_tree.item(selection[0], 'values')[0]
        try:
            from core.task_scheduler import get_task_scheduler
            scheduler = get_task_scheduler()

            full_id = [t.id for t in scheduler.list_tasks() if t.id.endswith(task_id)]
            if full_id:
                scheduler.pause_task(full_id[0])
                self._task_log.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] ⏸ 暂停任务: {task_id}\n")
                self._task_log.see(tk.END)
                self._refresh_tasks()
        except Exception as e:
            pass

    def _resume_task(self):
        """恢复选中的任务"""
        selection = self._task_tree.selection()
        if not selection:
            return

        task_id = self._task_tree.item(selection[0], 'values')[0]
        try:
            from core.task_scheduler import get_task_scheduler
            scheduler = get_task_scheduler()

            full_id = [t.id for t in scheduler.list_tasks() if t.id.endswith(task_id)]
            if full_id:
                scheduler.resume_task(full_id[0])
                self._task_log.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] ▶ 恢复任务: {task_id}\n")
                self._task_log.see(tk.END)
                self._refresh_tasks()
        except Exception as e:
            pass

    def _delete_task(self):
        """删除选中的任务"""
        selection = self._task_tree.selection()
        if not selection:
            return

        task_id = self._task_tree.item(selection[0], 'values')[0]
        try:
            from core.task_scheduler import get_task_scheduler
            scheduler = get_task_scheduler()

            full_id = [t.id for t in scheduler.list_tasks() if t.id.endswith(task_id)]
            if full_id:
                scheduler.remove_task(full_id[0])
                self._task_log.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] 🗑 删除任务: {task_id}\n")
                self._task_log.see(tk.END)
                self._refresh_tasks()
        except Exception as e:
            pass

    def _sample_data_task(self):
        """示例数据更新任务"""
        print(f"[{datetime.now()}] 执行数据更新任务...")
        return {"success": True}

    # ---- 实时行情轮询操作 ----

    def _subscribe_realtime(self):
        """订阅实时行情"""
        symbol = "000001"  # 简化：固定订阅示例股票
        try:
            from core.realtime_poller import get_realtime_poller
            poller = get_realtime_poller()
            poller.subscribe(symbol, self._on_realtime_data)

            # 添加到行情列表
            for item in self._quote_tree.get_children():
                if self._quote_tree.item(item, 'values')[0] == symbol:
                    return

            self._quote_tree.insert('', 'end', values=(symbol, '平安银行', '--', '--', '--', '--'))
            self._alert_log.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] ➕ 订阅: {symbol}\n")
            self._alert_log.see(tk.END)
        except Exception as e:
            self._alert_log.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] ❌ 订阅失败: {e}\n")
            self._alert_log.see(tk.END)

    def _start_realtime_polling(self):
        """启动实时行情轮询"""
        try:
            from core.realtime_poller import get_realtime_poller
            poller = get_realtime_poller()
            poller.start(poll_interval=5)
            self._realtime_status.config(text="运行中", foreground='green')
            self._alert_log.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] ✅ 实时行情轮询已启动\n")
            self._alert_log.see(tk.END)
        except Exception as e:
            self._alert_log.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] ❌ 启动失败: {e}\n")
            self._alert_log.see(tk.END)

    def _stop_realtime_polling(self):
        """停止实时行情轮询"""
        try:
            from core.realtime_poller import get_realtime_poller
            poller = get_realtime_poller()
            poller.stop()
            self._realtime_status.config(text="已停止", foreground='red')
            self._alert_log.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] ⏹ 实时行情轮询已停止\n")
            self._alert_log.see(tk.END)
        except Exception as e:
            pass

    def _on_realtime_data(self, data):
        """实时行情数据回调"""
        def update_ui():
            for item in self._quote_tree.get_children():
                if self._quote_tree.item(item, 'values')[0] == data.symbol:
                    color = 'green' if data.change_pct >= 0 else 'red'
                    self._quote_tree.item(item, values=(
                        data.symbol,
                        '平安银行',
                        f"{data.price:.2f}",
                        f"{data.change_pct:+.2f}%",
                        f"{data.volume/10000:.1f}万",
                        data.timestamp.strftime('%H:%M:%S')
                    ))

                    # 涨跌幅预警
                    if abs(data.change_pct) >= 5:
                        self._alert_log.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ {data.symbol} 涨跌幅 {data.change_pct:.2f}%\n")
                        self._alert_log.see(tk.END)
                    break

        self.root.after(0, update_ui)

    def _build_cline_agent_tab(self, notebook):
        """Cline智能体聊天界面"""
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="🤖 Cline智能体")
        
        # 聊天区域
        chat_frame = ttk.Frame(tab)
        chat_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        # 聊天消息区域
        self._cline_chat = scrolledtext.ScrolledText(chat_frame, bg='#0f0f1a', fg='#e0e0e0', 
                                                     font=('Microsoft YaHei', 10), wrap=tk.WORD)
        self._cline_chat.pack(fill='both', expand=True, padx=5, pady=5)
        self._cline_chat.insert('end', "🤖 Cline智能体已就绪\n")
        self._cline_chat.insert('end', "────────────────────────────────\n")
        self._cline_chat.insert('end', "您可以使用以下命令：\n")
        self._cline_chat.insert('end', "- 直接输入问题进行对话\n")
        self._cline_chat.insert('end', "- 执行文件操作、终端命令\n")
        self._cline_chat.insert('end', "- 分析量化策略、编写代码\n")
        self._cline_chat.insert('end', "────────────────────────────────\n\n")
        self._cline_chat.config(state='disabled')
        
        # 输入区域
        input_frame = ttk.Frame(tab)
        input_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Label(input_frame, text="提问:").pack(side='left', padx=5)
        self._cline_input = ttk.Entry(input_frame, width=80)
        self._cline_input.pack(side='left', padx=5, fill='x', expand=True)
        self._cline_input.bind('<Return>', self._send_cline_message)
        
        ttk.Button(input_frame, text="发送", command=self._send_cline_message).pack(side='left', padx=5)
        
        # 快速命令按钮
        quick_frame = ttk.LabelFrame(tab, text="快速命令")
        quick_frame.pack(fill='x', padx=5, pady=3)
        
        quick_commands = [
            ("📊 分析策略", "帮我分析这个量化策略的风险点"),
            ("💡 代码审查", "审查这段Python代码是否有问题"),
            ("📈 市场分析", "分析当前A股市场走势"),
            ("🔧 编写代码", "帮我写一个简单的MACD策略"),
            ("❓ 帮助", "你能做什么？"),
        ]
        
        for label, cmd in quick_commands:
            ttk.Button(quick_frame, text=label, 
                       command=lambda c=cmd: self._send_cline_message(text=c)).pack(side='left', padx=3)
    
    def _send_cline_message(self, event=None, text=None):
        """发送消息给Cline智能体"""
        if text is None:
            text = self._cline_input.get().strip()
        
        if not text:
            return
        
        # 清空输入框
        self._cline_input.delete(0, tk.END)
        
        # 显示用户消息
        self._cline_chat.config(state='normal')
        self._cline_chat.insert('end', f"👤 您: {text}\n\n")
        self._cline_chat.config(state='disabled')
        self._cline_chat.see(tk.END)
        
        # 在子线程中调用Cline
        def run_cline():
            try:
                from llm_manager import llm_manager
                
                # 切换到Cline提供者
                if llm_manager.set_active_provider('cline'):
                    # 调用聊天接口
                    response = llm_manager.simple_chat(text)
                    
                    # 更新UI
                    def update_response():
                        self._cline_chat.config(state='normal')
                        self._cline_chat.insert('end', f"🤖 Cline: {response}\n\n")
                        self._cline_chat.config(state='disabled')
                        self._cline_chat.see(tk.END)
                    
                    self.root.after(0, update_response)
                else:
                    self.root.after(0, lambda: self._show_cline_error("Cline智能体不可用"))
            except Exception as e:
                self.root.after(0, lambda: self._show_cline_error(f"Cline调用失败: {str(e)}"))
        
        threading.Thread(target=run_cline, daemon=True).start()
    
    def _show_cline_error(self, message):
        """显示Cline错误消息"""
        self._cline_chat.config(state='normal')
        self._cline_chat.insert('end', f"❌ {message}\n\n")
        self._cline_chat.config(state='disabled')
        self._cline_chat.see(tk.END)


# ============================================================

def main():
    """主入口"""
    print("=" * 60)
    print("  QS Robot V2.0 - 量化策略管理平台")
    print("  Aurora DeepSeek V3.2T + QS Robot 双核统一")
    print("=" * 60)
    print()

    app = QSRobotDesktopV2()
    app.run()


if __name__ == '__main__':
    main()
