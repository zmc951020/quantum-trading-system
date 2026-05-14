#!/usr/bin/env python3
"""
量化交易系统Web界面 - 优化版
参考架构：策略进程隔离 + 三级风控 + 多数据源容灾
"""
import os
import sys
import json
import time
import threading
import logging
from datetime import datetime
from flask import Flask, render_template, jsonify, request, redirect
from flask_socketio import SocketIO, emit
import redis

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from xbk_simulator import XbkSimulatedTrader, OrderType, OrderSide
from strategies.final_market_adaptive import FinalMarketAdaptiveGrid
from strategies.high_return_grid import HighReturnGridTrading
from strategies.ml_range_grid import MLRangeGridTrading
import pandas as pd

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 设置模板目录路径
templates_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'templates')
app = Flask(__name__, template_folder=templates_dir)
app.config['SECRET_KEY'] = 'your-secret-key-here'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Redis连接或内存存储作为替代
try:
    redis_client = redis.Redis(
        host=os.getenv('REDIS_HOST', 'localhost'),
        port=int(os.getenv('REDIS_PORT', 6379)),
        db=int(os.getenv('REDIS_DB', 2))
    )
    # 测试Redis连接
    redis_client.ping()
    print("OK Redis连接成功")
    redis_available = True
except Exception as e:
    print(f"NO Redis连接失败: {e}")
    print("使用内存存储作为替代")
    # 创建内存存储类
    class InMemoryStorage:
        def __init__(self):
            self.data = {}
        
        def get(self, key):
            return self.data.get(key)
        
        def set(self, key, value):
            self.data[key] = value
        
        def delete(self, key):
            if key in self.data:
                del self.data[key]
    
    redis_client = InMemoryStorage()
    redis_available = False

# 全局变量
accounts = {}
current_account = "default"

# 配置管理
import configparser
import os

# 读取配置文件
def load_config():
    """
    加载配置文件
    """
    config = configparser.ConfigParser()
    config_file = os.path.join(os.path.dirname(__file__), 'config.ini')
    
    # 默认配置
    default_config = {
        'RISK': {
            'max_drawdown': '0.10',
            'daily_loss_limit': '0.05',
            'atr_risk_ratio': '2.0',
            'position_limit': '0.8',
            'single_trade_limit': '0.15'
        },
        'ALERT': {
            'wechat_enabled': 'False',
            'dingtalk_enabled': 'False',
            'wechat_webhook': '',
            'dingtalk_webhook': ''
        },
        'DATA': {
            'tushare_token': '',
            'baostock_enabled': 'False'
        },
        'AUTH': {
            'admin_username': 'admin',
            'admin_password': 'admin123',
            'secret_key': 'your-secret-key-here'
        }
    }
    
    # 如果配置文件不存在，创建默认配置
    if not os.path.exists(config_file):
        with open(config_file, 'w') as f:
            for section, options in default_config.items():
                f.write(f'[{section}]\n')
                for key, value in options.items():
                    f.write(f'{key} = {value}\n')
                f.write('\n')
    
    config.read(config_file)
    
    # 合并默认配置和文件配置
    for section, options in default_config.items():
        if section not in config:
            config[section] = options
        else:
            for key, value in options.items():
                if key not in config[section]:
                    config[section][key] = value
    
    return config

# 加载配置
config = load_config()

# 风控配置
RISK_CONFIG = {
    'max_drawdown': float(config['RISK']['max_drawdown']),
    'daily_loss_limit': float(config['RISK']['daily_loss_limit']),
    'atr_risk_ratio': float(config['RISK']['atr_risk_ratio']),
    'position_limit': float(config['RISK']['position_limit']),
    'single_trade_limit': float(config['RISK']['single_trade_limit'])
}

class RiskManager:
    """
    风控管理器 - 三级风控机制和防钓鱼功能
    """

    def __init__(self, account):
        self.account = account
        self.daily_pnl = 0
        self.last_reset_date = datetime.now().date()
        self.max_drawdown_hit = False
        self.daily_loss_hit = False
        self.alert_events = []  # 报警事件记录
        self.fishing_detection = {}  # 钓鱼攻击检测

    def check_risk(self, symbol, action, quantity, price):
        """
        执行三级风控检查和防钓鱼检测
        """
        if self.max_drawdown_hit:
            message = f"账户 {self.account.name} 触发最大回撤熔断，暂停所有交易"
            logger.warning(message)
            self._record_alert_event("error", "最大回撤熔断", message)
            alert_manager.send_alert("风控告警", message, "warning")
            return False, "最大回撤熔断"

        if self.daily_loss_hit:
            message = f"账户 {self.account.name} 触发单日亏损熔断，暂停所有交易"
            logger.warning(message)
            self._record_alert_event("error", "单日亏损熔断", message)
            alert_manager.send_alert("风控告警", message, "warning")
            return False, "单日亏损熔断"

        if action == "buy":
            trade_value = quantity * price
            if trade_value / self.account.initial_balance > RISK_CONFIG['single_trade_limit']:
                message = f"账户 {self.account.name} 单次交易金额超过限制: {trade_value}"
                logger.warning(message)
                self._record_alert_event("warning", "单次交易超限", message)
                alert_manager.send_alert("风控告警", message, "warning")
                return False, "单次交易超限"

        available_balance = self._get_available_balance()
        if action == "buy":
            required = quantity * price
            if required > available_balance:
                message = f"账户 {self.account.name} 资金不足: 需要 {required}, 可用 {available_balance}"
                logger.warning(message)
                self._record_alert_event("warning", "资金不足", message)
                alert_manager.send_alert("风控告警", message, "warning")
                return False, "资金不足"

        # 防钓鱼攻击检测
        if not self._check_fishing_attack(symbol, action, quantity, price):
            message = f"账户 {self.account.name} 疑似钓鱼攻击，交易被拒绝"
            logger.warning(message)
            self._record_alert_event("error", "钓鱼攻击检测", message)
            alert_manager.send_alert("安全告警", message, "error")
            return False, "疑似钓鱼攻击"

        return True, "通过"

    def update_daily_pnl(self, pnl):
        """
        更新每日盈亏
        """
        today = datetime.now().date()
        if today != self.last_reset_date:
            self.daily_pnl = 0
            self.last_reset_date = today
            self.daily_loss_hit = False

        self.daily_pnl += pnl

        if abs(self.daily_pnl) / self.account.initial_balance > RISK_CONFIG['daily_loss_limit']:
            self.daily_loss_hit = True
            message = f"账户 {self.account.name} 触发单日亏损限制: {abs(self.daily_pnl)/self.account.initial_balance:.2%}"
            logger.warning(message)
            alert_manager.send_alert("风控告警", message, "error")

    def check_drawdown(self, current_balance):
        """
        检查回撤
        """
        peak = max(current_balance, self.account.initial_balance)
        drawdown = (peak - current_balance) / peak if peak > 0 else 0

        if drawdown > RISK_CONFIG['max_drawdown']:
            self.max_drawdown_hit = True
            message = f"账户 {self.account.name} 触发最大回撤限制: {drawdown:.2%}"
            logger.warning(message)
            alert_manager.send_alert("风控告警", message, "error")
            return False
        return True

    def _get_available_balance(self):
        """
        获取可用资金
        """
        stock = list(self.account.stocks.values())[0] if self.account.stocks else None
        if stock:
            return stock['trader'].get_account_info().get('data', {}).get('available', 0)
        return self.account.initial_balance

    def calculate_atr_position(self, symbol, atr):
        """
        基于ATR计算动态仓位
        """
        stock = self.account.stocks.get(symbol)
        if not stock:
            return 1.0

        base_position = RISK_CONFIG['position_limit']
        atr_factor = max(0.5, min(1.5, 1 / (atr * RISK_CONFIG['atr_risk_ratio'])))

        return base_position * atr_factor

    def reset_risk(self):
        """
        重置风控状态
        """
        self.max_drawdown_hit = False
        self.daily_loss_hit = False
        self.daily_pnl = 0
        self.alert_events = []
        self.fishing_detection = {}
        logger.info(f"账户 {self.account.name} 风控状态已重置")

    def _check_fishing_attack(self, symbol, action, quantity, price):
        """
        检测钓鱼攻击
        """
        if symbol not in self.fishing_detection:
            self.fishing_detection[symbol] = {
                'last_trade_time': None,
                'trade_count': 0,
                'last_price': price,
                'last_quantity': quantity
            }

        detection = self.fishing_detection[symbol]
        current_time = datetime.now()

        # 检查交易频率
        if detection['last_trade_time']:
            time_diff = (current_time - detection['last_trade_time']).total_seconds()
            if time_diff < 1:  # 1秒内多次交易
                detection['trade_count'] += 1
                if detection['trade_count'] > 5:  # 5次以上交易
                    return False
            else:
                detection['trade_count'] = 1
        else:
            detection['trade_count'] = 1

        # 检查价格异常
        if detection['last_price']:
            price_change = abs(price - detection['last_price']) / detection['last_price']
            if price_change > 0.05:  # 价格变化超过5%
                return False

        # 检查数量异常
        if detection['last_quantity'] > 0:
            quantity_change = abs(quantity - detection['last_quantity']) / detection['last_quantity']
            if quantity_change > 2:  # 数量变化超过2倍
                return False

        # 更新检测数据
        detection['last_trade_time'] = current_time
        detection['last_price'] = price
        detection['last_quantity'] = quantity

        return True

    def _record_alert_event(self, level, event_type, message):
        """
        记录报警事件
        """
        event = {
            'timestamp': datetime.now().isoformat(),
            'level': level,
            'type': event_type,
            'message': message
        }
        self.alert_events.append(event)
        # 只保留最近100条事件
        if len(self.alert_events) > 100:
            self.alert_events = self.alert_events[-100:]

    def get_alert_events(self, limit=20):
        """
        获取报警事件
        """
        return self.alert_events[-limit:]

    def get_risk_status(self):
        """
        获取风控状态
        """
        return {
            'max_drawdown_hit': self.max_drawdown_hit,
            'daily_loss_hit': self.daily_loss_hit,
            'daily_pnl': self.daily_pnl,
            'alert_events_count': len(self.alert_events),
            'recent_alerts': self.get_alert_events(5)
        }

class Account:
    """
    账户类 - 优化版
    """

    def __init__(self, name, initial_balance=100000.0):
        self.name = name
        self.initial_balance = initial_balance
        self.stocks = {}
        self.runners = {}
        self.risk_manager = RiskManager(self)

    def add_stock(self, symbol, trading_interval=180, strategy='final_market_adaptive'):
        """
        添加股票到账户
        """
        if symbol not in self.stocks:
            trader = XbkSimulatedTrader(initial_balance=self.initial_balance)
            login_result = trader.login("user", "password")

            if login_result.get("code") == 0:
                ticker = trader.get_ticker(symbol)
                if ticker.get("code") == 0:
                    base_price = ticker["data"]["last_price"]
                    
                    # 根据策略名称创建不同的策略实例
                    if strategy == 'high_return_grid':
                        strategy_instance = HighReturnGridTrading(base_price=base_price, initial_balance=self.initial_balance)
                    elif strategy == 'ml_range_grid':
                        strategy_instance = MLRangeGridTrading(base_price=base_price, initial_balance=self.initial_balance)
                    elif strategy.startswith('exp_'):
                        # 动态加载实验策略
                        try:
                            import importlib
                            import sys
                            import os
                            
                            # 添加策略目录到Python路径
                            strategies_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'strategies')
                            if strategies_dir not in sys.path:
                                sys.path.insert(0, strategies_dir)
                            
                            # 动态导入模块
                            module_name = strategy
                            module = importlib.import_module(module_name)
                            
                            # 假设策略类名与模块名相同（首字母大写）
                            class_name = strategy.replace('exp_', '').title().replace('_', '')
                            strategy_class = getattr(module, class_name)
                            
                            # 策略验证
                            if not hasattr(strategy_class, 'update_price'):
                                raise ValueError("策略类缺少必要的update_price方法")
                            
                            # 检查策略类是否有版本信息
                            version = getattr(module, '__version__', '1.0.0')
                            logger.info(f"加载实验策略: {strategy} (版本: {version})")
                            
                            strategy_instance = strategy_class(base_price=base_price, initial_balance=self.initial_balance)
                        except Exception as e:
                            logger.error(f"加载实验策略失败: {e}")
                            # 失败时使用默认策略
                            strategy_instance = FinalMarketAdaptiveGrid(base_price=base_price, initial_balance=self.initial_balance)
                    else:
                        strategy_instance = FinalMarketAdaptiveGrid(base_price=base_price, initial_balance=self.initial_balance)

                    # 记录策略版本
                    if strategy.startswith('exp_') and 'module' in locals():
                        strategy_version = getattr(module, '__version__', '1.0.0')
                    else:
                        strategy_version = '1.0.0'
                    
                    self.stocks[symbol] = {
                        'trader': trader,
                        'strategy': strategy_instance,
                        'price_history': [],
                        'trade_history': [],
                        'trading_interval': trading_interval,
                        'atr': 0.001,
                        'last_price': base_price,
                        'trend_direction': 'neutral',
                        'strategy_type': strategy,
                        'strategy_version': strategy_version,
                    }

                    runner = StrategyRunner(self.name, symbol, self.risk_manager)
                    self.runners[symbol] = runner
                    logger.info(f"账户 {self.name} 添加股票 {symbol} 成功，策略: {strategy}")
                    return True
        return False

    def remove_stock(self, symbol):
        """
        从账户中移除股票
        """
        if symbol in self.stocks:
            if symbol in self.runners:
                self.runners[symbol].stop()
                del self.runners[symbol]
            del self.stocks[symbol]
            logger.info(f"账户 {self.name} 移除股票 {symbol}")
            return True
        return False

    def start_stock_strategy(self, symbol):
        """
        启动股票策略
        """
        if symbol in self.runners:
            self.runners[symbol].start()
            logger.info(f"账户 {self.name} 启动股票 {symbol} 策略")
            return True
        return False

    def stop_stock_strategy(self, symbol):
        """
        停止股票策略
        """
        if symbol in self.runners:
            self.runners[symbol].stop()
            logger.info(f"账户 {self.name} 停止股票 {symbol} 策略")
            return True
        return False

    def get_all_positions(self):
        """
        获取所有持仓
        """
        positions = {}
        for symbol, stock in self.stocks.items():
            positions[symbol] = {
                'position': stock['strategy'].position,
                'last_price': stock.get('last_price', 0),
                'market_type': stock['strategy'].market_type,
                'grid_spacing': stock['strategy'].grid_spacing,
            }
        return positions

    def detect_one_sided_market(self, symbol):
        """
        检测单边行情 - 用于风控
        """
        if symbol not in self.stocks:
            return False

        stock = self.stocks[symbol]
        if len(stock['price_history']) < 20:
            return False

        prices = stock['price_history'][-20:]
        increases = sum(1 for i in range(1, len(prices)) if prices[i] > prices[i-1])
        decrease_ratio = increases / (len(prices) - 1)

        return decrease_ratio > 0.9 or decrease_ratio < 0.1

class StrategyRunner:
    """
    策略运行器 - 优化版
    """

    def __init__(self, account_name, symbol, risk_manager):
        self.account_name = account_name
        self.symbol = symbol
        self.running = False
        self.thread = None
        self.risk_manager = risk_manager
        self.performance = {
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "total_pnl": 0.0
        }

    def start(self):
        global accounts

        account = accounts.get(self.account_name)
        if not account:
            return

        stock = account.stocks.get(self.symbol)
        if not stock:
            return

        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        logger.info(f"策略运行器启动: 账户 {self.account_name}, 股票 {self.symbol}")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=5.0)
        logger.info(f"策略运行器停止: 账户 {self.account_name}, 股票 {self.symbol}")

    def _run_loop(self):
        global accounts

        while self.running:
            account = accounts.get(self.account_name)
            if not account:
                break

            stock = account.stocks.get(self.symbol)
            if not stock:
                break

            trader = stock['trader']
            strategy = stock['strategy']
            trading_interval = stock['trading_interval']

            ticker = trader.get_ticker(self.symbol)
            if ticker.get("code") == 0:
                current_price = ticker["data"]["last_price"]
                stock['price_history'].append(current_price)
                stock['last_price'] = current_price

                if len(stock['price_history']) >= 14:
                    atr = self._calculate_atr(stock['price_history'])
                    stock['atr'] = atr

                if account.detect_one_sided_market(self.symbol):
                    logger.warning(f"检测到单边行情，暂停买入: {self.symbol}")
                    stock['trend_direction'] = 'one_sided'
                else:
                    stock['trend_direction'] = 'neutral'

                price_series = pd.Series(stock['price_history'])
                result = strategy.update_price(current_price, price_series)

                if result and result.get("action"):
                    action = result["action"]
                    quantity = result.get("quantity", 0)
                    reason = result.get("reason", "策略信号")

                    check_passed, check_msg = self.risk_manager.check_risk(
                        self.symbol, action, quantity, current_price
                    )

                    if not check_passed:
                        logger.warning(f"风控拦截: {check_msg}, 股票 {self.symbol}")
                        result = None
                    else:
                        if action == "buy":
                            buy_result = trader.place_order(
                                symbol=self.symbol,
                                side=OrderSide.BUY,
                                order_type=OrderType.MARKET,
                                quantity=quantity
                            )
                            if buy_result.get("code") == 0:
                                stock['trade_history'].append({
                                    'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                                    'action': 'buy',
                                    'symbol': self.symbol,
                                    'quantity': quantity,
                                    'price': current_price,
                                    'reason': reason
                                })
                                self.performance['total_trades'] += 1
                        elif action == "sell":
                            sell_result = trader.place_order(
                                symbol=self.symbol,
                                side=OrderSide.SELL,
                                order_type=OrderType.MARKET,
                                quantity=quantity
                            )
                            if sell_result.get("code") == 0:
                                stock['trade_history'].append({
                                    'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                                    'action': 'sell',
                                    'symbol': self.symbol,
                                    'quantity': quantity,
                                    'price': current_price,
                                    'reason': reason
                                })
                                self.performance['total_trades'] += 1

                acc = trader.get_account_info()
                account_info = acc["data"] if acc.get("code") == 0 else {}

                if account_info:
                    self.risk_manager.check_drawdown(account_info.get('total_value', self.account_name))

                socketio.emit('market_data', {
                    'account': self.account_name,
                    'symbol': self.symbol,
                    'price': current_price,
                    'price_history': stock['price_history'][-50:],
                    'account_info': account_info,
                    'strategy': {
                        'market_type': strategy.market_type,
                        'grid_spacing': strategy.grid_spacing,
                        'position': strategy.position,
                        'atr': stock['atr'],
                        'trend_direction': stock['trend_direction'],
                    },
                    'trades': stock['trade_history'][-10:],
                    'performance': self.performance,
                    'risk_status': self.risk_manager.get_risk_status()
                })

            time.sleep(trading_interval)

    def _calculate_atr(self, prices, period=14):
        """
        计算ATR (Average True Range)
        """
        if len(prices) < period + 1:
            return 0.001

        trs = []
        for i in range(1, min(period + 1, len(prices))):
            high = prices[i]
            low = prices[i]
            prev_close = prices[i-1]

            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            trs.append(tr)

        return sum(trs) / len(trs) if trs else 0.001

class AlertManager:
    """
    告警管理器 - 支持企业微信和钉钉告警
    """

    def __init__(self):
        self.wechat_enabled = config['ALERT'].getboolean('wechat_enabled')
        self.dingtalk_enabled = config['ALERT'].getboolean('dingtalk_enabled')
        self.wechat_webhook = config['ALERT']['wechat_webhook']
        self.dingtalk_webhook = config['ALERT']['dingtalk_webhook']

    def send_alert(self, title, content, level='info'):
        """
        发送告警
        """
        if self.wechat_enabled:
            self._send_wechat_alert(title, content, level)
        if self.dingtalk_enabled:
            self._send_dingtalk_alert(title, content, level)

    def _send_wechat_alert(self, title, content, level):
        """
        发送企业微信告警
        """
        try:
            import requests
            data = {
                "msgtype": "markdown",
                "markdown": {
                    "content": f"## {title}\n> 级别: {level}\n> 时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n> 内容: {content}"
                }
            }
            response = requests.post(self.wechat_webhook, json=data, timeout=5)
            if response.status_code == 200:
                logger.info("企业微信告警发送成功")
            else:
                logger.warning(f"企业微信告警发送失败: {response.text}")
        except Exception as e:
            logger.warning(f"企业微信告警发送异常: {e}")

    def _send_dingtalk_alert(self, title, content, level):
        """
        发送钉钉告警
        """
        try:
            import requests
            data = {
                "msgtype": "markdown",
                "markdown": {
                    "title": title,
                    "text": f"## {title}\n> 级别: {level}\n> 时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n> 内容: {content}"
                }
            }
            response = requests.post(self.dingtalk_webhook, json=data, timeout=5)
            if response.status_code == 200:
                logger.info("钉钉告警发送成功")
            else:
                logger.warning(f"钉钉告警发送失败: {response.text}")
        except Exception as e:
            logger.warning(f"钉钉告警发送异常: {e}")

class MarketDataSource:
    """
    多数据源行情管理器 - 支持自动容灾切换
    """

    def __init__(self):
        self.sources = ['simulator', 'tushare', 'baostock']
        self.current_source = 'simulator'
        self.tushare_token = config['DATA']['tushare_token']
        self.baostock_enabled = config['DATA'].getboolean('baostock_enabled')

    def get_ticker(self, symbol):
        """
        获取行情数据 - 自动容灾
        """
        for source in self.sources:
            try:
                if source == 'simulator':
                    ticker = self._get_simulator_ticker(symbol)
                elif source == 'tushare' and self.tushare_token:
                    ticker = self._get_tushare_ticker(symbol)
                elif source == 'baostock' and self.baostock_enabled:
                    ticker = self._get_baostock_ticker(symbol)
                else:
                    continue

                if ticker and ticker.get("code") == 0:
                    self.current_source = source
                    return ticker
            except Exception as e:
                logger.warning(f"数据源 {source} 获取失败: {e}")
                continue

        return {"code": -1, "message": "所有数据源均不可用"}

    def _get_simulator_ticker(self, symbol):
        """模拟器数据源"""
        from xbk_simulator import XbkSimulatedTrader
        trader = XbkSimulatedTrader()
        return trader.get_ticker(symbol)

    def _get_tushare_ticker(self, symbol):
        """Tushare数据源"""
        try:
            import tushare as ts
            ts.set_token(self.tushare_token)
            pro = ts.pro_api()
            
            # 转换股票代码
            if symbol.endswith('.SH'):
                ts_code = symbol.replace('.SH', '.SH')
            elif symbol.endswith('.SZ'):
                ts_code = symbol.replace('.SZ', '.SZ')
            else:
                return {"code": -1, "message": "股票代码格式错误"}
            
            # 获取最新行情
            df = pro.daily(ts_code=ts_code, trade_date=time.strftime('%Y%m%d'))
            if not df.empty:
                last_price = df.iloc[0]['close']
                return {
                    "code": 0,
                    "data": {
                        "last_price": last_price,
                        "open": df.iloc[0]['open'],
                        "high": df.iloc[0]['high'],
                        "low": df.iloc[0]['low'],
                        "volume": df.iloc[0]['vol']
                    }
                }
            return {"code": -1, "message": "无行情数据"}
        except Exception as e:
            logger.warning(f"Tushare获取失败: {e}")
            return {"code": -1, "message": f"Tushare错误: {str(e)}"}

    def _get_baostock_ticker(self, symbol):
        """Baostock数据源"""
        try:
            import baostock as bs
            
            # 登录
            lg = bs.login()
            if lg.error_code != '0':
                return {"code": -1, "message": f"Baostock登录失败: {lg.error_msg}"}
            
            # 转换股票代码
            if symbol.endswith('.SH'):
                bs_code = 'sh.' + symbol.replace('.SH', '')
            elif symbol.endswith('.SZ'):
                bs_code = 'sz.' + symbol.replace('.SZ', '')
            else:
                return {"code": -1, "message": "股票代码格式错误"}
            
            # 获取最新行情
            rs = bs.query_history_k_data_plus(
                bs_code,
                "date,open,high,low,close,volume",
                start_date=time.strftime('%Y-%m-%d'),
                end_date=time.strftime('%Y-%m-%d'),
                frequency="d",
                adjustflag="3"
            )
            
            data_list = []
            while (rs.error_code == '0') & rs.next():
                data_list.append(rs.get_row_data())
            
            if data_list:
                last_price = float(data_list[0][4])
                bs.logout()
                return {
                    "code": 0,
                    "data": {
                        "last_price": last_price,
                        "open": float(data_list[0][1]),
                        "high": float(data_list[0][2]),
                        "low": float(data_list[0][3]),
                        "volume": float(data_list[0][5])
                    }
                }
            bs.logout()
            return {"code": -1, "message": "无行情数据"}
        except Exception as e:
            logger.warning(f"Baostock获取失败: {e}")
            return {"code": -1, "message": f"Baostock错误: {str(e)}"}

market_source = MarketDataSource()
alert_manager = AlertManager()

# 回测功能
class BacktestEngine:
    """
    回测引擎 - 支持策略回测和Walk-Forward验证
    """

    def __init__(self):
        self.strategies = {
            'final_market_adaptive': FinalMarketAdaptiveGrid,
            'high_return_grid': HighReturnGridTrading,
            'ml_range_grid': MLRangeGridTrading
        }
        
        # 策略分类
        self.strategy_categories = {
            'mature': ['final_market_adaptive', 'high_return_grid', 'ml_range_grid'],
            'experimental': []  # 实验策略
        }

    def backtest(self, strategy_name, symbol, start_date, end_date, initial_balance=100000):
        """
        执行回测
        """
        try:
            if strategy_name not in self.strategies:
                return {"code": -1, "message": "策略不存在"}

            # 模拟历史数据
            import numpy as np
            
            # 生成模拟数据
            days = (pd.to_datetime(end_date) - pd.to_datetime(start_date)).days
            dates = pd.date_range(start=start_date, end=end_date, freq='D')
            
            # 生成随机价格数据
            base_price = 100.0
            prices = []
            current_price = base_price
            
            for i in range(len(dates)):
                # 随机波动
                change = np.random.normal(0, 0.02)
                current_price = max(80, min(120, current_price * (1 + change)))
                prices.append(current_price)
            
            # 初始化策略
            strategy_class = self.strategies[strategy_name]
            strategy = strategy_class(base_price=prices[0], initial_balance=initial_balance)
            
            # 执行回测
            balance = initial_balance
            position = 0
            trades = []
            
            for i, (date, price) in enumerate(zip(dates, prices)):
                if i == 0:
                    continue
                
                # 更新策略
                price_series = pd.Series(prices[:i+1])
                result = strategy.update_price(price, price_series)
                
                # 处理交易
                if result and result.get("action"):
                    action = result["action"]
                    quantity = result.get("quantity", 0)
                    
                    if action == "buy":
                        cost = quantity * price
                        if cost <= balance:
                            balance -= cost
                            position += quantity
                            trades.append({
                                'date': date.strftime('%Y-%m-%d'),
                                'action': 'buy',
                                'price': price,
                                'quantity': quantity,
                                'balance': balance,
                                'position': position
                            })
                    elif action == "sell":
                        if quantity <= position:
                            revenue = quantity * price
                            balance += revenue
                            position -= quantity
                            trades.append({
                                'date': date.strftime('%Y-%m-%d'),
                                'action': 'sell',
                                'price': price,
                                'quantity': quantity,
                                'balance': balance,
                                'position': position
                            })
            
            # 计算最终资产
            final_asset = balance + position * prices[-1]
            total_return = (final_asset - initial_balance) / initial_balance
            
            # 计算夏普比率
            returns = []
            for i in range(1, len(prices)):
                daily_return = (prices[i] - prices[i-1]) / prices[i-1]
                returns.append(daily_return)
            
            if returns:
                sharpe_ratio = np.mean(returns) / (np.std(returns) + 1e-9) * np.sqrt(252)
            else:
                sharpe_ratio = 0
            
            # 计算最大回撤
            peak = initial_balance
            max_drawdown = 0
            for trade in trades:
                current_asset = trade['balance'] + trade['position'] * prices[dates.get_loc(pd.to_datetime(trade['date']))]
                if current_asset > peak:
                    peak = current_asset
                drawdown = (peak - current_asset) / peak
                if drawdown > max_drawdown:
                    max_drawdown = drawdown
            
            return {
                "code": 0,
                "data": {
                    "strategy": strategy_name,
                    "symbol": symbol,
                    "start_date": start_date,
                    "end_date": end_date,
                    "initial_balance": initial_balance,
                    "final_asset": final_asset,
                    "total_return": total_return,
                    "sharpe_ratio": sharpe_ratio,
                    "max_drawdown": max_drawdown,
                    "total_trades": len(trades),
                    "trades": trades
                }
            }
        except Exception as e:
            logger.error(f"回测失败: {e}")
            return {"code": -1, "message": f"回测失败: {str(e)}"}

    def walk_forward_test(self, strategy_name, symbol, start_date, end_date, initial_balance=100000, window=60):
        """
        Walk-Forward 样本外验证
        """
        try:
            if strategy_name not in self.strategies:
                return {"code": -1, "message": "策略不存在"}
            
            # 生成模拟数据
            import numpy as np
            dates = pd.date_range(start=start_date, end=end_date, freq='D')
            
            base_price = 100.0
            prices = []
            current_price = base_price
            
            for i in range(len(dates)):
                change = np.random.normal(0, 0.02)
                current_price = max(80, min(120, current_price * (1 + change)))
                prices.append(current_price)
            
            # 执行Walk-Forward测试
            results = []
            for i in range(window, len(dates), window):
                train_end = i
                test_end = min(i + window, len(dates))
                
                # 训练期数据
                train_prices = prices[:train_end]
                # 测试期数据
                test_prices = prices[train_end:test_end]
                
                # 初始化策略
                strategy_class = self.strategies[strategy_name]
                strategy = strategy_class(base_price=train_prices[0], initial_balance=initial_balance)
                
                # 训练期
                for price in train_prices[1:]:
                    price_series = pd.Series(train_prices[:train_prices.index(price)+1])
                    strategy.update_price(price, price_series)
                
                # 测试期
                balance = initial_balance
                position = 0
                test_trades = []
                
                for j, price in enumerate(test_prices):
                    price_series = pd.Series(prices[:train_end+j+1])
                    result = strategy.update_price(price, price_series)
                    
                    if result and result.get("action"):
                        action = result["action"]
                        quantity = result.get("quantity", 0)
                        
                        if action == "buy":
                            cost = quantity * price
                            if cost <= balance:
                                balance -= cost
                                position += quantity
                        elif action == "sell":
                            if quantity <= position:
                                revenue = quantity * price
                                balance += revenue
                                position -= quantity
                
                final_asset = balance + position * test_prices[-1]
                period_return = (final_asset - initial_balance) / initial_balance
                
                results.append({
                    "train_period": f"{dates[0].strftime('%Y-%m-%d')} to {dates[train_end-1].strftime('%Y-%m-%d')}",
                    "test_period": f"{dates[train_end].strftime('%Y-%m-%d')} to {dates[test_end-1].strftime('%Y-%m-%d')}",
                    "return": period_return
                })
            
            # 计算平均收益率
            avg_return = np.mean([r['return'] for r in results]) if results else 0
            
            return {
                "code": 0,
                "data": {
                    "strategy": strategy_name,
                    "symbol": symbol,
                    "start_date": start_date,
                    "end_date": end_date,
                    "window": window,
                    "results": results,
                    "average_return": avg_return
                }
            }
        except Exception as e:
            logger.error(f"Walk-Forward测试失败: {e}")
            return {"code": -1, "message": f"Walk-Forward测试失败: {str(e)}"}

backtest_engine = BacktestEngine()

# 用户认证
class AuthManager:
    """
    用户认证管理器
    """

    def __init__(self):
        self.username = config['AUTH']['admin_username']
        self.password = config['AUTH']['admin_password']

    def authenticate(self, username, password):
        """
        验证用户
        """
        return username == self.username and password == self.password

auth_manager = AuthManager()

# 初始化默认账户
accounts["default"] = Account("default")

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/')
def index():
    # 检查是否已登录
    session_id = request.cookies.get('session_id')
    if not session_id:
        return redirect('/login')
    
    global accounts
    return render_template('index.html', accounts=list(accounts.keys()))

@app.route('/api/accounts')
def get_accounts():
    global accounts
    return jsonify({
        'accounts': list(accounts.keys()),
        'current': current_account
    })

@app.route('/api/account/create', methods=['POST'])
def create_account():
    global accounts
    data = request.get_json()
    name = data.get('name')
    initial_balance = float(data.get('initial_balance', 100000.0))

    if name and name not in accounts:
        accounts[name] = Account(name, initial_balance)
        logger.info(f"创建账户: {name}, 初始资金: {initial_balance}")
        return jsonify({'status': 'success', 'message': f'账户 {name} 创建成功'})
    return jsonify({'status': 'error', 'message': '账户名称已存在'})

@app.route('/api/account/switch', methods=['POST'])
def switch_account():
    global current_account, accounts
    data = request.get_json()
    name = data.get('name')

    if name in accounts:
        current_account = name
        logger.info(f"切换账户: {name}")
        return jsonify({'status': 'success', 'message': f'已切换到账户 {name}'})
    return jsonify({'status': 'error', 'message': '账户不存在'})

@app.route('/api/account/stocks')
def get_account_stocks():
    global accounts, current_account
    account = accounts.get(current_account)
    if account:
        return jsonify({
            'stocks': list(account.stocks.keys()),
            'positions': account.get_all_positions()
        })
    return jsonify({'stocks': [], 'positions': {}})

@app.route('/api/account/reset_risk', methods=['POST'])
def reset_account_risk():
    """
    重置账户风控状态
    """
    global accounts, current_account
    data = request.get_json()
    name = data.get('name', current_account)

    if name in accounts:
        accounts[name].risk_manager.reset_risk()
        logger.info(f"重置风控状态: {name}")
        return jsonify({'status': 'success', 'message': f'账户 {name} 风控状态已重置'})
    return jsonify({'status': 'error', 'message': '账户不存在'})

@app.route('/api/stock/add', methods=['POST'])
def add_stock():
    global accounts, current_account
    data = request.get_json()
    symbol = data.get('symbol')
    trading_interval = int(data.get('interval', 180))
    strategy = data.get('strategy', 'final_market_adaptive')

    account = accounts.get(current_account)
    if account:
        success = account.add_stock(symbol, trading_interval, strategy)
        if success:
            return jsonify({'status': 'success', 'message': f'股票 {symbol} 添加成功，策略: {strategy}'})
        return jsonify({'status': 'error', 'message': '股票已存在'})
    return jsonify({'status': 'error', 'message': '账户不存在'})

@app.route('/api/stock/remove', methods=['POST'])
def remove_stock():
    global accounts, current_account
    data = request.get_json()
    symbol = data.get('symbol')

    account = accounts.get(current_account)
    if account:
        success = account.remove_stock(symbol)
        if success:
            return jsonify({'status': 'success', 'message': f'股票 {symbol} 移除成功'})
        return jsonify({'status': 'error', 'message': '股票不存在'})
    return jsonify({'status': 'error', 'message': '账户不存在'})

@app.route('/api/strategy/start', methods=['POST'])
def start_strategy():
    global accounts, current_account
    data = request.get_json()
    symbol = data.get('symbol')

    account = accounts.get(current_account)
    if account:
        success = account.start_stock_strategy(symbol)
        if success:
            return jsonify({'status': 'success', 'message': f'策略已启动'})
        return jsonify({'status': 'error', 'message': '股票不存在'})
    return jsonify({'status': 'error', 'message': '账户不存在'})

@app.route('/api/strategy/stop', methods=['POST'])
def stop_strategy():
    global accounts, current_account
    data = request.get_json()
    symbol = data.get('symbol')

    account = accounts.get(current_account)
    if account:
        success = account.stop_stock_strategy(symbol)
        if success:
            return jsonify({'status': 'success', 'message': f'策略已停止'})
        return jsonify({'status': 'error', 'message': '股票不存在'})
    return jsonify({'status': 'error', 'message': '账户不存在'})

@app.route('/api/status')
def get_status():
    global accounts, current_account
    account = accounts.get(current_account)
    if account:
        status = {
            'account': current_account,
            'stocks': {},
            'risk': account.risk_manager.get_risk_status()
        }
        for symbol, stock in account.stocks.items():
            status['stocks'][symbol] = {
                'running': symbol in account.runners and account.runners[symbol].running,
                'latest_price': stock['price_history'][-1] if stock['price_history'] else 0,
                'position': stock['strategy'].position if stock.get('strategy') else 0,
                'atr': stock.get('atr', 0),
                'trend_direction': stock.get('trend_direction', 'neutral')
            }
        return jsonify(status)
    return jsonify({'account': current_account, 'stocks': {}, 'risk': {}})

# 策略分类API
@app.route('/api/strategies')
def get_strategies():
    """
    获取策略列表和分类
    """
    strategies = {
        'mature': [
            {'value': 'final_market_adaptive', 'label': 'Final Market Adaptive Grid'},
            {'value': 'high_return_grid', 'label': 'High Return Grid Trading'},
            {'value': 'ml_range_grid', 'label': 'ML Range Grid Trading'}
        ],
        'experimental': []  # 实验策略
    }
    
    # 尝试加载实验策略
    import os
    strategies_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'strategies')
    if os.path.exists(strategies_dir):
        experimental_files = [f for f in os.listdir(strategies_dir) if f.startswith('exp_') and f.endswith('.py')]
    else:
        experimental_files = []
    
    for file in experimental_files:
        strategy_name = file[:-3]  # 移除.py后缀
        strategies['experimental'].append({
            'value': strategy_name,
            'label': f'Experimental: {strategy_name.replace("exp_", "")}'
        })
    
    return jsonify(strategies)

# 回测API
@app.route('/api/backtest', methods=['POST'])
def backtest():
    """
    执行策略回测
    """
    data = request.get_json()
    strategy_name = data.get('strategy', 'final_market_adaptive')
    symbol = data.get('symbol', '600000.SH')
    start_date = data.get('start_date', '2024-01-01')
    end_date = data.get('end_date', '2024-12-31')
    initial_balance = float(data.get('initial_balance', 100000))

    result = backtest_engine.backtest(
        strategy_name=strategy_name,
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        initial_balance=initial_balance
    )

    return jsonify(result)

@app.route('/api/walk_forward', methods=['POST'])
def walk_forward():
    """
    执行Walk-Forward测试
    """
    data = request.get_json()
    strategy_name = data.get('strategy', 'final_market_adaptive')
    symbol = data.get('symbol', '600000.SH')
    start_date = data.get('start_date', '2024-01-01')
    end_date = data.get('end_date', '2024-12-31')
    initial_balance = float(data.get('initial_balance', 100000))
    window = int(data.get('window', 60))

    result = backtest_engine.walk_forward_test(
        strategy_name=strategy_name,
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        initial_balance=initial_balance,
        window=window
    )

    return jsonify(result)

# 告警API
@app.route('/api/alert/send', methods=['POST'])
def send_alert():
    """
    发送告警
    """
    data = request.get_json()
    title = data.get('title', '系统通知')
    content = data.get('content', '测试告警')
    level = data.get('level', 'info')

    alert_manager.send_alert(title, content, level)
    return jsonify({'status': 'success', 'message': '告警发送成功'})

# 用户认证API
@app.route('/api/auth/login', methods=['POST'])
def login():
    """
    用户登录
    """
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if auth_manager.authenticate(username, password):
        # 生成会话ID
        session_id = f"{username}_{int(time.time())}"
        return jsonify({
            'success': True, 
            'message': '登录成功',
            'session_id': session_id,
            'user': {'username': username, 'role': 'admin'}
        })
    else:
        return jsonify({'success': False, 'message': '用户名或密码错误'})

@app.route('/api/auth/validate')
def validate_session():
    """
    验证会话
    """
    session_id = request.headers.get('X-Session-ID')
    if session_id:
        return jsonify({'valid': True})
    return jsonify({'valid': False})

@app.route('/api/user-info')
def get_user_info():
    """
    获取用户信息
    """
    session_id = request.cookies.get('session_id')
    if session_id:
        # 从会话ID中提取用户名
        username = session_id.split('_')[0]
        return jsonify({
            'success': True,
            'user': {'username': username, 'role': 'admin'}
        })
    return jsonify({'success': False, 'message': '未登录'})

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    """
    用户登出
    """
    return jsonify({'success': True, 'message': '登出成功'})

# 配置管理API
@app.route('/api/config')
def get_config():
    """
    获取配置信息
    """
    config_dict = {}
    for section in config.sections():
        config_dict[section] = dict(config[section])
    return jsonify(config_dict)

@app.route('/api/config/update', methods=['POST'])
def update_config():
    """
    更新配置信息
    """
    data = request.get_json()
    
    # 保存配置
    config_file = os.path.join(os.path.dirname(__file__), 'config.ini')
    with open(config_file, 'w') as f:
        for section, options in data.items():
            f.write(f'[{section}]\n')
            for key, value in options.items():
                f.write(f'{key} = {value}\n')
            f.write('\n')
    
    # 重新加载配置
    global config
    config = load_config()
    
    return jsonify({'status': 'success', 'message': '配置更新成功'})

# 策略测试API
@app.route('/api/strategy/test', methods=['POST'])
def test_strategy():
    """
    测试实验策略
    """
    data = request.get_json()
    strategy_name = data.get('strategy')
    symbol = data.get('symbol', '600000.SH')
    test_duration = int(data.get('duration', 100))  # 测试100个价格点
    
    try:
        import numpy as np
        
        # 生成模拟价格数据
        base_price = 100.0
        prices = []
        current_price = base_price
        
        for i in range(test_duration):
            # 随机波动
            change = np.random.normal(0, 0.02)
            current_price = max(80, min(120, current_price * (1 + change)))
            prices.append(current_price)
        
        # 加载策略
        if strategy_name.startswith('exp_'):
            import importlib
            import sys
            import os
            
            # 添加策略目录到Python路径
            strategies_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'strategies')
            if strategies_dir not in sys.path:
                sys.path.insert(0, strategies_dir)
            
            # 动态导入模块
            module = importlib.import_module(strategy_name)
            class_name = strategy_name.replace('exp_', '').title().replace('_', '')
            strategy_class = getattr(module, class_name)
            
            # 策略验证
            if not hasattr(strategy_class, 'update_price'):
                return jsonify({'status': 'error', 'message': '策略类缺少必要的update_price方法'})
            
            # 初始化策略
            strategy = strategy_class(base_price=base_price, initial_balance=100000)
        else:
            return jsonify({'status': 'error', 'message': '仅支持测试实验策略'})
        
        # 执行测试
        import pandas as pd
        price_series = pd.Series(prices)
        trades = []
        balance = 100000
        position = 0
        
        for i, price in enumerate(prices):
            result = strategy.update_price(price, price_series[:i+1])
            if result and result.get('action'):
                action = result['action']
                quantity = result.get('quantity', 0)
                reason = result.get('reason', '策略信号')
                
                if action == 'buy':
                    cost = quantity * price
                    if cost <= balance:
                        balance -= cost
                        position += quantity
                        trades.append({
                            'timestamp': i,
                            'action': 'buy',
                            'price': price,
                            'quantity': quantity,
                            'balance': balance,
                            'position': position,
                            'reason': reason
                        })
                elif action == 'sell':
                    if quantity <= position:
                        revenue = quantity * price
                        balance += revenue
                        position -= quantity
                        trades.append({
                            'timestamp': i,
                            'action': 'sell',
                            'price': price,
                            'quantity': quantity,
                            'balance': balance,
                            'position': position,
                            'reason': reason
                        })
        
        # 计算最终资产
        final_asset = balance + position * prices[-1]
        total_return = (final_asset - 100000) / 100000
        
        # 计算胜率
        winning_trades = sum(1 for trade in trades if trade['action'] == 'sell' and trade['balance'] > 100000)
        win_rate = winning_trades / len(trades) if trades else 0
        
        return jsonify({
            'status': 'success',
            'data': {
                'strategy': strategy_name,
                'symbol': symbol,
                'test_duration': test_duration,
                'initial_balance': 100000,
                'final_asset': final_asset,
                'total_return': total_return,
                'total_trades': len(trades),
                'win_rate': win_rate,
                'trades': trades
            }
        })
    except Exception as e:
        logger.error(f"策略测试失败: {e}")
        return jsonify({'status': 'error', 'message': f'策略测试失败: {str(e)}'})

# 策略文档API
@app.route('/api/strategy/docs/<strategy_name>')
def get_strategy_docs(strategy_name):
    """
    获取策略文档
    """
    try:
        if strategy_name.startswith('exp_'):
            import importlib
            import sys
            import os
            
            # 添加策略目录到Python路径
            strategies_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'strategies')
            if strategies_dir not in sys.path:
                sys.path.insert(0, strategies_dir)
            
            # 动态导入模块
            module = importlib.import_module(strategy_name)
            
            # 提取文档信息
            docs = {
                'name': strategy_name,
                'version': getattr(module, '__version__', '1.0.0'),
                'description': getattr(module, '__doc__', '无文档'),
                'author': getattr(module, '__author__', '未知'),
                'created_at': getattr(module, '__created__', '未知'),
                'parameters': getattr(module, '__parameters__', {})
            }
            
            # 提取策略类文档
            class_name = strategy_name.replace('exp_', '').title().replace('_', '')
            if hasattr(module, class_name):
                strategy_class = getattr(module, class_name)
                docs['class_doc'] = getattr(strategy_class, '__doc__', '无类文档')
                
                # 提取方法文档
                docs['methods'] = {}
                for method_name in dir(strategy_class):
                    if not method_name.startswith('_'):
                        method = getattr(strategy_class, method_name)
                        if callable(method):
                            docs['methods'][method_name] = getattr(method, '__doc__', '无方法文档')
            
            return jsonify({
                'status': 'success',
                'data': docs
            })
        else:
            return jsonify({'status': 'error', 'message': '仅支持获取实验策略文档'})
    except Exception as e:
        logger.error(f"获取策略文档失败: {e}")
        return jsonify({'status': 'error', 'message': f'获取策略文档失败: {str(e)}'})

@socketio.on('connect')
def handle_connect():
    print('客户端连接')
    logger.info('新的WebSocket连接')

    global accounts, current_account
    account = accounts.get(current_account)
    if account:
        for symbol, stock in account.stocks.items():
            if stock['price_history']:
                trader = stock['trader']
                acc = trader.get_account_info()
                account_info = acc["data"] if acc.get("code") == 0 else {}

                socketio.emit('market_data', {
                    'account': current_account,
                    'symbol': symbol,
                    'price': stock['price_history'][-1],
                    'price_history': stock['price_history'][-50:],
                    'account_info': account_info,
                    'strategy': {
                        'market_type': stock['strategy'].market_type if stock.get('strategy') else 'range_bound',
                        'grid_spacing': stock['strategy'].grid_spacing if stock.get('strategy') else 0.004,
                        'position': stock['strategy'].position if stock.get('strategy') else 0,
                        'atr': stock.get('atr', 0),
                        'trend_direction': stock.get('trend_direction', 'neutral'),
                    },
                    'trades': stock['trade_history'][-10:]
                })

if __name__ == '__main__':
    template_dir = os.path.join(os.path.dirname(__file__), 'templates')
    if not os.path.exists(template_dir):
        os.makedirs(template_dir)

    static_dir = os.path.join(os.path.dirname(__file__), 'static')
    if not os.path.exists(static_dir):
        os.makedirs(static_dir)

    logger.info("量化交易系统启动")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
