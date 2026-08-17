"""Vibe-Trading 77个Skill模块注册表"""
from typing import Dict, List, Optional, Any

VIBE_MODULES: Dict[str, Dict[str, str]] = {
    # ============================================================
    # strategy (17) - 策略分析模块
    # ============================================================
    "elliott-wave": {
        "module": "core.vibe_elliott_wave", "class": "SignalEngine",
        "desc": "艾略特波浪理论", "category": "strategy",
    },
    "harmonic": {
        "module": "core.vibe_harmonic", "class": "SignalEngine",
        "desc": "谐波形态", "category": "strategy",
    },
    "ichimoku": {
        "module": "core.vibe_ichimoku", "class": "SignalEngine",
        "desc": "一目均衡表", "category": "strategy",
    },
    "candlestick": {
        "module": "core.vibe_candlestick", "class": "SignalEngine",
        "desc": "K线形态识别", "category": "strategy",
    },
    "smc": {
        "module": "core.vibe_smc", "class": "SignalEngine",
        "desc": "聪明钱概念", "category": "strategy",
    },
    "volatility": {
        "module": "core.vibe_volatility", "class": "SignalEngine",
        "desc": "波动率策略", "category": "strategy",
    },
    "pair-trading": {
        "module": "core.vibe_pair_trading", "class": "SignalEngine",
        "desc": "配对交易", "category": "strategy",
    },
    "seasonal": {
        "module": "core.vibe_seasonal", "class": "SignalEngine",
        "desc": "季节性策略", "category": "strategy",
    },
    "event-driven": {
        "module": "core.vibe_event_driven", "class": "SignalEngine",
        "desc": "事件驱动", "category": "strategy",
    },
    "chanlun": {
        "module": "core.vibe_chanlun", "class": "SignalEngine",
        "desc": "缠论", "category": "strategy",
    },
    "execution-model": {
        "module": "core.vibe_execution_model", "class": "SignalEngine",
        "desc": "执行模型", "category": "strategy",
    },
    "ml-strategy": {
        "module": "core.vibe_ml_strategy", "class": "SignalEngine",
        "desc": "机器学习策略", "category": "strategy",
    },
    "multi-factor": {
        "module": "core.vibe_multi_factor", "class": "SignalEngine",
        "desc": "多因子选股", "category": "strategy",
    },
    "cross-market-strategy": {
        "module": "core.vibe_cross_market", "class": "SignalEngine",
        "desc": "跨市场策略", "category": "strategy",
    },
    "minute-analysis": {
        "module": "core.vibe_minute_analysis", "class": "SignalEngine",
        "desc": "分钟级分析", "category": "strategy",
    },
    "strategy-generate": {
        "module": "core.vibe_strategy_generate", "class": "SignalEngine",
        "desc": "策略生成", "category": "strategy",
    },
    "technical-basic": {
        "module": "core.technical_analysis", "class": "TechnicalAnalysisEngine",
        "desc": "基础技术指标", "category": "strategy",
    },

    # ============================================================
    # fundamental (8) - 基本面分析模块
    # ============================================================
    "financial-statement": {
        "module": "core.vibe_financial_statement", "class": "SignalEngine",
        "desc": "财务报表分析", "category": "fundamental",
    },
    "valuation-model": {
        "module": "core.vibe_valuation_model", "class": "SignalEngine",
        "desc": "估值模型", "category": "fundamental",
    },
    "earnings-forecast": {
        "module": "core.vibe_earnings_forecast", "class": "SignalEngine",
        "desc": "盈利预测", "category": "fundamental",
    },
    "earnings-revision": {
        "module": "core.vibe_earnings_revision", "class": "SignalEngine",
        "desc": "盈利修正", "category": "fundamental",
    },
    "dividend-analysis": {
        "module": "core.vibe_dividend_analysis", "class": "SignalEngine",
        "desc": "股息分析", "category": "fundamental",
    },
    "fundamental-filter": {
        "module": "core.vibe_fundamental_filter", "class": "SignalEngine",
        "desc": "基本面筛选", "category": "fundamental",
    },
    "credit-analysis": {
        "module": "core.vibe_credit_analysis", "class": "SignalEngine",
        "desc": "信用分析", "category": "fundamental",
    },
    "corporate-events": {
        "module": "core.vibe_corporate_events", "class": "SignalEngine",
        "desc": "公司事件分析", "category": "fundamental",
    },
    "ashare-st-filter": {
        "module": "core.vibe_ashare_st_filter", "class": "SignalEngine",
        "desc": "A股ST风险预警", "category": "fundamental",
    },

    # ============================================================
    # macro_market (10) - 宏观市场分析模块
    # ============================================================
    "global-macro": {
        "module": "core.vibe_global_macro", "class": "SignalEngine",
        "desc": "全球宏观", "category": "macro_market",
    },
    "macro-analysis": {
        "module": "core.vibe_macro_analysis", "class": "SignalEngine",
        "desc": "宏观经济分析", "category": "macro_market",
    },
    "geopolitical-risk": {
        "module": "core.vibe_geopolitical_risk", "class": "SignalEngine",
        "desc": "地缘政治风险", "category": "macro_market",
    },
    "commodity-analysis": {
        "module": "core.vibe_commodity_analysis", "class": "SignalEngine",
        "desc": "大宗商品分析", "category": "macro_market",
    },
    "market-microstructure": {
        "module": "core.vibe_market_microstructure", "class": "SignalEngine",
        "desc": "市场微观结构", "category": "macro_market",
    },
    "sector-rotation": {
        "module": "core.vibe_sector_rotation", "class": "SignalEngine",
        "desc": "板块轮动", "category": "macro_market",
    },
    "behavioral-finance": {
        "module": "core.vibe_behavioral_finance", "class": "SignalEngine",
        "desc": "行为金融", "category": "macro_market",
    },
    "sentiment-analysis": {
        "module": "core.vibe_sentiment_analysis", "class": "SignalEngine",
        "desc": "市场情绪分析", "category": "macro_market",
    },
    "social-media": {
        "module": "core.vibe_social_media", "class": "SignalEngine",
        "desc": "社交媒体舆情", "category": "macro_market",
    },
    "correlation-analysis": {
        "module": "core.vibe_correlation_analysis", "class": "SignalEngine",
        "desc": "相关性分析", "category": "macro_market",
    },

    # ============================================================
    # risk (6) - 风险管理模块
    # ============================================================
    "monte-carlo": {
        "module": "core.vibe_monte_carlo", "class": "MonteCarloValidator",
        "desc": "蒙特卡洛模拟", "category": "risk",
    },
    "hedging-strategy": {
        "module": "core.vibe_hedging_strategy", "class": "SignalEngine",
        "desc": "对冲策略", "category": "risk",
    },
    "asset-allocation": {
        "module": "core.vibe_asset_allocation", "class": "SignalEngine",
        "desc": "资产配置", "category": "risk",
    },
    "performance-attribution": {
        "module": "core.vibe_performance_attribution", "class": "SignalEngine",
        "desc": "绩效归因", "category": "risk",
    },
    "backtest-diagnose": {
        "module": "core.vibe_backtest_diagnose", "class": "SignalEngine",
        "desc": "回测诊断", "category": "risk",
    },
    "shadow-account": {
        "module": "core.vibe_shadow_account", "class": "ShadowAccountAnalyzer",
        "desc": "影子账户", "category": "risk",
    },

    # ============================================================
    # crypto (7) - 加密货币模块
    # ============================================================
    "onchain-analysis": {
        "module": "core.vibe_onchain_analysis", "class": "SignalEngine",
        "desc": "链上分析", "category": "crypto",
    },
    "defi-yield": {
        "module": "core.vibe_defi_yield", "class": "SignalEngine",
        "desc": "DeFi收益分析", "category": "crypto",
    },
    "liquidation-heatmap": {
        "module": "core.vibe_liquidation_heatmap", "class": "SignalEngine",
        "desc": "清算热力图", "category": "crypto",
    },
    "crypto-derivatives": {
        "module": "core.vibe_crypto_derivatives", "class": "SignalEngine",
        "desc": "加密货币衍生品", "category": "crypto",
    },
    "perp-funding-basis": {
        "module": "core.vibe_perp_funding_basis", "class": "SignalEngine",
        "desc": "永续合约资金费率", "category": "crypto",
    },
    "stablecoin-flow": {
        "module": "core.vibe_stablecoin_flow", "class": "SignalEngine",
        "desc": "稳定币流向", "category": "crypto",
    },
    "token-unlock": {
        "module": "core.vibe_token_unlock", "class": "SignalEngine",
        "desc": "代币解锁分析", "category": "crypto",
    },

    # ============================================================
    # options (5) - 期权衍生品模块
    # ============================================================
    "options-strategy": {
        "module": "core.vibe_options_strategy", "class": "SignalEngine",
        "desc": "期权策略", "category": "options",
    },
    "options-advanced": {
        "module": "core.vibe_options_advanced", "class": "SignalEngine",
        "desc": "高级期权分析", "category": "options",
    },
    "options-payoff": {
        "module": "core.vibe_options_payoff", "class": "SignalEngine",
        "desc": "期权收益结构", "category": "options",
    },
    "options-skills": {
        "module": "core.vibe_options_skills", "class": "OptionsAnalyzer",
        "desc": "期权技能集", "category": "options",
    },
    "convertible-bond": {
        "module": "core.vibe_convertible_bond", "class": "SignalEngine",
        "desc": "可转债分析", "category": "options",
    },

    # ============================================================
    # data_sources (8) - 数据源模块
    # ============================================================
    "yfinance": {
        "module": "core.vibe_yfinance", "class": "YFinanceLoader",
        "desc": "YFinance数据", "category": "data_sources",
    },
    "ccxt": {
        "module": "core.vibe_ccxt", "class": "CCXTDataLoader",
        "desc": "CCXT数据", "category": "data_sources",
    },
    "mootdx": {
        "module": "core.vibe_mootdx", "class": "TDXDataLoader",
        "desc": "通达信数据接口", "category": "data_sources",
    },
    "edgar-sec": {
        "module": "core.vibe_edgar_sec", "class": "SignalEngine",
        "desc": "SEC EDGAR数据", "category": "data_sources",
    },
    "data-routing": {
        "module": "core.vibe_data_routing", "class": "DataRouter",
        "desc": "数据路由", "category": "data_sources",
    },
    "web-reader": {
        "module": "core.vibe_web_reader", "class": "WebReader",
        "desc": "网页内容读取", "category": "data_sources",
    },
    "doc-reader": {
        "module": "core.vibe_doc_reader", "class": "DocReader",
        "desc": "文档读取", "category": "data_sources",
    },
    "pine-script": {
        "module": "core.vibe_pine_script", "class": "SignalEngine",
        "desc": "Pine Script转换", "category": "data_sources",
    },

    # ============================================================
    # cross_border (4) - 跨境投资模块
    # ============================================================
    "adr-hshare": {
        "module": "core.vibe_adr_hshare", "class": "SignalEngine",
        "desc": "ADR/H股联动", "category": "cross_border",
    },
    "hk-connect-flow": {
        "module": "core.vibe_hk_connect_flow", "class": "SignalEngine",
        "desc": "港股通资金流向", "category": "cross_border",
    },
    "us-etf-flow": {
        "module": "core.vibe_us_etf_flow", "class": "SignalEngine",
        "desc": "美股ETF资金流", "category": "cross_border",
    },
    "etf-analysis": {
        "module": "core.vibe_etf_analysis", "class": "SignalEngine",
        "desc": "ETF分析", "category": "cross_border",
    },
    "fund-analysis": {
        "module": "core.vibe_fund_analysis", "class": "SignalEngine",
        "desc": "基金分析", "category": "cross_border",
    },

    # ============================================================
    # alpha (3) - 因子研究模块
    # ============================================================
    "alpha-factors": {
        "module": "core.vibe_alpha_factors", "class": "AlphaFactorEngine",
        "desc": "Alpha因子库", "category": "alpha",
    },
    "alpha-zoo": {
        "module": "core.vibe_alpha_zoo", "class": "AlphaZoo",
        "desc": "Alpha因子库", "category": "alpha",
    },
    "factor-research": {
        "module": "core.vibe_factor_research", "class": "SignalEngine",
        "desc": "因子研究", "category": "alpha",
    },

    # ============================================================
    # tools (9) - 工具集模块
    # ============================================================
    "quant-statistics": {
        "module": "core.vibe_quant_statistics", "class": "SignalEngine",
        "desc": "量化统计", "category": "tools",
    },
    "report-generate": {
        "module": "core.vibe_report_generate", "class": "ReportGenerator",
        "desc": "报告生成", "category": "tools",
    },
    "trade-journal": {
        "module": "core.vibe_trade_journal", "class": "SignalEngine",
        "desc": "交易日志", "category": "tools",
    },
    "research-goal": {
        "module": "core.vibe_research_goal", "class": "ResearchGoal",
        "desc": "研究方向", "category": "tools",
    },
    "strategy-exporter": {
        "module": "core.vibe_strategy_exporter", "class": "StrategyCodeExporter",
        "desc": "策略导出", "category": "tools",
    },
    "vnpy-export": {
        "module": "core.vibe_vnpy_export", "class": "SignalEngine",
        "desc": "VNPY导出", "category": "tools",
    },
    "regulatory-knowledge": {
        "module": "core.vibe_regulatory_knowledge", "class": "RegulatoryKB",
        "desc": "监管知识库", "category": "tools",
    },
    "29-agents": {
        "module": "core.vibe_29_agents", "class": "VibeAgentAnalyzer",
        "desc": "29智能体投票", "category": "tools",
    },
}


def get_module_info(name: str) -> Optional[Dict[str, str]]:
    """获取指定模块的注册信息"""
    return VIBE_MODULES.get(name)


def get_modules_by_category(category: str) -> Dict[str, Dict[str, str]]:
    """获取指定分类的所有模块"""
    return {k: v for k, v in VIBE_MODULES.items() if v["category"] == category}


def get_all_categories() -> List[str]:
    """获取所有分类名称"""
    seen = []
    for v in VIBE_MODULES.values():
        if v["category"] not in seen:
            seen.append(v["category"])
    return seen


def get_module_count() -> int:
    """获取已注册模块总数"""
    return len(VIBE_MODULES)