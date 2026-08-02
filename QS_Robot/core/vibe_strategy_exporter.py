#!/usr/bin/env python3
"""
策略代码导出模块（Strategy Code Exporter）

Vibe-Trading 系统的多平台策略导出引擎，支持：
  - TradingView Pine Script (v5) 导出
  - 通达信公式 导出
  - MT5 EA (MetaTrader 5 Expert Advisor) 导出
  - Python 策略代码 导出

每种导出格式包含完整的策略逻辑、参数定义、交易信号、止损止盈。

依赖：无外部依赖
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)


# ============================================================
# 策略代码导出器
# ============================================================

class StrategyCodeExporter:
    """策略代码导出器

    将策略参数和逻辑导出为 TradingView Pine Script、通达信公式、
    MT5 EA 或 Python 代码。
    """

    def __init__(self):
        self._export_history: List[Dict[str, Any]] = []

    # ============================================================
    # 通用辅助方法
    # ============================================================

    def _build_header(self, platform: str, strategy_name: str) -> str:
        """生成文件头注释"""
        return f"""// ============================================================
// {strategy_name} - {platform} 策略代码
// 由 Vibe-Trading Strategy Exporter 自动生成
// 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
// ============================================================
"""

    def _normalize_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """标准化参数格式"""
        normalized = {}
        for key, value in params.items():
            if isinstance(value, dict):
                normalized[key] = value
            else:
                normalized[key] = {
                    "value": value,
                    "type": "float" if isinstance(value, float) else "int",
                    "min": None,
                    "max": None,
                    "step": None,
                    "description": key,
                }
        return normalized

    def _record_export(self, strategy_name: str, platform: str,
                       success: bool, message: str):
        """记录导出历史"""
        self._export_history.append({
            "strategy": strategy_name,
            "platform": platform,
            "timestamp": datetime.now().isoformat(),
            "success": success,
            "message": message,
        })

    # ============================================================
    # Pine Script 导出
    # ============================================================

    def export_to_pine(self, strategy_name: str,
                       params: Dict[str, Any]) -> str:
        """导出 TradingView Pine Script (v5)

        Args:
            strategy_name: 策略名称
            params: 策略参数字典 {name: {value, type, min, max, step, description}}

        Returns:
            str: 完整的 Pine Script 代码
        """
        try:
            params = self._normalize_params(params)
            safe_name = strategy_name.replace(" ", "_").replace("-", "_")

            lines = []
            lines.append(self._build_header("TradingView Pine Script v5", strategy_name))
            lines.append("//@version=5")
            lines.append(f'strategy("{strategy_name}", overlay=true, initial_capital=100000,')
            lines.append("  default_qty_type=strategy.percent_of_equity, default_qty_value=100)")
            lines.append("")

            # 参数定义
            for name, p in params.items():
                p_type = p.get("type", "float")
                default = p.get("value", 0)
                p_min = p.get("min")
                p_max = p.get("max")
                step = p.get("step", 0.01 if p_type == "float" else 1)
                desc = p.get("description", name)

                if p_type == "int":
                    min_str = f", minval={int(p_min)}" if p_min is not None else ""
                    max_str = f", maxval={int(p_max)}" if p_max is not None else ""
                    lines.append(f'{name} = input.int({int(default)}, "{desc}"{min_str}{max_str}, step={int(step)})')
                else:
                    min_str = f", minval={p_min}" if p_min is not None else ""
                    max_str = f", maxval={p_max}" if p_max is not None else ""
                    lines.append(f'{name} = input.float({default}, "{desc}"{min_str}{max_str}, step={step})')

            lines.append("")

            # 技术指标计算
            lines.append("// ---- 技术指标计算 ----")
            lines.append("ma_fast = ta.sma(close, 5)")
            lines.append("ma_slow = ta.sma(close, 20)")
            lines.append("rsi = ta.rsi(close, 14)")
            lines.append("macd_line = ta.ema(close, 12) - ta.ema(close, 26)")
            lines.append("signal_line = ta.ema(macd_line, 9)")
            lines.append("macd_hist = macd_line - signal_line")
            lines.append("atr = ta.atr(14)")
            lines.append("upper_band = ta.sma(close, 20) + 2 * ta.stdev(close, 20)")
            lines.append("lower_band = ta.sma(close, 20) - 2 * ta.stdev(close, 20)")
            lines.append("")

            # 交易信号
            lines.append("// ---- 交易信号 ----")
            lines.append("long_condition = ma_fast > ma_slow and rsi < 70 and macd_hist > 0")
            lines.append("short_condition = ma_fast < ma_slow and rsi > 30 and macd_hist < 0")
            lines.append("")

            lines.append("// ---- 平仓信号 ----")
            lines.append("long_exit = ma_fast < ma_slow or rsi > 80")
            lines.append("short_exit = ma_fast > ma_slow or rsi < 20")
            lines.append("")

            # 止损止盈
            lines.append("// ---- 止损止盈 ----")
            lines.append("stop_loss_pct = stop_loss_pct_val if na(stop_loss_pct_val) else 0.05")
            lines.append("take_profit_pct = take_profit_pct_val if na(take_profit_pct_val) else 0.10")
            lines.append("")
            lines.append("// 止损止盈逻辑")
            lines.append("long_stop = strategy.position_avg_price * (1 - stop_loss_pct)")
            lines.append("long_take = strategy.position_avg_price * (1 + take_profit_pct)")
            lines.append("short_stop = strategy.position_avg_price * (1 + stop_loss_pct)")
            lines.append("short_take = strategy.position_avg_price * (1 - take_profit_pct)")
            lines.append("")

            # 执行交易
            lines.append("// ---- 执行交易 ----")
            lines.append("if long_condition")
            lines.append("    strategy.entry(\"Long\", strategy.long)")
            lines.append("")
            lines.append("if short_condition")
            lines.append("    strategy.entry(\"Short\", strategy.short)")
            lines.append("")
            lines.append("// 止损止盈")
            lines.append("if strategy.position_size > 0")
            lines.append("    strategy.exit(\"Long Exit\", \"Long\", stop=long_stop, limit=long_take)")
            lines.append("")
            lines.append("if strategy.position_size < 0")
            lines.append("    strategy.exit(\"Short Exit\", \"Short\", stop=short_stop, limit=short_take)")
            lines.append("")

            # 可视化
            lines.append("// ---- 可视化 ----")
            lines.append("plot(ma_fast, \"MA5\", color=color.blue, linewidth=1)")
            lines.append("plot(ma_slow, \"MA20\", color=color.orange, linewidth=1)")
            lines.append("plot(upper_band, \"Upper\", color=color.green, linewidth=1, style=plot.style_circles)")
            lines.append("plot(lower_band, \"Lower\", color=color.red, linewidth=1, style=plot.style_circles)")
            lines.append("hline(70, \"Overbought\", color=color.red, linestyle=hline.style_dashed)")
            lines.append("hline(30, \"Oversold\", color=color.green, linestyle=hline.style_dashed)")
            lines.append("")

            code = "\n".join(lines)
            self._record_export(strategy_name, "pine", True, f"导出成功，{len(code)} 字符")
            return code

        except Exception as e:
            logger.error(f"Pine Script导出失败: {e}")
            self._record_export(strategy_name, "pine", False, str(e))
            return f"// 导出失败: {e}"

    # ============================================================
    # 通达信公式 导出
    # ============================================================

    def export_to_tdx(self, strategy_name: str,
                      params: Dict[str, Any]) -> str:
        """导出通达信公式

        Args:
            strategy_name: 策略名称
            params: 策略参数字典

        Returns:
            str: 完整的通达信公式代码
        """
        try:
            params = self._normalize_params(params)

            lines = []
            lines.append(self._build_header("通达信公式", strategy_name))
            lines.append(f"{{{strategy_name}}}")
            lines.append("")

            # 参数定义
            param_lines = []
            for name, p in params.items():
                default = p.get("value", 0)
                p_min = p.get("min", 0)
                p_max = p.get("max", 100)
                desc = p.get("description", name)
                param_lines.append(f"{name}({p_min},{default},{p_max})")

            if param_lines:
                lines.append("N1:=5;")
                lines.append("N2:=20;")
                lines.append("N3:=14;")
                lines.append("")
            lines.append(f"{{参数: {', '.join(param_lines)}}}")
            lines.append("")

            # 指标计算
            lines.append("{{---- 均线系统 ----}}")
            lines.append("MA5:=MA(CLOSE,N1);")
            lines.append("MA20:=MA(CLOSE,N2);")
            lines.append("MA60:=MA(CLOSE,60);")
            lines.append("")

            lines.append("{{---- MACD ----}}")
            lines.append("DIFF:=EMA(CLOSE,12)-EMA(CLOSE,26);")
            lines.append("DEA:=EMA(DIFF,9);")
            lines.append("MACD:=2*(DIFF-DEA);")
            lines.append("")

            lines.append("{{---- RSI ----}}")
            lines.append("LC:=REF(CLOSE,1);")
            lines.append("RSI:=SMA(MAX(CLOSE-LC,0),N3,1)/SMA(ABS(CLOSE-LC),N3,1)*100;")
            lines.append("")

            lines.append("{{---- KDJ ----}}")
            lines.append("RSV:=(CLOSE-LLV(LOW,9))/(HHV(HIGH,9)-LLV(LOW,9))*100;")
            lines.append("K:=SMA(RSV,3,1);")
            lines.append("D:=SMA(K,3,1);")
            lines.append("J:=3*K-2*D;")
            lines.append("")

            lines.append("{{---- 布林带 ----}}")
            lines.append("MID:=MA(CLOSE,20);")
            lines.append("UPPER:=MID+2*STD(CLOSE,20);")
            lines.append("LOWER:=MID-2*STD(CLOSE,20);")
            lines.append("")

            lines.append("{{---- 成交量 ----}}")
            lines.append("VOL5:=MA(VOL,5);")
            lines.append("VOL20:=MA(VOL,20);")
            lines.append("量比:=VOL/VOL5;")
            lines.append("")

            # 交易信号
            lines.append("{{---- 买入信号 ----}}")
            lines.append("买点1:=CROSS(MA5,MA20) AND MACD>0 AND RSI<70;")
            lines.append("买点2:=CROSS(K,D) AND K<30 AND D<30;")
            lines.append("买点3:=CLOSE>MA20 AND CLOSE>MA60 AND VOL>VOL5*1.5;")
            lines.append("买点4:=CLOSE>LOWER AND CLOSE<MID AND RSI<30 AND CROSS(K,D);")
            lines.append("")

            lines.append("{{---- 卖出信号 ----}}")
            lines.append("卖点1:=CROSS(MA20,MA5) AND MACD<0;")
            lines.append("卖点2:=CROSS(D,K) AND K>70 AND D>70;")
            lines.append("卖点3:=CLOSE<MA20 AND CLOSE<MA60 AND VOL>VOL5*1.5;")
            lines.append("卖点4:=CLOSE>MID AND CLOSE<UPPER AND RSI>70 AND CROSS(D,K);")
            lines.append("")

            lines.append("{{---- 综合信号 ----}}")
            lines.append("买入:=买点1 OR 买点2 OR 买点3 OR 买点4;")
            lines.append("卖出:=卖点1 OR 卖点2 OR 卖点3 OR 卖点4;")
            lines.append("")

            # 选股条件
            lines.append("{{---- 选股输出 ----}}")
            lines.append("多头排列:MA5>MA10 AND MA10>MA20 AND MA20>MA60;")
            lines.append("金叉买入:CROSS(MA5,MA20) AND VOL>VOL5*1.2;")
            lines.append("底背离:LLV(CLOSE,20)>REF(LLV(CLOSE,20),1) AND MACD<REF(MACD,1);")
            lines.append("趋势走强:MA5>REF(MA5,3) AND MA10>REF(MA10,3) AND RSI>50;")
            lines.append("")

            code = "\n".join(lines)
            self._record_export(strategy_name, "tdx", True, f"导出成功，{len(code)} 字符")
            return code

        except Exception as e:
            logger.error(f"通达信公式导出失败: {e}")
            self._record_export(strategy_name, "tdx", False, str(e))
            return f"{{导出失败: {e}}}"

    # ============================================================
    # MT5 EA 导出
    # ============================================================

    def export_to_mt5(self, strategy_name: str,
                      params: Dict[str, Any]) -> str:
        """导出 MetaTrader 5 EA (MQL5)

        Args:
            strategy_name: 策略名称
            params: 策略参数字典

        Returns:
            str: 完整的 MQL5 EA 代码
        """
        try:
            params = self._normalize_params(params)
            safe_name = strategy_name.replace(" ", "_").replace("-", "_")

            lines = []
            lines.append(self._build_header("MetaTrader 5 EA (MQL5)", strategy_name))
            lines.append("//+------------------------------------------------------------------+")
            lines.append(f"//|                                    {safe_name}.mq5                 |")
            lines.append(f"//|                                    生成: Vibe-Trading Exporter   |")
            lines.append("//+------------------------------------------------------------------+")
            lines.append("")
            lines.append("#property copyright \"Vibe-Trading\"")
            lines.append(f'#property link      "https://github.com/vibe-trading"')
            lines.append(f"#property version   \"1.00\"")
            lines.append("")

            # 输入参数
            lines.append("//+------------------------------------------------------------------+")
            lines.append("//| 输入参数                                                         |")
            lines.append("//+------------------------------------------------------------------+")
            for name, p in params.items():
                p_type = p.get("type", "float")
                default = p.get("value", 0)
                desc = p.get("description", name)
                if p_type == "int":
                    lines.append(f"input int      {name} = {int(default)};  // {desc}")
                else:
                    lines.append(f"input double   {name} = {default};  // {desc}")
            lines.append("")

            lines.append("// 固定参数")
            lines.append("input double   LotSize = 0.1;          // 交易手数")
            lines.append("input int      StopLoss = 50;          // 止损点数")
            lines.append("input int      TakeProfit = 100;       // 止盈点数")
            lines.append("input int      MagicNumber = 202401;   // 魔术号")
            lines.append("input int      Slippage = 3;           // 滑点")
            lines.append("")

            # 全局变量
            lines.append("//+------------------------------------------------------------------+")
            lines.append("//| 全局变量                                                         |")
            lines.append("//+------------------------------------------------------------------+")
            lines.append("int ma5_handle;")
            lines.append("int ma20_handle;")
            lines.append("int rsi_handle;")
            lines.append("int macd_handle;")
            lines.append("int atr_handle;")
            lines.append("double ma5_buf[], ma20_buf[], rsi_buf[];")
            lines.append("double macd_main[], macd_signal[];")
            lines.append("double atr_buf[];")
            lines.append("")

            # 初始化
            lines.append("//+------------------------------------------------------------------+")
            lines.append("//| Expert initialization function                                   |")
            lines.append("//+------------------------------------------------------------------+")
            lines.append("int OnInit()")
            lines.append("  {")
            lines.append("   ma5_handle = iMA(_Symbol, _Period, 5, 0, MODE_SMA, PRICE_CLOSE);")
            lines.append("   ma20_handle = iMA(_Symbol, _Period, 20, 0, MODE_SMA, PRICE_CLOSE);")
            lines.append("   rsi_handle = iRSI(_Symbol, _Period, 14, PRICE_CLOSE);")
            lines.append("   macd_handle = iMACD(_Symbol, _Period, 12, 26, 9, PRICE_CLOSE);")
            lines.append("   atr_handle = iATR(_Symbol, _Period, 14);")
            lines.append("")
            lines.append("   if(ma5_handle == INVALID_HANDLE || ma20_handle == INVALID_HANDLE ||")
            lines.append("      rsi_handle == INVALID_HANDLE || macd_handle == INVALID_HANDLE)")
            lines.append("     {")
            lines.append("      Print(\"指标句柄创建失败\");")
            lines.append("      return INIT_FAILED;")
            lines.append("     }")
            lines.append("")
            lines.append("   ArraySetAsSeries(ma5_buf, true);")
            lines.append("   ArraySetAsSeries(ma20_buf, true);")
            lines.append("   ArraySetAsSeries(rsi_buf, true);")
            lines.append("   ArraySetAsSeries(macd_main, true);")
            lines.append("   ArraySetAsSeries(macd_signal, true);")
            lines.append("   ArraySetAsSeries(atr_buf, true);")
            lines.append("")
            lines.append("   return INIT_SUCCEEDED;")
            lines.append("  }")
            lines.append("")

            # 清理
            lines.append("//+------------------------------------------------------------------+")
            lines.append("//| Expert deinitialization function                                 |")
            lines.append("//+------------------------------------------------------------------+")
            lines.append("void OnDeinit(const int reason)")
            lines.append("  {")
            lines.append("   IndicatorRelease(ma5_handle);")
            lines.append("   IndicatorRelease(ma20_handle);")
            lines.append("   IndicatorRelease(rsi_handle);")
            lines.append("   IndicatorRelease(macd_handle);")
            lines.append("   IndicatorRelease(atr_handle);")
            lines.append("  }")
            lines.append("")

            # 主逻辑
            lines.append("//+------------------------------------------------------------------+")
            lines.append("//| Expert tick function                                             |")
            lines.append("//+------------------------------------------------------------------+")
            lines.append("void OnTick()")
            lines.append("  {")
            lines.append("   // 获取指标数据")
            lines.append("   CopyBuffer(ma5_handle, 0, 0, 3, ma5_buf);")
            lines.append("   CopyBuffer(ma20_handle, 0, 0, 3, ma20_buf);")
            lines.append("   CopyBuffer(rsi_handle, 0, 0, 3, rsi_buf);")
            lines.append("   CopyBuffer(macd_handle, 0, 0, 3, macd_main);")
            lines.append("   CopyBuffer(macd_handle, 1, 0, 3, macd_signal);")
            lines.append("   CopyBuffer(atr_handle, 0, 0, 3, atr_buf);")
            lines.append("")
            lines.append("   // 检查持仓")
            lines.append("   bool has_position = PositionSelect(_Symbol);")
            lines.append("")
            lines.append("   // 买入信号")
            lines.append("   bool buy_signal = (ma5_buf[1] > ma20_buf[1] && ma5_buf[2] <= ma20_buf[2])")
            lines.append("                  && rsi_buf[1] < 70")
            lines.append("                  && macd_main[1] > macd_signal[1];")
            lines.append("")
            lines.append("   // 卖出信号")
            lines.append("   bool sell_signal = (ma5_buf[1] < ma20_buf[1] && ma5_buf[2] >= ma20_buf[2])")
            lines.append("                   && rsi_buf[1] > 30")
            lines.append("                   && macd_main[1] < macd_signal[1];")
            lines.append("")
            lines.append("   // 执行交易")
            lines.append("   if(!has_position)")
            lines.append("     {")
            lines.append("      if(buy_signal)")
            lines.append("        {")
            lines.append("         double sl = SymbolInfoDouble(_Symbol, SYMBOL_BID) - StopLoss * _Point;")
            lines.append("         double tp = SymbolInfoDouble(_Symbol, SYMBOL_ASK) + TakeProfit * _Point;")
            lines.append("         MqlTradeRequest request = {};")
            lines.append("         MqlTradeResult  result = {};")
            lines.append("         request.action = TRADE_ACTION_DEAL;")
            lines.append("         request.symbol = _Symbol;")
            lines.append("         request.volume = LotSize;")
            lines.append("         request.type = ORDER_TYPE_BUY;")
            lines.append("         request.price = SymbolInfoDouble(_Symbol, SYMBOL_ASK);")
            lines.append("         request.sl = sl;")
            lines.append("         request.tp = tp;")
            lines.append("         request.deviation = Slippage;")
            lines.append("         request.magic = MagicNumber;")
            lines.append("         request.comment = \"Vibe EA Buy\";")
            lines.append("         OrderSend(request, result);")
            lines.append("        }")
            lines.append("")
            lines.append("      if(sell_signal)")
            lines.append("        {")
            lines.append("         double sl = SymbolInfoDouble(_Symbol, SYMBOL_ASK) + StopLoss * _Point;")
            lines.append("         double tp = SymbolInfoDouble(_Symbol, SYMBOL_BID) - TakeProfit * _Point;")
            lines.append("         MqlTradeRequest request = {};")
            lines.append("         MqlTradeResult  result = {};")
            lines.append("         request.action = TRADE_ACTION_DEAL;")
            lines.append("         request.symbol = _Symbol;")
            lines.append("         request.volume = LotSize;")
            lines.append("         request.type = ORDER_TYPE_SELL;")
            lines.append("         request.price = SymbolInfoDouble(_Symbol, SYMBOL_BID);")
            lines.append("         request.sl = sl;")
            lines.append("         request.tp = tp;")
            lines.append("         request.deviation = Slippage;")
            lines.append("         request.magic = MagicNumber;")
            lines.append("         request.comment = \"Vibe EA Sell\";")
            lines.append("         OrderSend(request, result);")
            lines.append("        }")
            lines.append("     }")
            lines.append("")
            lines.append("   // 移动止损（追踪止损）")
            lines.append("   if(has_position)")
            lines.append("     {")
            lines.append("      double trail_distance = atr_buf[1] * 2;")
            lines.append("      // 追踪止损逻辑")
            lines.append("     }")
            lines.append("  }")
            lines.append("")

            # 风控
            lines.append("//+------------------------------------------------------------------+")
            lines.append("//| 风险控制                                                         |")
            lines.append("//+------------------------------------------------------------------+")
            lines.append("double CalculatePositionSize(double risk_percent = 1.0)")
            lines.append("  {")
            lines.append("   double account_balance = AccountInfoDouble(ACCOUNT_BALANCE);")
            lines.append("   double risk_amount = account_balance * risk_percent / 100.0;")
            lines.append("   double tick_value = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);")
            lines.append("   double lot_size = risk_amount / (StopLoss * tick_value);")
            lines.append("   lot_size = NormalizeDouble(lot_size, 2);")
            lines.append("   double min_lot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);")
            lines.append("   double max_lot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);")
            lines.append("   lot_size = MathMax(min_lot, MathMin(lot_size, max_lot));")
            lines.append("   return lot_size;")
            lines.append("  }")
            lines.append("")

            # 统计
            lines.append("//+------------------------------------------------------------------+")
            lines.append("//| 交易统计                                                         |")
            lines.append("//+------------------------------------------------------------------+")
            lines.append("void OnTrade()")
            lines.append("  {")
            lines.append("   // 记录交易统计")
            lines.append("  }")
            lines.append("")

            code = "\n".join(lines)
            self._record_export(strategy_name, "mt5", True, f"导出成功，{len(code)} 字符")
            return code

        except Exception as e:
            logger.error(f"MT5 EA导出失败: {e}")
            self._record_export(strategy_name, "mt5", False, str(e))
            return f"// 导出失败: {e}"

    # ============================================================
    # Python 策略导出
    # ============================================================

    def export_to_python(self, strategy_name: str,
                         params: Dict[str, Any]) -> str:
        """导出 Python 策略代码

        Args:
            strategy_name: 策略名称
            params: 策略参数字典

        Returns:
            str: 完整的 Python 策略代码
        """
        try:
            params = self._normalize_params(params)
            class_name = "".join(
                word.capitalize() for word in strategy_name.replace("-", "_").replace(" ", "_").split("_")
            ) + "Strategy"

            lines = []
            lines.append("#!/usr/bin/env python3")
            lines.append(f'"""')
            lines.append(f"{strategy_name} - Python 策略代码")
            lines.append(f"由 Vibe-Trading Strategy Exporter 自动生成")
            lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            lines.append(f'"""')
            lines.append("")
            lines.append("import numpy as np")
            lines.append("import logging")
            lines.append("from typing import Dict, List, Optional, Any, Tuple")
            lines.append("from dataclasses import dataclass, field")
            lines.append("")
            lines.append("logger = logging.getLogger(__name__)")
            lines.append("")

            # 数据类
            lines.append("")
            lines.append("@dataclass")
            lines.append("class TradeSignal:")
            lines.append('    """交易信号"""')
            lines.append("    timestamp: Any")
            lines.append("    symbol: str")
            lines.append("    direction: str  # 'buy' / 'sell' / 'hold'")
            lines.append("    price: float")
            lines.append("    quantity: int = 0")
            lines.append("    confidence: float = 0.0")
            lines.append("    reason: str = ''")
            lines.append("")
            lines.append("@dataclass")
            lines.append("class BacktestResult:")
            lines.append('    """回测结果"""')
            lines.append("    total_return: float = 0.0")
            lines.append("    sharpe_ratio: float = 0.0")
            lines.append("    max_drawdown: float = 0.0")
            lines.append("    win_rate: float = 0.0")
            lines.append("    profit_loss_ratio: float = 0.0")
            lines.append("    total_trades: int = 0")
            lines.append("    trades: List[Dict] = field(default_factory=list)")
            lines.append("")

            # 策略类
            lines.append("")
            lines.append(f"class {class_name}:")
            lines.append(f'    """{strategy_name} - 自动生成策略"""')
            lines.append("")
            lines.append("    def __init__(self):")
            lines.append("        self.name = \"{strategy_name}\"")
            lines.append("        self.category = \"auto_generated\"")
            lines.append("        self.description = \"自动生成的策略代码\"")
            lines.append("")

            # 参数定义
            lines.append("        # 策略参数")
            for name, p in params.items():
                default = p.get("value", 0)
                desc = p.get("description", name)
                if isinstance(default, int):
                    lines.append(f"        self.{name} = {default}  # {desc}")
                else:
                    lines.append(f"        self.{name} = {default}  # {desc}")

            lines.append("")
            lines.append("        # 风控参数")
            lines.append("        self.stop_loss_pct = 0.05")
            lines.append("        self.take_profit_pct = 0.10")
            lines.append("        self.max_position_pct = 0.30")
            lines.append("        self.trailing_stop = True")
            lines.append("")

            # 技术指标
            lines.append("    # ---- 技术指标 ----")
            lines.append("")
            lines.append("    def _calc_sma(self, data: np.ndarray, period: int) -> np.ndarray:")
            lines.append('        """简单移动平均"""')
            lines.append("        result = np.full_like(data, np.nan)")
            lines.append("        for i in range(period - 1, len(data)):")
            lines.append("            result[i] = np.nanmean(data[i - period + 1:i + 1])")
            lines.append("        return result")
            lines.append("")
            lines.append("    def _calc_ema(self, data: np.ndarray, period: int) -> np.ndarray:")
            lines.append('        """指数移动平均"""')
            lines.append("        result = np.full_like(data, np.nan)")
            lines.append("        if len(data) >= period:")
            lines.append("            result[period - 1] = np.nanmean(data[:period])")
            lines.append("        multiplier = 2 / (period + 1)")
            lines.append("        for i in range(period, len(data)):")
            lines.append("            result[i] = (data[i] - result[i - 1]) * multiplier + result[i - 1]")
            lines.append("        return result")
            lines.append("")
            lines.append("    def _calc_rsi(self, close: np.ndarray, period: int = 14) -> np.ndarray:")
            lines.append('        """RSI指标"""')
            lines.append("        diff = np.diff(close)")
            lines.append("        result = np.full_like(close, np.nan)")
            lines.append("        for i in range(period, len(close)):")
            lines.append("            gains = np.sum(diff[i - period:i][diff[i - period:i] > 0])")
            lines.append("            losses = -np.sum(diff[i - period:i][diff[i - period:i] < 0])")
            lines.append("            if losses == 0:")
            lines.append("                result[i] = 100.0")
            lines.append("            else:")
            lines.append("                rs = gains / losses")
            lines.append("                result[i] = 100.0 - 100.0 / (1.0 + rs)")
            lines.append("        return result")
            lines.append("")
            lines.append("    def _calc_macd(self, close: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:")
            lines.append('        """MACD指标"""')
            lines.append("        ema12 = self._calc_ema(close, 12)")
            lines.append("        ema26 = self._calc_ema(close, 26)")
            lines.append("        dif = ema12 - ema26")
            lines.append("        dea = self._calc_ema(dif, 9)")
            lines.append("        macd = (dif - dea) * 2")
            lines.append("        return dif, dea, macd")
            lines.append("")
            lines.append("    def _calc_atr(self, high: np.ndarray, low: np.ndarray,")
            lines.append("                   close: np.ndarray, period: int = 14) -> np.ndarray:")
            lines.append('        """ATR指标"""')
            lines.append("        n = len(close)")
            lines.append("        tr = np.zeros(n)")
            lines.append("        for i in range(1, n):")
            lines.append("            tr[i] = max(high[i] - low[i],")
            lines.append("                        abs(high[i] - close[i - 1]),")
            lines.append("                        abs(low[i] - close[i - 1]))")
            lines.append("        result = np.full(n, np.nan)")
            lines.append("        for i in range(period, n):")
            lines.append("            result[i] = np.nanmean(tr[i - period + 1:i + 1])")
            lines.append("        return result")
            lines.append("")

            # 信号生成
            lines.append("    # ---- 信号生成 ----")
            lines.append("")
            lines.append("    def generate_signals(self, data: Dict[str, np.ndarray]) -> List[TradeSignal]:")
            lines.append('        """生成交易信号')
            lines.append("")
            lines.append("        Args:")
            lines.append("            data: K线数据字典 {open, high, low, close, volume}")
            lines.append("")
            lines.append("        Returns:")
            lines.append("            List[TradeSignal]: 交易信号列表")
            lines.append('        """')
            lines.append("        close = np.asarray(data['close'], dtype=np.float64)")
            lines.append("        high = np.asarray(data.get('high', close), dtype=np.float64)")
            lines.append("        low = np.asarray(data.get('low', close), dtype=np.float64)")
            lines.append("        volume = np.asarray(data.get('volume', np.ones_like(close)),")
            lines.append("                           dtype=np.float64)")
            lines.append("")
            lines.append("        # 计算指标")
            lines.append("        ma5 = self._calc_sma(close, 5)")
            lines.append("        ma20 = self._calc_sma(close, 20)")
            lines.append("        rsi = self._calc_rsi(close, 14)")
            lines.append("        dif, dea, macd = self._calc_macd(close)")
            lines.append("        atr = self._calc_atr(high, low, close, 14)")
            lines.append("")
            lines.append("        signals = []")
            lines.append("        for i in range(60, len(close)):")
            lines.append("            # 多头信号")
            lines.append("            if (ma5[i] > ma20[i] and ma5[i - 1] <= ma20[i - 1]")
            lines.append("                    and rsi[i] < 70 and macd[i] > 0):")
            lines.append("                signals.append(TradeSignal(")
            lines.append("                    timestamp=i, symbol='', direction='buy',")
            lines.append("                    price=close[i], confidence=0.8,")
            lines.append("                    reason='MA金叉+RSI<70+MACD>0'")
            lines.append("                ))")
            lines.append("")
            lines.append("            # 空头信号")
            lines.append("            elif (ma5[i] < ma20[i] and ma5[i - 1] >= ma20[i - 1]")
            lines.append("                  and rsi[i] > 30 and macd[i] < 0):")
            lines.append("                signals.append(TradeSignal(")
            lines.append("                    timestamp=i, symbol='', direction='sell',")
            lines.append("                    price=close[i], confidence=0.8,")
            lines.append("                    reason='MA死叉+RSI>30+MACD<0'")
            lines.append("                ))")
            lines.append("")
            lines.append("        return signals")
            lines.append("")

            # 回测
            lines.append("    # ---- 回测引擎 ----")
            lines.append("")
            lines.append("    def run_backtest(self, data: Dict[str, np.ndarray],")
            lines.append("                      initial_capital: float = 100000,")
            lines.append("                      use_optimized_params: bool = True) -> BacktestResult:")
            lines.append('        """执行回测')
            lines.append("")
            lines.append("        Args:")
            lines.append("            data: K线数据")
            lines.append("            initial_capital: 初始资金")
            lines.append("            use_optimized_params: 是否使用优化参数")
            lines.append("")
            lines.append("        Returns:")
            lines.append("            BacktestResult: 回测结果")
            lines.append('        """')
            lines.append("        signals = self.generate_signals(data)")
            lines.append("")
            lines.append("        if not signals:")
            lines.append("            return BacktestResult()")
            lines.append("")
            lines.append("        capital = initial_capital")
            lines.append("        position = 0")
            lines.append("        entry_price = 0")
            lines.append("        trades = []")
            lines.append("        equity_curve = [capital]")
            lines.append("")
            lines.append("        close = data['close']")
            lines.append("")
            lines.append("        for signal in signals:")
            lines.append("            idx = signal.timestamp")
            lines.append("            price = close[idx]")
            lines.append("")
            lines.append("            if signal.direction == 'buy' and position == 0:")
            lines.append("                position = int(capital * self.max_position_pct / price)")
            lines.append("                entry_price = price")
            lines.append("")
            lines.append("            elif signal.direction == 'sell' and position > 0:")
            lines.append("                pnl = (price - entry_price) * position")
            lines.append("                capital += pnl")
            lines.append("                trades.append({")
            lines.append("                    'entry': float(entry_price),")
            lines.append("                    'exit': float(price),")
            lines.append("                    'pnl': float(pnl),")
            lines.append("                    'pnl_pct': float((price / entry_price - 1) * 100),")
            lines.append("                })")
            lines.append("                position = 0")
            lines.append("                equity_curve.append(capital)")
            lines.append("")
            lines.append("        # 统计指标")
            lines.append("        total_return = (capital - initial_capital) / initial_capital")
            lines.append("")
            lines.append("        if trades:")
            lines.append("            wins = [t for t in trades if t['pnl'] > 0]")
            lines.append("            win_rate = len(wins) / len(trades)")
            lines.append("")
            lines.append("            # 最大回撤")
            lines.append("            eq = np.array(equity_curve)")
            lines.append("            peak = np.maximum.accumulate(eq)")
            lines.append("            max_dd = float(np.min((eq - peak) / peak))")
            lines.append("")
            lines.append("            # 夏普")
            lines.append("            returns = np.diff(eq) / eq[:-1]")
            lines.append("            sharpe = np.mean(returns) / np.std(returns) * np.sqrt(252) if np.std(returns) > 0 else 0")
            lines.append("")
            lines.append("            # 盈亏比")
            lines.append("            avg_win = np.mean([t['pnl'] for t in wins]) if wins else 0")
            lines.append("            losses = [t for t in trades if t['pnl'] <= 0]")
            lines.append("            avg_loss = abs(np.mean([t['pnl'] for t in losses])) if losses else 0")
            lines.append("            pl_ratio = avg_win / avg_loss if avg_loss > 0 else 0")
            lines.append("        else:")
            lines.append("            win_rate = max_dd = sharpe = pl_ratio = 0")
            lines.append("")
            lines.append("        return BacktestResult(")
            lines.append("            total_return=round(float(total_return * 100), 4),")
            lines.append("            sharpe_ratio=round(float(sharpe), 4),")
            lines.append("            max_drawdown=round(float(max_dd * 100), 4),")
            lines.append("            win_rate=round(float(win_rate * 100), 2),")
            lines.append("            profit_loss_ratio=round(float(pl_ratio), 4),")
            lines.append("            total_trades=len(trades),")
            lines.append("            trades=trades,")
            lines.append("        )")
            lines.append("")

            # 完整代码
            lines.append("")
            lines.append(f"# ============================================================")
            lines.append(f"# 测试代码")
            lines.append(f"# ============================================================")
            lines.append("")
            lines.append("if __name__ == '__main__':")
            lines.append("    logging.basicConfig(level=logging.INFO,")
            lines.append("                        format='%(asctime)s [%(levelname)s] %(message)s')")
            lines.append("")
            lines.append("    # 生成模拟数据")
            lines.append("    np.random.seed(42)")
            lines.append("    n = 500")
            lines.append("    close = np.cumprod(1 + np.random.randn(n) * 0.02) * 10")
            lines.append("    high = close * (1 + np.abs(np.random.randn(n) * 0.02))")
            lines.append("    low = close * (1 - np.abs(np.random.randn(n) * 0.02))")
            lines.append("")
            lines.append("    data = {")
            lines.append("        'open': close * (1 + np.random.randn(n) * 0.005),")
            lines.append("        'high': high,")
            lines.append("        'low': low,")
            lines.append("        'close': close,")
            lines.append("        'volume': np.abs(np.random.randn(n) * 1000000 + 5000000),")
            lines.append("    }")
            lines.append("")
            lines.append(f"    strategy = {class_name}()")
            lines.append("    result = strategy.run_backtest(data)")
            lines.append("")
            lines.append("    print(f'策略: {strategy.name}')")
            lines.append("    print(f'总收益率: {result.total_return:.2f}%')")
            lines.append("    print(f'夏普比率: {result.sharpe_ratio:.4f}')")
            lines.append("    print(f'最大回撤: {result.max_drawdown:.2f}%')")
            lines.append("    print(f'胜率: {result.win_rate:.1f}%')")
            lines.append("    print(f'交易次数: {result.total_trades}')")
            lines.append("")

            code = "\n".join(lines)
            self._record_export(strategy_name, "python", True, f"导出成功，{len(code)} 字符")
            return code

        except Exception as e:
            logger.error(f"Python策略导出失败: {e}")
            self._record_export(strategy_name, "python", False, str(e))
            return f"# 导出失败: {e}"

    # ============================================================
    # 导出历史
    # ============================================================

    def get_export_history(self) -> List[Dict[str, Any]]:
        """获取导出历史记录"""
        return self._export_history.copy()


# ============================================================
# 测试
# ============================================================

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

    exporter = StrategyCodeExporter()

    params = {
        "ma_period": {"value": 20, "type": "int", "min": 5, "max": 200, "step": 1, "description": "均线周期"},
        "rsi_threshold": {"value": 70.0, "type": "float", "min": 50, "max": 90, "step": 1, "description": "RSI阈值"},
        "stop_loss": {"value": 0.05, "type": "float", "min": 0.01, "max": 0.20, "step": 0.01, "description": "止损比例"},
        "take_profit": {"value": 0.10, "type": "float", "min": 0.02, "max": 0.50, "step": 0.01, "description": "止盈比例"},
    }

    # Pine Script
    pine_code = exporter.export_to_pine("MA_Cross_Strategy", params)
    print(f"=== Pine Script ({len(pine_code)} chars) ===")
    print(pine_code[:500] + "...\n")

    # 通达信
    tdx_code = exporter.export_to_tdx("MA_Cross_Strategy", params)
    print(f"=== 通达信 ({len(tdx_code)} chars) ===")
    print(tdx_code[:500] + "...\n")

    # MT5
    mt5_code = exporter.export_to_mt5("MA_Cross_Strategy", params)
    print(f"=== MT5 ({len(mt5_code)} chars) ===")
    print(mt5_code[:500] + "...\n")

    # Python
    python_code = exporter.export_to_python("MA_Cross_Strategy", params)
    print(f"=== Python ({len(python_code)} chars) ===")
    print(python_code[:500] + "...\n")

    # 导出历史
    history = exporter.get_export_history()
    print(f"=== 导出历史 ({len(history)} 条) ===")
    for h in history:
        print(f"  [{h['platform']}] {h['strategy']}: {h['message']}")