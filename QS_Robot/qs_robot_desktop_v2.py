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

        # 标签5: 系统监控
        self._build_monitor_tab(notebook)

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
        """回测中心标签页"""
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="🧪 回测中心")

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

        # 结果列表
        columns = ('strategy', 'return', 'sharpe', 'drawdown', 'winrate', 'trades')
        self._bt_tree = ttk.Treeview(tab, columns=columns, show='headings', height=12)
        self._bt_tree.heading('strategy', text='策略')
        self._bt_tree.heading('return', text='收益%')
        self._bt_tree.heading('sharpe', text='夏普')
        self._bt_tree.heading('drawdown', text='回撤%')
        self._bt_tree.heading('winrate', text='胜率%')
        self._bt_tree.heading('trades', text='交易次数')
        self._bt_tree.column('strategy', width=200)
        self._bt_tree.column('return', width=80)
        self._bt_tree.column('sharpe', width=80)
        self._bt_tree.column('drawdown', width=80)
        self._bt_tree.column('winrate', width=80)
        self._bt_tree.column('trades', width=80)
        self._bt_tree.pack(fill='both', expand=True, padx=5)

        # 回测日志
        self._bt_log = scrolledtext.ScrolledText(tab, height=6, bg='#0f0f1a',
                                                  fg='#00ff88', font=('Consolas', 9))
        self._bt_log.pack(fill='x', padx=5, pady=5)

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
                else:
                    self._tau_shepherd_status.set(f"❌ 失败: {result.get('error', '未知错误')}")
            except Exception as e:
                self._tau_shepherd_status.set(f"❌ 异常: {str(e)}")

        threading.Thread(target=run_thread, daemon=True).start()

    def _build_monitor_tab(self, notebook):
        """系统监控标签页"""
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="🔍 系统监控")

        # 健康状态
        health_frame = ttk.Frame(tab)
        health_frame.pack(fill='x', padx=5, pady=5)

        ttk.Label(health_frame, text="系统健康状态",
                  font=('Microsoft YaHei', 12, 'bold')).pack(anchor='w')

        self._health_text = scrolledtext.ScrolledText(
            health_frame, height=8, bg='#0f0f1a', fg='#e0e0e0',
            font=('Consolas', 9), state='disabled'
        )
        self._health_text.pack(fill='x', pady=5)

        # 增益模块
        gain_frame = ttk.Frame(tab)
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
        risk_frame = ttk.Frame(tab)
        risk_frame.pack(fill='x', padx=5, pady=5)
        ttk.Label(risk_frame, text="风险控制状态",
                  font=('Microsoft YaHei', 12, 'bold')).pack(anchor='w')
        self._risk_text = scrolledtext.ScrolledText(
            risk_frame, height=8, bg='#0f0f1a', fg='#e0e0e0',
            font=('Consolas', 9), state='disabled'
        )
        self._risk_text.pack(fill='x', pady=5)

    def _build_action_bar(self):
        """底部操作栏"""
        bar = ttk.Frame(self.root)
        bar.pack(fill='x', padx=5, pady=3)

        ttk.Checkbutton(bar, text="自动刷新(30s)", variable=self._auto_refresh).pack(side='left', padx=5)
        ttk.Button(bar, text="🔽 最小化到托盘", command=self._minimize_to_tray).pack(side='left', padx=5)
        ttk.Button(bar, text="🖥 打开Aurora Web", command=self._open_aurora).pack(side='left', padx=5)
        ttk.Button(bar, text="❌ 退出", command=self._quit_app).pack(side='right', padx=5)

        ttk.Label(bar, text="QS Robot V2.0 | Aurora DeepSeek V3.2T",
                  font=('Microsoft YaHei', 8), foreground='#555555').pack(side='right', padx=20)

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
        """刷新策略列表"""
        if not self.strategy_mgr:
            return
        try:
            strategies = self.strategy_mgr.get_strategy_list(force=True)
            self._strategy_tree.delete(*self._strategy_tree.get_children())
            for s in strategies:
                status = "运行中" if s['name'] in self.strategy_mgr._active_strategies else "停止"
                tau_status = self._tau_cache.get(s['name'], '--')
                self._strategy_tree.insert('', 'end', values=(
                    s['name'], s.get('category', ''), s.get('label', s['name']), status, tau_status
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
            # 更新缓存并刷新显示
            self._tau_cache[strategy_name] = f"★{score:.3f}"
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
        """执行回测"""
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
            result = self.strategy_mgr.run_backtest(name, days, balance)
            self._bt_tree.insert('', 0, values=(
                result.strategy_name, f"{result.total_return_pct:.2f}",
                f"{result.sharpe_ratio:.4f}", f"{result.max_drawdown:.2f}",
                f"{result.win_rate:.1f}", result.total_trades
            ))
            self._bt_log.insert(tk.END,
                f"[{datetime.now().strftime('%H:%M:%S')}] ✅ 完成: "
                f"收益={result.total_return_pct:.2f}%, 夏普={result.sharpe_ratio:.4f}\n")
            self._bt_log.see(tk.END)
            self._set_status("回测完成", 'green')
        except Exception as e:
            self._bt_log.insert(tk.END,
                f"[{datetime.now().strftime('%H:%M:%S')}] ❌ 失败: {e}\n")
            self._bt_log.see(tk.END)
            self._set_status(f"回测失败: {e}", 'red')

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
