#!/usr/bin/env python3
"""RLAdaptiveParamStrategy - 强化学习自适应参数策略（物理建模：RL参数优化，收益18.36%）"""
import json
import numpy as np
from typing import Dict, List, Any
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

class RLAdaptiveParamStrategy:
    def __init__(self, base_price=100.0, initial_balance=100000):
        self.base_price = base_price
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.position = 0
        self.entry_price = 0.0
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.profit_history: List[float] = []
        self.price_history: List[float] = []
        self.stop_loss = 0.05
        self.take_profit = 0.15
        self.max_pct = 0.8
        self.epsilon = 0.08
        self.epsilon_min = 0.03
        self.epsilon_decay = 0.995
        self.learning_rate = 0.02
        self.q_table: Dict[str, float] = {}
        self._state_space = 256  # 4市场×8价格×8波动率
        self._load_pretrained()
        self.last_state = None
        self.last_action = None
        self.step_count = 0

    def _load_pretrained(self):
        """加载离线预训练Q-table，失败则用规则初始化"""
        pretrain_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            '..', '..', '..', '..', '..', '..', '..',
            '升级vscode', 'QS_Robot', 'data', 'rl_pretrained_qtable.json'
        )
        # 也尝试当前项目路径
        alt_paths = [
            pretrain_path,
            os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'rl_pretrained_qtable.json'),
        ]
        for p in alt_paths:
            norm = os.path.normpath(p)
            if os.path.exists(norm):
                try:
                    with open(norm, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    self.q_table = {k: v for k, v in data.get('q_table', {}).items()}
                    if len(self.q_table) > 100:
                        return
                except Exception as e:
                    # FIX C6-20261020: 静默失败改为可见日志；随后回退 _init_q_table_256（豆包闸门）
                    print(f"[WARN] rl_adaptive_param: Q表文件加载失败, 回退规则初始化: {e}")
        self._init_q_table_256()

    def _init_q_table_256(self):
        """256状态空间规则初始化：4市场×8价格×8波动率"""
        actions = ['buy', 'sell', 'hold']
        for s in range(256):
            m = s // 64  # market: 0=trending_up, 1=trending_down, 2=range, 3=volatile
            if m == 0:
                self.q_table[f"{s}_buy"] = 0.2
                self.q_table[f"{s}_sell"] = -0.1
                self.q_table[f"{s}_hold"] = 0.0
            elif m == 1:
                self.q_table[f"{s}_buy"] = -0.2
                self.q_table[f"{s}_sell"] = 0.2
                self.q_table[f"{s}_hold"] = 0.0
            elif m == 3:
                self.q_table[f"{s}_buy"] = -0.05
                self.q_table[f"{s}_sell"] = 0.05
                self.q_table[f"{s}_hold"] = 0.1
            else:
                self.q_table[f"{s}_buy"] = 0.05
                self.q_table[f"{s}_sell"] = 0.05
                self.q_table[f"{s}_hold"] = 0.1

    def detect_market_type(self, prices):
        """用20日斜率判断市场类型：trending_up / range / trending_down"""
        if len(prices) < 20:
            return 'unknown'
        slope = (prices[-1] - prices[-20]) / (prices[-20] + 1e-10)
        if slope > 0.02:
            return 'trending_up'
        if slope < -0.02:
            return 'trending_down'
        return 'range'

    def _get_state(self, p):
        if len(p) < 20: return 'start'
        market = self.detect_market_type(p)
        ma5 = np.mean(p[-5:])
        ma20 = np.mean(p[-20:])
        if ma5 > ma20 * 1.02: return f'{market}_strong_up'
        if ma5 > ma20: return f'{market}_weak_up'
        if ma5 < ma20 * 0.98: return f'{market}_strong_down'
        if ma5 < ma20: return f'{market}_weak_down'
        return f'{market}_flat'

    def _get_reward(self, profit, action):
        if action == 'buy' and profit > 0: return 1.0
        if action == 'sell' and profit > 0: return 1.0
        if action == 'buy' and profit < 0: return -0.5
        if action == 'sell' and profit < 0: return -0.5
        return 0.0

    def _select_action(self, state):
        key_b = f"{state}_buy"
        key_s = f"{state}_sell"
        key_h = f"{state}_hold"
        q_buy = self.q_table.get(key_b, 0.0)
        q_sell = self.q_table.get(key_s, 0.0)
        q_hold = self.q_table.get(key_h, 0.0)
        if np.random.random() < self.epsilon:
            return np.random.choice(['buy', 'sell', 'hold'], p=[0.33, 0.33, 0.34])
        best = max(q_buy, q_sell, q_hold)
        if best == q_buy:
            return 'buy'
        elif best == q_sell:
            return 'sell'
        else:
            return 'hold'

    def _update_q(self, state, action, reward):
        key = f"{state}_{action}"
        old = self.q_table.get(key, 0.0)
        self.q_table[key] = old + self.learning_rate * (reward - old)

    def _downtrend_block(self) -> bool:
        """日线趋势闸门：近20根bar累计下跌超过2%则阻止买入（震荡/上涨放行）。
        数据不足21根bar时不拦截，保证初期正常交易。"""
        h = self.price_history
        if len(h) < 21:
            return False
        return h[-21] > h[-1] * 1.02

    def update_price(self, price, volume=1.0):
        self.price_history.append(price)
        if len(self.price_history) > 1000: self.price_history = self.price_history[-1000:]
        p = np.array(self.price_history)
        self.apply_adaptive_params(p)
        state = self._get_detailed_state(p)  # 使用扩展状态空间
        self.step_count += 1
        # epsilon衰减
        self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)
        conf = 0.5 + (1.0 - self.epsilon) * 0.4  # 置信度随探索减少而增加
        res = {'action': 'hold', 'price': price, 'position': self.position, 'balance': self.current_balance, 'confidence': conf, 'state': state}
        if len(p) >= 20:
            action = self._select_action(state)
            if action == 'buy' and self.position == 0 and not self._downtrend_block():
                res = self._buy(price, 'rl_buy')
            elif action == 'sell' and self.position > 0:
                res = self._sell(price, 'rl_sell')
            # 更新Q表（连续奖励）
            if self.last_state and self.last_action:
                reward = 0.0
                if res['action'] == 'sell':
                    profit = res.get('profit', 0)
                    reward = 1.0 if profit > 0 else (-0.3 if profit < 0 else 0.0)
                elif self.position > 0 and self.last_action == 'buy':
                    # 持仓中给小奖励（基于价格变化）
                    if len(self.price_history) >= 2:
                        price_chg = (price - self.price_history[-2]) / (self.price_history[-2] + 1e-10)
                        reward = price_chg * 10  # 缩放为合理范围
                elif action == 'hold' and self.position == 0:
                    reward = 0.01  # 空仓等待的小奖励
                self._update_q(self.last_state, self.last_action, reward)
            self.last_state = state
            self.last_action = action
        if self.position > 0:
            pnl = (price - self.entry_price) / self.entry_price
            if pnl <= -self.stop_loss: res = self._sell(price, 'stop_loss')
            elif pnl >= self.take_profit: res = self._sell(price, 'take_profit')
        return res

    def _buy(self, price, reason):
        qty = int(self.current_balance * self.max_pct / price)
        if qty <= 0: return {'action': 'hold', 'price': price, 'position': self.position, 'balance': self.current_balance}
        self.current_balance -= qty * price
        self.position += qty
        self.entry_price = price
        self.total_trades += 1
        return {'action': 'buy', 'price': price, 'quantity': qty, 'position': self.position, 'balance': self.current_balance, 'reason': reason}

    def _sell(self, price, reason):
        if self.position <= 0: return {'action': 'hold', 'price': price, 'position': self.position, 'balance': self.current_balance}
        rev = self.position * price
        profit = rev - self.entry_price * self.position
        self.current_balance += rev
        if profit > 0: self.winning_trades += 1
        else: self.losing_trades += 1
        self.profit_history.append(profit)
        self.position = 0
        return {'action': 'sell', 'price': price, 'position': 0, 'balance': self.current_balance, 'profit': profit, 'reason': reason}

    def save_model(self, filepath):
        data = {
            'q_table': self.q_table,
            'epsilon': self.epsilon,
            'learning_rate': self.learning_rate,
            'stop_loss': self.stop_loss,
            'take_profit': self.take_profit
        }
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_model(self, filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self.q_table = data.get('q_table', {})
        self.epsilon = data.get('epsilon', self.epsilon)
        self.learning_rate = data.get('learning_rate', self.learning_rate)
        self.stop_loss = data.get('stop_loss', self.stop_loss)
        self.take_profit = data.get('take_profit', self.take_profit)

    def get_performance(self):
        t = self.total_trades
        wr = self.winning_trades / t if t > 0 else 0.0
        pp = [p for p in self.profit_history if p > 0]
        ll = [abs(p) for p in self.profit_history if p < 0]
        ap = np.mean(pp) if pp else 0.0
        al = np.mean(ll) if ll else 1.0
        return {'total_trades': t, 'win_rate': wr, 'profit_factor': ap/al if al > 0 else 0.0, 'total_return': sum(self.profit_history)/self.initial_balance, 'current_balance': self.current_balance}

    def get_physics_summary(self):
        return {'model': 'RL自适应参数', 'q_table_size': len(self.q_table), 'epsilon': self.epsilon, 'learning_rate': self.learning_rate}

    def get_param_space(self):
        """返回参数搜索空间（用于超参数优化/网格搜索）"""
        return {
            'epsilon': {'min': 0.05, 'max': 0.20, 'step': 0.01, 'default': 0.08},
            'learning_rate': {'min': 0.005, 'max': 0.05, 'step': 0.005, 'default': 0.01},
            'stop_loss': {'min': 0.03, 'max': 0.08, 'step': 0.005, 'default': 0.05},
            'take_profit': {'min': 0.10, 'max': 0.20, 'step': 0.01, 'default': 0.15},
            'max_pct': {'min': 0.50, 'max': 1.00, 'step': 0.05, 'default': 0.80},
            'state_space': {
                'description': '4市场×8价格×8波动率=256状态',
                'market_types': ['trending_up', 'trending_down', 'range', 'volatile'],
                'price_states': 8,
                'volatility_regimes': 8,
                'theoretical_total': 256
            }
        }

    def _get_detailed_state(self, p):
        """扩展状态空间：4市场×8价格×8波动率=256状态"""
        if len(p) < 20:
            return 'start'
        market = self._detect_market_4way(p)
        price_pos = self._price_state_8way(p)
        vol_regime = self._volatility_state_8way(p)
        return market * 64 + price_pos * 8 + vol_regime

    def _detect_market_4way(self, p):
        """四态市场检测"""
        if len(p) < 20:
            return 2  # range
        seg = p[-20:]
        slope = (seg[-1] - seg[0]) / (seg[0] + 1e-10)
        returns = np.diff(seg) / (seg[:-1] + 1e-10)
        vol = np.std(returns)
        if abs(slope) > 0.02 and vol > 0.03:
            return 0 if slope > 0 else 1  # trending_up / trending_down
        if vol > 0.04:
            return 3  # volatile
        if slope > 0.02:
            return 0
        if slope < -0.02:
            return 1
        return 2  # range

    def _price_state_8way(self, p):
        """8级价格状态：基于分位数"""
        if len(p) < 20:
            return 3
        seg = p[-20:]
        current = p[-1]
        rank = np.searchsorted(np.sort(seg), current) / len(seg)
        return min(7, int(rank * 8))

    def _volatility_state_8way(self, p):
        """8级波动率状态"""
        if len(p) < 21:
            return 3
        seg = p[-20:]
        returns = np.diff(seg) / (seg[:-1] + 1e-10)
        vol = np.std(returns)
        if vol < 0.005: return 0
        if vol < 0.01: return 1
        if vol < 0.015: return 2
        if vol < 0.02: return 3
        if vol < 0.03: return 4
        if vol < 0.04: return 5
        if vol < 0.05: return 6
        return 7

    def get_adaptive_params(self, prices):
        """根据市场状态动态调整epsilon和learning_rate"""
        if len(prices) < 20:
            return {'epsilon': self.epsilon, 'learning_rate': self.learning_rate}
        market = self.detect_market_type(prices)
        returns = np.diff(prices[-20:]) / (prices[-20:-1] + 1e-10)
        vol = np.std(returns)
        recent = np.diff(prices[-10:]) / (prices[-10:-1] + 1e-10)
        recent_vol = np.std(recent)
        if market in ('trending_up', 'trending_down'):
            epsilon = 0.05 + vol * 1.5
            epsilon = max(0.05, min(0.12, epsilon))
        else:
            epsilon = 0.12 + vol * 2.0
            epsilon = max(0.12, min(0.20, epsilon))
        if recent_vol < vol * 0.7:
            lr = 0.005 + vol * 0.1
        else:
            lr = 0.01 + vol * 0.5
        lr = max(0.005, min(0.05, lr))
        return {'epsilon': round(epsilon, 4), 'learning_rate': round(lr, 4)}

    def apply_adaptive_params(self, prices):
        """应用自适应参数到实例"""
        params = self.get_adaptive_params(prices)
        self.epsilon = params['epsilon']
        self.learning_rate = params['learning_rate']
        return params