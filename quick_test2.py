import sys; sys.path.insert(0, r'd:\Gupiao\升级vscode\QS_Robot\core')
from optimizer_tau_cluster import BacktestCache, MockBacktestEngine, CacheStats
import time, random

print('=' * 60)
print('场景1: 理想场景 - 完全重复参数')
print('=' * 60)
cache = BacktestCache()
engine = MockBacktestEngine(use_cache=True, cache=cache)
params_list = [{'short_period': i, 'long_period': i*2, 'threshold': 0.05, 'stop_loss': 0.05} for i in range(5, 30)]

start = time.time()
for p in params_list:
    engine.run_backtest('test', p)
t1 = time.time() - start

engine.call_count = 0
cache._stats = CacheStats()
start = time.time()
for p in params_list:
    engine.run_backtest('test', p)
t2 = time.time() - start
s2 = cache.get_stats()
print(f'  冷启动: {t1:.2f}s | 热缓存: {t2:.2f}s | 加速比: {t1/t2:.1f}x | 命中率: {s2.hit_rate*100:.0f}%')

print(f'\n{"=" * 60}')
print('场景2: 真实场景 - 优化器产生连续变化参数 (贝叶斯/遗传算法)')
print('=' * 60)
cache = BacktestCache()
engine = MockBacktestEngine(use_cache=True, cache=cache)

# 模拟优化器: 每次在当前最优附近微扰 (step=0.001, 连续变化)
def generate_optimizer_params(iterations=50, initial={'short_period': 20.0, 'long_period': 60.0, 'threshold': 0.05, 'stop_loss': 0.05}):
    params = []
    current = initial.copy()
    for i in range(iterations):
        # 模拟贝叶斯优化: 在当前最优附近微扰
        current = {
            'short_period': max(5, current['short_period'] + random.choice([-1, -0.5, 0, 0.5, 1])),
            'long_period': max(10, current['long_period'] + random.choice([-2, -1, 0, 1, 2])),
            'threshold': max(0.001, current['threshold'] + random.uniform(-0.002, 0.002)),
            'stop_loss': max(0.01, current['stop_loss'] + random.uniform(-0.005, 0.005))
        }
        params.append({k: round(v, 4) for k, v in current.items()})
    return params

optimizer_params = generate_optimizer_params(100)

start = time.time()
for p in optimizer_params:
    engine.run_backtest('test', p)
t_real = time.time() - start
s_real = cache.get_stats()
cnt_real = engine.call_count

print(f'  100组连续变化参数 (模拟贝叶斯优化探索)')
print(f'  实际调用回测次数: {cnt_real}/100 = 缓存命中: {100 - cnt_real}')
print(f'  缓存命中率: {s_real.hit_rate*100:.1f}%')
print(f'  总耗时: {t_real:.2f}s')

# 无缓存对比
engine_nocache = MockBacktestEngine(use_cache=False, cache=BacktestCache())
start = time.time()
for p in optimizer_params:
    engine_nocache.run_backtest('test', p)
t_nocache = time.time() - start
print(f'  无缓存耗时: {t_nocache:.2f}s')
print(f'  实际加速比: {t_nocache/t_real:.2f}x')

print(f'\n{"=" * 60}')
print('场景3: 多优化器并行 - 搜索空间重叠分析')
print('=' * 60)

# 模拟3个优化器: 贝叶斯、遗传、网格
optimizer1 = generate_optimizer_params(50, {'short_period': 20.0, 'long_period': 60.0, 'threshold': 0.05, 'stop_loss': 0.05})
optimizer2 = generate_optimizer_params(50, {'short_period': 15.0, 'long_period': 50.0, 'threshold': 0.03, 'stop_loss': 0.08})
optimizer3 = generate_optimizer_params(50, {'short_period': 25.0, 'long_period': 70.0, 'threshold': 0.07, 'stop_loss': 0.03})

# 混合所有参数
all_params = optimizer1 + optimizer2 + optimizer3
random.shuffle(all_params)

cache = BacktestCache()
engine = MockBacktestEngine(use_cache=True, cache=cache)
start = time.time()
for p in all_params:
    engine.run_backtest('test', p)
t_multi = time.time() - start
s_multi = cache.get_stats()
cnt_multi = engine.call_count

print(f'  3个优化器共产生 {len(all_params)} 组参数')
print(f'  实际调用回测次数: {cnt_multi}/{len(all_params)}')
print(f'  缓存命中率: {s_multi.hit_rate*100:.1f}%')
print(f'  总耗时: {t_multi:.2f}s')

engine_nocache = MockBacktestEngine(use_cache=False, cache=BacktestCache())
start = time.time()
for p in all_params:
    engine_nocache.run_backtest('test', p)
t_multi_nocache = time.time() - start
print(f'  无缓存耗时: {t_multi_nocache:.2f}s')
print(f'  实际加速比: {t_multi_nocache/t_multi:.2f}x')

print(f'\n{"=" * 60}')
print('关键发现')
print('=' * 60)
print('  1. 理想重复场景: 加速比极高 (缓存100%命中)')
print('  2. 真实优化场景: 缓存命中率很低 (连续变化参数几乎不重复)')
print('  3. 多优化器并行: 搜索空间重叠度决定缓存价值')
print('  结论: 仅靠"精确缓存"无法达到韬定律的"时间缩微"目标')
print('  需要: 相似参数复用 + 增量计算 + 搜索空间折叠')
