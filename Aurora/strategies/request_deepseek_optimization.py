#!/usr/bin/env python3
"""
请求DeepSeek优化横盘、波动、下跌市场的策略
"""

import requests
import json

DEEPSEEK_API_KEY = "sk-e97d90fb3ae8419faca6657a745b66bf"
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"

SYSTEM_PROMPT = """你是一位专业的量化交易策略优化专家。
请直接生成完整的Python代码，不要描述，给出可运行的代码。"""

USER_PROMPT = """# 策略优化请求

## 当前测试结果

| 市场类型 | 收益率 | 交易次数 | 胜率 |
|---------|--------|----------|------|
| 上涨市场 | 78.46% | 866 | 33.37% |
| 横盘市场 | -4.64% | 1210 | 18.93% |
| 波动市场 | 6.67% | 1026 | 20.18% |
| 下跌市场 | -42.00% | 914 | 7.00% |

## 问题分析

1. **横盘市场**：交易过于频繁，胜率低，导致亏损
2. **下跌市场**：严重亏损，缺乏有效的止损机制和风险控制
3. **波动市场**：收益尚可，但胜率仍有提升空间

## 优化目标

1. **横盘市场**：降低交易频率，提高胜率，实现正收益
2. **下跌市场**：限制亏损，实现保本或小幅盈利
3. **波动市场**：提高收益和胜率

## 请求优化方案

请提供以下优化：

1. **改进的PPO奖励函数**：针对不同市场类型设计差异化奖励
2. **动态风险控制**：根据市场状态调整仓位和止损
3. **市场识别增强**：更好地识别横盘/下跌/波动市场
4. **自适应交易频率**：根据市场类型调整交易频率

## 输出要求

请生成完整的Python代码，包含：
1. 优化后的TradingAgent类
2. 改进的PPO网络
3. 多市场自适应策略
4. 完整的测试代码

直接生成代码，不要描述。"""

def main():
    print("正在请求DeepSeek优化策略...")
    
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

        # 保存优化后的代码
        output_path = "optimized_strategy_deepseek.py"
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✅ 优化代码已保存到: {output_path}")
        
    except Exception as e:
        print(f"请求失败: {e}")

if __name__ == "__main__":
    main()