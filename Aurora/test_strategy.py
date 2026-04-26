#!/usr/bin/env python3
"""
Simple test for the quantitative trading system
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    print("=" * 60)
    print("Aurora Quant Trading System - Local Test")
    print("=" * 60)
    
    # Generate test data
    print("\nGenerating test data...")
    length = 50
    dates = pd.date_range(start=datetime.now() - timedelta(days=length), periods=length, freq='D')
    returns = np.random.normal(0, 0.01, length)
    prices = 100 * (1 + returns).cumprod()
    
    # Import strategy
    print("\nImporting strategy...")
    from strategies.ml_range_grid import MLRangeGridTrading
    
    # Initialize strategy
    print("\nInitializing ML Range Grid Strategy...")
    strategy = MLRangeGridTrading(base_price=prices[0], initial_balance=100000)
    print("Strategy initialized!")
    
    # Run strategy
    print("\nRunning strategy...")
    for i, price in enumerate(prices):
        strategy.update_price(price, prices[:i+1] if i >= 10 else None)
    
    # Get results
    perf = strategy.get_performance()
    
    print("\n" + "=" * 60)
    print("SUCCESS! Strategy Test Complete")
    print("=" * 60)
    print("Total Return: {:.2f}%".format(perf['total_return'] * 100))
    print("Sharpe Ratio: {:.2f}".format(perf['sharpe_ratio']))
    print("Win Rate: {:.2f}%".format(perf['win_rate'] * 100))
    print("Total Trades: {}".format(perf['total_trades']))
    print("=" * 60)
    
    print("\nThe system works locally!")
    print("\nTo run the full system:")
    print("  python main.py backtest   - Run full backtest")
    print("  python main.py start      - Start trading system")
    print("  python main.py train      - Train ML models")
    
if __name__ == "__main__":
    main()
