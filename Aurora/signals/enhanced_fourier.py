#!/usr/bin/env python3
"""
增强型傅里叶特征提取器
"""

import math
import numpy as np
from scipy.fft import fft, fftfreq
from scipy.signal import find_peaks, welch
import warnings
warnings.filterwarnings('ignore')

class EnhancedFourierExtractor:
    """
    生产级傅里叶特征提取器
    - 自适应窗口选择
    - 统计显著性检验
    - 多尺度融合
    - 实时相位追踪
    """
    
    def __init__(self, config=None):
        """
        初始化傅里叶特征提取器
        
        Args:
            config: 配置参数
        """
        if config is None:
            config = {}
        
        self.min_window = config.get('min_window', 32)
        self.max_window = config.get('max_window', 256)
        self.top_k_cycles = config.get('top_k_cycles', 5)
        self.significance_level = config.get('significance_level', 0.05)
        self.use_welch = config.get('use_welch', True)
        
        # 缓存机制
        self.fft_cache = {}
        self.cycle_memory = []  # 周期记忆
        
    def extract_features(self, price_series, volume_series=None):
        """
        主特征提取函数
        
        Args:
            price_series: 价格序列
            volume_series: 成交量序列（可选）
            
        Returns:
            dict: 特征字典
        """
        # 1. 平稳化处理
        log_returns = np.diff(np.log(price_series))
        
        # 2. 自适应窗口选择
        optimal_window = self._select_optimal_window(log_returns)
        
        # 3. 频谱估计
        if self.use_welch:
            freqs, psd = welch(log_returns[-optimal_window:], 
                              nperseg=min(optimal_window//2, 64),
                              return_onesided=True)
        else:
            fft_vals = fft(log_returns[-optimal_window:])
            freqs = fftfreq(optimal_window, d=1)[:optimal_window//2]
            psd = np.abs(fft_vals[:optimal_window//2])**2
        
        # 4. 周期显著性检验
        significant_cycles = self._test_cycle_significance(psd, freqs)
        
        # 5. 瞬时相位计算（希尔伯特变换）
        from scipy.signal import hilbert
        analytic_signal = hilbert(log_returns[-64:])
        instantaneous_phase = np.angle(analytic_signal)[-1]
        
        # 6. 频谱熵计算
        normalized_psd = psd / (np.sum(psd) + 1e-10)
        spectral_entropy = -np.sum(normalized_psd * np.log2(normalized_psd + 1e-10))
        
        # 7. 周期性强度评估
        cycle_strength = self._calculate_cycle_strength(psd)
        
        # 8. 谐波分析
        harmonics = self._analyze_harmonics(freqs, psd, significant_cycles)
        
        # 9. 平稳性检验（ADF Test）
        from statsmodels.tsa.stattools import adfuller
        adf_result = adfuller(log_returns[-optimal_window:], autolag='AIC')
        stationarity = 1.0 if adf_result[1] < 0.05 else adf_result[1]
        
        # 10. 趋势置信度（使用Mann-Kendall检验）
        trend_confidence = self._mann_kendall_test(log_returns[-optimal_window:])
        
        return {
            'dominant_periods': [c['period'] for c in significant_cycles[:3]],
            'cycle_strength': cycle_strength,
            'phase_position': instantaneous_phase,
            'spectral_entropy': spectral_entropy,
            'trend_confidence': trend_confidence,
            'harmonics': harmonics,
            'stationarity': stationarity,
            'optimal_window': optimal_window
        }
    
    def _select_optimal_window(self, data):
        """
        基于数据长度和特征自动选择最优窗口
        
        Args:
            data: 数据序列
            
        Returns:
            int: 最优窗口大小
        """
        if len(data) < self.min_window:
            return len(data)
        
        # 尝试多个窗口大小，选择使频谱最清晰的窗口
        best_window = self.min_window
        best_clarity = 0
        
        for window in [32, 64, 96, 128, 192, 256]:
            if window > len(data):
                break
                
            segment = data[-window:]
            fft_vals = np.abs(fft(segment)[:window//2])
            
            # 计算频谱清晰度（主峰与其他峰的比例）
            sorted_vals = np.sort(fft_vals)[::-1]
            if len(sorted_vals) > 1:
                clarity = sorted_vals[0] / (sorted_vals[1] + 1e-10)
                if clarity > best_clarity:
                    best_clarity = clarity
                    best_window = window
        
        return best_window
    
    def _test_cycle_significance(self, psd, freqs):
        """
        Fisher's G-test 周期显著性检验
        
        Args:
            psd: 功率谱密度
            freqs: 频率
            
        Returns:
            list: 显著周期列表
        """
        total_power = np.sum(psd)
        significant_cycles = []
        
        # 找出功率谱中的峰值
        peaks, properties = find_peaks(psd, height=np.mean(psd) + np.std(psd))
        
        for peak in peaks:
            if peak == 0:  # 跳过直流分量
                continue
                
            # Fisher's G统计量
            g_stat = psd[peak] / total_power
            
            # 计算p值
            n = len(psd)
            p_value = self._fisher_g_pvalue(g_stat, n)
            
            if p_value < self.significance_level:
                period = 1.0 / freqs[peak] if freqs[peak] > 0 else np.inf
                if period < 1000:  # 过滤过长的周期
                    significant_cycles.append({
                        'period': period,
                        'frequency': freqs[peak],
                        'power': psd[peak],
                        'g_statistic': g_stat,
                        'p_value': p_value,
                        'confidence': 1 - p_value
                    })
        
        # 按置信度排序
        significant_cycles.sort(key=lambda x: x['confidence'], reverse=True)
        return significant_cycles
    
    def _fisher_g_pvalue(self, g, n):
        """
        Fisher's G-test p值计算
        
        Args:
            g: G统计量
            n: 样本数量
            
        Returns:
            float: p值
        """
        k = int(1 / g)
        p_value = 0
        for j in range(1, k + 1):
            term = (-1)**(j-1) * math.comb(n, j) * (1 - j*g)**(n-1)
            p_value += term
        return min(p_value, 1.0)
    
    def _calculate_cycle_strength(self, psd):
        """
        计算周期性强度（0-1之间）
        1表示完美的周期性，0表示完全随机
        
        Args:
            psd: 功率谱密度
            
        Returns:
            float: 周期性强度
        """
        total_power = np.sum(psd)
        if total_power == 0:
            return 0.0
            
        # 计算前10%最大功率占总功率的比例
        sorted_psd = np.sort(psd)[::-1]
        top_10_percent = int(len(psd) * 0.1)
        concentrated_power = np.sum(sorted_psd[:top_10_percent]) / total_power
        
        return concentrated_power
    
    def _analyze_harmonics(self, freqs, psd, fundamental_cycles):
        """
        谐波分析：识别主导周期的倍频和分频
        
        Args:
            freqs: 频率
            psd: 功率谱密度
            fundamental_cycles: 主导周期
            
        Returns:
            list: 谐波列表
        """
        harmonics = []
        for cycle in fundamental_cycles[:2]:  # 只分析前2个主导周期
            base_freq = cycle['frequency']
            
            # 检查倍频（2倍、3倍）
            for harmonic in [2, 3, 4]:
                harmonic_freq = base_freq * harmonic
                idx = np.argmin(np.abs(freqs - harmonic_freq))
                if idx < len(psd):
                    harmonics.append({
                        'base_period': cycle['period'],
                        'harmonic_type': f'{harmonic}x',
                        'frequency': freqs[idx],
                        'power_ratio': psd[idx] / cycle['power']
                    })
            
            # 检查分频（1/2、1/3）
            for subharmonic in [0.5, 1/3]:
                sub_freq = base_freq * subharmonic
                idx = np.argmin(np.abs(freqs - sub_freq))
                if idx < len(psd):
                    harmonics.append({
                        'base_period': cycle['period'],
                        'harmonic_type': f'{1/subharmonic:.0f}分频',
                        'frequency': freqs[idx],
                        'power_ratio': psd[idx] / cycle['power']
                    })
        
        return harmonics
    
    def _mann_kendall_test(self, data):
        """
        Mann-Kendall趋势检验
        返回趋势置信度 (0-1)
        
        Args:
            data: 数据序列
            
        Returns:
            float: 趋势置信度
        """
        n = len(data)
        s = 0
        for i in range(n-1):
            for j in range(i+1, n):
                s += np.sign(data[j] - data[i])
        
        # 方差计算
        var_s = n * (n - 1) * (2 * n + 5) / 18
        
        # 标准化
        if s > 0:
            z = (s - 1) / np.sqrt(var_s)
        elif s < 0:
            z = (s + 1) / np.sqrt(var_s)
        else:
            z = 0
        
        # 转换为置信度
        from scipy.stats import norm
        confidence = 2 * (1 - norm.cdf(abs(z)))
        
        return confidence
