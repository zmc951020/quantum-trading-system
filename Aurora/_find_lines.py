with open('visualization.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()
for i, line in enumerate(lines, 1):
    if 'def get_strategies' in line or 'def start_strategy' in line or 'def backtest_strategy' in line or 'def get_strategy_params' in line or 'strategies = [' in line:
        print(f'{i}: {line.rstrip()}')
    if "strategy_name == 'FourierRLStrategy'" in line or "strategy_name == 'FinalMarketAdaptiveGrid'" in line or "strategy_name == 'MLRangeGridTrading'" in line or "strategy_name == 'HuijinValueStrategy'" in line:
        print(f'{i}: {line.rstrip()}')
