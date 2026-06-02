import sys; sys.path.insert(0, r'd:\Gupiao\升级vscode\QS_Robot\core')
from optimizer_tau_cluster import BacktestCache, MockBacktestEngine, CacheStats
import time, random

cache = BacktestCache()
engine = MockBacktestEngine(use_cache=True, cache=cache)
params_list = [{'short_period': i, 'long_period': i*2, 'threshold': 0.05, 'stop_loss': 0.05} for i in range(5, 30)]

# 第一次
start = time.time()
for p in params_list:
    engine.run_backtest('test', p)
t1 = time.time() - start
cnt1 = engine.call_count

# 第二次(热缓存)
engine.call_count = 0
cache._stats = CacheStats()
start = time.time()
for p in params_list:
    engine.run_backtest('test', p)
t2 = time.time() - start
cnt2 = engine.call_count
s2 = cache.get_stats()

print(f'第一次: {t1:.2f}s, 调用次数: {cnt1}')
print(f'第二次: {t2:.2f}s, 调用次数: {cnt2}, 命中率: {s2.hit_rate*100:.1f}%')
print(f'加速比: {t1/t2:.2f}x')
