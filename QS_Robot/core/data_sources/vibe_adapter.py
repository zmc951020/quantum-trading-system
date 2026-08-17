#!/usr/bin/env python3
"""
Vibe-Trading 港大智能体数据源适配器

接入 vibe-trading-ai 的 backtest.loaders 模块:
  - AKShare (A股/港股/期货/宏观经济)
  - tushare (A股/指数/基金)
  - yfinance (美股/港股/全球)
  - CCXT (加密货币)
  - Futu (港股/美股)
  - MT5 (外汇/期货)

降级策略: vibe-trading-ai 不可用时，回退到本地 data_fetcher
"""

from typing import Dict, List, Optional, Any
import logging

from core.data_sources.base_adapter import BaseDataSourceAdapter

logger = logging.getLogger(__name__)

# 检测 Vibe-Trading 安装状态
VIBE_AVAILABLE = False
VIBE_LOADERS = {}

def _check_vibe():
    global VIBE_AVAILABLE, VIBE_LOADERS
    try:
        import backtest
        VIBE_AVAILABLE = True
        try:
            from backtest.loaders.akshare_loader import DataLoader
            VIBE_LOADERS['akshare'] = DataLoader
        except ImportError: pass
        try:
            from backtest.loaders.tushare import TushareDataLoader
            VIBE_LOADERS['tushare'] = TushareDataLoader
        except ImportError: pass
        try:
            from backtest.loaders.yfinance_loader import YFinanceLoader
            VIBE_LOADERS['yfinance'] = YFinanceLoader
        except ImportError: pass
        try:
            from backtest.loaders.ccxt_loader import CCXTLoader
            VIBE_LOADERS['ccxt'] = CCXTLoader
        except ImportError: pass
        try:
            from backtest.loaders.futu import FutuLoader
            VIBE_LOADERS['futu'] = FutuLoader
        except ImportError: pass
        try:
            from backtest.loaders.mootdx_loader import MootdxLoader
            VIBE_LOADERS['mootdx'] = MootdxLoader
        except ImportError: pass
        active = list(VIBE_LOADERS.keys())
        logger.info(f"[VibeAdapter] 已加载 {len(active)} 个数据源: {active}")
    except ImportError:
        logger.warning("[VibeAdapter] Vibe-Trading 未安装，使用本地数据源")
    except Exception as e:
        logger.warning(f"[VibeAdapter] 初始化异常: {e}")

_check_vibe()


class VibeAdapter(BaseDataSourceAdapter):
    """Vibe-Trading 智能体数据源适配器"""

    name = "vibe"

    def _init(self):
        self._available = VIBE_AVAILABLE
        self._loader_instances = {}
        if self._available:
            self._init_loaders()
        else:
            logger.info("[VibeAdapter] 降级模式：使用本地数据源")
            self._available = True  # 允许作为降级源

    def _init_loaders(self):
        """初始化各数据源加载器"""
        for name, loader_cls in VIBE_LOADERS.items():
            if loader_cls:
                try:
                    self._loader_instances[name] = loader_cls()
                    logger.debug(f"[VibeAdapter] {name} 加载器已初始化")
                except Exception as e:
                    logger.warning(f"[VibeAdapter] {name} 加载失败: {e}")

    def _get_loader(self, name: str = 'akshare'):
        """获取加载器实例"""
        return self._loader_instances.get(name)

    # --------------------------------------------------------
    # K线数据
    # --------------------------------------------------------

    def get_kline(self, symbol: str, period: str = "daily", days: int = 500) -> Optional[Dict[str, Any]]:
        if VIBE_AVAILABLE:
            for loader_name in ['akshare', 'tushare', 'yfinance']:
                loader = self._get_loader(loader_name)
                if not loader:
                    continue
                try:
                    from datetime import datetime, timedelta
                    end_date = datetime.now().strftime("%Y-%m-%d")
                    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
                    result = loader.fetch([symbol], start_date, end_date, interval="1D")
                    if result and symbol in result:
                        df = result[symbol]
                        if df is not None and not df.empty:
                            return {
                                'success': True, 'source': f'vibe-{loader_name}',
                                'data': df,
                                'symbol': symbol, 'period': period,
                            }
                except Exception as e:
                    logger.debug(f"[VibeAdapter] {loader_name} K线失败: {e}")

        # 降级到本地数据源
        return self._fallback_kline(symbol, period, days)

    def _fallback_kline(self, symbol: str, period: str, days: int) -> Optional[Dict]:
        try:
            from core.data_fetcher import get_data_fetcher
            return get_data_fetcher().get_kline(symbol, period=period, days=days)
        except Exception:
            return None

    # --------------------------------------------------------
    # 财务数据
    # --------------------------------------------------------

    def get_financial(self, symbol: str) -> Optional[Dict[str, Any]]:
        if VIBE_AVAILABLE:
            try:
                loader = self._get_loader('akshare') or self._get_loader('tushare')
                if loader:
                    df = loader.load_financials(symbol)
                    if df is not None and not df.empty:
                        return {'success': True, 'source': 'vibe', 'data': df}
            except Exception as e:
                logger.debug(f"[VibeAdapter] 财务数据失败: {e}")

        try:
            from core.data_fetcher import get_data_fetcher
            return get_data_fetcher().get_financials(symbol)
        except Exception:
            return None

    # --------------------------------------------------------
    # 实时行情
    # --------------------------------------------------------

    def get_realtime(self, symbol: str) -> Optional[Dict[str, Any]]:
        if VIBE_AVAILABLE:
            try:
                loader = self._get_loader('akshare')
                if loader:
                    data = loader.load_realtime(symbol)
                    if data is not None:
                        return {'success': True, 'source': 'vibe-akshare', 'data': data}
            except Exception as e:
                logger.debug(f"[VibeAdapter] 实时行情失败: {e}")

        try:
            from core.data_fetcher import get_data_fetcher
            return get_data_fetcher().get_realtime(symbol)
        except Exception:
            return None

    # --------------------------------------------------------
    # 股票列表
    # --------------------------------------------------------

    def get_stock_list(self, market: str = "A股") -> List[Dict]:
        if VIBE_AVAILABLE:
            try:
                loader = self._get_loader('akshare')
                if loader:
                    df = loader.load_stock_list(market)
                    if df is not None and not df.empty:
                        return df.to_dict('records')
            except Exception as e:
                logger.debug(f"[VibeAdapter] 股票列表失败: {e}")

        try:
            from core.data_fetcher import get_data_fetcher
            return get_data_fetcher().get_stock_list(market) or []
        except Exception:
            return []

    # --------------------------------------------------------
    # 状态查询
    # --------------------------------------------------------

    def get_status(self) -> Dict:
        return {
            'name': self.name,
            'vibe_available': VIBE_AVAILABLE,
            'loaders': list(self._loader_instances.keys()),
            'priority': self.priority,
        }