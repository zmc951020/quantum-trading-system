#!/usr/bin/env python3
"""
纯Python实现的HMM（隐马尔可夫模型）
用于市场状态识别
当hmmlearn不可用时使用此实现
"""

import numpy as np
from typing import Tuple, Optional

class GaussianHMM:
    """
    高斯隐马尔可夫模型纯Python实现
    用于市场状态识别（低波动趋势市、高波动震荡市、危机模式）
    """

    def __init__(self, n_states: int = 3, n_iter: int = 100, tol: float = 1e-4):
        """
        初始化高斯HMM

        Args:
            n_states: 隐藏状态数量
            n_iter: 最大迭代次数
            tol: 收敛阈值
        """
        self.n_states = n_states
        self.n_iter = n_iter
        self.tol = tol
        self.means = None
        self.covars = None
        self.transmat = None
        self.startprob = None
        self.converged_ = False

    def _initialize_params(self, X: np.ndarray):
        """
        初始化参数

        Args:
            X: 观测数据
        """
        n_samples, n_features = X.shape

        # 初始化均值：使用K-means风格的分段初始化
        indices = np.linspace(0, n_samples, self.n_states + 1, dtype=int)
        self.means = np.array([X[indices[i]:indices[i+1]].mean(axis=0)
                               for i in range(self.n_states)])

        # 初始化协方差：使用全局协方差
        self.covars = np.array([np.cov(X.T) + np.eye(n_features) * 1e-6
                                for _ in range(self.n_states)])

        # 初始化转移矩阵：使用等概率转移
        self.transmat = np.full((self.n_states, self.n_states), 1.0 / self.n_states)

        # 初始化起始概率：等概率
        self.startprob = np.full(self.n_states, 1.0 / self.n_states)

    def _gaussian_pdf(self, X: np.ndarray, mean: np.ndarray, covar: np.ndarray) -> np.ndarray:
        """
        计算多元高斯概率密度

        Args:
            X: 观测数据 (n_samples, n_features)
            mean: 均值 (n_features,)
            covar: 协方差 (n_features, n_features)

        Returns:
            概率密度值 (n_samples,)
        """
        n_features = X.shape[1]
        diff = X - mean

        # 计算协方差矩阵的行列式和逆矩阵
        try:
            covar_inv = np.linalg.inv(covar)
            covar_det = np.linalg.det(covar)
        except np.linalg.LinAlgError:
            covar = covar + np.eye(n_features) * 1e-6
            covar_inv = np.linalg.inv(covar)
            covar_det = np.linalg.det(covar)

        # 计算Mahalanobis距离
        mahalanobis = np.sum(diff @ covar_inv * diff, axis=1)

        # 计算概率密度
        norm_const = 1.0 / (np.power(2 * np.pi, n_features / 2) * np.sqrt(covar_det))
        pdf = norm_const * np.exp(-0.5 * mahalanobis)

        return pdf

    def _forward_backward(self, X: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        前向后向算法

        Args:
            X: 观测数据

        Returns:
            gamma: 后验概率
            xi_sum: 转移概率的期望
            log_likelihood: 对数似然
        """
        n_samples = X.shape[0]

        # 计算发射概率
        emission_probs = np.zeros((n_samples, self.n_states))
        for i in range(self.n_states):
            emission_probs[:, i] = self._gaussian_pdf(X, self.means[i], self.covars[i])

        # 初始化前向概率
        alpha = np.zeros((n_samples, self.n_states))
        alpha[0] = self.startprob * emission_probs[0]
        alpha[0] /= alpha[0].sum() + 1e-300

        # 前向传递
        log_likelihood = 0
        for t in range(1, n_samples):
            alpha[t] = emission_probs[t] * (alpha[t-1] @ self.transmat)
            alpha_sum = alpha[t].sum()
            if alpha_sum > 0:
                alpha[t] /= alpha_sum
                log_likelihood += np.log(alpha_sum)

        # 初始化后向概率
        beta = np.zeros((n_samples, self.n_states))
        beta[-1] = 1.0

        # 后向传递
        for t in range(n_samples - 2, -1, -1):
            beta[t] = self.transmat @ (emission_probs[t + 1] * beta[t + 1])
            beta[t] /= beta[t].sum() + 1e-300

        # 计算后验概率
        gamma = alpha * beta
        gamma /= gamma.sum(axis=1, keepdims=True) + 1e-300

        # 计算转移概率的期望
        xi_sum = np.zeros((self.n_states, self.n_states))
        for t in range(n_samples - 1):
            numerator = alpha[t].reshape(-1, 1) * self.transmat * emission_probs[t + 1] * beta[t + 1].reshape(1, -1)
            denominator = (numerator.sum() + 1e-300)
            xi_sum += numerator / denominator

        return gamma, xi_sum, log_likelihood

    def _m_step(self, X: np.ndarray, gamma: np.ndarray, xi_sum: np.ndarray):
        """
        M步：更新参数

        Args:
            X: 观测数据
            gamma: 后验概率
            xi_sum: 转移概率的期望
        """
        n_samples = X.shape[0]

        # 更新起始概率
        self.startprob = gamma[0]
        self.startprob /= self.startprob.sum() + 1e-300

        # 更新转移矩阵
        for i in range(self.n_states):
            xi_sum[i, :] /= xi_sum[i, :].sum() + 1e-300
        self.transmat = xi_sum

        # 更新均值和协方差
        for i in range(self.n_states):
            gamma_i = gamma[:, i]
            gamma_sum = gamma_i.sum()

            if gamma_sum > 0:
                # 更新均值
                self.means[i] = (gamma_i @ X) / gamma_sum

                # 更新协方差
                diff = X - self.means[i]
                self.covars[i] = (gamma_i.reshape(-1, 1) * diff).T @ diff / gamma_sum + np.eye(X.shape[1]) * 1e-6

    def fit(self, X: np.ndarray) -> 'GaussianHMM':
        """
        拟合模型

        Args:
            X: 观测数据 (n_samples, n_features)

        Returns:
            self
        """
        X = np.asarray(X)

        self._initialize_params(X)

        for iteration in range(self.n_iter):
            gamma, xi_sum, log_likelihood = self._forward_backward(X)

            self._m_step(X, gamma, xi_sum)

            if iteration > 0 and hasattr(self, 'prev_log_likelihood'):
                if abs(log_likelihood - self.prev_log_likelihood) < self.tol:
                    self.converged_ = True
                    break

            self.prev_log_likelihood = log_likelihood

        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        """
        预测最可能的状态序列

        Args:
            X: 观测数据

        Returns:
            状态序列
        """
        X = np.asarray(X)
        n_samples = X.shape[0]

        # 计算发射概率
        emission_probs = np.zeros((n_samples, self.n_states))
        for i in range(self.n_states):
            emission_probs[:, i] = self._gaussian_pdf(X, self.means[i], self.covars[i])

        # 初始化
        delta = np.zeros((n_samples, self.n_states))
        psi = np.zeros((n_samples, self.n_states), dtype=int)

        delta[0] = self.startprob * emission_probs[0]

        # 前向递推
        for t in range(1, n_samples):
            for j in range(self.n_states):
                delta[t, j] = np.max(delta[t - 1] * self.transmat[:, j]) * emission_probs[t, j]
                psi[t, j] = np.argmax(delta[t - 1] * self.transmat[:, j])

        # 回溯
        states = np.zeros(n_samples, dtype=int)
        states[-1] = np.argmax(delta[-1])

        for t in range(n_samples - 2, -1, -1):
            states[t] = psi[t + 1, states[t + 1]]

        return states

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """
        预测后验概率

        Args:
            X: 观测数据

        Returns:
            后验概率 (n_samples, n_states)
        """
        X = np.asarray(X)
        gamma, _, _ = self._forward_backward(X)
        return gamma


def detect_market_regime(prices: list, volatility_threshold: float = 0.02, crisis_threshold: float = 0.05) -> dict:
    """
    使用HMM检测市场状态

    Args:
        prices: 价格序列
        volatility_threshold: 波动率阈值
        crisis_threshold: 危机阈值

    Returns:
        市场状态信息
    """
    prices = np.array(prices)

    if len(prices) < 30:
        return {
            'regime': 1,
            'regime_label': 'CHOPPY_HIGH_VOL',
            'regime_name': '高波动震荡市',
            'confidence': 0.5,
            'reason': '数据不足'
        }

    # 计算收益率
    returns = np.diff(prices) / prices[:-1]

    # 添加收益率的绝对值作为第二个特征
    X = np.column_stack([returns, np.abs(returns)])

    # 尝试使用GaussianHMM
    try:
        model = GaussianHMM(n_states=3, n_iter=100)
        model.fit(X)
        states = model.predict(X)
        probs = model.predict_proba(X)

        # 计算每个状态的平均收益率和波动率
        state_stats = []
        for i in range(3):
            mask = states == i
            if mask.sum() > 0:
                avg_return = returns[mask[:-1] if len(mask) > len(returns) else mask].mean()
                avg_volatility = np.abs(returns[mask[:-1] if len(mask) > len(returns) else mask]).mean()
                state_stats.append({
                    'state': i,
                    'avg_return': avg_return,
                    'avg_volatility': avg_volatility
                })

        # 按波动率排序状态
        state_stats.sort(key=lambda x: x['avg_volatility'])

        # 映射到市场状态
        low_vol_state = state_stats[0]['state'] if len(state_stats) > 0 else 0
        high_vol_state = state_stats[1]['state'] if len(state_stats) > 1 else 1
        crisis_state = state_stats[2]['state'] if len(state_stats) > 2 else 2

        # 当前状态
        current_state = states[-1]
        current_prob = probs[-1]

        if current_state == crisis_state or state_stats[2]['avg_volatility'] > crisis_threshold:
            regime = 2
            regime_label = 'CRISIS_MODE'
            regime_name = '危机模式'
        elif current_state == low_vol_state and state_stats[0]['avg_volatility'] < volatility_threshold:
            regime = 0
            regime_label = 'TRENDING_LOW_VOL'
            regime_name = '低波动趋势市'
        else:
            regime = 1
            regime_label = 'CHOPPY_HIGH_VOL'
            regime_name = '高波动震荡市'

        confidence = float(current_prob[current_state])

        return {
            'regime': regime,
            'regime_label': regime_label,
            'regime_name': regime_name,
            'confidence': confidence,
            'state_stats': state_stats,
            'reason': f'基于HMM模型识别，当前状态概率: {confidence:.2%}'
        }

    except Exception as e:
        # 如果HMM失败，使用简单的启发式方法
        recent_volatility = np.abs(returns[-20:]).mean()
        recent_return = returns[-20:].mean()

        if recent_volatility > crisis_threshold:
            regime = 2
            regime_label = 'CRISIS_MODE'
            regime_name = '危机模式'
        elif recent_volatility < volatility_threshold:
            regime = 0
            regime_label = 'TRENDING_LOW_VOL'
            regime_name = '低波动趋势市'
        else:
            regime = 1
            regime_label = 'CHOPPY_HIGH_VOL'
            regime_name = '高波动震荡市'

        return {
            'regime': regime,
            'regime_label': regime_label,
            'regime_name': regime_name,
            'confidence': 0.6,
            'reason': f'基于启发式方法，波动率: {recent_volatility:.2%}'
        }


if __name__ == '__main__':
    # 测试代码
    np.random.seed(42)

    # 生成模拟数据
    prices = []
    price = 50000
    for i in range(200):
        if i < 70:
            # 低波动趋势
            price *= (1 + np.random.normal(0.001, 0.01))
        elif i < 140:
            # 高波动震荡
            price *= (1 + np.random.normal(0, 0.02))
        else:
            # 危机
            price *= (1 + np.random.normal(-0.002, 0.05))
        prices.append(price)

    prices = np.array(prices)

    # 检测市场状态
    result = detect_market_regime(prices)

    print("市场状态检测结果:")
    print(f"  状态编号: {result['regime']}")
    print(f"  状态标签: {result['regime_label']}")
    print(f"  状态名称: {result['regime_name']}")
    print(f"  置信度: {result['confidence']:.2%}")
    print(f"  原因: {result.get('reason', 'N/A')}")
