#!/usr/bin/env python3
"""
请求DeepSeek进行全面优化
"""

import requests
import json

DEEPSEEK_API_KEY = "sk-e97d90fb3ae8419faca6657a745b66bf"
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"

SYSTEM_PROMPT = """你是一位专业的量化交易策略专家，擅长：
1. 机器学习驱动的市场自适应策略
2. 动态网格交易算法
3. 多市场类型的差异化策略设计
4. 资金管理和风险控制

请直接生成完整的Python代码，包含详细注释。"""

USER_PROMPT = """# 量化交易策略深度优化请求

## 当前问题分析

### 测试结果对比

| 市场类型 | 原始策略收益率 | 优化后收益率 | 问题 |
|---------|-------------|-------------|------|
| 上涨市场 | 78.46% | 57.55% | ✗ 收益大幅下降 |
| 横盘市场 | -4.64% | 0.82% | ✗ 收益太小 |
| 下跌市场 | -42.00% | 0.00% | ✗ 过于保守，完全不交易 |
| 波动市场 | 6.67% | 2.26% | ✗ 收益太小 |

## 核心需求

### 1. 上涨市场策略保持原有表现
- 恢复原有的激进策略
- 保持高收益特征

### 2. 横盘市场优化
- 提高交易频率但保持高胜率
- 网格间距要小（0.1%-0.3%）
- 资金使用率60%-80%
- 目标收益：5%-10%/10天

### 3. 下跌市场优化
- 金字塔式承接策略
- 分批建仓，越跌越买
- 目标：小幅盈利或保本
- 风险控制：最大回撤≤5%

### 4. 波动市场优化
- 高抛低吸策略
- 结合布林带、RSI指标
- 网格间距动态调整
- 目标收益：8%-15%/10天

## 技术要求

### 1. 机器学习市场识别
- 使用RandomForest分类器识别市场类型
- 特征：波动率、趋势强度、RSI、MACD等
- 实时更新模型

### 2. 动态网格策略
- 上涨市场：趋势跟随 + 宽松网格
- 横盘市场：紧密网格 + 高抛低吸
- 下跌市场：金字塔承接 + 严格止损
- 波动市场：动态网格 + 指标配合

### 3. 关键点位分析
- 支撑位/压力位检测
- 斐波那契回撤位
- 成交量加权平均价

### 4. 资金动态分配
- 根据市场类型调整仓位
- 风险储备金机制
- 盈利再投资策略

## 输出要求

请生成完整的Python代码，包含：
1. 市场识别模块（机器学习）
2. 动态网格交易策略
3. 多市场自适应切换
4. 关键点位分析
5. 资金管理系统
6. 完整测试框架

直接生成可运行代码。"""

def main():
    print("正在请求DeepSeek进行深度优化...")
    
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT}
        ],
        "temperature": 0.3,
        "max_tokens": 8000
    }

    try:
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=data, timeout=180)
        response.raise_for_status()

        result = response.json()
        content = result["choices"][0]["message"]["content"]

        # 清理markdown代码标记
        content = content.replace("```python\n", "").replace("\n```", "")
        
        # 保存优化后的代码
        output_path = "final_optimized_strategy.py"
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✅ 优化代码已保存到: {output_path}")
        
    except Exception as e:
        print(f"请求失败: {e}")

if __name__ == "__main__":
    main()