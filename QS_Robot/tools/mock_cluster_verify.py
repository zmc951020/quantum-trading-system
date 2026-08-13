"""模拟集群选股闭环验证脚本
构造190只模拟股票数据，运行 u=0.0/n=5 集群选股，验证闭环链路
"""
import os, sys, json, random, logging, shutil, time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "core"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("mock_test")

CACHE_DIR = os.path.join(PROJECT_ROOT, "data", "bus_cache")
MOCK_DIR = os.path.join(CACHE_DIR, "_mock_190")
MOCK_SYMBOL_PREFIX = "MOCK"


def _make_bars(n: int, seed: int, scenario: str) -> dict:
    """生成模拟K线数据。对 hot3 场景精确构造低位+3/3热启动条件。"""
    random.seed(seed)
    bars = {"date": [], "open": [], "high": [], "low": [], "close": [], "volume": []}

    if scenario == "hot3":
        # 精确构造：先高位下跌形成低位，再热启动反弹
        # 阶段1 (0 ~ n-80): 高位震荡
        # 阶段2 (n-80 ~ n-40): 下跌形成低位
        # 阶段3 (n-40 ~ n-1): 底部反弹，最后20天满足3/3热启动
        for i in range(n):
            if i < n - 80:
                price = random.uniform(25, 30)
            elif i < n - 40:
                price = 30 - (i - (n - 80)) * 1.2
                price = max(price, 8 + random.uniform(-0.5, 0.5))
            else:
                price = 8 + (i - (n - 40)) * 0.15
                price += random.uniform(-0.2, 0.3)

            c = price
            o = c * random.uniform(0.99, 1.01)
            h = max(o, c) * random.uniform(1.0, 1.02)
            l = min(o, c) * random.uniform(0.98, 1.0)

            if i >= n - 5:
                v = random.randint(3000000, 8000000)
            else:
                v = random.randint(500000, 1500000)

            bars["date"].append(f"2026-{1 + (i // 21):02d}-{1 + (i % 21):02d}")
            bars["open"].append(round(o, 2))
            bars["high"].append(round(h, 2))
            bars["low"].append(round(l, 2))
            bars["close"].append(round(c, 2))
            bars["volume"].append(float(v))

    elif scenario == "hot2":
        # 2/3条件：放量+止跌，但站不上MA60
        for i in range(n):
            progress = i / n
            price = 20 - progress * 10 + random.uniform(-0.5, 0.5)
            price = max(5, price)
            c = price
            o = c * random.uniform(0.99, 1.01)
            h = max(o, c) * 1.01
            l = min(o, c) * 0.99
            v = random.randint(3000000, 8000000) if i >= n - 5 else random.randint(500000, 1500000)
            bars["date"].append(f"2026-{1 + (i // 21):02d}-{1 + (i % 21):02d}")
            bars["open"].append(round(o, 2))
            bars["high"].append(round(h, 2))
            bars["low"].append(round(l, 2))
            bars["close"].append(round(c, 2))
            bars["volume"].append(float(v))

    elif scenario == "hot1":
        # 1/3条件：只有止跌
        for i in range(n):
            progress = i / n
            price = 20 - progress * 10 + random.uniform(-0.3, 0.3)
            price = max(5, price)
            c = price
            o = c * random.uniform(0.99, 1.01)
            h = max(o, c) * 1.01
            l = min(o, c) * 0.99
            v = random.randint(300000, 1200000)
            bars["date"].append(f"2026-{1 + (i // 21):02d}-{1 + (i % 21):02d}")
            bars["open"].append(round(o, 2))
            bars["high"].append(round(h, 2))
            bars["low"].append(round(l, 2))
            bars["close"].append(round(c, 2))
            bars["volume"].append(float(v))

    elif scenario == "hot0":
        # 0/3条件：持续下跌，无热启动
        for i in range(n):
            price = 25 - i * 0.15 + random.uniform(-0.5, 0.5)
            price = max(3, price)
            c = price
            o = c * random.uniform(0.99, 1.01)
            h = max(o, c) * 1.01
            l = min(o, c) * 0.99
            v = random.randint(300000, 1200000)
            bars["date"].append(f"2026-{1 + (i // 21):02d}-{1 + (i % 21):02d}")
            bars["open"].append(round(o, 2))
            bars["high"].append(round(h, 2))
            bars["low"].append(round(l, 2))
            bars["close"].append(round(c, 2))
            bars["volume"].append(float(v))

    else:  # low0: 不在低位，价格持续高位
        for i in range(n):
            price = random.uniform(50, 100)
            c = price
            o = c * random.uniform(0.99, 1.01)
            h = max(o, c) * 1.01
            l = min(o, c) * 0.99
            v = random.randint(500000, 2000000)
            bars["date"].append(f"2026-{1 + (i // 21):02d}-{1 + (i % 21):02d}")
            bars["open"].append(round(o, 2))
            bars["high"].append(round(h, 2))
            bars["low"].append(round(l, 2))
            bars["close"].append(round(c, 2))
            bars["volume"].append(float(v))

    return bars


def generate_mock_files():
    """生成190个模拟股票数据文件"""
    os.makedirs(MOCK_DIR, exist_ok=True)

    scenarios = (
        ["hot3"] * 10 +     # 10只: 3/3热启动 → 预期通过
        ["hot2"] * 30 +     # 30只: 2/3热启动 → u=0.0时淘汰
        ["hot1"] * 30 +     # 30只: 1/3热启动 → 淘汰
        ["hot0"] * 30 +     # 30只: 0/3热启动 → 淘汰
        ["low0"] * 90       # 90只: 不在低位 → 淘汰
    )

    for i, scenario in enumerate(scenarios):
        symbol = f"{MOCK_SYMBOL_PREFIX}{i:04d}"
        bars = _make_bars(n=250, seed=i * 7 + 42, scenario=scenario)

        data = {
            "data": {
                "dates": bars["date"],
                "opens": bars["open"],
                "highs": bars["high"],
                "lows": bars["low"],
                "closes": bars["close"],
                "volumes": bars["volume"],
                "symbol": symbol,
                "count": 250,
                "_mock": True,
                "_scenario": scenario,
            },
            "_expire_at": time.time() + 86400,
            "_created_at": time.time(),
        }

        fpath = os.path.join(MOCK_DIR, f"{symbol}.json")
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

    logger.info("已生成 %d 个模拟数据文件 (hot3×10, hot2×30, hot1×30, hot0×30, low0×90)",
                len(scenarios))
    return [f"{MOCK_SYMBOL_PREFIX}{i:04d}" for i in range(len(scenarios))]


def inject_mock_loader(codes: list[str]):
    """将模拟数据注入到 bus_cache 中"""
    injected = 0
    for fname in os.listdir(MOCK_DIR):
        if not fname.endswith(".json"):
            continue
        src = os.path.join(MOCK_DIR, fname)
        dst = os.path.join(CACHE_DIR, fname)
        shutil.copy2(src, dst)
        injected += 1
    logger.info("已注入 %d 个模拟文件到 bus_cache", injected)
    return injected


def cleanup_mock_files():
    """清理模拟数据"""
    count = 0
    if os.path.exists(MOCK_DIR):
        for fname in os.listdir(MOCK_DIR):
            if not fname.endswith(".json"):
                continue
            fp = os.path.join(CACHE_DIR, fname)
            if os.path.exists(fp):
                os.remove(fp)
                count += 1
        shutil.rmtree(MOCK_DIR, ignore_errors=True)
    logger.info("已清理 %d 个模拟文件", count)


def run_verification():
    """运行集群选股闭环验证"""
    print()
    print("=" * 70)
    print("  模拟集群选股闭环验证: u=0.0 (最严格), n=5")
    print("=" * 70)
    print()

    # 1. 生成模拟数据
    codes = generate_mock_files()
    inject_mock_loader(codes)

    try:
        # 2. 初始化集群选股器
        from core.cluster_stock_selector import ClusterStockSelector

        selector = ClusterStockSelector()
        logger.info("策略加载完成: %d 个策略", len(selector._strategies))

        # 3. 执行扫描
        print()
        print("--- 执行扫描 u=0.0, n=5 ---")
        print()
        result = selector.scan(codes, u=0.0, n=5)

        # 4. 验证结果
        print()
        print("=" * 70)
        print("  验证结果")
        print("=" * 70)
        print(f"  扫描总数: {result.total_scanned}")
        print(f"  通过数:   {result.passed}")
        print(f"  入选数:   {len(result.stocks)}")
        print(f"  平均分:   {result.avg_score}")
        print(f"  耗时:     {result.elapsed_seconds}s")
        print(f"  参数:     {result.params}")
        print()

        # 预期: u=0.0需要3/3热启动, 只有hot3的10只能通过低位筛选
        # 但这10只中有多少能通过32策略信号触发则取决于策略本身
        print("--- 入选股票 ---")
        for i, s in enumerate(result.stocks):
            print(f"  #{i+1} {s.code} 优良度={s.goodness:.4f} "
                  f"低位={s.low_score}/5 热启={s.hot_score}/3 "
                  f"信号={s.signal_count} 策略={s.strategy_names[:3]}")

        # 5. 验证入池闭环
        print()
        print("--- 自动入池验证 ---")
        if result.stocks:
            from core.stock_pool import get_stock_pool_manager, PoolLevel, StockSource

            mgr = get_stock_pool_manager()
            pushed = 0
            for s in result.stocks:
                try:
                    mgr.add_stock(s.code, name=f"模拟{s.code}", level=PoolLevel.CANDIDATE, source=StockSource.THS_IWENCAI)
                    pushed += 1
                except Exception as e:
                    logger.warning("入池失败 %s: %s", s.code, e)

            print(f"  入池成功: {pushed}/{len(result.stocks)}")

        # 6. 总结
        print()
        print("=" * 70)
        print("  闭环验证结论")
        print("=" * 70)
        print(f"  [选股] 190只扫描 → {result.passed}只通过 → {len(result.stocks)}只入选")
        print(f"  [入池] {pushed if result.stocks else 0}只自动入候选池")
        print(f"  [链路] 选股→筛选→排名→入池 闭环: {'✅ 生效' if result.stocks else '⚠️ 无入选'}")

        if len(result.stocks) == 0:
            print()
            print("  ⚠️ 无股票入选。可能原因:")
            print("     1. 模拟数据未触发策略信号 (32个策略对模拟数据无buy信号)")
            print("     2. 低位筛选太严格 (模拟数据价格走势不符合低位条件)")
            print("     3. 热启动条件太严格 (u=0.0需要3/3条件全部满足)")
            print()
            print("  💡 建议: 尝试 u=0.5 放宽条件重新测试")

        return result

    finally:
        cleanup_mock_files()


if __name__ == "__main__":
    run_verification()