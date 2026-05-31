#!/usr/bin/env python3
"""
请求DeepSeek Flash直接生成完整优化代码
"""

import os
import requests
import json
import datetime

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
DEEPSEEK_API_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com") + "/chat/completions"

SYSTEM_PROMPT = """你是一位专业的量化交易策略专家，擅长：
1. 策略设计和优化
2. 金融数学建模
3. 机器学习和强化学习在量化交易中的应用
4. 风险管理和资产配置

请直接生成完整的、可运行的Python代码，不要只描述，要给出实际代码。"""

USER_PROMPT = """# 请直接生成完整的优化后策略代码

## 策略文件位置
D:\\Gupiao\\量化交易测试设备方案\\攒机\\最后评估01\\DS-V3.2T量化交易专用工作站配置深度研判与采购决策报告02_files\\攒机配置\\Aurora\\strategies\\final_market_adaptive.py

## 当前策略存在的问题
1. 交易频率极低（日均0.2-1.2次），远低于目标100次
2. 夏普比率接近0
3. 资金利用率低
4. Q-learning设计缺陷

## 需要实现的优化

### 1. PPO算法替代Q-learning
- 使用PyTorch实现PPO网络
- 策略网络（Actor）+ 价值网络（Critic）
- GAE优势估计

### 2. 状态空间扩展
- 多时间尺度特征（短期/长期收益率）
- 技术指标（RSI、波动率、趋势强度）
- 持仓状态和资金比例

### 3. 改进的奖励函数
```python
reward = immediate_profit - trade_cost - risk_penalty + frequency_reward + diversity_reward
```

### 4. 自适应止损/止盈
- 基于波动率动态调整止损距离
- 追踪止损机制

## 请求

请直接生成以下内容：

1. **完整的PPO算法实现代码**（包含PPONetwork、PPOTrainer类）
2. **增强的强化学习交易代理类**（EnhancedRLTrader）
3. **更新后的FinalMarketAdaptiveGrid类**，整合PPO
4. **参数持久化机制**
5. **完整的测试框架代码**

请确保代码：
- 可以直接运行
- 包含中文注释
- 有完整的错误处理
- 支持分钟级交易

生成完整的Python文件内容，我可以直接保存运行。"""

def main():
    print("正在请求DeepSeek Flash生成完整优化代码...")
    print("=" * 80)

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

        print("DeepSeek Flash 生成的代码：")
        print("=" * 80)
        print(content[:3000] + "..." if len(content) > 3000 else content)
        print("=" * 80)

        # 保存完整代码
        output_path = r"D:\Gupiao\量化交易测试设备方案\攒机\最后评估01\DS-V3.2T量化交易专用工作站配置深度研判与采购决策报告02_files\攒机配置\Aurora\strategies\final_market_adaptive_rl_optimized.py"

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("#!/usr/bin/env python3\n")
            f.write("\"\"\"\n")
            f.write("量化交易策略 - PPO强化学习优化版\n")
            f.write("由DeepSeek Flash自动生成\n")
            f.write(f"生成时间：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("\"\"\"\n\n")
            f.write(content)

        print(f"\n完整代码已保存至：{output_path}")
        print("注意：代码已保存，请检查是否有语法错误或需要调整的部分")

    except requests.exceptions.RequestException as e:
        print(f"请求失败：{e}")
    except KeyError as e:
        print(f"解析响应失败：{e}")
    except Exception as e:
        print(f"发生错误：{e}")

if __name__ == "__main__":
    main()