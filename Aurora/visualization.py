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
from flask import Flask, render_template, jsonify, request, redirect, session as flask_session
import pandas as pd
import numpy as np
from functools import wraps

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 首先单独导入 user_manager（关键！）
user_manager = None
try:
    from user_manager import user_manager
    print("[OK] user_manager imported successfully")
except Exception as e:
    print(f"[WARNING] user_manager import failed: {e}")

# ========== 会话认证装饰器 ==========
def require_session(f):
    """要求有效会话的装饰器 - 保护交易安全API"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 检查请求头中的会话ID
        session_id = request.headers.get('X-Session-ID')
        if not session_id:
            return jsonify({
                'success': False,
                'message': 'SESSION_REQUIRED: 缺少会话ID',
                'code': 'SESSION_MISSING'
            }), 401
        
        if not user_manager:
            return jsonify({
                'success': False,
                'message': 'SESSION_REQUIRED: 用户系统不可用',
                'code': 'USER_MANAGER_UNAVAILABLE'
            }), 503
        
        session = user_manager.validate_session(session_id)
        if not session:
            return jsonify({
                'success': False,
                'message': 'SESSION_REQUIRED: 会话无效或已过期',
                'code': 'SESSION_INVALID'
            }), 401
        
        # 将会话信息注入到请求中
        request.current_session = session
        request.current_user = session.get('username', 'unknown')
        return f(*args, **kwargs)
    return decorated_function


# 导入策略注册表（统一策略管理）
try:
    from strategies.strategy_registry import (
        STRATEGY_REGISTRY, get_strategy_list_api, create_strategy,
        get_strategy_info, get_strategies_by_category, get_strategies_by_regime,
        get_recommended_strategies, StrategyCategory, MarketRegime
    )
    STRATEGIES_AVAILABLE = True
    print(f"[OK] StrategyRegistry loaded: {len(STRATEGY_REGISTRY)} strategies registered")
except ImportError as e:
    print(f"[WARNING] StrategyRegistry import failed: {e}")
    # 回退到直接导入
    try:
        from strategies.fourier_rl_strategy import FourierRLStrategy
        from strategies.final_market_adaptive import FinalMarketAdaptiveGrid
        from strategies.ml_range_grid import MLRangeGridTrading
        from strategies.huijin_value_strategy import HuijinValueStrategy
        from strategies.strategy_base import StrategyManager
        from strategies.strategy_combiner import StrategyCombiner
        from signals.dual_market_state import DualDimensionMarketState
        from models.model_persistence import ModelPersistenceManager
        from xbk_api_client import XbkApiClient, XbkDataFeed, XbkTrader
        from technical_analyzer import TechnicalAnalyzer
        STRATEGIES_AVAILABLE = True
    except ImportError as e2:
        print(f"导入策略模块失败: {str(e2)}")
        print("将以基本模式启动，部分功能可能受限")
        STRATEGIES_AVAILABLE = False
        from technical_analyzer import TechnicalAnalyzer

# 导入系统健康监控和安全模块
health_monitor = None
monitoring_scheduler = None
database_manager = None
security_control = None
geo_location = None
trade_validator = None

try:
    from monitor.system_health import get_system_health_monitor
    health_monitor = get_system_health_monitor()
    print("[OK] system_health_monitor imported successfully")
except Exception as e:
    print(f"[WARNING] system_health_monitor import failed: {e}")

try:
    from monitor.scheduler import get_monitoring_scheduler, initialize_default_tasks
    initialize_default_tasks()
    monitoring_scheduler = get_monitoring_scheduler()
    print("[OK] monitoring_scheduler imported successfully")
except Exception as e:
    print(f"[WARNING] monitoring_scheduler import failed: {e}")

try:
    from utils.database_manager import get_database_manager
    database_manager = get_database_manager()
    print("[OK] database_manager imported successfully")
except Exception as e:
    print(f"[WARNING] database_manager import failed: {e}")

try:
    from risk.data_source_risk_control import get_security_control
    security_control = get_security_control()
    print("[OK] security_control imported successfully")
except Exception as e:
    print(f"[WARNING] security_control import failed: {e}")

try:
    import geo_location as gl
    geo_location = gl.geo_location
    print("[OK] geo_location imported successfully")
except Exception as e:
    print(f"[WARNING] geo_location import failed: {e}")

try:
    from trade_security import (
        trade_validator, critical_path_validator, 
        fund_security_validator, trade_execution_engine
    )
    print("[OK] trade_validator imported successfully")
except Exception as e:
    print(f"[WARNING] trade_validator import failed: {e}")

# ========== 增益性优化模块导入 ==========
strategy_performance_tracker = None
unified_risk_controller = None
smart_param_optimizer = None
rl_enhancer = None
data_quality_validator = None

# ========== 数据库维护模块 ==========
db_maintenance_scheduler = None

try:
    from utils.db_maintenance import DatabaseMaintenanceScheduler
    db_maintenance_scheduler = DatabaseMaintenanceScheduler()
    print("[OK] DatabaseMaintenanceScheduler imported successfully")
except Exception as e:
    print(f"[WARNING] DatabaseMaintenanceScheduler import failed: {e}")

try:
    from utils.strategy_performance_tracker import get_performance_tracker
    strategy_performance_tracker = get_performance_tracker()
    print("[OK] strategy_performance_tracker imported successfully")
except Exception as e:
    print(f"[WARNING] strategy_performance_tracker import failed: {e}")

try:
    from utils.unified_risk_controller import get_risk_controller
    unified_risk_controller = get_risk_controller()
    print("[OK] unified_risk_controller imported successfully")
except Exception as e:
    print(f"[WARNING] unified_risk_controller import failed: {e}")

try:
    from utils.smart_param_optimizer import get_param_optimizer
    smart_param_optimizer = get_param_optimizer()
    print("[OK] smart_param_optimizer imported successfully")
except Exception as e:
    print(f"[WARNING] smart_param_optimizer import failed: {e}")

try:
    from utils.rl_enhancer import get_rl_enhancer
    rl_enhancer = get_rl_enhancer()
    print("[OK] rl_enhancer imported successfully")
except Exception as e:
    print(f"[WARNING] rl_enhancer import failed: {e}")

try:
    from utils.data_quality_validator import get_data_validator
    data_quality_validator = get_data_validator()
    print("[OK] data_quality_validator imported successfully")
except Exception as e:
    print(f"[WARNING] data_quality_validator import failed: {e}")

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
            'max_cancel_rate': 0.8,
            'whitelist_cities': ['青州', '烟台'],  # 白名单城市
            'disable_off_hours_check': True  # 禁用非工作时间检查
        }
        # 从 user_manager 加载安全配置（如果可用）
        self._load_security_config_from_user_manager()

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
    
    def _load_security_config_from_user_manager(self):
        """从 user_manager 加载安全配置"""
        try:
            if user_manager:
                security_config = user_manager.get_security_config()
                self.config['whitelist_cities'] = security_config.get('whitelist_cities', ['青州', '烟台'])
                self.config['disable_off_hours_check'] = security_config.get('disable_off_hours_check', True)
                print("[OK] 已从 user_manager 加载安全配置")
        except Exception as e:
            print(f"[WARNING] 从 user_manager 加载安全配置失败: {e}")
    
    def update_security_config(self):
        """更新安全配置（从 user_manager 重新加载）"""
        self._load_security_config_from_user_manager()

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
        
        # 检查位置是否在白名单中
        current_city = signals.get('current_city', '')
        if current_city in self.config.get('whitelist_cities', []):
            # 白名单城市，不检查地理位置异常
            pass
        else:
            if signals.get('unusual_location'):
                score += 30
            if signals.get('location_changes', 0) > 2:
                score += 35
            if signals.get('rapid_location_change'):
                score += 30
        
        # 检查是否禁用非工作时间检查
        if not self.config.get('disable_off_hours_check', False):
            if signals.get('off_hours_login'):
                score += 15
        
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

        # 检查是否禁用非工作时间检查
        if not self.config.get('disable_off_hours_check', False):
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

# ========== 西部宽客 API 配置 ==========
# 实盘交易环境
XBK_API_KEY = env_config.get('XBK_API_KEY', '60201554shhr')
XBK_API_SECRET = env_config.get('XBK_API_SECRET', '200231')
XBK_API_URL = env_config.get('XBK_API_URL', 'https://api.westquant.cn/sim')

# 实盘交易环境（请在获取真实密钥后替换）
# XBK_API_KEY = '您的真实API密钥'
# XBK_API_SECRET = '您的真实API密钥密码'
XBK_API_URL_LIVE = env_config.get('XBK_API_URL_LIVE', 'https://api.westquant.cn/api')

# 交易模式配置
CURRENT_TRADING_MODE = 'sim'  # 'sim' 模拟交易, 'live' 实盘交易

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


# 数据更新线程的失败计数
_data_update_error_count = 0
_last_error_log_time = 0

def data_update_thread():
    """后台数据更新线程"""
    global market_data, performance_data, current_symbol
    global _data_update_error_count, _last_error_log_time

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
                    _data_update_error_count += 1
                    now = time.time()
                    if _data_update_error_count <= 1 or now - _last_error_log_time >= 30:
                        print(f"更新策略时出错: {e}")
                        _last_error_log_time = now

            if new_data['price'] > 0:
                for trade in trading_pool_manager.get_open_trades():
                    trading_pool_manager.update_pnl(trade['symbol'], new_data['price'])

            ml_grid_optimizer.update_metrics()

        except Exception as e:
            _data_update_error_count += 1
            now = time.time()
            if _data_update_error_count <= 1 or now - _last_error_log_time >= 30:
                print(f"获取市场数据时出错: {e}")
                _last_error_log_time = now

        time.sleep(1)



threading.Thread(target=data_update_thread, daemon=True).start()


@app.route('/')
def index():
    """主页 - 完整的可视化页面"""
    session_id = request.cookies.get('session_id')
    if not session_id:
        session_id = request.headers.get('X-Session-ID')

    if session_id and user_manager:
        user = user_manager.validate_session(session_id)
        if user:
            return render_template('dashboard.html', user=user)

    return redirect('/login')


@app.route('/login')
def login():
    """登录页面"""
    return render_template('login.html')


@app.route('/register')
def register_page():
    """注册页面"""
    return render_template('register.html')


@app.route('/security-config')
def security_config():
    """安全配置管理页面"""
    return render_template('security-config.html')


@app.route('/security-monitor')
def security_monitor():
    """安全监控中心页面 - 可视化展示完整安全流程"""
    return render_template('security_monitor.html')

@app.route('/maintenance')
def maintenance():
    """系统维护页面 - 显示系统状态、维护任务和服务状态"""
    return render_template('maintenance.html')

@app.route('/simple-test')
def simple_test():
    """简单测试页面"""
    return render_template('simple_test.html')

@app.route('/dashboard')
def dashboard():
    """监控仪表盘页面 - 渲染完整仪表盘"""
    session_id = request.cookies.get('session_id')
    if not session_id:
        session_id = request.headers.get('X-Session-ID')

    if session_id and user_manager:
        user = user_manager.validate_session(session_id)
        if user:
            return render_template('dashboard.html', user=user)

    return redirect('/login')


@app.route('/deepseek')
def deepseek():
    """DeepSeek 量化交易界面"""
    session_id = request.cookies.get('session_id')
    if not session_id:
        session_id = request.headers.get('X-Session-ID')

    if session_id and user_manager:
        user = user_manager.validate_session(session_id)
        if user:
            return render_template('deepseek.html', user=user)

    return render_template('login.html')


@app.route('/api/health')
def api_health():
    """
    综合健康检查端点
    检测系统各核心组件的健康状态
    """
    results = {
        "timestamp": datetime.now().isoformat(),
        "status": "healthy",
        "components": {}
    }
    
    # 检测各核心组件
    checks = [
        ("auth", check_auth_service),
        ("strategy", check_strategy_service),
        ("risk", check_risk_service),
        ("data", check_data_service),
        ("system", check_system_resources),
        ("port", check_port_status)
    ]
    
    # 添加新模块的检查
    new_checks = [
        ("health_monitor", check_health_monitor),
        ("monitoring_scheduler", check_monitoring_scheduler),
        ("database", check_database_manager),
        ("security", check_security_control)
    ]
    
    all_checks = checks + new_checks
    
    for name, check_func in all_checks:
        try:
            result = check_func()
            results["components"][name] = result
            if result["status"] != "healthy":
                results["status"] = "degraded" if results["status"] == "healthy" else "critical"
        except Exception as e:
            results["components"][name] = {
                "status": "critical",
                "error": str(e)
            }
            results["status"] = "critical"
    
    # 根据状态返回HTTP状态码
    status_code = 200 if results["status"] == "healthy" else 503
    return jsonify(results), status_code


def check_health_monitor():
    """检查健康监控模块"""
    try:
        if health_monitor:
            summary = health_monitor.get_health_summary()
            return {
                "status": "healthy",
                "message": "健康监控正常",
                "total_checks": summary.get("total_checks", 0),
                "last_check": summary.get("last_check")
            }
        else:
            return {"status": "warning", "message": "健康监控未初始化"}
    except Exception as e:
        return {"status": "critical", "error": str(e)}


def check_monitoring_scheduler():
    """检查监控调度器"""
    try:
        if monitoring_scheduler:
            status = monitoring_scheduler.get_status()
            return {
                "status": "healthy",
                "message": "监控调度器正常",
                "running": status.get("running", False),
                "task_count": status.get("task_count", 0)
            }
        else:
            return {"status": "warning", "message": "监控调度器未初始化"}
    except Exception as e:
        return {"status": "critical", "error": str(e)}


def check_database_manager():
    """检查数据库管理器"""
    try:
        if database_manager:
            stats = database_manager.get_database_stats()
            return {
                "status": "healthy",
                "message": "数据库正常",
                "stats": stats
            }
        else:
            return {"status": "warning", "message": "数据库管理器未初始化"}
    except Exception as e:
        return {"status": "critical", "error": str(e)}


def check_security_control():
    """检查安全控制模块"""
    try:
        if security_control:
            return {
                "status": "healthy",
                "message": "安全控制正常"
            }
        else:
            return {"status": "warning", "message": "安全控制未初始化"}
    except Exception as e:
        return {"status": "critical", "error": str(e)}


@app.route('/api/health/full')
def api_health_full():
    """获取完整的系统健康检查报告"""
    try:
        if health_monitor:
            result = health_monitor.check_all_modules()
            return jsonify({
                "success": True,
                "data": result
            })
        else:
            return jsonify({
                "success": False,
                "message": "健康监控未初始化"
            }), 503
    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


@app.route('/api/monitor/status')
def api_monitor_status():
    """获取监控调度器状态"""
    try:
        if monitoring_scheduler:
            status = monitoring_scheduler.get_status()
            return jsonify({
                "success": True,
                "data": status
            })
        else:
            return jsonify({
                "success": False,
                "message": "监控调度器未初始化"
            }), 503
    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


@app.route('/api/database/stats')
def api_database_stats():
    """获取数据库统计信息"""
    try:
        if database_manager:
            stats = database_manager.get_database_stats()
            return jsonify({
                "success": True,
                "data": stats
            })
        else:
            return jsonify({
                "success": False,
                "message": "数据库管理器未初始化"
            }), 503
    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


def check_auth_service():
    """检查认证服务"""
    try:
        return {
            "status": "healthy",
            "message": "认证服务正常",
            "users_count": len(user_manager.users) if user_manager else 0
        }
    except Exception as e:
        return {"status": "critical", "error": str(e)}


def check_strategy_service():
    """检查策略服务"""
    try:
        if STRATEGIES_AVAILABLE:
            return {
                "status": "healthy",
                "message": "策略服务正常",
                "strategies_count": len(strategy_manager.list_strategies()) if strategy_manager else 0,
                "current_strategy": current_strategy.__class__.__name__ if current_strategy else "None"
            }
        return {"status": "warning", "message": "策略模块不可用"}
    except Exception as e:
        return {"status": "critical", "error": str(e)}


def check_risk_service():
    """检查风险控制服务"""
    try:
        return {
            "status": "healthy",
            "message": "风控服务正常",
            "circuit_breaker": "active" if pyramid_phishing_defense and pyramid_phishing_defense.circuit_breaker_triggered else "inactive"
        }
    except Exception as e:
        return {"status": "critical", "error": str(e)}


def check_data_service():
    """检查数据服务"""
    try:
        # 检查数据缓存目录是否存在
        import os
        cache_dir = os.path.join(os.path.dirname(__file__), 'data_cache')
        exists = os.path.exists(cache_dir)
        return {
            "status": "healthy" if exists else "warning",
            "message": "数据缓存目录存在" if exists else "数据缓存目录不存在",
            "cache_exists": exists
        }
    except Exception as e:
        return {"status": "critical", "error": str(e)}


def check_system_resources():
    """检查系统资源"""
    try:
        import psutil
        process = psutil.Process()
        memory_usage = process.memory_info().rss / (1024 * 1024)
        cpu_percent = psutil.cpu_percent(interval=0.1)
        
        status = "healthy"
        if memory_usage > 1000:
            status = "warning"
        if cpu_percent > 80:
            status = "warning"
        
        return {
            "status": status,
            "message": "系统资源正常",
            "memory_mb": round(memory_usage, 1),
            "cpu_percent": cpu_percent
        }
    except ImportError:
        return {"status": "healthy", "message": "系统资源监控不可用（缺少psutil）"}
    except Exception as e:
        return {"status": "warning", "error": str(e)}


def check_port_status():
    """检查端口状态"""
    try:
        from utils.port_manager import get_port_manager
        pm = get_port_manager()
        
        ports = [5000, 8000, 8080]
        port_status = {}
        all_available = True
        
        for port in ports:
            available = pm.is_port_available(port)
            port_status[str(port)] = "available" if available else "in_use"
            if not available:
                all_available = False
        
        return {
            "status": "healthy" if all_available else "warning",
            "message": "端口状态正常" if all_available else "部分端口被占用",
            "ports": port_status
        }
    except Exception as e:
        return {"status": "warning", "error": str(e)}


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
    """获取策略列表（含分类分组）"""
    try:
        from strategies.strategy_registry import get_strategy_list_api
        api_data = get_strategy_list_api()
        return jsonify(api_data)
    except ImportError:
        # 回退到旧版列表（完整14策略）
        strategies = [
            {'name': 'FourierRLStrategy', 'label': '傅里叶强化学习策略', 'description': '傅里叶变换+PPO强化学习'},
            {'name': 'FinalMarketAdaptiveGrid', 'label': '市场自适应网格策略', 'description': '随机森林市场分类+自适应网格'},
            {'name': 'MLRangeGridTrading', 'label': '机器学习网格交易策略', 'description': '随机森林优化网格步长'},
            {'name': 'HuijinValueStrategy', 'label': '汇金价值AI轮动策略', 'description': '价值投资+AI轮动'},
            {'name': 'AdaptiveMLStrategy', 'label': '自适应机器学习策略', 'description': '在线学习+自适应参数调整'},
            {'name': 'AdaptiveRangeGridTrading', 'label': '自适应范围网格策略', 'description': '动态范围检测+网格交易'},
            {'name': 'DownMarketStrategy', 'label': '下跌市场防御策略', 'description': '下跌趋势对冲+仓位控制'},
            {'name': 'MultiFactorResonanceStrategy', 'label': '多因子共振策略', 'description': '多技术指标共振信号'},
            {'name': 'MovingAveragesStrategy', 'label': '移动平均线趋势策略', 'description': '双均线交叉+趋势跟踪'},
            {'name': 'HighReturnGridTrading', 'label': '高收益网格交易策略', 'description': '激进网格+高频率交易'},
            {'name': 'GridTrading', 'label': '经典网格交易策略', 'description': '经典网格+区间震荡交易'},
            {'name': 'DCAStrategy', 'label': '定投策略', 'description': '定期定额+成本平均'},
            {'name': 'PPOTradingAgent', 'label': 'PPO强化学习交易智能体', 'description': '深度强化学习+自主决策'},
            {'name': 'FinalOptimizedStrategy', 'label': '最终优化综合策略', 'description': '多策略融合+综合优化'},
        ]
        return jsonify({'categories': {}, 'total_count': len(strategies), 'active_count': 0, 'beta_count': 0})


@app.route('/api/strategy-info')
def get_strategy_info_api():
    """获取单个策略的详细信息"""
    strategy_name = request.args.get('name', '')
    if not strategy_name:
        return jsonify({'error': '请指定策略名称'}), 400

    try:
        from strategies.strategy_registry import get_strategy_info as get_info
        info = get_info(strategy_name)
        if info:
            return jsonify(info)
        return jsonify({'error': f'策略不存在: {strategy_name}'}), 404
    except ImportError:
        return jsonify({'error': '策略注册表不可用'}), 500


@app.route('/api/start-strategy', methods=['POST'])
def start_strategy():
    """启动策略（使用策略注册表工厂）"""
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

        # 使用策略注册表工厂创建策略实例
        try:
            from strategies.strategy_registry import create_strategy, get_strategy_info
            info = get_strategy_info(strategy_name)
            if info:
                strategy = create_strategy(strategy_name, initial_balance=initial_balance)
            else:
                return jsonify({'error': f'策略不存在: {strategy_name}'}), 400
        except ImportError:
            # 回退到旧版硬编码（完整14策略映射）
            strategy_map = {
                'FourierRLStrategy': ('strategies.fourier_rl_strategy', 'FourierRLStrategy'),
                'FinalMarketAdaptiveGrid': ('strategies.final_market_adaptive', 'FinalMarketAdaptiveGrid'),
                'MLRangeGridTrading': ('strategies.ml_range_grid', 'MLRangeGridTrading'),
                'HuijinValueStrategy': ('strategies.huijin_value_strategy', 'HuijinValueStrategy'),
                'AdaptiveMLStrategy': ('strategies.adaptive_ml_strategy', 'AdaptiveMLStrategy'),
                'AdaptiveRangeGridTrading': ('strategies.adaptive_range_grid', 'AdaptiveRangeGridTrading'),
                'DownMarketStrategy': ('strategies.downtrend_optimized', 'DownMarketStrategy'),
                'MultiFactorResonanceStrategy': ('strategies.multi_factor_resonance', 'MultiFactorResonanceStrategy'),
                'MovingAveragesStrategy': ('strategies.trend_trading', 'MovingAveragesStrategy'),
                'HighReturnGridTrading': ('strategies.high_return_grid', 'HighReturnGridTrading'),
                'GridTrading': ('strategies.grid_trading', 'GridTrading'),
                'DCAStrategy': ('strategies.fund_allocation', 'DCAStrategy'),
                'PPOTradingAgent': ('strategies.ppo_trading_agent', 'PPOTradingAgent'),
                'FinalOptimizedStrategy': ('strategies.final_optimized_strategy', 'FinalOptimizedStrategy'),
            }
            if strategy_name in strategy_map:
                module_path, class_name = strategy_map[strategy_name]
                import importlib
                module = importlib.import_module(module_path)
                strategy_class = getattr(module, class_name)
                strategy = strategy_class(initial_balance=initial_balance)
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
    """运行回测（自动保存结果到数据库）"""
    data = request.json
    strategy_name = data.get('strategy_name', 'FourierRLStrategy')
    initial_balance = data.get('initial_balance', 100000.0)
    days = data.get('days', 30)
    params = data.get('params', {})
    symbol = data.get('symbol', 'BTCUSDT')

    try:
        # 使用策略注册表工厂创建策略实例
        try:
            from strategies.strategy_registry import create_strategy, get_strategy_info
            info = get_strategy_info(strategy_name)
            if info:
                strategy = create_strategy(strategy_name, initial_balance=initial_balance, **params)
            else:
                return jsonify({'error': f'策略不存在: {strategy_name}'}), 400
        except ImportError:
            # 回退到旧版硬编码（完整14策略映射）
            strategy_map = {
                'FourierRLStrategy': ('strategies.fourier_rl_strategy', 'FourierRLStrategy'),
                'FinalMarketAdaptiveGrid': ('strategies.final_market_adaptive', 'FinalMarketAdaptiveGrid'),
                'MLRangeGridTrading': ('strategies.ml_range_grid', 'MLRangeGridTrading'),
                'HuijinValueStrategy': ('strategies.huijin_value_strategy', 'HuijinValueStrategy'),
                'AdaptiveMLStrategy': ('strategies.adaptive_ml_strategy', 'AdaptiveMLStrategy'),
                'AdaptiveRangeGridTrading': ('strategies.adaptive_range_grid', 'AdaptiveRangeGridTrading'),
                'DownMarketStrategy': ('strategies.downtrend_optimized', 'DownMarketStrategy'),
                'MultiFactorResonanceStrategy': ('strategies.multi_factor_resonance', 'MultiFactorResonanceStrategy'),
                'MovingAveragesStrategy': ('strategies.trend_trading', 'MovingAveragesStrategy'),
                'HighReturnGridTrading': ('strategies.high_return_grid', 'HighReturnGridTrading'),
                'GridTrading': ('strategies.grid_trading', 'GridTrading'),
                'DCAStrategy': ('strategies.fund_allocation', 'DCAStrategy'),
                'PPOTradingAgent': ('strategies.ppo_trading_agent', 'PPOTradingAgent'),
                'FinalOptimizedStrategy': ('strategies.final_optimized_strategy', 'FinalOptimizedStrategy'),
            }
            if strategy_name in strategy_map:
                module_path, class_name = strategy_map[strategy_name]
                import importlib
                module = importlib.import_module(module_path)
                strategy_class = getattr(module, class_name)
                strategy = strategy_class(initial_balance=initial_balance, **params)
            else:
                return jsonify({'error': '策略不存在'}), 400

        prices = []
        start_date = datetime.now()
        for i in range(days * 24 * 60):
            price = 50000 + np.random.normal(0, 500)
            prices.append(price)
            strategy.update_price(price)
            if i % 1000 == 0:
                time.sleep(0.01)

        end_date = datetime.now()
        performance = strategy.get_performance()

        # 计算回测指标
        final_balance = performance.get('balance', initial_balance)
        total_return = performance.get('total_return', (final_balance - initial_balance) / initial_balance * 100)
        max_drawdown = performance.get('max_drawdown', 0)
        sharpe_ratio = performance.get('sharpe_ratio', 0)
        total_trades = performance.get('total_trades', 0)
        winning_trades = performance.get('winning_trades', 0)
        losing_trades = performance.get('losing_trades', 0)
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0

        # 保存回测结果到数据库
        if database_manager:
            result_dict = {
                'strategy_name': strategy_name,
                'symbol': symbol,
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'initial_balance': initial_balance,
                'final_balance': final_balance,
                'total_return': total_return,
                'annualized_return': total_return / (days / 365) if days > 0 else 0,
                'max_drawdown': max_drawdown,
                'sharpe_ratio': sharpe_ratio,
                'win_rate': win_rate,
                'total_trades': total_trades,
                'winning_trades': winning_trades,
                'losing_trades': losing_trades,
                'profit_factor': performance.get('profit_factor', 0),
                'config': params
            }
            db_success = database_manager.save_backtest_result(result_dict)
        else:
            db_success = False

        return jsonify({
            'success': True,
            'performance': performance,
            'total_days': days,
            'data_points': len(prices),
            'params': params,
            'db_saved': db_success,
            'message': '回测完成，结果已保存到数据库' if db_success else '回测完成，但数据库不可用'
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/backtest/history')
def get_backtest_history():
    """获取回测历史记录"""
    strategy_name = request.args.get('strategy_name', None)
    limit = int(request.args.get('limit', 20))
    sort_by = request.args.get('sort_by', 'created_at')

    if not database_manager:
        return jsonify({
            'success': False,
            'message': '数据库管理器不可用',
            'results': []
        })

    results = database_manager.get_backtest_results(
        strategy_name=strategy_name if strategy_name else None,
        limit=limit,
        sort_by=sort_by
    )

    return jsonify({
        'success': True,
        'results': results,
        'total': len(results)
    })


@app.route('/api/backtest/best')
def get_best_backtest():
    """获取最佳回测结果"""
    strategy_name = request.args.get('strategy_name', '')
    metric = request.args.get('metric', 'total_return')

    if not strategy_name:
        return jsonify({'success': False, 'message': '请指定策略名称'}), 400

    if not database_manager:
        return jsonify({'success': False, 'message': '数据库管理器不可用'})

    result = database_manager.get_best_backtest_result(strategy_name, metric)
    return jsonify({
        'success': True,
        'result': result
    })


@app.route('/api/backtest/delete', methods=['POST'])
def delete_backtest_results():
    """删除回测结果"""
    if not database_manager:
        return jsonify({'success': False, 'message': '数据库管理器不可用'})

    data = request.json
    strategy_name = data.get('strategy_name', None)
    before_date = data.get('before_date', None)

    deleted = database_manager.delete_backtest_results(
        strategy_name=strategy_name,
        before_date=before_date
    )

    return jsonify({
        'success': True,
        'deleted': deleted,
        'message': f'已删除 {deleted} 条回测记录'
    })


@app.route('/api/strategy-params')
def get_strategy_params():
    """获取策略参数（从注册表动态获取）"""
    strategy_name = request.args.get('strategy_name', 'FourierRLStrategy')

    try:
        from strategies.strategy_registry import get_strategy_info
        info = get_strategy_info(strategy_name)
        if info:
            params = {}
            for pname, pinfo in info["params"].items():
                params[pname] = {
                    "default": pinfo["default"],
                    "type": pinfo["type"],
                    "desc": pinfo["desc"]
                }
            return jsonify({
                'strategy_name': strategy_name,
                'params': params,
                'label': info['label'],
                'description': info['description'],
                'regime': info['regime'].value,
                'tags': info['tags'],
                'strengths': info['strengths'],
                'performance_rating': info['performance_rating']
            })
    except ImportError:
        pass

    # 回退到旧版硬编码（完整14策略参数映射）
    params = {}
    strategy_params_map = {
        'FourierRLStrategy': {
            'lookback_period': 60,
            'max_position_size': 0.5,
            'stop_loss_pct': 0.02,
            'take_profit_pct': 0.05,
            'risk_score_threshold': 0.7,
            'fourier_top_n': 3,
            'learning_rate': 0.0003,
            'gamma': 0.99,
            'gae_lambda': 0.95
        },
        'FinalMarketAdaptiveGrid': {
            'grid_levels': 5,
            'base_order_size': 0.1,
            'profit_taking_pct': 0.01,
            'stop_loss_pct': 0.03,
            'adaptation_factor': 0.1
        },
        'MLRangeGridTrading': {
            'window_size': 20,
            'num_std': 2.0,
            'grid_spacing': 0.005,
            'max_positions': 10,
            'profit_target': 0.015
        },
        'HuijinValueStrategy': {
            'initial_balance': 100000.0,
            'config_path': r"D:\Gupiao\量化交易测试设备方案\攒机\量化交易\汇金价值AI轮动策略\strategy_config.json"
        },
        'AdaptiveMLStrategy': {
            'lookback': 30,
            'max_position': 0.4,
            'stop_loss': 0.025,
            'take_profit': 0.04,
            'learning_rate': 0.001,
            'hidden_size': 64
        },
        'AdaptiveRangeGridTrading': {
            'grid_levels': 8,
            'base_size': 0.05,
            'profit_pct': 0.012,
            'stop_pct': 0.025,
            'range_buffer': 0.02
        },
        'DownMarketStrategy': {
            'max_position': 0.2,
            'stop_loss': 0.015,
            'reentry_threshold': 0.03,
            'hedge_ratio': 0.5
        },
        'MultiFactorResonanceStrategy': {
            'rsi_period': 14,
            'macd_fast': 12,
            'macd_slow': 26,
            'volume_ratio': 1.5,
            'score_threshold': 0.7
        },
        'MovingAveragesStrategy': {
            'fast_ma': 5,
            'slow_ma': 20,
            'signal_ma': 9,
            'stop_loss': 0.02
        },
        'HighReturnGridTrading': {
            'grid_levels': 12,
            'base_size': 0.08,
            'profit_pct': 0.02,
            'stop_pct': 0.04,
            'max_position': 0.6
        },
        'GridTrading': {
            'grid_levels': 10,
            'base_size': 0.1,
            'profit_pct': 0.01,
            'stop_pct': 0.03,
            'price_min': 45000,
            'price_max': 55000
        },
        'DCAStrategy': {
            'investment_amount': 1000,
            'interval_days': 7,
            'max_position': 0.3,
            'stop_loss': 0.1
        },
        'PPOTradingAgent': {
            'learning_rate': 0.0003,
            'gamma': 0.99,
            'clip_epsilon': 0.2,
            'hidden_size': 128,
            'max_position': 0.5
        },
        'FinalOptimizedStrategy': {
            'lookback': 40,
            'max_position': 0.35,
            'stop_loss': 0.02,
            'take_profit': 0.06,
            'rsi_oversold': 30,
            'rsi_overbought': 70
        },
    }
    if strategy_name in strategy_params_map:
        params = strategy_params_map[strategy_name]

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
    """用户注册（兼容前端发送的 city 字段）"""
    data = request.json
    username = data.get('username')
    password = data.get('password')
    # 兼容前端 register.html 发送 city 字段，同时支持 email 字段
    email = data.get('email', data.get('city', ''))

    if not username or not password:
        return jsonify({'success': False, 'message': '缺少用户名或密码'}), 400

    result = user_manager.register(username, password, email)
    return jsonify(result)


@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    """用户登录（自动检测地理位置 + 设备指纹）"""
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    # 自动获取真实IP和地理位置
    detected_city = None
    real_ip = None
    
    try:
        if geo_location:
            real_ip = geo_location.get_client_ip(request)
            if real_ip:
                location_info = geo_location.get_location_from_ip(real_ip)
                if location_info.get('success'):
                    detected_city = location_info.get('city', '')
                    print(f"[安全] 检测到登录IP: {real_ip}, 城市: {detected_city}")
    except Exception as e:
        print(f"地理位置检测失败: {e}")
    
    # 如果检测失败，使用用户提供的城市作为备选
    city = data.get('city', detected_city)
    if not city:
        city = detected_city
    
    if not username or not password:
        return jsonify({'error': '缺少用户名或密码'}), 400
    
    # 生成设备指纹
    device_fingerprint = None
    if user_manager and geo_location:
        # 从请求中获取设备信息
        user_agent = request.headers.get('User-Agent')
        # 使用geo_location来生成设备指纹（虽然geo_location已有这个方法吗？让我们用user_manager的方法
        device_fingerprint = user_manager.generate_device_fingerprint(
            user_agent=user_agent,
            timezone=data.get('timezone'),
            language=data.get('language')
        )
    
    remember_device = data.get('remember_device', False)

    result = user_manager.login(username, password, city, real_ip, 
                                device_fingerprint, remember_device)
    
    # 添加地理位置信息到响应
    if 'user' in result:
        result['user']['detected_city'] = detected_city
        result['user']['login_ip'] = real_ip
    
    return jsonify(result)


@app.route('/api/auth/logout', methods=['POST'])
def auth_logout():
    """用户登出"""
    session_id = request.headers.get('X-Session-ID')
    if not session_id:
        return jsonify({'error': '缺少会话ID'}), 400

    result = user_manager.logout(session_id)
    return jsonify(result)


@app.route('/api/test/location')
def test_location():
    """测试地理位置检测功能"""
    try:
        result = {
            'success': True,
            'client_ip': '未检测到',
            'detected_city': '未检测到'
        }
        
        if geo_location:
            client_ip = geo_location.get_client_ip(request)
            if client_ip:
                location = geo_location.get_location_from_ip(client_ip)
                result['client_ip'] = client_ip
                if location.get('success'):
                    result['detected_city'] = location.get('city', '未知')
                    result['country'] = location.get('country', '')
                    result['region'] = location.get('region', '')
                    result['timezone'] = location.get('timezone', '')
        
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ========== 交易安全验证API ==========

@app.route('/api/trade/validate', methods=['POST'])
@require_session
def validate_trade():
    """
    极致安全的订单验证
    包含：时间窗口、IP白名单、API Key、金额限制、频率控制
    """
    if not trade_validator:
        return jsonify({'success': False, 'message': '交易验证系统不可用'})
    
    data = request.json
    
    # 获取真实IP
    client_ip = None
    if geo_location:
        client_ip = geo_location.get_client_ip(request)
    
    # 构建订单信息
    order_info = {
        'symbol': data.get('symbol'),
        'amount': float(data.get('amount', 0)),
        'price': float(data.get('price', 0)),
        'side': data.get('side'),
        'ip': client_ip or data.get('ip'),
        'api_key': data.get('api_key'),
        'user_id': data.get('user_id')
    }
    
    # 执行极致安全验证
    result = trade_validator.validate_order(order_info)
    return jsonify(result)


@app.route('/api/trade/security/config', methods=['GET'])
@require_session
def get_trade_security_config():
    """获取交易安全配置"""
    if not trade_validator:
        return jsonify({'success': False, 'message': '交易验证系统不可用'})
    
    return jsonify({
        'success': True,
        'config': trade_validator.config
    })


@app.route('/api/trade/security/add-ip', methods=['POST'])
@require_session
def add_trusted_ip():
    """添加受信任的交易IP"""
    if not trade_validator:
        return jsonify({'success': False, 'message': '交易验证系统不可用'})
    
    data = request.json
    result = trade_validator.add_trusted_ip(
        data.get('ip'),
        data.get('description')
    )
    return jsonify(result)


@app.route('/api/trade/security/add-api-key', methods=['POST'])
@require_session
def add_valid_api_key():
    """添加有效API Key"""
    if not trade_validator:
        return jsonify({'success': False, 'message': '交易验证系统不可用'})
    
    data = request.json
    result = trade_validator.add_valid_api_key(
        data.get('api_key'),
        data.get('name')
    )
    return jsonify(result)


@app.route('/api/trade/critical/validate', methods=['POST'])
@require_session
def validate_critical_path():
    """
    毫秒级关键路径验证 - 订单执行前的绝对卡死
    这是发送交易所订单前的最后一道防线
    """
    if not critical_path_validator:
        return jsonify({'allowed': False, 'reason': 'CRITICAL: 关键路径验证器不可用'})
    
    data = request.json
    ip = data.get('ip', '')
    api_key = data.get('api_key', '')
    check_time = data.get('check_time', True)
    
    # 获取真实IP
    if geo_location and not ip:
        ip = geo_location.get_client_ip(request)
    
    # 关键路径毫秒级验证
    allowed, reason = critical_path_validator.validate_critical_path(ip, api_key, check_time)
    
    return jsonify({
        'allowed': allowed,
        'reason': reason,
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/trade/critical/refresh', methods=['POST'])
@require_session
def refresh_critical_config():
    """刷新关键路径配置（非关键路径调用）"""
    if not critical_path_validator:
        return jsonify({'success': False, 'message': '关键路径验证器不可用'})
    
    critical_path_validator.refresh_config()
    return jsonify({'success': True, 'message': '关键路径配置已刷新'})


# ========== 资金安全验证API ==========

@app.route('/api/fund/validate', methods=['POST'])
@require_session
def validate_fund_withdrawal():
    """
    资金提现验证 - 极致卡死模式
    默认：完全禁止任何资金提取
    """
    if not fund_security_validator:
        return jsonify({'allowed': False, 'reason': 'FUND: 资金安全验证器不可用'})
    
    data = request.json
    account_id = data.get('account_id', '')
    amount = float(data.get('amount', 0))
    admin_approved = data.get('admin_approved', False)
    
    # 资金提现验证
    allowed, reason = fund_security_validator.validate_withdrawal(
        account_id, amount, admin_approved
    )
    
    return jsonify({
        'allowed': allowed,
        'reason': reason,
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/fund/block-all', methods=['POST'])
@require_session
def block_all_withdrawals():
    """完全卡死所有资金提现"""
    if not fund_security_validator:
        return jsonify({'success': False, 'message': '资金安全验证器不可用'})
    
    result = fund_security_validator.block_all_withdrawals()
    return jsonify(result)


@app.route('/api/fund/blacklist/add', methods=['POST'])
@require_session
def add_to_withdrawal_blacklist():
    """添加账户到提现黑名单"""
    if not fund_security_validator:
        return jsonify({'success': False, 'message': '资金安全验证器不可用'})
    
    data = request.json
    account_id = data.get('account_id', '')
    result = fund_security_validator.add_to_blacklist(account_id)
    return jsonify(result)


@app.route('/api/fund/mode/only-trading', methods=['POST'])
@require_session
def set_only_trading_mode():
    """设置仅交易模式（禁止任何资金提取）"""
    if not fund_security_validator:
        return jsonify({'success': False, 'message': '资金安全验证器不可用'})
    
    data = request.json
    enabled = data.get('enabled', True)
    result = fund_security_validator.set_only_trading_mode(enabled)
    return jsonify(result)


@app.route('/api/fund/config', methods=['GET'])
@require_session
def get_fund_security_config():
    """获取资金安全配置"""
    if not fund_security_validator:
        return jsonify({'success': False, 'message': '资金安全验证器不可用'})
    
    return jsonify({
        'success': True,
        'config': fund_security_validator.config
    })


# ========== 完整交易执行API ==========

@app.route('/api/trade/execute', methods=['POST'])
@require_session
def execute_full_trade():
    """
    完整的交易执行流程
    1. 毫秒级关键路径验证
    2. 验证通过 -> 执行交易
    3. 验证失败 -> 拒绝交易
    
    参数:
        monitor: bool (可选) - 是否返回监控日志
    """
    if not trade_execution_engine:
        return jsonify({
            'status': 'ERROR',
            'action': '❌ 执行引擎不可用',
            'reason': '交易执行引擎未初始化',
        }), 500
    
    data = request.json
    
    # 获取真实IP
    client_ip = data.get('ip', '')
    if geo_location and not client_ip:
        client_ip = geo_location.get_client_ip(request)
    
    # 构建订单信息
    order_info = {
        'symbol': data.get('symbol', ''),
        'side': data.get('side', 'buy'),
        'amount': float(data.get('amount', 0)),
        'price': float(data.get('price', 0)),
        'ip': client_ip,
        'api_key': data.get('api_key', ''),
        'user_id': data.get('user_id', ''),
    }
    
    # 是否开启监控
    monitor = data.get('monitor', False)
    
    # 调用完整交易执行引擎（带监控
    result = trade_execution_engine.execute_trade(order_info, monitor=monitor)
    
    return jsonify(result)


@app.route('/api/trade/report', methods=['GET'])
@require_session
def get_trade_report():
    """获取交易执行报告"""
    if not trade_execution_engine:
        return jsonify({
            'success': False,
            'message': '交易执行引擎不可用',
        })
    
    return jsonify({
        'success': True,
        'report': trade_execution_engine.get_execution_report(),
    })


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


@app.route('/api/security/config', methods=['GET'])
def get_security_config():
    """获取安全配置"""
    session_id = request.headers.get('X-Session-ID')
    session = user_manager.validate_session(session_id)
    if not session:
        return jsonify({'error': '未授权访问'}), 401

    config = user_manager.get_security_config()
    return jsonify({'success': True, 'config': config})


@app.route('/api/security/whitelist/add', methods=['POST'])
def add_whitelist_city():
    """添加城市到白名单"""
    session_id = request.headers.get('X-Session-ID')
    session = user_manager.validate_session(session_id)
    if not session:
        return jsonify({'error': '未授权访问'}), 401
    
    # 检查是否是管理员
    user = user_manager.get_user(session['username'])
    if user['role'] != 'admin':
        return jsonify({'error': '权限不足'}), 403

    data = request.json
    city = data.get('city')
    if not city:
        return jsonify({'error': '缺少城市名'}), 400

    result = user_manager.add_whitelist_city(city)
    
    # 更新风控系统配置
    if pyramid_phishing_defense:
        pyramid_phishing_defense.update_security_config()
    
    return jsonify(result)


@app.route('/api/security/whitelist/remove', methods=['POST'])
def remove_whitelist_city():
    """从白名单移除城市"""
    session_id = request.headers.get('X-Session-ID')
    session = user_manager.validate_session(session_id)
    if not session:
        return jsonify({'error': '未授权访问'}), 401
    
    user = user_manager.get_user(session['username'])
    if user['role'] != 'admin':
        return jsonify({'error': '权限不足'}), 403

    data = request.json
    city = data.get('city')
    if not city:
        return jsonify({'error': '缺少城市名'}), 400

    result = user_manager.remove_whitelist_city(city)
    
    if pyramid_phishing_defense:
        pyramid_phishing_defense.update_security_config()
    
    return jsonify(result)


@app.route('/api/security/off-hours', methods=['POST'])
def set_off_hours_check():
    """设置非工作时间检查"""
    session_id = request.headers.get('X-Session-ID')
    session = user_manager.validate_session(session_id)
    if not session:
        return jsonify({'error': '未授权访问'}), 401
    
    user = user_manager.get_user(session['username'])
    if user['role'] != 'admin':
        return jsonify({'error': '权限不足'}), 403

    data = request.json
    enabled = data.get('enabled', True)
    
    result = user_manager.set_off_hours_check(enabled)
    
    if pyramid_phishing_defense:
        pyramid_phishing_defense.update_security_config()
    
    return jsonify(result)


@app.route('/api/security/location-check', methods=['POST'])
def set_location_check():
    """设置地域验证开关"""
    session_id = request.headers.get('X-Session-ID')
    session = user_manager.validate_session(session_id)
    if not session:
        return jsonify({'error': '未授权访问'}), 401
    
    user = user_manager.get_user(session['username'])
    if user['role'] != 'admin':
        return jsonify({'error': '权限不足'}), 403

    data = request.json
    enabled = data.get('enabled', True)
    
    result = user_manager.toggle_location_check(enabled)
    
    if pyramid_phishing_defense:
        pyramid_phishing_defense.update_security_config()
    
    return jsonify(result)


@app.route('/api/security/all-check', methods=['POST'])
def set_all_security_check():
    """设置所有安全检查开关"""
    session_id = request.headers.get('X-Session-ID')
    session = user_manager.validate_session(session_id)
    if not session:
        return jsonify({'error': '未授权访问'}), 401
    
    user = user_manager.get_user(session['username'])
    if user['role'] != 'admin':
        return jsonify({'error': '权限不足'}), 403

    data = request.json
    enabled = data.get('enabled', True)
    
    result = user_manager.toggle_all_security(enabled)
    
    if pyramid_phishing_defense:
        pyramid_phishing_defense.update_security_config()
    
    return jsonify(result)


@app.route('/api/security/config-update', methods=['POST'])
def update_security_config():
    """批量更新安全配置"""
    session_id = request.headers.get('X-Session-ID')
    session = user_manager.validate_session(session_id)
    if not session:
        return jsonify({'error': '未授权访问'}), 401
    
    user = user_manager.get_user(session['username'])
    if user['role'] != 'admin':
        return jsonify({'error': '权限不足'}), 403

    data = request.json
    result = user_manager.set_security_config(data)
    
    if pyramid_phishing_defense:
        pyramid_phishing_defense.update_security_config()
    
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


# ========== 增益性优化模块API端点 ==========

# ---- 1. StrategyPerformanceTracker API ----

@app.route('/api/gain/performance/metrics')
def api_gain_performance_metrics():
    """获取策略性能指标"""
    if not strategy_performance_tracker:
        return jsonify({'success': False, 'message': '性能追踪器不可用'}), 503
    
    strategy_name = request.args.get('strategy_name', '')
    window = int(request.args.get('window', 20))
    
    if not strategy_name:
        # 返回所有策略指标
        all_metrics = strategy_performance_tracker.get_all_strategy_metrics(window=window)
        result = {}
        for sname, metrics in all_metrics.items():
            result[sname] = {
                'total_trades': metrics.total_trades,
                'total_profit': round(metrics.total_profit, 2),
                'win_rate': round(metrics.win_rate * 100, 2),
                'profit_loss_ratio': round(metrics.profit_loss_ratio, 2),
                'sharpe_ratio': round(metrics.sharpe_ratio, 2),
                'sortino_ratio': round(metrics.sortino_ratio, 2),
                'calmar_ratio': round(metrics.calmar_ratio, 2),
                'max_drawdown': round(metrics.max_drawdown * 100, 2),
            }
        return jsonify({'success': True, 'data': result})
    
    metrics = strategy_performance_tracker.get_rolling_metrics(strategy_name, window=window)
    summary = strategy_performance_tracker.get_performance_summary(strategy_name)
    by_regime = strategy_performance_tracker.get_trades_by_regime(strategy_name)
    
    return jsonify({
        'success': True,
        'data': {
            'rolling_metrics': {
                'total_trades': metrics.total_trades,
                'total_profit': round(metrics.total_profit, 2),
                'win_rate': round(metrics.win_rate * 100, 2),
                'profit_loss_ratio': round(metrics.profit_loss_ratio, 2),
                'sharpe_ratio': round(metrics.sharpe_ratio, 2),
                'sortino_ratio': round(metrics.sortino_ratio, 2),
                'calmar_ratio': round(metrics.calmar_ratio, 2),
                'max_drawdown': round(metrics.max_drawdown * 100, 2),
            },
            'summary': summary,
            'by_regime': {k: len(v) for k, v in by_regime.items()},
        }
    })


@app.route('/api/gain/performance/enable', methods=['POST'])
def api_gain_performance_enable():
    """启用/禁用性能追踪器"""
    if not strategy_performance_tracker:
        return jsonify({'success': False, 'message': '性能追踪器不可用'}), 503
    
    data = request.json
    enabled = data.get('enabled', True)
    strategy_performance_tracker.enabled = enabled
    
    return jsonify({
        'success': True,
        'enabled': enabled,
        'message': f'性能追踪器已{"启用" if enabled else "禁用"}'
    })


@app.route('/api/gain/performance/reset', methods=['POST'])
def api_gain_performance_reset():
    """重置性能追踪器"""
    if not strategy_performance_tracker:
        return jsonify({'success': False, 'message': '性能追踪器不可用'}), 503
    
    strategy_performance_tracker.reset()
    return jsonify({'success': True, 'message': '性能追踪器已重置'})


# ---- 2. UnifiedRiskController API ----

@app.route('/api/gain/risk/status')
def api_gain_risk_status():
    """获取统一风险控制状态"""
    if not unified_risk_controller:
        return jsonify({'success': False, 'message': '风险控制器不可用'}), 503
    
    global_report = unified_risk_controller.get_global_risk_report()
    budget = unified_risk_controller.get_risk_budget()
    
    return jsonify({
        'success': True,
        'data': {
            'enabled': unified_risk_controller.enabled,
            'global_report': global_report,
            'budget': {
                'total_budget': round(budget.total_budget, 2),
                'used_budget': round(budget.used_budget, 2),
                'remaining_budget': round(budget.remaining_budget, 2),
                'strategy_allocations': budget.strategy_allocations,
            }
        }
    })


@app.route('/api/gain/risk/enable', methods=['POST'])
def api_gain_risk_enable():
    """启用/禁用风险控制器"""
    if not unified_risk_controller:
        return jsonify({'success': False, 'message': '风险控制器不可用'}), 503
    
    data = request.json
    enabled = data.get('enabled', True)
    unified_risk_controller.enabled = enabled
    
    return jsonify({
        'success': True,
        'enabled': enabled,
        'message': f'风险控制器已{"启用" if enabled else "禁用"}'
    })


@app.route('/api/gain/risk/strategy-report')
def api_gain_risk_strategy_report():
    """获取指定策略的风险报告"""
    if not unified_risk_controller:
        return jsonify({'success': False, 'message': '风险控制器不可用'}), 503
    
    strategy_name = request.args.get('strategy_name', '')
    if not strategy_name:
        return jsonify({'success': False, 'message': '请指定策略名称'}), 400
    
    report = unified_risk_controller.get_strategy_risk_report(strategy_name)
    return jsonify({'success': True, 'data': report})


# ---- 3. SmartParamOptimizer API ----

@app.route('/api/gain/optimizer/status')
def api_gain_optimizer_status():
    """获取参数优化器状态"""
    if not smart_param_optimizer:
        return jsonify({'success': False, 'message': '参数优化器不可用'}), 503
    
    return jsonify({
        'success': True,
        'data': {
            'enabled': smart_param_optimizer.enabled,
            'total_optimizations': smart_param_optimizer._total_optimizations,
            'total_early_stops': smart_param_optimizer._total_early_stops,
            'config': smart_param_optimizer.config,
        }
    })


@app.route('/api/gain/optimizer/enable', methods=['POST'])
def api_gain_optimizer_enable():
    """启用/禁用参数优化器"""
    if not smart_param_optimizer:
        return jsonify({'success': False, 'message': '参数优化器不可用'}), 503
    
    data = request.json
    enabled = data.get('enabled', True)
    smart_param_optimizer.enabled = enabled
    
    return jsonify({
        'success': True,
        'enabled': enabled,
        'message': f'参数优化器已{"启用" if enabled else "禁用"}'
    })


@app.route('/api/gain/optimizer/history')
def api_gain_optimizer_history():
    """获取优化历史"""
    if not smart_param_optimizer:
        return jsonify({'success': False, 'message': '参数优化器不可用'}), 503
    
    strategy_name = request.args.get('strategy_name', '')
    if not strategy_name:
        return jsonify({'success': False, 'message': '请指定策略名称'}), 400
    
    history = smart_param_optimizer._optimization_history.get(strategy_name, [])
    return jsonify({
        'success': True,
        'data': history[-20:]  # 返回最近20条
    })


# ---- 4. RLEnhancer API ----

@app.route('/api/gain/rl/status')
def api_gain_rl_status():
    """获取RL增强器状态"""
    if not rl_enhancer:
        return jsonify({'success': False, 'message': 'RL增强器不可用'}), 503
    
    return jsonify({
        'success': True,
        'data': {
            'enabled': rl_enhancer.enabled,
            'total_steps': rl_enhancer._total_steps,
            'total_updates': rl_enhancer._total_updates,
            'buffer_size': len(rl_enhancer._replay_buffer),
            'config': rl_enhancer.config,
        }
    })


@app.route('/api/gain/rl/enable', methods=['POST'])
def api_gain_rl_enable():
    """启用/禁用RL增强器"""
    if not rl_enhancer:
        return jsonify({'success': False, 'message': 'RL增强器不可用'}), 503
    
    data = request.json
    enabled = data.get('enabled', True)
    rl_enhancer.enabled = enabled
    
    return jsonify({
        'success': True,
        'enabled': enabled,
        'message': f'RL增强器已{"启用" if enabled else "禁用"}'
    })


@app.route('/api/gain/rl/reset', methods=['POST'])
def api_gain_rl_reset():
    """重置RL增强器"""
    if not rl_enhancer:
        return jsonify({'success': False, 'message': 'RL增强器不可用'}), 503
    
    rl_enhancer.reset()
    return jsonify({'success': True, 'message': 'RL增强器已重置'})


# ---- 5. DataQualityValidator API ----

@app.route('/api/gain/quality/status')
def api_gain_quality_status():
    """获取数据质量验证器状态"""
    if not data_quality_validator:
        return jsonify({'success': False, 'message': '数据质量验证器不可用'}), 503
    
    return jsonify({
        'success': True,
        'data': {
            'enabled': data_quality_validator.enabled,
            'total_checks': data_quality_validator._total_checks,
            'total_issues': data_quality_validator._total_issues,
            'config': data_quality_validator.config,
        }
    })


@app.route('/api/gain/quality/enable', methods=['POST'])
def api_gain_quality_enable():
    """启用/禁用数据质量验证器"""
    if not data_quality_validator:
        return jsonify({'success': False, 'message': '数据质量验证器不可用'}), 503
    
    data = request.json
    enabled = data.get('enabled', True)
    data_quality_validator.enabled = enabled
    
    return jsonify({
        'success': True,
        'enabled': enabled,
        'message': f'数据质量验证器已{"启用" if enabled else "禁用"}'
    })


@app.route('/api/gain/quality/check', methods=['POST'])
def api_gain_quality_check():
    """执行数据质量检查"""
    if not data_quality_validator:
        return jsonify({'success': False, 'message': '数据质量验证器不可用'}), 503
    
    data = request.json
    report = data_quality_validator.check_data_quality(data)
    
    return jsonify({
        'success': True,
        'data': {
            'overall_score': report.overall_score,
            'missing_rate': report.missing_rate,
            'anomaly_rate': report.anomaly_rate,
            'duplicate_rate': report.duplicate_rate,
            'staleness_seconds': report.staleness_seconds,
            'cross_validation_score': report.cross_validation_score,
            'issues': report.issues[:10],  # 最多返回10条
            'warnings': report.warnings[:10],
        }
    })


# ---- 6. 增益模块全局状态 ----

@app.route('/api/gain/status')
def api_gain_all_status():
    """获取所有增益模块的状态"""
    result = {}
    
    # 性能追踪器
    if strategy_performance_tracker:
        result['performance_tracker'] = {
            'enabled': strategy_performance_tracker.enabled,
            'strategies': list(strategy_performance_tracker._trade_history.keys()),
        }
    else:
        result['performance_tracker'] = {'enabled': False, 'available': False}
    
    # 风险控制器
    if unified_risk_controller:
        result['risk_controller'] = {
            'enabled': unified_risk_controller.enabled,
            'capital': unified_risk_controller._total_capital,
            'strategies': list(unified_risk_controller._strategy_risk.keys()),
        }
    else:
        result['risk_controller'] = {'enabled': False, 'available': False}
    
    # 参数优化器
    if smart_param_optimizer:
        result['param_optimizer'] = {
            'enabled': smart_param_optimizer.enabled,
            'total_optimizations': smart_param_optimizer._total_optimizations,
        }
    else:
        result['param_optimizer'] = {'enabled': False, 'available': False}
    
    # RL增强器
    if rl_enhancer:
        result['rl_enhancer'] = {
            'enabled': rl_enhancer.enabled,
            'total_steps': rl_enhancer._total_steps,
            'buffer_size': len(rl_enhancer._replay_buffer),
        }
    else:
        result['rl_enhancer'] = {'enabled': False, 'available': False}
    
    # 数据质量验证器
    if data_quality_validator:
        result['data_validator'] = {
            'enabled': data_quality_validator.enabled,
            'total_checks': data_quality_validator._total_checks,
        }
    else:
        result['data_validator'] = {'enabled': False, 'available': False}
    
    return jsonify({'success': True, 'data': result})


# ---- 7. 数据库维护模块 API ----

@app.route('/api/maintenance/status')
def api_maintenance_status():
    """获取数据库维护状态"""
    if not db_maintenance_scheduler:
        return jsonify({'success': False, 'message': '数据库维护模块不可用'}), 503
    
    status = db_maintenance_scheduler.get_maintenance_status()
    return jsonify({
        'success': True,
        'data': status
    })


@app.route('/api/maintenance/backup', methods=['POST'])
def api_maintenance_backup():
    """执行数据库备份"""
    if not db_maintenance_scheduler:
        return jsonify({'success': False, 'message': '数据库维护模块不可用'}), 503
    
    result = db_maintenance_scheduler.perform_backup()
    if result:
        return jsonify({
            'success': True,
            'data': {'backup_path': result},
            'message': '数据库备份完成'
        })
    else:
        return jsonify({
            'success': False,
            'message': '数据库备份失败'
        }), 500


@app.route('/api/maintenance/archive', methods=['POST'])
def api_maintenance_archive():
    """执行数据归档"""
    if not db_maintenance_scheduler:
        return jsonify({'success': False, 'message': '数据库维护模块不可用'}), 503
    
    results = db_maintenance_scheduler.perform_archive()
    total = sum(results.values())
    return jsonify({
        'success': True,
        'data': {
            'results': results,
            'total_deleted': total
        },
        'message': f'归档完成，共删除{total}条记录'
    })


@app.route('/api/maintenance/vacuum', methods=['POST'])
def api_maintenance_vacuum():
    """执行数据库压缩"""
    if not db_maintenance_scheduler:
        return jsonify({'success': False, 'message': '数据库维护模块不可用'}), 503
    
    success = db_maintenance_scheduler.perform_vacuum()
    if success:
        return jsonify({
            'success': True,
            'message': '数据库压缩完成'
        })
    else:
        return jsonify({
            'success': False,
            'message': '数据库压缩失败'
        }), 500


@app.route('/api/maintenance/auto', methods=['POST'])
def api_maintenance_auto():
    """启动/停止自动维护"""
    if not db_maintenance_scheduler:
        return jsonify({'success': False, 'message': '数据库维护模块不可用'}), 503
    
    data = request.json
    enabled = data.get('enabled', True)
    
    if enabled:
        db_maintenance_scheduler.start_auto_maintenance(interval_minutes=60)
        return jsonify({
            'success': True,
            'enabled': True,
            'message': '自动维护已启动（检查间隔：60分钟）'
        })
    else:
        db_maintenance_scheduler.stop_auto_maintenance()
        return jsonify({
            'success': True,
            'enabled': False,
            'message': '自动维护已停止'
        })


@app.route('/api/maintenance/check', methods=['POST'])
def api_maintenance_check():
    """执行维护检查（按需执行所有需要的维护操作）"""
    if not db_maintenance_scheduler:
        return jsonify({'success': False, 'message': '数据库维护模块不可用'}), 503
    
    results = db_maintenance_scheduler.check_and_maintain()
    return jsonify({
        'success': True,
        'data': {
            'backup': results.get('backup') is not None,
            'archive': results.get('archive') is not None,
            'vacuum': results.get('vacuum') is not None,
        },
        'message': '维护检查完成'
    })


def create_templates():
    """创建模板文件"""
    templates_dir = 'templates'
    if not os.path.exists(templates_dir):
        os.makedirs(templates_dir)


if __name__ == '__main__':
    create_templates()
    
    # 启动数据库自动维护调度器
    if db_maintenance_scheduler:
        try:
            db_maintenance_scheduler.start()
            print("[OK] 数据库自动维护调度器已启动")
        except Exception as e:
            print(f"[WARNING] 启动数据库维护调度器失败: {e}")
    
    print("启动Aurora量化交易系统可视化界面...")
    print("访问地址: http://localhost:5000")
    # 生产环境：使用 debug=False 避免暴露敏感信息
    # 如需远程访问，可改为 host='0.0.0.0'，但需确保防火墙和认证已配置
    app.run(host='127.0.0.1', port=5000, debug=False)
    
    # 应用退出时停止数据库维护调度器
    if db_maintenance_scheduler:
        try:
            db_maintenance_scheduler.stop()
            print("[OK] 数据库自动维护调度器已停止")
        except Exception as e:
            print(f"[WARNING] 停止数据库维护调度器失败: {e}")
