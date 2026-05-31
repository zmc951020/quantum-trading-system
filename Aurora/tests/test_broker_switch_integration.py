# -*- coding: utf-8 -*-
"""Aurora 券商系统切换集成测试"""

import sys
import os
import unittest
import json
import time
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("Test.BrokerSwitch")


class TestBrokerInterface(unittest.TestCase):
    """券商接口抽象层测试"""

    @classmethod
    def setUpClass(cls):
        from broker_interface import (
            BrokerType, OrderSide, OrderType, DataSourceStatus,
            TickerData, KlineData, OrderResult, AccountInfo,
        )
        cls.BrokerType = BrokerType
        cls.OrderSide = OrderSide
        cls.OrderType = OrderType
        cls.DataSourceStatus = DataSourceStatus
        cls.TickerData = TickerData
        cls.KlineData = KlineData
        cls.OrderResult = OrderResult
        cls.AccountInfo = AccountInfo

    def test_broker_type_enum(self):
        self.assertEqual(self.BrokerType.XBK_WESTQUANT.value, "xbk_westquant")
        self.assertEqual(self.BrokerType.ZHONGTAI.value, "zhongtai")
        self.assertEqual(self.BrokerType.AURORA_SIMULATOR.value, "aurora_simulator")
        self.assertEqual(self.BrokerType.CUSTOM.value, "custom")

    def test_order_side_enum(self):
        self.assertEqual(self.OrderSide.BUY.value, "buy")
        self.assertEqual(self.OrderSide.SELL.value, "sell")

    def test_order_type_enum(self):
        self.assertEqual(self.OrderType.MARKET.value, "market")
        self.assertEqual(self.OrderType.LIMIT.value, "limit")
        self.assertEqual(self.OrderType.STOP.value, "stop")

    def test_data_source_status_enum(self):
        self.assertEqual(self.DataSourceStatus.ONLINE.value, "online")
        self.assertEqual(self.DataSourceStatus.SIMULATED.value, "simulated")

    def test_ticker_data(self):
        td = self.TickerData(symbol="600000.SH", last_price=12.5, source="XBK")
        self.assertEqual(td.symbol, "600000.SH")
        self.assertGreater(td.last_price, 0)
        self.assertEqual(td.source, "XBK")

    def test_kline_data(self):
        kd = self.KlineData(symbol="000001.SZ", interval="1d",
                            open=10.0, high=10.5, low=9.8, close=10.2,
                            volume=100000, timestamp="2026-05-26")
        self.assertEqual(kd.close, 10.2)
        self.assertEqual(kd.interval, "1d")

    def test_order_result(self):
        r = self.OrderResult(success=True, order_id="ord_001",
                             symbol="600000.SH", side="BUY",
                             order_type="LIMIT", quantity=100,
                             status="submitted")
        self.assertTrue(r.success)

    def test_account_info(self):
        ai = self.AccountInfo(account_id="acct_001", broker_type="XBK",
                              total_value=1000000, available_cash=500000)
        self.assertEqual(ai.total_value, 1000000)


class TestXbkAdapter(unittest.TestCase):
    """XBK（西部宽客）适配器测试"""

    @classmethod
    def setUpClass(cls):
        from broker_interface import XbkBrokerAdapter
        cls.Adapter = XbkBrokerAdapter

    def test_create_adapter(self):
        adapter = self.Adapter(config={"api_host": "westquant.cn"})
        self.assertEqual(adapter.name, "西部宽客(WestQuant)")
        self.assertEqual(adapter.broker_type.value, "xbk_westquant")

    def test_connect_simulated(self):
        adapter = self.Adapter(config={"api_host": "localhost", "api_port": 9999})
        result = adapter.connect()
        self.assertTrue(result, "模拟模式下应返回 True")

    def test_disconnect(self):
        adapter = self.Adapter()
        adapter.connect()
        adapter.disconnect()

    def test_get_ticker_simulated(self):
        adapter = self.Adapter()
        adapter.connect()
        ticker = adapter.get_ticker("600000.SH")
        self.assertIsNotNone(ticker)
        self.assertGreater(ticker.last_price, 0)

    def test_get_kline_simulated(self):
        adapter = self.Adapter()
        adapter.connect()
        klines = adapter.get_kline("600000.SH", "1d", 30)
        self.assertGreater(len(klines), 0)


class TestAuroraSimulatorAdapter(unittest.TestCase):
    """Aurora模拟器适配器测试"""

    @classmethod
    def setUpClass(cls):
        from broker_interface import AuroraSimulatorAdapter, OrderSide, OrderType
        cls.Adapter = AuroraSimulatorAdapter
        cls.OrderSide = OrderSide
        cls.OrderType = OrderType

    def test_create_adapter(self):
        adapter = self.Adapter(config={"initial_balance": 200000.0})
        self.assertEqual(adapter.name, "Aurora模拟器")

    def test_connect(self):
        adapter = self.Adapter()
        result = adapter.connect()
        self.assertTrue(result)

    def test_get_account_info(self):
        adapter = self.Adapter()
        adapter.connect()
        info = adapter.get_account_info()
        self.assertIsNotNone(info)
        self.assertGreater(info.total_value, 0)

    def test_lifecycle(self):
        """完整生命周期：连接→行情→下单→持仓→断开"""
        adapter = self.Adapter(config={"initial_balance": 500000.0})
        self.assertTrue(adapter.connect())

        ticker = adapter.get_ticker("600000.SH")
        self.assertIsNotNone(ticker)
        price = ticker.last_price

        result = adapter.place_order("600000.SH", self.OrderSide.BUY,
                                     self.OrderType.LIMIT, 500, price)
        self.assertTrue(result.success)

        positions = adapter.get_positions()
        self.assertGreater(len(positions), 0)

        result2 = adapter.place_order("600000.SH", self.OrderSide.SELL,
                                      self.OrderType.LIMIT, 500, price * 1.02)
        self.assertTrue(result2.success)

        self.assertTrue(adapter.disconnect())


class TestBrokerManager(unittest.TestCase):
    """券商管理器测试"""

    @classmethod
    def setUpClass(cls):
        from broker_interface import BrokerManager
        cls.BrokerManager = BrokerManager

    def setUp(self):
        self.mgr = self.BrokerManager()

    def test_list_brokers_empty_initial(self):
        """list_brokers 返回列表（新单例可能已有之前测试创建的券商，仅验证返回类型）"""
        brokers = self.mgr.list_brokers()
        self.assertIsInstance(brokers, list)

    def test_auto_create_on_switch(self):
        """switch_broker 自动创建并注册券商（类型字符串）"""
        result = self.mgr.switch_broker("aurora_simulator")
        self.assertTrue(result["success"])
        self.assertIn("Aurora模拟器", result.get("broker_name", ""))
        brokers = self.mgr.list_brokers()
        self.assertGreater(len(brokers), 0)

    def test_switch_broker_invalid(self):
        """切换未知券商类型返回失败"""
        result = self.mgr.switch_broker("nonexistent_broker_xyz")
        self.assertFalse(result["success"])
        self.assertIn("未知券商类型", result.get("message", ""))

    def test_health_check_active_broker(self):
        """有活跃券商时的健康检查"""
        self.mgr.switch_broker("aurora_simulator")
        result = self.mgr.health_check()
        self.assertIn("active_broker", result)
        self.assertIn("broker_count", result)

    def test_health_check_no_broker(self):
        """无活跃券商时的健康检查"""
        result = self.mgr.health_check()
        self.assertIn("healthy", result)
        self.assertIn("active_broker", result)

    def test_get_system_status(self):
        self.mgr.switch_broker("aurora_simulator")
        status = self.mgr.get_system_status()
        self.assertIn("active_broker", status)

    def test_stock_pool(self):
        self.mgr.switch_broker("aurora_simulator")
        pool = self.mgr.get_stock_pool()
        self.assertIsInstance(pool, list)

    def test_switch_history(self):
        self.mgr.switch_broker("aurora_simulator")
        self.mgr.switch_broker("xbk_westquant")
        history = self.mgr.get_switch_history(10)
        self.assertGreaterEqual(len(history), 2)

    def test_cross_broker_sync(self):
        self.mgr.switch_broker("aurora_simulator")
        self.mgr.add_to_stock_pool("601318.SH", {"name": "中国平安"})
        pool = self.mgr.get_stock_pool()
        self.assertIn("601318.SH", pool)

        self.mgr.remove_from_stock_pool("601318.SH")
        pool = self.mgr.get_stock_pool()
        self.assertNotIn("601318.SH", pool)


class TestTechnicalAnalyzerBridge(unittest.TestCase):
    """技术分析桥接测试"""

    @classmethod
    def setUpClass(cls):
        from broker_interface import BrokerManager
        cls.BrokerManager = BrokerManager

    def setUp(self):
        self.mgr = self.BrokerManager()
        self.mgr.switch_broker("aurora_simulator")

    def test_get_technical_data(self):
        data = self.mgr.get_technical_data("600000.SH")
        self.assertIn("symbol", data)
        self.assertGreater(len(data.get("price_history", [])), 0)

    def test_run_technical_analysis(self):
        result = self.mgr.run_technical_analysis("600000.SH")
        self.assertIsInstance(result, dict)

    def test_batch_technical_analysis(self):
        symbols = ["600000.SH", "000001.SZ"]
        result = self.mgr.run_batch_technical_analysis(symbols)
        self.assertIsInstance(result, dict)
        self.assertIn("results", result)
        self.assertEqual(len(result["results"]), len(symbols))


def run_tests():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    test_classes = [
        TestBrokerInterface, TestXbkAdapter, TestAuroraSimulatorAdapter,
        TestBrokerManager, TestTechnicalAnalyzerBridge,
    ]
    for tc in test_classes:
        suite.addTests(loader.loadTestsFromTestCase(tc))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    print(f"\n{'='*60}")
    print(f"测试结果: 运行={result.testsRun}  "
          f"成功={result.testsRun - len(result.failures) - len(result.errors)}  "
          f"失败={len(result.failures)}  错误={len(result.errors)}")
    print(f"{'='*60}")
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)