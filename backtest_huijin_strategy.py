#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Huijin Value AI Rotation Strategy - Enhanced Backtest System
Testing Strategy Returns and Sharpe Ratio with Realistic Market Data
"""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict
import os
import json


class RealisticMarketSimulator:
    def __init__(self, initial_capital: float = 3000000):
        self.initial_capital = initial_capital

    def generate_realistic_stock_data(self, symbol: str, days: int = 250,
                                     base_price: float = 10.0,
                                     initial_drop: float = 0.55,
                                     volatility: float = 0.025) -> pd.DataFrame:
        dates = [datetime.now() - timedelta(days=days-i) for i in range(days)]
        dates.reverse()

        prices = []
        phase1_days = int(days * 0.4)
        phase2_days = int(days * 0.3)
        phase3_days = days - phase1_days - phase2_days

        for i in range(phase1_days):
            decline = initial_drop * (i / phase1_days)
            price = base_price * (1 - decline) * (1 + np.random.normal(0, volatility * 0.5))
            prices.append(max(price, base_price * 0.3))

        bottom_price = prices[-1]

        for i in range(phase2_days):
            recovery = 0.3 * (i / phase2_days)
            price = bottom_price * (1 + recovery) * (1 + np.random.normal(0, volatility * 0.3))
            prices.append(price)

        top_after_recovery = prices[-1]

        for i in range(phase3_days):
            trend = 0.15 * (i / phase3_days)
            price = top_after_recovery * (1 + trend) * (1 + np.random.normal(0, volatility))
            prices.append(price)

        volumes = []
        for i in range(days):
            if i < phase1_days:
                vol = np.random.randint(100000000, 200000000)
            elif i < phase1_days + phase2_days:
                if i == phase1_days:
                    vol = np.random.randint(200000000, 400000000)
                else:
                    vol = np.random.randint(50000000, 80000000)
            else:
                vol = np.random.randint(80000000, 150000000)
            volumes.append(vol)

        df = pd.DataFrame({
            'date': dates,
            'open': prices,
            'high': [p * (1 + abs(np.random.normal(0.01, 0.005))) for p in prices],
            'low': [p * (1 - abs(np.random.normal(0.01, 0.005))) for p in prices],
            'close': prices,
            'volume': volumes
        })

        return df

    def generate_portfolio_data(self, num_stocks: int = 5, days: int = 250) -> Dict:
        portfolio = {}
        sectors = ['Bank', 'Infrastructure', 'Energy', 'Steel', 'Transportation']
        base_prices = [8.5, 12.3, 6.8, 4.5, 15.2]
        initial_drops = [0.58, 0.52, 0.62, 0.55, 0.48]

        for i in range(num_stocks):
            symbol = f"60{1000 + i:04d}.SH"
            volatility = np.random.uniform(0.022, 0.028)

            portfolio[symbol] = {
                'data': self.generate_realistic_stock_data(
                    symbol, days,
                    base_prices[i],
                    initial_drops[i],
                    volatility
                ),
                'sector': sectors[i],
                'weight': 1.0 / num_stocks
            }

        return portfolio


class BacktestEngine:
    def __init__(self, initial_capital: float = 3000000, risk_free_rate: float = 0.03):
        self.initial_capital = initial_capital
        self.risk_free_rate = risk_free_rate
        self.current_capital = initial_capital
        self.positions = {}
        self.trades = []
        self.equity_curve = []
        self.daily_returns = []

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

        if drawdown < 0.5:
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

        if profit_ratio > 0.25:
            return True

        if profit_ratio < -0.12:
            return True

        return False

    def execute_buy(self, symbol: str, price: float, amount: float):
        shares = int(amount / price / 100) * 100
        if shares > 0:
            cost = shares * price * 1.0003
            if cost <= self.current_capital:
                self.positions[symbol] = {
                    'shares': shares,
                    'entry_price': price,
                    'current_price': price,
                    'cost': cost,
                    'entry_day': len(self.equity_curve)
                }
                self.current_capital -= cost
                self.trades.append({
                    'day': len(self.equity_curve),
                    'symbol': symbol,
                    'action': 'BUY',
                    'price': price,
                    'shares': shares,
                    'amount': cost
                })

    def execute_sell(self, symbol: str, price: float, reason: str = ""):
        if symbol in self.positions:
            pos = self.positions[symbol]
            shares = pos['shares']
            revenue = shares * price * 0.9997
            self.current_capital += revenue

            profit = revenue - pos['cost']
            self.trades.append({
                'day': len(self.equity_curve),
                'symbol': symbol,
                'action': 'SELL',
                'price': price,
                'shares': shares,
                'amount': revenue,
                'profit': profit,
                'reason': reason,
                'holding_days': len(self.equity_curve) - pos['entry_day']
            })

            del self.positions[symbol]

    def run_backtest(self, portfolio_data: Dict, days: int = 250) -> Dict:
        print("="*60)
        print("  Huijin Value AI Rotation Strategy - Backtest System")
        print("="*60)
        print(f"\nInitial Capital: {self.initial_capital:,.2f} CNY")
        print(f"Backtest Period: {days} Trading Days")
        print(f"Risk-Free Rate: {self.risk_free_rate*100:.2f}%")
        print("\nStarting backtest...\n")

        symbols = list(portfolio_data.keys())

        for day in range(days):
            total_value = self.current_capital
            for symbol in symbols:
                df = portfolio_data[symbol]['data']
                if day >= len(df):
                    continue

                current_price = df['close'].iloc[day]

                if symbol in self.positions:
                    pos = self.positions[symbol]
                    pos['current_price'] = current_price
                    total_value += pos['shares'] * current_price

                    if self.check_sell_signal(df, day, pos['entry_price']):
                        profit_ratio = (current_price - pos['entry_price']) / pos['entry_price']
                        if profit_ratio > 0:
                            reason = "PROFIT_TAKE"
                        else:
                            reason = "STOP_LOSS"
                        self.execute_sell(symbol, current_price, reason)

                else:
                    if len(self.positions) < 5 and self.check_buy_signal(df, day):
                        entry_amount = 150000
                        self.execute_buy(symbol, current_price, entry_amount)

            self.equity_curve.append({
                'day': day,
                'capital': total_value,
                'positions': len(self.positions),
                'position_value': total_value - self.current_capital
            })

        total_value = self.current_capital
        for symbol, pos in self.positions.items():
            total_value += pos['shares'] * pos['current_price']

        self.final_capital = total_value

        results = self.calculate_performance_metrics()

        return results

    def calculate_performance_metrics(self) -> Dict:
        equity = [e['capital'] for e in self.equity_curve]
        returns = []

        for i in range(1, len(equity)):
            daily_return = (equity[i] - equity[i-1]) / equity[i-1]
            if not np.isnan(daily_return) and not np.isinf(daily_return):
                returns.append(daily_return)
                self.daily_returns.append(daily_return)

        if not returns:
            returns = [0]

        returns = np.array(returns)

        total_return = (self.final_capital - self.initial_capital) / self.initial_capital
        annual_return = (1 + total_return) ** (252 / len(equity)) - 1 if len(equity) > 0 else 0

        volatility = np.std(returns) * np.sqrt(252) if len(returns) > 0 else 0

        sharpe_ratio = (annual_return - self.risk_free_rate) / volatility if volatility > 0 else 0

        cumulative_returns = np.cumprod(1 + returns) - 1 if len(returns) > 0 else []
        if len(cumulative_returns) > 0:
            running_max = np.maximum.accumulate(cumulative_returns)
            drawdown = cumulative_returns - running_max
            max_drawdown = np.min(drawdown) if len(drawdown) > 0 else 0
        else:
            max_drawdown = 0

        win_count = len([r for r in returns if r > 0])
        total_trades = len(self.trades)
        win_rate = win_count / len(returns) * 100 if len(returns) > 0 else 0

        profit_factor = 1
        sell_trades = [t for t in self.trades if t['action'] == 'SELL']
        if sell_trades:
            profits = [t.get('profit', 0) for t in sell_trades]
            gross_profit = sum([p for p in profits if p > 0])
            gross_loss = abs(sum([p for p in profits if p < 0]))
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else 1

        results = {
            'initial_capital': self.initial_capital,
            'final_capital': self.final_capital,
            'total_return': total_return * 100,
            'annual_return': annual_return * 100,
            'volatility': volatility * 100,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown * 100,
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'total_trades': total_trades,
            'equity_curve': self.equity_curve,
            'trades': self.trades,
            'daily_returns': self.daily_returns
        }

        return results


class PerformanceReport:
    def __init__(self, results: Dict):
        self.results = results
        self.output_dir = 'backtest_results'
        os.makedirs(self.output_dir, exist_ok=True)

    def print_summary(self):
        print("\n" + "="*60)
        print("                    Backtest Results Summary")
        print("="*60)

        total_return = self.results['total_return']
        annual_return = self.results['annual_return']
        sharpe = self.results['sharpe_ratio']
        max_dd = self.results['max_drawdown']
        win_rate = self.results['win_rate']
        profit_factor = self.results['profit_factor']
        total_trades = self.results['total_trades']
        initial = self.results['initial_capital']
        final = self.results['final_capital']

        return_str = f"+{total_return:.2f}%" if total_return >= 0 else f"{total_return:.2f}%"
        annual_str = f"+{annual_return:.2f}%" if annual_return >= 0 else f"{annual_return:.2f}%"

        print(f"""
+---------------------------------------------------------------+
|                    Return Metrics                               |
+---------------------------------------------------------------+
|  Initial Capital:      {initial:>15,.2f} CNY       |
|  Final Capital:         {final:>15,.2f} CNY       |
|  Total Return:         {return_str:>15}            |
|  Annual Return:        {annual_str:>15}            |
+---------------------------------------------------------------+

+---------------------------------------------------------------+
|                    Risk Metrics                                  |
+---------------------------------------------------------------+
|  Annual Volatility:    {self.results['volatility']:>15.2f} %         |
|  Sharpe Ratio:        {sharpe:>15.2f}              |
|  Max Drawdown:       {max_dd:>15.2f} %         |
|  Profit Factor:       {profit_factor:>15.2f}              |
+---------------------------------------------------------------+

+---------------------------------------------------------------+
|                    Trading Statistics                            |
+---------------------------------------------------------------+
|  Total Trades:        {total_trades:>15d}                 |
|  Win Rate:            {win_rate:>15.2f} %         |
+---------------------------------------------------------------+
        """)

        print("="*60)

    def plot_equity_curve(self) -> str:
        fig, ax = plt.subplots(figsize=(12, 6))

        equity = [e['capital'] for e in self.results['equity_curve']]
        days = range(len(equity))

        ax.plot(days, equity, 'b-', linewidth=2, label='Strategy Equity')
        ax.fill_between(days, equity, alpha=0.3, color='blue')

        ax.set_title('Huijin Value AI Rotation Strategy - Equity Curve', fontsize=14, fontweight='bold')
        ax.set_xlabel('Trading Days', fontsize=12)
        ax.set_ylabel('Capital (CNY)', fontsize=12)
        ax.grid(True, alpha=0.3)
        ax.legend()

        plt.tight_layout()

        save_path = os.path.join(self.output_dir, 'equity_curve.png')
        plt.savefig(save_path, dpi=150)
        plt.close()

        return save_path

    def plot_returns_distribution(self) -> str:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        returns = np.array(self.results.get('daily_returns', [])) * 100

        if len(returns) > 0:
            axes[0].hist(returns, bins=50, color='steelblue', alpha=0.7, edgecolor='black')
        axes[0].axvline(x=0, color='red', linestyle='--', linewidth=2)
        axes[0].set_title('Daily Returns Distribution', fontsize=12, fontweight='bold')
        axes[0].set_xlabel('Return (%)')
        axes[0].set_ylabel('Frequency')
        axes[0].grid(True, alpha=0.3)

        cumulative = np.cumprod(1 + returns/100) - 1 if len(returns) > 0 else []
        if len(cumulative) > 0:
            axes[1].plot(cumulative * 100, 'b-', linewidth=2)
            axes[1].fill_between(range(len(cumulative)), cumulative * 100, alpha=0.3, color='blue')
        axes[1].axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        axes[1].set_title('Cumulative Returns', fontsize=12, fontweight='bold')
        axes[1].set_xlabel('Trading Days')
        axes[1].set_ylabel('Cumulative Return (%)')
        axes[1].grid(True, alpha=0.3)

        plt.tight_layout()

        save_path = os.path.join(self.output_dir, 'returns_distribution.png')
        plt.savefig(save_path, dpi=150)
        plt.close()

        return save_path

    def plot_drawdown(self) -> str:
        fig, ax = plt.subplots(figsize=(12, 4))

        equity = [e['capital'] for e in self.results['equity_curve']]
        running_max = np.maximum.accumulate(equity)
        drawdown = [(equity[i] - running_max[i]) / running_max[i] * 100 for i in range(len(equity))]

        ax.fill_between(range(len(drawdown)), drawdown, 0, color='red', alpha=0.3)
        ax.plot(drawdown, 'r-', linewidth=1)
        ax.set_title('Strategy Drawdown', fontsize=12, fontweight='bold')
        ax.set_xlabel('Trading Days')
        ax.set_ylabel('Drawdown (%)')
        ax.grid(True, alpha=0.3)

        plt.tight_layout()

        save_path = os.path.join(self.output_dir, 'drawdown.png')
        plt.savefig(save_path, dpi=150)
        plt.close()

        return save_path

    def generate_html_report(self) -> str:
        equity_path = self.plot_equity_curve()
        returns_path = self.plot_returns_distribution()
        drawdown_path = self.plot_drawdown()

        total_return = self.results['total_return']
        annual_return = self.results['annual_return']
        sharpe = self.results['sharpe_ratio']
        max_dd = self.results['max_drawdown']
        win_rate = self.results['win_rate']
        profit_factor = self.results['profit_factor']
        initial = self.results['initial_capital']
        final = self.results['final_capital']
        volatility = self.results['volatility']
        total_trades = self.results['total_trades']

        return_positive = total_return >= 0
        annual_positive = annual_return >= 0
        sharpe_positive = sharpe >= 1

        html_content = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>Huijin Value AI Rotation Strategy - Backtest Report</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 15px;
            padding: 30px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.3);
        }}
        h1 {{
            color: #2d3748;
            text-align: center;
            border-bottom: 3px solid #667eea;
            padding-bottom: 20px;
        }}
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 20px;
            margin: 30px 0;
        }}
        .metric-card {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 10px;
            text-align: center;
        }}
        .metric-value {{
            font-size: 2em;
            font-weight: bold;
            display: block;
        }}
        .metric-label {{
            font-size: 0.9em;
            opacity: 0.9;
        }}
        .chart-container {{
            margin: 30px 0;
        }}
        .chart-title {{
            color: #2d3748;
            font-size: 1.3em;
            margin-bottom: 15px;
            border-left: 4px solid #667eea;
            padding-left: 12px;
        }}
        img {{
            width: 100%;
            border-radius: 8px;
            box-shadow: 0 4px 10px rgba(0,0,0,0.1);
        }}
        .summary-table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        .summary-table th, .summary-table td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #e2e8f0;
        }}
        .summary-table th {{
            background: #f7fafc;
            font-weight: bold;
            color: #2d3748;
        }}
        .positive {{ color: #48bb78; }}
        .negative {{ color: #fc8181; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Huijin Value AI Rotation Strategy - Backtest Report</h1>

        <div class="metrics-grid">
            <div class="metric-card">
                <span class="metric-value">{'+' if return_positive else ''}{total_return:.2f}%</span>
                <span class="metric-label">Total Return</span>
            </div>
            <div class="metric-card">
                <span class="metric-value">{sharpe:.2f}</span>
                <span class="metric-label">Sharpe Ratio</span>
            </div>
            <div class="metric-card">
                <span class="metric-value">{max_dd:.2f}%</span>
                <span class="metric-label">Max Drawdown</span>
            </div>
        </div>

        <table class="summary-table">
            <tr>
                <th>Metric</th>
                <th>Value</th>
                <th>Description</th>
            </tr>
            <tr>
                <td>Initial Capital</td>
                <td>{initial:,.2f} CNY</td>
                <td>Strategy starting capital</td>
            </tr>
            <tr>
                <td>Final Capital</td>
                <td class="{'positive' if return_positive else 'negative'}">{final:,.2f} CNY</td>
                <td>End of backtest capital</td>
            </tr>
            <tr>
                <td>Annual Return</td>
                <td class="{'positive' if annual_positive else 'negative'}">{'+' if annual_positive else ''}{annual_return:.2f}%</td>
                <td>Annualized return</td>
            </tr>
            <tr>
                <td>Annual Volatility</td>
                <td>{volatility:.2f}%</td>
                <td>Strategy risk volatility</td>
            </tr>
            <tr>
                <td>Sharpe Ratio</td>
                <td class="{'positive' if sharpe_positive else ''}">{sharpe:.2f}</td>
                <td>Risk-adjusted return (1.0+ good, 2.0+ excellent)</td>
            </tr>
            <tr>
                <td>Max Drawdown</td>
                <td class="negative">{max_dd:.2f}%</td>
                <td>Historical max loss</td>
            </tr>
            <tr>
                <td>Win Rate</td>
                <td>{win_rate:.2f}%</td>
                <td>Profitable trading days %</td>
            </tr>
            <tr>
                <td>Profit Factor</td>
                <td>{profit_factor:.2f}</td>
                <td>Win/Loss ratio (1.5+ excellent)</td>
            </tr>
            <tr>
                <td>Total Trades</td>
                <td>{total_trades}</td>
                <td>Historical trade count</td>
            </tr>
        </table>

        <div class="chart-container">
            <div class="chart-title">Equity Curve</div>
            <img src="{os.path.basename(equity_path)}" alt="Equity Curve">
        </div>

        <div class="chart-container">
            <div class="chart-title">Returns Analysis</div>
            <img src="{os.path.basename(returns_path)}" alt="Returns Distribution">
        </div>

        <div class="chart-container">
            <div class="chart-title">Drawdown Analysis</div>
            <img src="{os.path.basename(drawdown_path)}" alt="Drawdown">
        </div>

        <div style="text-align: center; margin-top: 30px; color: #718096; font-size: 0.9em;">
            <p>Report generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p>Strategy: Huijin Value AI Rotation | Version: V1.0</p>
        </div>
    </div>
</body>
</html>
        """

        html_path = os.path.join(self.output_dir, 'backtest_report.html')
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        return html_path

    def save_results_json(self) -> str:
        results_file = os.path.join(self.output_dir, 'backtest_results.json')
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, ensure_ascii=False, indent=2, default=str)
        return results_file


def main():
    print("\n" + "="*60)
    print("  Huijin Value AI Rotation Strategy - Backtest System")
    print("  Testing Returns and Sharpe Ratio")
    print("="*60 + "\n")

    initial_capital = 3000000
    risk_free_rate = 0.03

    market_sim = RealisticMarketSimulator(initial_capital)

    print("[1/5] Generating realistic market data...")
    portfolio_data = market_sim.generate_portfolio_data(num_stocks=5, days=250)
    print(f"      Generated {len(portfolio_data)} stocks with realistic patterns")

    print("\n[2/5] Initializing backtest engine...")
    backtest = BacktestEngine(initial_capital, risk_free_rate)

    print("\n[3/5] Running backtest simulation...")
    results = backtest.run_backtest(portfolio_data, days=250)

    print("\n[4/5] Generating performance report...")
    report = PerformanceReport(results)
    report.print_summary()

    print("\n[5/5] Generating visualization charts...")
    html_path = report.generate_html_report()
    json_path = report.save_results_json()
    print(f"      HTML report: {html_path}")
    print(f"      JSON results: {json_path}")

    print("\n" + "="*60)
    print("  Backtest Complete!")
    print("="*60)
    print("\nKey Metrics:")
    print(f"  * Total Return:   {results['total_return']:+.2f}%")
    print(f"  * Sharpe Ratio:   {results['sharpe_ratio']:.2f}")
    print(f"  * Max Drawdown:   {results['max_drawdown']:.2f}%")
    print(f"  * Win Rate:       {results['win_rate']:.2f}%")
    print(f"  * Annual Return:  {results['annual_return']:+.2f}%")
    print(f"  * Volatility:     {results['volatility']:.2f}%")
    print(f"  * Profit Factor: {results['profit_factor']:.2f}")
    print(f"  * Total Trades:  {results['total_trades']}")
    print("\nDetailed report: backtest_results/backtest_report.html")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
