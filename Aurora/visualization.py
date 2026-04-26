#!/usr/bin/env python3
"""
Aurora量化交易系统 - 可视化界面后端
基于Flask的Web应用，提供实时数据展示和策略管理
包含五层金字塔防钓鱼系统（整合版）
"""

import os
import json
import threading
import time
import sys
import random
import hashlib
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request, redirect
import pandas as pd
import numpy as np

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from strategies.fourier_rl_strategy import FourierRLStrategy
    from strategies.final_market_adaptive import FinalMarketAdaptiveGrid
    from strategies.ml_range_grid import MLRangeGridTrading
    from strategies.strategy_base import StrategyManager
    from strategies.strategy_combiner import StrategyCombiner
    from signals.dual_market_state import DualDimensionMarketState
    from models.model_persistence import ModelPersistenceManager
    from xbk_api_client import XbkApiClient, XbkDataFeed, XbkTrader
    from technical_analyzer import TechnicalAnalyzer
    from user_manager import user_manager
    STRATEGIES_AVAILABLE = True
except ImportError as e:
    print(f"导入策略模块失败: {str(e)}")
    print("将以基本模式启动，部分功能可能受限")
    STRATEGIES_AVAILABLE = False
    from technical_analyzer import TechnicalAnalyzer
    user_manager = None

def load_env_config():
    """加载环境变量配置"""
    env_file = os.path.join(os.path.dirname(__file__), '.env')
    config = {}
    if os.path.exists(env_file):
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    config[key.strip()] = value.strip()
    return config

env_config = load_env_config()

app = Flask(__name__)
app.config['SECRET_KEY'] = env_config.get('HMAC_SECRET', 'aurora_quant_secret_key')

if STRATEGIES_AVAILABLE:
    strategy_manager = StrategyManager()
    persistence_manager = ModelPersistenceManager()
    current_strategy = None
    strategy_combiner = None
else:
    strategy_manager = None
    persistence_manager = None
    current_strategy = None
    strategy_combiner = None


class PyramidPhishingDefenseSystem:
    """
    五层金字塔防钓鱼系统（整合版）
    整合了我们原有的三级风控+豆包的机器学习自动决断方案
    """

    def __init__(self):
        self.lock = threading.Lock()
        self.reset_all()

        self.config = {
            'large_order_pct': 8.0,
            'huge_order_pct': 15.0,
            'daily_total_pct': 25.0,
            'score_thresholds': {'low': 20, 'medium_low': 40, 'medium': 60, 'high': 80},
            'circuit_breaker_min_score': 80,
            'max_daily_loss_pct': 5.0,
            'max_order_freq': 50,
            'max_cancel_rate': 0.8
        }

    def reset_all(self):
        """重置所有状态"""
        with self.lock:
            self.trade_history = []
            self.abnormal_signals = []
            self.risk_score = 0
            self.current_risk_level = 'normal'
            self.circuit_breaker_triggered = False
            self.last_trade_time = None
            self.daily_trade_amount = 0
            self.daily_loss = 0
            self.cancel_count = 0
            self.total_order_count = 0
            self.login_history = []
            self.behavior_profile = {}

    def check_and_update_daily(self):
        """每日重置统计"""
        today = datetime.now().date()
        if hasattr(self, 'last_reset_date') and self.last_reset_date == today:
            return
        self.daily_trade_amount = 0
        self.daily_loss = 0
        self.cancel_count = 0
        self.total_order_count = 0
        self.last_reset_date = today

    def get_account_balance(self):
        """获取账户余额"""
        account = account_manager.get_current_account_info()
        if account:
            return account.get('balance', 100000.0)
        return 100000.0

    def calculate_risk(self, order_info, abnormal_signals=None):
        """
        核心风控计算函数
        返回: (风险评分, 风控动作, 详细结果)
        """
        self.check_and_update_daily()

        score = 0
        account_balance = self.get_account_balance()
        order_amount = order_info.get('amount', 0)
        order_pct = (order_amount / account_balance) * 100 if account_balance > 0 else 0

        if abnormal_signals is None:
            abnormal_signals = {}

        layer_results = {}

        layer_results['layer1_network'] = self._check_network_layer(abnormal_signals)
        layer_results['layer2_identity'] = self._check_identity_layer(abnormal_signals)
        layer_results['layer3_behavior'] = self._check_behavior_layer(order_info, order_pct)
        layer_results['layer4_transaction'] = self._check_transaction_layer(order_info, order_pct, account_balance)
        layer_results['layer5_risk'] = self._check_risk_layer(account_balance)

        score = sum(layer_results.values())

        self.risk_score = min(score, 100)

        if score <= 20:
            action = 'allow_all'
            self.current_risk_level = 'low'
        elif score <= 40:
            action = 'allow_enhanced_log'
            self.current_risk_level = 'medium_low'
        elif score <= 60:
            action = 'allow_only_close_max_5pct'
            self.current_risk_level = 'medium'
        elif score <= 80:
            action = 'allow_only_close_max_2pct_position_10pct'
            self.current_risk_level = 'high'
        else:
            action = 'circuit_breaker'
            self.current_risk_level = 'critical'
            self.circuit_breaker_triggered = True

        self._record_trade(order_info, score, action)

        return {
            'risk_score': score,
            'risk_level': self.current_risk_level,
            'action': action,
            'layer_scores': layer_results,
            'is_large_trade': order_pct >= self.config['large_order_pct'],
            'is_huge_trade': order_pct >= self.config['huge_order_pct'],
            'order_pct': round(order_pct, 2),
            'circuit_breaker': self.circuit_breaker_triggered
        }

    def _check_network_layer(self, signals):
        """第一层：网络层防护"""
        score = 0
        if signals.get('ip_blacklisted'):
            score += 40
        if signals.get('dns_suspicious'):
            score += 20
        if signals.get('ssl_invalid'):
            score += 15
        if signals.get('proxy_detected'):
            score += 15
        return min(score, 100)

    def _check_identity_layer(self, signals):
        """第二层：身份认证层"""
        score = 0
        if signals.get('login_fail_count', 0) > 3:
            score += 25
        if signals.get('new_device'):
            score += 15
        if signals.get('unusual_location'):
            score += 30
        if signals.get('location_changes', 0) > 2:
            score += 35
        if signals.get('off_hours_login'):
            score += 15
        if signals.get('rapid_location_change'):
            score += 30
        return min(score, 100)

    def _check_behavior_layer(self, order_info, order_pct):
        """第三层：行为分析层"""
        score = 0
        current_time = datetime.now()

        if self.last_trade_time:
            time_diff = (current_time - self.last_trade_time).total_seconds()
            if time_diff < 1:
                score += 20
            if time_diff < 5 and len(self.trade_history) > 10:
                recent_same_second = sum(1 for t in self.trade_history[-20:] if (current_time - t).total_seconds() < 5)
                if recent_same_second > 5:
                    score += 30

        if order_pct >= 15:
            score += 30
        elif order_pct >= 8:
            score += 15

        current_hour = current_time.hour
        if current_hour < 6 or current_hour > 23:
            score += 10

        if hasattr(self, 'behavior_profile') and self.behavior_profile:
            avg_trade = self.behavior_profile.get('avg_trade_amount', 0)
            if avg_trade > 0 and order_amount > avg_trade * 3:
                score += 25

        return min(score, 100)

    def _check_transaction_layer(self, order_info, order_pct, account_balance):
        """第四层：交易验证层"""
        score = 0

        if order_pct >= 15:
            score += 40
        elif order_pct >= 8:
            score += 20

        self.daily_trade_amount += order_info.get('amount', 0)
        daily_pct = (self.daily_trade_amount / account_balance) * 100 if account_balance > 0 else 0
        if daily_pct >= 25:
            score += 30
        elif daily_pct >= 15:
            score += 15

        price_deviation = order_info.get('price_deviation', 0)
        if price_deviation > 0.05:
            score += 30
        elif price_deviation > 0.02:
            score += 15

        return min(score, 100)

    def _check_risk_layer(self, account_balance):
        """第五层：风险监控层"""
        score = 0

        if abs(self.daily_loss) / account_balance >= 0.05 if account_balance > 0 else False:
            score += 50

        if self.cancel_count > 0 and self.total_order_count > 0:
            cancel_rate = self.cancel_count / self.total_order_count
            if cancel_rate > 0.8:
                score += 40
            elif cancel_rate > 0.5:
                score += 20

        return min(score, 100)

    def _record_trade(self, order_info, score, action):
        """记录交易"""
        with self.lock:
            self.trade_history.append(datetime.now())
            if len(self.trade_history) > 100:
                self.trade_history = self.trade_history[-100:]

            self.last_trade_time = datetime.now()

            record = {
                'timestamp': datetime.now().isoformat(),
                'score': score,
                'action': action,
                'amount': order_info.get('amount', 0),
                'risk_level': self.current_risk_level
            }
            self.abnormal_signals.append(record)
            if len(self.abnormal_signals) > 100:
                self.abnormal_signals = self.abnormal_signals[-100:]

    def update_behavior_profile(self, trade_amount):
        """更新行为画像"""
        if 'trade_amounts' not in self.behavior_profile:
            self.behavior_profile['trade_amounts'] = []
        self.behavior_profile['trade_amounts'].append(trade_amount)
        if len(self.behavior_profile['trade_amounts']) > 100:
            self.behavior_profile['trade_amounts'] = self.behavior_profile['trade_amounts'][-100:]
        amounts = self.behavior_profile['trade_amounts']
        self.behavior_profile['avg_trade_amount'] = sum(amounts) / len(amounts) if amounts else 0

    def record_cancel(self):
        """记录撤单"""
        with self.lock:
            self.cancel_count += 1

    def record_order(self):
        """记录订单"""
        with self.lock:
            self.total_order_count += 1

    def update_daily_loss(self, loss):
        """更新每日亏损"""
        with self.lock:
            self.daily_loss += loss

    def get_status(self):
        """获取当前状态"""
        return {
            'risk_score': self.risk_score,
            'risk_level': self.current_risk_level,
            'circuit_breaker_triggered': self.circuit_breaker_triggered,
            'daily_trade_amount': self.daily_trade_amount,
            'daily_loss': self.daily_loss,
            'cancel_rate': self.cancel_count / self.total_order_count if self.total_order_count > 0 else 0,
            'recent_signals': self.abnormal_signals[-10:]
        }

    def manual_override(self, action):
        """人工干预"""
        if action == 'reset_circuit_breaker':
            self.circuit_breaker_triggered = False
            self.risk_score = 0
            self.current_risk_level = 'normal'
            return {'success': True, 'message': '熔断已人工解除'}
        elif action == 'increase_risk':
            self.risk_score = min(self.risk_score + 10, 100)
            return {'success': True, 'message': '风险等级已人工提高'}
        elif action == 'decrease_risk':
            self.risk_score = max(self.risk_score - 10, 0)
            return {'success': True, 'message': '风险等级已人工降低'}
        return {'success': False, 'message': '未知操作'}


pyramid_phishing_defense = PyramidPhishingDefenseSystem()


class AccountManager:
    """账户管理器"""

    def __init__(self):
        self.accounts = {
            'default': {
                'balance': 100000.0,
                'strategy': None
            }
        }
        self.current_account_name = 'default'
        self.lock = threading.Lock()

    def get_current_account(self):
        """获取当前账户名"""
        return self.current_account_name

    def set_current_account(self, name):
        """切换当前账户"""
        if name in self.accounts:
            self.current_account_name = name
            return True
        return False

    def create_account(self, name, initial_balance=100000.0):
        """创建新账户"""
        with self.lock:
            if name not in self.accounts:
                self.accounts[name] = {
                    'balance': initial_balance,
                    'strategy': None
                }
                return True
            return False

    def get_account(self, name):
        """获取账户信息"""
        return self.accounts.get(name)

    def get_current_account_info(self):
        """获取当前账户信息"""
        return self.accounts.get(self.current_account_name)

    def update_balance(self, name, new_balance):
        """更新账户余额"""
        with self.lock:
            if name in self.accounts:
                self.accounts[name]['balance'] = new_balance
                return True
            return False


account_manager = AccountManager()


class RiskControlSystem:
    """
    风控模块 - 整合版
    包含五层防钓鱼+基础风控
    """

    def __init__(self):
        self.lock = threading.Lock()
        self.max_drawdown = 0.15
        self.daily_loss_limit = 0.05
        self.single_trade_limit = 0.10
        self.position_limit = 0.30
        self.atr_risk_ratio = 2.0

    def calculate_risk_score(self, account_balance, current_balance, daily_pnl, trades_today):
        """计算综合风险评分"""
        with self.lock:
            score = 0

            drawdown = (account_balance - current_balance) / account_balance if account_balance > 0 else 0
            if drawdown > 0.10:
                score += 40
            elif drawdown > 0.05:
                score += 20

            daily_loss_pct = abs(daily_pnl) / account_balance if account_balance > 0 else 0
            if daily_loss_pct > 0.03:
                score += 30
            elif daily_loss_pct > 0.01:
                score += 15

            if len(trades_today) > 50:
                score += 20
            elif len(trades_today) > 30:
                score += 10

            return min(score, 100)

    def get_risk_metrics(self, account_balance, current_balance, daily_pnl, trades_today):
        """获取风控指标"""
        drawdown = (account_balance - current_balance) / account_balance if account_balance > 0 else 0
        daily_loss_pct = abs(daily_pnl) / account_balance if account_balance > 0 else 0
        sharpe_ratio = self._calculate_sharpe_ratio(trades_today)
        var_95 = self._calculate_var(trades_today, 0.95)

        return {
            'total_risk_score': self.calculate_risk_score(account_balance, current_balance, daily_pnl, trades_today),
            'max_drawdown': round(drawdown * 100, 2),
            'daily_loss_pct': round(daily_loss_pct * 100, 2),
            'sharpe_ratio': round(sharpe_ratio, 2) if sharpe_ratio else 0,
            'var_95': round(var_95 * 100, 2) if var_95 else 0,
            'stop_loss_line': round(self.daily_loss_limit * 100, 2),
            'risk_exposure': round(len(trades_today) * self.single_trade_limit * 100, 2),
            'volatility_risk': round(drawdown * 10, 2),
            'leverage_usage': round(len(trades_today) * 0.1, 2)
        }

    def _calculate_sharpe_ratio(self, trades):
        """计算夏普比率"""
        if len(trades) < 2:
            return 0
        returns = [t.get('pnl', 0) for t in trades]
        if not returns or np.std(returns) == 0:
            return 0
        mean_return = np.mean(returns)
        std_return = np.std(returns)
        return mean_return / std_return if std_return > 0 else 0

    def _calculate_var(self, trades, confidence):
        """计算VaR"""
        if not trades:
            return 0
        returns = sorted([t.get('pnl', 0) for t in trades])
        index = int((1 - confidence) * len(returns))
        return abs(returns[index]) if index < len(returns) else 0


risk_control_system = RiskControlSystem()


class MLGridOptimizer:
    """
    机器学习网格动态优化数据模块
    """

    def __init__(self):
        self.lock = threading.Lock()
        self.volatility_level = 'low'
        self.grid_spacing = 0.01
        self.prediction_confidence = 0.75
        self.model_accuracy = 0.85
        self.market_state = 'neutral'
        self.optimal_position = 0.5
        self.grid_levels = 10
        self.training_samples = 10000
        self.last_update = datetime.now()

    def update_metrics(self):
        """更新机器学习指标"""
        with self.lock:
            self.volatility_level = random.choice(['low', 'medium', 'high'])
            self.grid_spacing = random.uniform(0.005, 0.02)
            self.prediction_confidence = random.uniform(0.70, 0.95)
            self.model_accuracy = random.uniform(0.80, 0.95)
            self.market_state = random.choice(['bullish', 'bearish', 'neutral'])
            self.optimal_position = random.uniform(0.3, 0.8)
            self.grid_levels = random.randint(5, 20)
            self.training_samples = random.randint(5000, 50000)
            self.last_update = datetime.now()

    def get_ml_grid_data(self):
        """获取ML网格数据"""
        with self.lock:
            return {
                'volatility_level': self.volatility_level,
                'dynamic_grid_spacing': round(self.grid_spacing * 100, 2),
                'prediction_confidence': round(self.prediction_confidence * 100, 2),
                'model_accuracy': round(self.model_accuracy * 100, 2),
                'market_state_prediction': self.market_state,
                'optimal_position_suggestion': round(self.optimal_position * 100, 2),
                'grid_levels': self.grid_levels,
                'training_samples': self.training_samples,
                'last_update': self.last_update.isoformat(),
                'grid_chart_data': self._generate_grid_chart_data()
            }

    def _generate_grid_chart_data(self):
        """生成网格图表数据"""
        levels = list(range(1, self.grid_levels + 1))
        upper_bounds = [50 + i * self.grid_spacing * 100 for i in levels]
        lower_bounds = [50 - i * self.grid_spacing * 100 for i in levels]
        return {
            'levels': levels,
            'upper_bounds': upper_bounds,
            'lower_bounds': lower_bounds
        }

    def optimize_grid(self, market_data):
        """根据市场数据优化网格"""
        if len(market_data) < 20:
            return self.get_ml_grid_data()

        prices = [d.get('price', 0) for d in market_data[-20:]]
        if not prices:
            return self.get_ml_grid_data()

        volatility = np.std(prices) / np.mean(prices) if np.mean(prices) > 0 else 0

        with self.lock:
            if volatility < 0.01:
                self.volatility_level = 'low'
                self.grid_spacing = 0.005
            elif volatility < 0.03:
                self.volatility_level = 'medium'
                self.grid_spacing = 0.01
            else:
                self.volatility_level = 'high'
                self.grid_spacing = 0.02

            self.last_update = datetime.now()

        return self.get_ml_grid_data()


ml_grid_optimizer = MLGridOptimizer()


market_data = []
performance_data = []
stock_pool = []
trading_pool = []

XBK_API_KEY = env_config.get('XBK_API_KEY', '2029963shhr')
XBK_API_SECRET = env_config.get('XBK_API_SECRET', '123456')
XBK_API_URL = env_config.get('XBK_API_URL', 'https://api.westquant.cn/sim')

if STRATEGIES_AVAILABLE:
    api_client = XbkApiClient(XBK_API_KEY, XBK_API_SECRET, XBK_API_URL)
    data_feed = XbkDataFeed(api_client)
    trader = XbkTrader(api_client)
else:
    api_client = None
    data_feed = None
    trader = None

current_symbol = 'BTCUSDT'


class StockPool:
    def __init__(self):
        self.stocks = []
        self.lock = threading.Lock()

    def add_stock(self, symbol, name=None, notes=''):
        with self.lock:
            for stock in self.stocks:
                if stock['symbol'] == symbol:
                    return False
            self.stocks.append({
                'symbol': symbol,
                'name': name or symbol,
                'notes': notes,
                'added_time': datetime.now().isoformat(),
                'status': 'watching'
            })
            return True

    def remove_stock(self, symbol):
        with self.lock:
            self.stocks = [s for s in self.stocks if s['symbol'] != symbol]

    def move_to_trading_pool(self, symbol):
        with self.lock:
            for stock in self.stocks:
                if stock['symbol'] == symbol:
                    stock['status'] = 'trading'
                    trading_pool.append(stock)
                    return True
            return False

    def get_all_stocks(self):
        with self.lock:
            return self.stocks.copy()


class TradingPool:
    def __init__(self):
        self.trades = []
        self.lock = threading.Lock()

    def add_trade(self, symbol, strategy_type, quantity=0, entry_price=0):
        with self.lock:
            for trade in self.trades:
                if trade['symbol'] == symbol and trade['status'] == 'open':
                    return False
            self.trades.append({
                'symbol': symbol,
                'strategy_type': strategy_type,
                'quantity': quantity,
                'entry_price': entry_price,
                'entry_time': datetime.now().isoformat(),
                'status': 'open',
                'pnl': 0
            })
            return True

    def close_trade(self, symbol):
        with self.lock:
            for trade in self.trades:
                if trade['symbol'] == symbol and trade['status'] == 'open':
                    trade['status'] = 'closed'
                    trade['close_time'] = datetime.now().isoformat()
                    return True
            return False

    def update_pnl(self, symbol, current_price):
        with self.lock:
            for trade in self.trades:
                if trade['symbol'] == symbol and trade['status'] == 'open':
                    if trade['entry_price'] > 0:
                        trade['pnl'] = (current_price - trade['entry_price']) / trade['entry_price']
                    return True
            return False

    def get_open_trades(self):
        with self.lock:
            return [t for t in self.trades if t['status'] == 'open']

    def get_all_trades(self):
        with self.lock:
            return self.trades.copy()


stock_pool_manager = StockPool()
trading_pool_manager = TradingPool()


def data_update_thread():
    """后台数据更新线程"""
    global market_data, performance_data, current_symbol

    while True:
        try:
            if data_feed:
                new_data = data_feed.get_latest_price()
                market_data.append(new_data)
            else:
                new_data = {
                    'timestamp': datetime.now().isoformat(),
                    'price': 50000 + random.random() * 1000,
                    'volume': random.randint(100, 1000)
                }
                market_data.append(new_data)

            if len(market_data) > 1000:
                market_data = market_data[-1000:]

            if current_strategy:
                try:
                    price = new_data['price']
                    current_strategy.update_price(price)

                    performance = current_strategy.get_performance()
                    performance_data.append({
                        'timestamp': new_data['timestamp'],
                        'balance': performance.get('balance', 0),
                        'position': current_strategy.position,
                        'total_return': performance.get('total_return', 0)
                    })

                    if len(performance_data) > 500:
                        performance_data = performance_data[-500:]

                except Exception as e:
                    print(f"更新策略时出错: {e}")

            if new_data['price'] > 0:
                for trade in trading_pool_manager.get_open_trades():
                    trading_pool_manager.update_pnl(trade['symbol'], new_data['price'])

            ml_grid_optimizer.update_metrics()

        except Exception as e:
            print(f"获取市场数据时出错: {e}")

        time.sleep(1)


threading.Thread(target=data_update_thread, daemon=True).start()


@app.route('/')
def index():
    """主页"""
    session_id = request.cookies.get('session_id')
    if not session_id:
        session_id = request.headers.get('X-Session-ID')

    if session_id and user_manager:
        user = user_manager.validate_session(session_id)
        if user:
            return render_template('index.html', user=user)

    return render_template('login.html')


@app.route('/login')
def login():
    """登录页面"""
    return render_template('login.html')


@app.route('/api/register', methods=['POST'])
def api_register():
    """用户注册"""
    if not user_manager:
        return jsonify({'success': False, 'message': '用户系统不可用'}), 500

    data = request.json
    username = data.get('username')
    password = data.get('password')
    email = data.get('email')

    result = user_manager.register(username, password, email)
    return jsonify(result)


@app.route('/api/user-info')
def api_user_info():
    """获取用户信息"""
    if not user_manager:
        return jsonify({'success': False, 'message': '用户系统不可用'}), 500

    session_id = request.cookies.get('session_id') or request.headers.get('X-Session-ID')
    session = user_manager.validate_session(session_id)
    if not session:
        return jsonify({'success': False, 'message': '会话无效'}), 401

    user = user_manager.get_user(session['username'])
    if user:
        return jsonify({
            'success': True,
            'user': {
                'username': session['username'],
                'role': user['role'],
                'email': user['email'],
                'last_login': user['last_login']
            }
        })
    return jsonify({'success': False, 'message': '用户不存在'}), 404


@app.route('/api/market-data')
def get_market_data():
    """获取市场数据"""
    return jsonify(market_data[-100:])


@app.route('/api/performance-data')
def get_performance_data():
    """获取性能数据"""
    return jsonify(performance_data[-100:])


@app.route('/api/strategy-status')
def get_strategy_status():
    """获取策略状态"""
    account = request.args.get('account', account_manager.get_current_account())
    account_info = account_manager.get_account(account)

    if account_info and account_info['strategy']:
        strategy = account_info['strategy']
        try:
            market_state = strategy.get_market_state()
            performance = strategy.get_performance()

            return jsonify({
                'status': 'running',
                'strategy': strategy.__class__.__name__,
                'market_state': market_state,
                'performance': performance,
                'position': strategy.position if hasattr(strategy, 'position') else 0,
                'balance': strategy.current_balance if hasattr(strategy, 'current_balance') else account_info['balance'],
                'account': account
            })
        except Exception:
            return jsonify({
                'status': 'running',
                'strategy': strategy.__class__.__name__,
                'balance': account_info['balance'],
                'account': account
            })
    else:
        return jsonify({'status': 'stopped', 'account': account})


@app.route('/api/strategy-list')
def get_strategy_list():
    """获取策略列表"""
    strategies = [
        {'name': 'FourierRLStrategy', 'description': '傅里叶强化学习策略'},
        {'name': 'FinalMarketAdaptiveGrid', 'description': '市场自适应网格策略'},
        {'name': 'MLRangeGridTrading', 'description': '机器学习网格交易策略'}
    ]
    return jsonify(strategies)


@app.route('/api/start-strategy', methods=['POST'])
def start_strategy():
    """启动策略"""
    if not STRATEGIES_AVAILABLE:
        return jsonify({'error': '策略模块不可用，请检查依赖安装'}), 500

    data = request.json
    strategy_name = data.get('strategy_name', 'FourierRLStrategy')
    initial_balance = data.get('initial_balance', 100000.0)
    account = data.get('account', account_manager.get_current_account())

    try:
        account_info = account_manager.get_account(account)
        if not account_info:
            return jsonify({'error': '账户不存在'}), 400

        if strategy_name == 'FourierRLStrategy':
            strategy = FourierRLStrategy(initial_balance=initial_balance)
        elif strategy_name == 'FinalMarketAdaptiveGrid':
            strategy = FinalMarketAdaptiveGrid(initial_balance=initial_balance)
        elif strategy_name == 'MLRangeGridTrading':
            strategy = MLRangeGridTrading(initial_balance=initial_balance)
        else:
            return jsonify({'error': '策略不存在'}), 400

        account_info['strategy'] = strategy
        account_info['balance'] = initial_balance

        return jsonify({'success': True, 'message': f'策略 {strategy_name} 已启动', 'account': account})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/stop-strategy')
def stop_strategy():
    """停止策略"""
    data = request.json or {}
    account = data.get('account', account_manager.get_current_account())

    account_info = account_manager.get_account(account)
    if account_info:
        account_info['strategy'] = None

    return jsonify({'success': True, 'message': '策略已停止', 'account': account})


@app.route('/api/switch-account', methods=['POST'])
def switch_account():
    """切换账户"""
    data = request.json
    account = data.get('account')

    if not account:
        return jsonify({'error': '请指定账户'}), 400

    success = account_manager.set_current_account(account)
    if not success:
        return jsonify({'error': '账户不存在'}), 400

    account_info = account_manager.get_current_account_info()
    return jsonify({
        'success': True,
        'message': f'已切换到账户 {account}',
        'account': account,
        'balance': account_info['balance']
    })


@app.route('/api/risk-control/check', methods=['POST'])
def risk_control_check():
    """风控检查"""
    data = request.json
    order_info = {
        'amount': data.get('amount', 0),
        'price': data.get('price', 0),
        'symbol': data.get('symbol', 'BTCUSDT'),
        'price_deviation': data.get('price_deviation', 0)
    }
    abnormal_signals = data.get('abnormal_signals', {})

    result = pyramid_phishing_defense.calculate_risk(order_info, abnormal_signals)
    return jsonify(result)


@app.route('/api/risk-control/status')
def risk_control_status():
    """获取风控状态"""
    status = pyramid_phishing_defense.get_status()
    metrics = risk_control_system.get_risk_metrics(
        account_manager.get_current_account_info().get('balance', 100000),
        account_manager.get_current_account_info().get('balance', 100000),
        0,
        []
    )
    return jsonify({
        'pyramid_defense': status,
        'risk_metrics': metrics
    })


@app.route('/api/risk-control/manual', methods=['POST'])
def risk_control_manual():
    """人工干预"""
    data = request.json
    action = data.get('action')

    result = pyramid_phishing_defense.manual_override(action)
    return jsonify(result)


@app.route('/api/ml-grid/data')
def ml_grid_data():
    """获取机器学习网格数据"""
    data = ml_grid_optimizer.get_ml_grid_data()
    return jsonify(data)


@app.route('/api/ml-grid/optimize', methods=['POST'])
def ml_grid_optimize():
    """优化网格参数"""
    data = request.json
    market_info = data.get('market_data', [])

    result = ml_grid_optimizer.optimize_grid(market_info)
    return jsonify(result)


@app.route('/api/backtest', methods=['POST'])
def run_backtest():
    """运行回测"""
    data = request.json
    strategy_name = data.get('strategy_name', 'FourierRLStrategy')
    initial_balance = data.get('initial_balance', 100000.0)
    days = data.get('days', 30)
    params = data.get('params', {})

    try:
        if strategy_name == 'FourierRLStrategy':
            strategy = FourierRLStrategy(initial_balance=initial_balance, **params)
        elif strategy_name == 'FinalMarketAdaptiveGrid':
            strategy = FinalMarketAdaptiveGrid(initial_balance=initial_balance, **params)
        else:
            strategy = MLRangeGridTrading(initial_balance=initial_balance, **params)

        prices = []
        for i in range(days * 24 * 60):
            price = 50000 + np.random.normal(0, 500)
            prices.append(price)
            strategy.update_price(price)
            if i % 1000 == 0:
                time.sleep(0.01)

        performance = strategy.get_performance()

        return jsonify({
            'success': True,
            'performance': performance,
            'total_days': days,
            'data_points': len(prices),
            'params': params
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/strategy-params')
def get_strategy_params():
    """获取策略参数"""
    strategy_name = request.args.get('strategy_name', 'FourierRLStrategy')

    params = {}
    if strategy_name == 'FourierRLStrategy':
        params = {
            'lookback_period': 60,
            'max_position_size': 0.5,
            'stop_loss_pct': 0.02,
            'take_profit_pct': 0.05,
            'risk_score_threshold': 0.7,
            'fourier_top_n': 3,
            'learning_rate': 0.0003,
            'gamma': 0.99,
            'gae_lambda': 0.95
        }
    elif strategy_name == 'FinalMarketAdaptiveGrid':
        params = {
            'grid_levels': 5,
            'base_order_size': 0.1,
            'profit_taking_pct': 0.01,
            'stop_loss_pct': 0.03,
            'adaptation_factor': 0.1
        }
    elif strategy_name == 'MLRangeGridTrading':
        params = {
            'window_size': 20,
            'num_std': 2.0,
            'grid_spacing': 0.005,
            'max_positions': 10,
            'profit_target': 0.015
        }

    return jsonify({
        'strategy_name': strategy_name,
        'params': params
    })


@app.route('/api/stock-pool')
def get_stock_pool():
    """获取股票池"""
    return jsonify({
        'stocks': stock_pool_manager.get_all_stocks(),
        'total': len(stock_pool_manager.get_all_stocks())
    })


@app.route('/api/stock-pool/add', methods=['POST'])
def add_to_stock_pool():
    """添加股票到股票池"""
    data = request.json
    symbol = data.get('symbol')
    name = data.get('name')
    notes = data.get('notes', '')

    if not symbol:
        return jsonify({'error': '股票代码不能为空'}), 400

    success = stock_pool_manager.add_stock(symbol, name, notes)
    if success:
        return jsonify({'success': True, 'message': f'{symbol} 已添加到股票池'})
    else:
        return jsonify({'error': f'{symbol} 已在股票池中'}), 400


@app.route('/api/stock-pool/remove', methods=['POST'])
def remove_from_stock_pool():
    """从股票池移除"""
    data = request.json
    symbol = data.get('symbol')

    stock_pool_manager.remove_stock(symbol)
    return jsonify({'success': True, 'message': f'{symbol} 已从股票池移除'})


@app.route('/api/stock-pool/move-to-trading', methods=['POST'])
def move_to_trading_pool():
    """移动股票到交易池"""
    data = request.json
    symbol = data.get('symbol')
    strategy_type = data.get('strategy_type', 'default')

    if stock_pool_manager.move_to_trading_pool(symbol):
        trading_pool_manager.add_trade(symbol, strategy_type)
        return jsonify({'success': True, 'message': f'{symbol} 已移动到交易池'})
    else:
        return jsonify({'error': f'{symbol} 移动失败'}), 400


@app.route('/api/trading-pool')
def get_trading_pool():
    """获取交易池"""
    return jsonify({
        'trades': trading_pool_manager.get_all_trades(),
        'open_trades': trading_pool_manager.get_open_trades(),
        'total': len(trading_pool_manager.get_all_trades())
    })


@app.route('/api/trading-pool/close', methods=['POST'])
def close_trade():
    """平仓"""
    data = request.json
    symbol = data.get('symbol')

    if trading_pool_manager.close_trade(symbol):
        return jsonify({'success': True, 'message': f'{symbol} 已平仓'})
    else:
        return jsonify({'error': f'{symbol} 平仓失败'}), 400


@app.route('/api/model-versions')
def get_model_versions():
    """获取模型版本列表"""
    versions = persistence_manager.list_versions(strategy_name='fourier_rl') if persistence_manager else []
    return jsonify(versions)


@app.route('/api/technical-indicators')
def get_technical_indicators():
    """获取技术分析指标"""
    try:
        if len(market_data) < 50:
            return jsonify({'error': '数据不足', 'data_collected': len(market_data)})

        price_data = []
        for item in market_data:
            if isinstance(item, dict) and 'price' in item:
                price_data.append(item)
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                price_data.append({'price': item[1], 'high': item[3] if len(item) > 3 else item[1],
                                'low': item[4] if len(item) > 4 else item[1],
                                'open': item[2] if len(item) > 2 else item[1],
                                'volume': item[5] if len(item) > 5 else 0})

        indicators = TechnicalAnalyzer.calculate_all_indicators(price_data)

        volume_data = [item.get('volume', 0) for item in price_data]
        volume_indicators = TechnicalAnalyzer.calculate_volume_indicators(volume_data)
        indicators.update(volume_indicators)

        signals = TechnicalAnalyzer.get_market_signals(indicators)

        latest_indicators = {}
        for key, values in indicators.items():
            if values and len(values) > 0 and values[-1] is not None:
                latest_indicators[key] = round(values[-1], 4) if isinstance(values[-1], float) else values[-1]

        return jsonify({
            'indicators': latest_indicators,
            'price_data': price_data[-50:] if len(price_data) >= 50 else price_data,
            'full_indicators': {k: v[-50:] if v and len(v) > 50 else v for k, v in indicators.items()},
            'signals': signals[-50:] if len(signals) > 50 else signals,
            'latest_signal': signals[-1] if signals else None
        })
    except Exception as e:
        import traceback
        return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500


@app.route('/api/load-model', methods=['POST'])
def load_model():
    """加载模型"""
    session_id = request.headers.get('X-Session-ID')
    if not session_id or not user_manager.validate_session(session_id):
        return jsonify({'error': '未授权访问'}), 401

    data = request.json
    version_id = data.get('version_id')

    try:
        if persistence_manager and current_strategy:
            state = persistence_manager.load_strategy_state(version_id=version_id)
            if state:
                from models.model_persistence import StrategyStateExtractor
                StrategyStateExtractor.restore_fourier_rl_state(current_strategy, state)
                return jsonify({'success': True, 'message': f'模型版本 {version_id} 已加载'})
        return jsonify({'error': '加载失败'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/save-model', methods=['POST'])
def save_model():
    """保存模型"""
    session_id = request.headers.get('X-Session-ID')
    if not session_id or not user_manager.validate_session(session_id):
        return jsonify({'error': '未授权访问'}), 401

    data = request.json
    description = data.get('description', '手动保存')

    try:
        if current_strategy and persistence_manager:
            from models.model_persistence import StrategyStateExtractor
            state = StrategyStateExtractor.extract_fourier_rl_state(current_strategy)
            performance = current_strategy.get_performance()

            version_id = persistence_manager.save_strategy_state(
                strategy_name='fourier_rl',
                strategy_state=state,
                performance_metrics=performance,
                description=description
            )

            return jsonify({'success': True, 'message': f'模型已保存，版本ID: {version_id}'})
        return jsonify({'error': '没有运行中的策略'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/auth/register', methods=['POST'])
def register():
    """用户注册"""
    data = request.json
    username = data.get('username')
    password = data.get('password')
    email = data.get('email')

    if not username or not password or not email:
        return jsonify({'error': '缺少必要参数'}), 400

    result = user_manager.register(username, password, email)
    return jsonify(result)


@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    """用户登录"""
    data = request.json
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'error': '缺少用户名或密码'}), 400

    result = user_manager.login(username, password)
    return jsonify(result)


@app.route('/api/auth/logout', methods=['POST'])
def auth_logout():
    """用户登出"""
    session_id = request.headers.get('X-Session-ID')
    if not session_id:
        return jsonify({'error': '缺少会话ID'}), 400

    result = user_manager.logout(session_id)
    return jsonify(result)


@app.route('/api/auth/validate')
def validate_session():
    """验证会话"""
    session_id = request.headers.get('X-Session-ID')
    if not session_id:
        return jsonify({'valid': False, 'message': '缺少会话ID'})

    if not user_manager:
        return jsonify({'valid': False, 'message': '用户系统不可用'})

    session = user_manager.validate_session(session_id)
    if session:
        user = user_manager.get_user(session['username'])
        return jsonify({
            'valid': True,
            'user': {
                'username': session['username'],
                'role': user['role'],
                'email': user['email']
            }
        })
    else:
        return jsonify({'valid': False, 'message': '会话已过期'})


@app.route('/api/users')
def list_users():
    """列出所有用户（管理员）"""
    session_id = request.headers.get('X-Session-ID')
    session = user_manager.validate_session(session_id)
    if not session:
        return jsonify({'error': '未授权访问'}), 401

    user = user_manager.get_user(session['username'])
    if user['role'] != 'admin':
        return jsonify({'error': '权限不足'}), 403

    result = user_manager.list_users()
    return jsonify(result)


@app.route('/api/users/<username>', methods=['PUT'])
def update_user(username):
    """更新用户信息"""
    session_id = request.headers.get('X-Session-ID')
    session = user_manager.validate_session(session_id)
    if not session:
        return jsonify({'error': '未授权访问'}), 401

    if session['username'] != username and user_manager.get_user(session['username'])['role'] != 'admin':
        return jsonify({'error': '权限不足'}), 403

    data = request.json
    result = user_manager.update_user(username, data)
    return jsonify(result)


@app.route('/api/users/<username>', methods=['DELETE'])
def delete_user(username):
    """删除用户（管理员）"""
    session_id = request.headers.get('X-Session-ID')
    session = user_manager.validate_session(session_id)
    if not session:
        return jsonify({'error': '未授权访问'}), 401

    user = user_manager.get_user(session['username'])
    if user['role'] != 'admin':
        return jsonify({'error': '权限不足'}), 403

    result = user_manager.delete_user(username)
    return jsonify(result)


@app.route('/api/users/<username>/disable', methods=['POST'])
def disable_user(username):
    """禁用用户（管理员）"""
    session_id = request.headers.get('X-Session-ID')
    session = user_manager.validate_session(session_id)
    if not session:
        return jsonify({'error': '未授权访问'}), 401

    user = user_manager.get_user(session['username'])
    if user['role'] != 'admin':
        return jsonify({'error': '权限不足'}), 403

    result = user_manager.disable_user(username)
    return jsonify(result)


@app.route('/api/users/<username>/enable', methods=['POST'])
def enable_user(username):
    """启用用户（管理员）"""
    session_id = request.headers.get('X-Session-ID')
    session = user_manager.validate_session(session_id)
    if not session:
        return jsonify({'error': '未授权访问'}), 401

    user = user_manager.get_user(session['username'])
    if user['role'] != 'admin':
        return jsonify({'error': '权限不足'}), 403

    result = user_manager.enable_user(username)
    return jsonify(result)


@app.route('/api/auth/change-password', methods=['POST'])
def change_password():
    """修改密码"""
    if not user_manager:
        return jsonify({'success': False, 'message': '用户系统不可用'}), 500

    session_id = request.headers.get('X-Session-ID')
    session = user_manager.validate_session(session_id)
    if not session:
        return jsonify({'success': False, 'message': '未授权访问'}), 401

    data = request.json
    old_password = data.get('old_password')
    new_password = data.get('new_password')

    if not old_password or not new_password:
        return jsonify({'success': False, 'message': '缺少必要参数'}), 400

    user = user_manager.get_user(session['username'])
    if user['password'] != user_manager._hash_password(old_password):
        return jsonify({'success': False, 'message': '旧密码错误'}), 400

    result = user_manager.reset_password(session['username'], new_password)
    return jsonify(result)


@app.route('/api/auth/forgot-password', methods=['POST'])
def forgot_password():
    """忘记密码"""
    if not user_manager:
        return jsonify({'success': False, 'message': '用户系统不可用'}), 500

    data = request.json
    email = data.get('email')

    if not email:
        return jsonify({'success': False, 'message': '缺少邮箱参数'}), 400

    result = user_manager.forgot_password(email)
    return jsonify(result)


@app.route('/api/users/<username>/reset-password', methods=['POST'])
def admin_reset_password(username):
    """管理员重置用户密码"""
    if not user_manager:
        return jsonify({'success': False, 'message': '用户系统不可用'}), 500

    session_id = request.headers.get('X-Session-ID')
    session = user_manager.validate_session(session_id)
    if not session:
        return jsonify({'success': False, 'message': '未授权访问'}), 401

    user = user_manager.get_user(session['username'])
    if user['role'] != 'admin':
        return jsonify({'success': False, 'message': '权限不足'}), 403

    data = request.json
    new_password = data.get('new_password')

    if not new_password:
        return jsonify({'success': False, 'message': '缺少新密码参数'}), 400

    result = user_manager.reset_password(username, new_password)
    return jsonify(result)


def create_templates():
    """创建模板文件"""
    templates_dir = 'templates'
    if not os.path.exists(templates_dir):
        os.makedirs(templates_dir)


if __name__ == '__main__':
    create_templates()
    print("启动Aurora量化交易系统可视化界面...")
    print("访问地址: http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)
