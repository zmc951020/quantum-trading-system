#!/usr/bin/env python3
"""
傅里叶加强学习量化交易策略
"""

import numpy as np
import pandas as pd
from typing import Dict, Optional, Any
from strategies.strategy_base import StrategyBase
from signals.enhanced_fourier import EnhancedFourierExtractor
from signals.regime_detector import MarketRegimeDetector
from signals.dual_market_state import DualDimensionMarketState, TrendTypeDetector
from models.ppo_agent import PPOAgent
from models.production_env import ProductionTradingEnv
from models.model_persistence import ModelPersistenceManager, StrategyStateExtractor
from risk.enhanced_risk_manager import EnhancedRiskManager
from monitoring.fourier_monitor import FourierMonitor
from monitoring.alert_manager import AlertManager

class FourierRLStrategy(StrategyBase):
    """
    傅里叶加强学习量化交易策略
    """
    
    def __init__(self, base_price: float = 100.0, initial_balance: float = 100000):
        """
        初始化傅里叶策略
        
        Args:
            base_price: 基准价格
            initial_balance: 初始资金
        """
        super().__init__(base_price, initial_balance)
        
        # 初始化傅里叶特征提取器
        self.fourier_extractor = EnhancedFourierExtractor()
        
        # 初始化市场状态识别器
        self.regime_detector = MarketRegimeDetector()

        # 双维度市场状态识别器
        self.dual_market_state = DualDimensionMarketState()
        self.trend_detector = TrendTypeDetector()
        
        # 价格历史
        self.price_history = []
        
        # 市场状态
        self.current_regime = 0  # 0: 低波动趋势市, 1: 高波动震荡市, 2: 危机模式
        
        # 交易参数
        self.commission_rate = 0.0003  # 万三
        self.slippage = 0.0001  # 万分之一
        
        # 风控参数
        self.stop_loss_pct = 0.05  # 5%
        self.take_profit_pct = 0.15  # 15%
        self.max_position_pct = 0.95  # 95%
        
        # 模型相关
        self.ppo_agent = None
        self.model_trained = False
        
        # 风险管理
        self.risk_manager = EnhancedRiskManager()
        self.peak_value = initial_balance  # 峰值价值
        self.daily_pnl = []  # 每日盈亏
        
        # 监控模块
        self.monitor = FourierMonitor()

        # 告警管理器
        self.alert_manager = AlertManager()

        # 模型持久化管理器
        self.persistence_manager = ModelPersistenceManager(base_dir="./model_storage/fourier_rl")
        self.auto_save_interval = 100  # 每100次更新自动保存
        self.update_count = 0

        # 尝试加载上次保存的状态
        self._try_load_saved_state()
        
    def update_price(self, current_price: float, data: Optional[pd.Series] = None) -> Dict[str, Any]:
        """
        更新价格并执行交易
        
        Args:
            current_price: 当前价格
            data: 价格数据
            
        Returns:
            交易结果
        """
        # 记录价格历史
        self.price_history.append(current_price)
        
        # 计算收益率
        returns = []
        if len(self.price_history) > 1:
            for i in range(1, len(self.price_history)):
                returns.append(np.log(self.price_history[i] / self.price_history[i-1]))
        
        # 更新市场状态
        if len(returns) >= 100:
            self.current_regime = self.regime_detector.predict_regime(
                np.array(returns),
                None  # 暂时不使用成交量
            )

        # 更新双维度市场状态
        self.dual_market_state.update_hmm_state(self.current_regime)

        # 检测趋势类型（使用Aurora原有逻辑）
        trend_type = 'range_bound'
        if data is not None and len(data) >= 20:
            trend_type = self.trend_detector.detect(data)
        self.dual_market_state.update_trend_type(trend_type)

        # 获取双维度交叉决策
        dual_decision = self.dual_market_state.get_decision()

        # 提取傅里叶特征
        features = {}
        if len(self.price_history) >= 64:
            features = self.fourier_extractor.extract_features(
                np.array(self.price_history)
            )
        
        # 计算当前组合价值
        portfolio_value = self.current_balance + self.position * current_price
        
        # 更新峰值价值
        if portfolio_value > self.peak_value:
            self.peak_value = portfolio_value
        
        # 计算回撤
        drawdown = (self.peak_value - portfolio_value) / self.peak_value
        
        # 初始化风险评分
        risk_score = 0
        
        # 检查回撤限制
        if not self.risk_manager.check_drawdown_limit(portfolio_value, self.peak_value):
            # 超过回撤限制，平仓
            if self.position > 0:
                self._update_monitor(features if features else {}, risk_score, portfolio_value, drawdown)
                return self._sell_all(current_price, "drawdown_limit")
            self._update_monitor(features if features else {}, risk_score, portfolio_value, drawdown)
            return {"action": "hold", "balance": self.current_balance, "position": self.position}
        
        # 检查单日亏损限制
        if len(self.daily_pnl) > 0:
            daily_loss = sum(self.daily_pnl[-24:])  # 最近24小时的盈亏
            if not self.risk_manager.check_daily_loss_limit(daily_loss, self.initial_balance):
                # 超过单日亏损限制，平仓
                if self.position > 0:
                    self._update_monitor(features if features else {}, risk_score, portfolio_value, drawdown)
                    return self._sell_all(current_price, "daily_loss_limit")
                self._update_monitor(features if features else {}, risk_score, portfolio_value, drawdown)
                return {"action": "hold", "balance": self.current_balance, "position": self.position}
        
        # 双维度市场状态调整
        # 危机模式：强制平仓
        if self.current_regime == 2:
            if self.position > 0:
                self._update_monitor(features if features else {}, risk_score, portfolio_value, drawdown)
                return self._sell_all(current_price, "crisis_mode")
            self._update_monitor(features if features else {}, risk_score, portfolio_value, drawdown)
            return {"action": "hold", "balance": self.current_balance, "position": self.position}

        # 高波动环境：根据趋势类型调整
        if self.current_regime == 1:
            recommended_ratio = dual_decision['recommended_position_ratio']
            current_ratio = self.position * current_price / portfolio_value if portfolio_value > 0 else 0

            # 如果当前仓位超过推荐仓位，降低仓位
            if current_ratio > recommended_ratio and self.position > 0 and current_price > self.entry_price:
                reduce_ratio = (current_ratio - recommended_ratio) / current_ratio
                self._update_monitor(features if features else {}, risk_score, portfolio_value, drawdown)
                return self._sell_partial(current_price, reduce_ratio, "high_vol_adjustment")

        # 计算风险评分
        if len(returns) >= 20:
            risk_score = self.risk_manager.get_risk_score(
                self.position * current_price,
                self.initial_balance,
                self.current_regime,
                pd.Series(returns)
            )
        
        # 初始化fourier_features
        fourier_features = features if features else {}
        
        # 基于风险评分调整交易策略
        if risk_score > 80:
            # 高风险，减少交易
            if self.position > 0 and current_price > self.entry_price:
                self._update_monitor(fourier_features, risk_score, portfolio_value, drawdown)
                return self._sell_partial(current_price, 0.7, "high_risk")
        
        # 基于傅里叶特征的交易决策
        if features:
            cycle_strength = features.get('cycle_strength', 0)
            phase_position = features.get('phase_position', 0)
            dominant_periods = features.get('dominant_periods', [])

            # 根据双维度决策调整交易行为
            recommended_strategy = dual_decision['recommended_strategy']
            recommended_ratio = dual_decision['recommended_position_ratio']
            current_ratio = self.position * current_price / portfolio_value if portfolio_value > 0 else 0

            # 周期性强时进行交易
            if cycle_strength > 0.6:
                # 相位分析：负相位可能是买入机会，正相位可能是卖出机会

                # 检查是否适合开仓
                can_open_position = (
                    dual_decision['signal'] in ['long', 'neutral'] and
                    current_ratio < recommended_ratio
                )

                if phase_position < -1.0 and self.position == 0 and can_open_position:
                    # 计算最优持仓大小
                    optimal_position = self.risk_manager.calculate_position_size(
                        self.initial_balance,
                        self.current_regime
                    )

                    # 检查风险
                    if len(returns) >= 20:
                        risk_check = self.risk_manager.check_regime_based_risk(
                            optimal_position,
                            self.initial_balance,
                            self.current_regime,
                            pd.Series(returns)
                        )

                        if not risk_check['overall_ok']:
                            return {"action": "hold", "balance": self.current_balance, "position": self.position}

                    # 买入信号
                    return self._buy(current_price, "fourier_buy_signal")

                # 检查是否应该卖出
                should_close_position = (
                    phase_position > 1.0 and self.position > 0
                ) or dual_decision['signal'] == 'liquidate'

                if should_close_position:
                    # 卖出信号
                    return self._sell_all(current_price, "fourier_sell_signal")
        
        # 动态止损止盈
        if self.position > 0:
            # 计算动态止损止盈价格
            sl_tp = self.risk_manager.calculate_stop_loss_take_profit(
                self.entry_price,
                self.current_regime,
                current_price
            )
            
            if current_price < sl_tp['stop_loss']:
                # 卖出前更新监控
                self._update_monitor(fourier_features, risk_score, portfolio_value, drawdown)
                return self._sell_all(current_price, "dynamic_stop_loss")
            elif current_price > sl_tp['take_profit']:
                # 卖出前更新监控
                self._update_monitor(fourier_features, risk_score, portfolio_value, drawdown)
                return self._sell_all(current_price, "dynamic_take_profit")
        
        # 更新监控
        self._update_monitor(fourier_features, risk_score, portfolio_value, drawdown)

        # 自动保存策略状态
        self.update_count += 1
        if self.update_count % self.auto_save_interval == 0:
            self._auto_save_state()

        return {"action": "hold", "balance": self.current_balance, "position": self.position}
    
    def _update_monitor(self, fourier_features: Dict, risk_score: float, portfolio_value: float, drawdown: float):
        """
        更新监控模块
        
        Args:
            fourier_features: 傅里叶特征
            risk_score: 风险评分
            portfolio_value: 组合价值
            drawdown: 回撤
        """
        self.monitor.update_metrics(
            fourier_features=fourier_features,
            regime=self.current_regime,
            risk_score=risk_score,
            portfolio_value=portfolio_value,
            drawdown=drawdown
        )
        
        # 检查告警
        metrics = {
            'cycle_strength': fourier_features.get('cycle_strength', 0),
            'phase_position': fourier_features.get('phase_position', 0),
            'spectral_entropy': fourier_features.get('spectral_entropy', 0),
            'risk_score': risk_score,
            'current_regime': self.current_regime,
            'drawdown': drawdown
        }
        
        # 计算单日盈亏
        if self.daily_pnl:
            metrics['daily_pnl'] = sum(self.daily_pnl[-24:])
        
        # 检查告警
        alerts = self.alert_manager.check_alerts(metrics)

        # 打印告警信息
        for alert in alerts:
            print(f"[{alert['level'].upper()}] {alert['message']} - {alert['timestamp']}")

    def _auto_save_state(self):
        """
        自动保存策略状态
        """
        try:
            state = StrategyStateExtractor.extract_fourier_rl_state(self)
            performance = self.get_performance()

            version_id = self.persistence_manager.save_strategy_state(
                strategy_name="fourier_rl",
                strategy_state=state,
                performance_metrics=performance,
                description=f"自动保存 - 第{self.update_count}次更新"
            )

            if version_id:
                print(f"[INFO] 策略状态已自动保存: {version_id}")
        except Exception as e:
            print(f"[WARNING] 自动保存策略状态失败: {e}")

    def _try_load_saved_state(self):
        """
        尝试加载上次保存的状态
        """
        try:
            state = self.persistence_manager.load_strategy_state(strategy_name="fourier_rl")
            if state:
                StrategyStateExtractor.restore_fourier_rl_state(self, state)
                print("[INFO] 已加载上次保存的策略状态")
        except Exception as e:
            print(f"[INFO] 未找到保存的策略状态或加载失败: {e}")
    
    def _buy(self, current_price: float, reason: str) -> Dict[str, Any]:
        """
        买入
        
        Args:
            current_price: 当前价格
            reason: 买入原因
            
        Returns:
            交易结果
        """
        # 计算可用资金
        available_balance = self.current_balance * 0.9  # 保留10%现金
        
        # 计算买入数量
        max_position = (self.initial_balance * self.max_position_pct) / current_price
        buy_quantity = min(available_balance / current_price, max_position - self.position)
        
        if buy_quantity > 0.01:
            # 计算实际买入金额（包含滑点和手续费）
            buy_price = current_price * (1 + self.slippage)
            cost = buy_quantity * buy_price * (1 + self.commission_rate)
            
            if cost <= available_balance:
                self.position += buy_quantity
                self.current_balance -= cost
                
                if self.entry_price == 0:
                    self.entry_price = buy_price
                
                self.total_trades += 1
                
                # 计算交易后的组合价值和回撤
                portfolio_value = self.current_balance + self.position * current_price
                drawdown = (self.peak_value - portfolio_value) / self.peak_value
                
                # 提取当前傅里叶特征
                fourier_features = {}
                if len(self.price_history) >= 64:
                    fourier_features = self.fourier_extractor.extract_features(
                        np.array(self.price_history)
                    )
                
                # 计算风险评分
                returns = []
                if len(self.price_history) > 1:
                    for i in range(1, len(self.price_history)):
                        returns.append(np.log(self.price_history[i] / self.price_history[i-1]))
                
                risk_score = 0
                if len(returns) >= 20:
                    risk_score = self.risk_manager.get_risk_score(
                        self.position * current_price,
                        self.initial_balance,
                        self.current_regime,
                        pd.Series(returns)
                    )
                
                # 更新监控
                self._update_monitor(fourier_features, risk_score, portfolio_value, drawdown)
                
                return {
                    "action": "buy",
                    "quantity": buy_quantity,
                    "price": buy_price,
                    "balance": self.current_balance,
                    "position": self.position,
                    "reason": reason
                }
        
        return {"action": "hold", "balance": self.current_balance, "position": self.position}
    
    def _sell_all(self, current_price: float, reason: str) -> Dict[str, Any]:
        """
        卖出全部
        
        Args:
            current_price: 当前价格
            reason: 卖出原因
            
        Returns:
            交易结果
        """
        if self.position > 0:
            # 计算实际卖出金额（包含滑点和手续费）
            sell_price = current_price * (1 - self.slippage)
            revenue = self.position * sell_price * (1 - self.commission_rate)
            
            self.current_balance += revenue
            quantity = self.position
            self.position = 0
            
            # 计算盈亏
            if self.entry_price > 0:
                profit = revenue - quantity * self.entry_price
                self.profit_history.append(profit)
                if profit > 0:
                    self.winning_trades += 1
                else:
                    self.losing_trades += 1
            
            self.total_trades += 1
            self.entry_price = 0
            
            # 计算交易后的组合价值和回撤
            portfolio_value = self.current_balance + self.position * current_price
            drawdown = (self.peak_value - portfolio_value) / self.peak_value
            
            # 提取当前傅里叶特征
            fourier_features = {}
            if len(self.price_history) >= 64:
                fourier_features = self.fourier_extractor.extract_features(
                    np.array(self.price_history)
                )
            
            # 计算风险评分
            returns = []
            if len(self.price_history) > 1:
                for i in range(1, len(self.price_history)):
                    returns.append(np.log(self.price_history[i] / self.price_history[i-1]))
            
            risk_score = 0
            if len(returns) >= 20:
                risk_score = self.risk_manager.get_risk_score(
                    self.position * current_price,
                    self.initial_balance,
                    self.current_regime,
                    pd.Series(returns)
                )
            
            # 更新监控
            self._update_monitor(fourier_features, risk_score, portfolio_value, drawdown)
            
            return {
                "action": "sell",
                "quantity": quantity,
                "price": sell_price,
                "balance": self.current_balance,
                "position": self.position,
                "reason": reason
            }
        
        return {"action": "hold", "balance": self.current_balance, "position": self.position}
    
    def _sell_partial(self, current_price: float, percentage: float, reason: str) -> Dict[str, Any]:
        """
        部分卖出
        
        Args:
            current_price: 当前价格
            percentage: 卖出比例
            reason: 卖出原因
            
        Returns:
            交易结果
        """
        if self.position > 0:
            sell_quantity = self.position * percentage
            
            if sell_quantity > 0.01:
                # 计算实际卖出金额（包含滑点和手续费）
                sell_price = current_price * (1 - self.slippage)
                revenue = sell_quantity * sell_price * (1 - self.commission_rate)
                
                self.current_balance += revenue
                self.position -= sell_quantity
                
                # 计算盈亏
                if self.entry_price > 0:
                    profit = revenue - sell_quantity * self.entry_price
                    self.profit_history.append(profit)
                    if profit > 0:
                        self.winning_trades += 1
                    else:
                        self.losing_trades += 1
                
                self.total_trades += 1
                
                return {
                    "action": "sell",
                    "quantity": sell_quantity,
                    "price": sell_price,
                    "balance": self.current_balance,
                    "position": self.position,
                    "reason": reason
                }
        
        return {"action": "hold", "balance": self.current_balance, "position": self.position}
    
    def get_performance(self) -> Dict[str, float]:
        """
        获取策略性能指标
        
        Returns:
            性能指标字典
        """
        total_return = (self.current_balance + self.position * self.last_price - self.initial_balance) / self.initial_balance
        
        # 计算夏普比率（简化版）
        if len(self.profit_history) > 0:
            returns = np.array(self.profit_history) / self.initial_balance
            sharpe_ratio = np.mean(returns) / (np.std(returns) + 1e-8) * np.sqrt(252)  # 年化
        else:
            sharpe_ratio = 0
        
        # 计算胜率
        win_rate = self.winning_trades / self.total_trades if self.total_trades > 0 else 0
        
        # 计算最大回撤（简化版）
        max_drawdown = 0
        peak = self.initial_balance
        for profit in self.profit_history:
            current_value = peak + profit
            if current_value > peak:
                peak = current_value
            drawdown = (peak - current_value) / peak
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        
        return {
            'total_return': total_return,
            'sharpe_ratio': sharpe_ratio,
            'win_rate': win_rate,
            'max_drawdown': max_drawdown,
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades
        }
    
    def train_model(self, data: pd.Series):
        """
        训练PPO模型
        
        Args:
            data: 价格数据
        """
        # 创建环境
        env = ProductionTradingEnv(
            df=data.to_frame('Close'),
            feature_extractor=self.fourier_extractor,
            regime_detector=self.regime_detector,
            config={
                'initial_capital': self.initial_balance,
                'commission_rate': self.commission_rate,
                'stop_loss_pct': self.stop_loss_pct,
                'take_profit_pct': self.take_profit_pct
            }
        )
        
        # 创建并训练PPO智能体
        self.ppo_agent = PPOAgent(env)
        self.ppo_agent.train(total_timesteps=100000)
        self.model_trained = True
    
    def get_market_state(self) -> Dict[str, Any]:
        """
        获取市场状态（双维度）

        Returns:
            市场状态字典
        """
        state_labels = {
            0: 'TRENDING_LOW_VOL',
            1: 'CHOPPY_HIGH_VOL',
            2: 'CRISIS_MODE'
        }

        features = {}
        if len(self.price_history) >= 64:
            features = self.fourier_extractor.extract_features(
                np.array(self.price_history)
            )

        # 获取双维度决策
        dual_decision = self.dual_market_state.get_decision()

        return {
            'current_regime': self.current_regime,
            'regime_label': state_labels.get(self.current_regime, 'UNKNOWN'),
            'fourier_features': features,
            'price_history_length': len(self.price_history),
            # 双维度市场状态
            'dual_dimension': {
                'hmm_state': self.current_regime,
                'hmm_label': dual_decision['hmm_label'],
                'trend_type': dual_decision['trend_type'],
                'trend_label': dual_decision['trend_label'],
                'signal': dual_decision['signal'],
                'recommended_position_ratio': dual_decision['recommended_position_ratio'],
                'recommended_strategy': dual_decision['recommended_strategy'],
                'description': dual_decision['description']
            }
        }
