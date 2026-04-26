#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
汇金价值AI轮动策略 - Aurora交易系统适配器
将汇金策略集成到Aurora的策略架构中
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, Optional, List
from .strategy_base import StrategyBase


class HuijinValueStrategyAdapter(StrategyBase):
    """
    汇金价值AI轮动策略 Aurora适配器
    实现价值股深度回调后的分批建仓和AI轮动交易
    """

    def __init__(self, base_price: float, initial_balance: float = 3000000):
        super().__init__(base_price, initial_balance)
        self.base_price = base_price
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.position = 0
        self.is_active = True
        self.last_price = base_price
        self.entry_price = 0

        self.price_history = []
        self.volume_history = []
        self.trades = []
        self.equity_curve = []

        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.profit_history = []

        self.max_positions = 5
        self.position_size = 150000
        self.buy_signal_threshold = 0.5
        self.profit_target = 0.25
        self.stop_loss = 0.12

    def calculate_volatility(self, prices: List[float], window: int = 20) -> float:
        if len(prices) < window:
            return 0.02
        returns = []
        for i in range(window, len(prices)):
            ret = (prices[i] - prices[i-window]) / prices[i-window]
            returns.append(ret)
        if not returns:
            return 0.02
        return np.std(returns) * np.sqrt(252)

    def check_buy_signal(self, df: pd.DataFrame, index: int) -> bool:
        if index < 65:
            return False

        prices = df['close'].tolist()[:index+1]
        current_price = prices[-1]

        lookback = max(0, index - 60)
        historical_prices = prices[:lookback]

        if not historical_prices or len(historical_prices) < 10:
            return False

        max_price = max(historical_prices)
        if max_price == 0:
            return False
        drawdown = (max_price - current_price) / max_price

        if drawdown < self.buy_signal_threshold:
            return False

        recent_vol = self.calculate_volatility(prices[-60:])
        if recent_vol < 0.01:
            return False

        volume = df['volume'].iloc[index]
        avg_volume = df['volume'].iloc[max(0, index-20):index].mean()
        if avg_volume == 0:
            return False

        if volume < avg_volume * 0.6:
            return True

        return False

    def check_sell_signal(self, df: pd.DataFrame, index: int, entry_price: float) -> bool:
        if index < 20:
            return False

        current_price = df['close'].iloc[index]
        profit_ratio = (current_price - entry_price) / entry_price

        if profit_ratio > self.profit_target:
            return True

        if profit_ratio < -self.stop_loss:
            return True

        return False

    def update_price(self, current_price: float, data: Optional[pd.Series] = None) -> Dict[str, Any]:
        self.price_history.append(current_price)
        self.last_price = current_price

        action = "hold"
        reason = ""
        shares = 0
        amount = 0

        if not self.is_active:
            return {
                "action": "hold",
                "balance": self.current_balance,
                "position": self.position,
                "shares": 0,
                "entry_price": 0
            }

        if data is not None and isinstance(data, pd.DataFrame):
            current_index = len(self.price_history) - 1
            if current_index >= 0 and current_index < len(data):
                if self.check_sell_signal(data, current_index, self.entry_price):
                    if self.position > 0:
                        profit_ratio = (current_price - self.entry_price) / self.entry_price
                        action = "sell"
                        reason = "profit_take" if profit_ratio > 0 else "stop_loss"
                        shares = self.position
                        amount = shares * current_price * 0.9997
                        self.current_balance += amount
                        self.profit_history.append(amount - self.position * self.entry_price)
                        if profit_ratio > 0:
                            self.winning_trades += 1
                        else:
                            self.losing_trades += 1
                        self.position = 0
                        self.entry_price = 0
                        self.total_trades += 1
        else:
            if self.position == 0 and len(self.price_history) >= 2:
                prices = self.price_history[-60:] if len(self.price_history) >= 60 else self.price_history
                if len(prices) >= 20:
                    max_price = max(prices)
                    drawdown = (max_price - current_price) / max_price
                    volatility = self.calculate_volatility(prices)
                    if drawdown >= self.buy_signal_threshold and volatility >= 0.01:
                        shares = int(self.position_size / current_price / 100) * 100
                        if shares > 0:
                            cost = shares * current_price * 1.0003
                            if cost <= self.current_balance:
                                self.position = shares
                                self.entry_price = current_price
                                self.current_balance -= cost
                                action = "buy"
                                shares = shares
                                amount = cost
                                self.total_trades += 1

        self.equity_curve.append(self.current_balance + self.position * current_price)

        return {
            "action": action,
            "balance": self.current_balance,
            "position": self.position,
            "shares": shares,
            "amount": amount,
            "entry_price": self.entry_price,
            "current_price": current_price,
            "reason": reason
        }

    def get_performance(self) -> Dict[str, float]:
        final_capital = self.current_balance + self.position * self.last_price
        total_return = (final_capital - self.initial_balance) / self.initial_balance * 100

        win_rate = self.winning_trades / self.total_trades * 100 if self.total_trades > 0 else 0

        returns = []
        for i in range(1, len(self.equity_curve)):
            if self.equity_curve[i-1] > 0:
                daily_return = (self.equity_curve[i] - self.equity_curve[i-1]) / self.equity_curve[i-1]
                returns.append(daily_return)

        if returns:
            volatility = np.std(returns) * np.sqrt(252)
            mean_return = np.mean(returns) * 252
            risk_free_rate = 0.03
            sharpe_ratio = (mean_return - risk_free_rate) / volatility if volatility > 0 else 0
        else:
            volatility = 0
            sharpe_ratio = 0

        cumulative_returns = np.cumprod(1 + np.array(returns)) - 1 if returns else []
        max_drawdown = 0
        if len(cumulative_returns) > 0:
            running_max = np.maximum.accumulate(cumulative_returns)
            drawdown = cumulative_returns - running_max
            max_drawdown = np.min(drawdown) * 100 if len(drawdown) > 0 else 0

        return {
            "initial_balance": self.initial_balance,
            "current_balance": final_capital,
            "return": total_return,
            "sharpe_ratio": sharpe_ratio,
            "volatility": volatility * 100,
            "max_drawdown": max_drawdown,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": win_rate,
            "position": self.position,
            "entry_price": self.entry_price,
            "last_price": self.last_price
        }

    def set_active(self, active: bool):
        self.is_active = active

    def get_equity_curve(self) -> List[float]:
        return self.equity_curve

    def get_trades(self) -> List[Dict]:
        return self.trades

    def reset(self):
        self.current_balance = self.initial_balance
        self.position = 0
        self.entry_price = 0
        self.price_history = []
        self.equity_curve = []
        self.trades = []
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.profit_history = []