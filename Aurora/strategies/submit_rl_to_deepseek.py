#!/usr/bin/env python3
"""
提交强化学习优化后的策略代码给DeepSeek Flash进行分析
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

请基于用户提供的策略代码和需求，进行专业分析并提供优化建议。"""

USER_PROMPT = """# 量化交易策略强化学习优化版

## 一、策略架构

策略采用**四层架构**：
1. **市场识别层** - 市场分类器识别市场类型（上涨/下跌/横盘）
2. **策略决策层** - 根据市场类型选择对应策略组合
3. **风险控制层** - 动态止损、仓位管理
4. **参数优化层** - 机器学习+强化学习持续优化参数

## 二、核心策略模块

### 2.1 上涨市场策略
- 斐波那契回调买入
- 波浪回调买入（基于波浪理论）
- 突破买入（基于肯特纳通道）
- 网格回调买入
- 网格分批止盈

### 2.2 下跌市场策略
- 金字塔承接策略（5个级别）
- 反转信号买入（多周期RSI协同）
- 超跌反弹买入

### 2.3 横盘市场策略
- 网格低买高卖
- 黄金分割交易

## 三、强化学习优化（新增）

### 3.1 Q-learning代理
- **状态空间**：价格变化、RSI、波动率、市场类型
- **动作空间**：buy、sell、hold、increase_position、decrease_position
- **ε-贪婪策略**：探索率从0.3衰减至0.05
- **折扣因子**：0.99

### 3.2 参数探索机制
- 基于当前最佳参数进行微小扰动（±10%）
- 探索率和学习率自适应衰减

### 3.3 奖励函数
```python
reward = total_return * 0.5 + sharpe_ratio * 0.3 - max_drawdown * 0.2
```

### 3.4 参数持久化
- 自动保存最优参数到 `strategy_params/optimized_params.pkl`
- 保存训练历史到 `strategy_params/training_history.json`
- 策略重启时自动加载历史最优参数

## 四、当前测试结果

| 市场类型 | 收益率 | 夏普比率 | 最大回撤 | 日均交易 |
|---------|--------|----------|----------|----------|
| 横盘市场 | 0.35% | 0.02 | 6.63% | 1.2次 |
| 上涨市场 | -0.01% | -0.00 | 4.01% | 0.8次 |
| 下跌市场 | -0.08% | -0.01 | 3.31% | 0.4次 |
| 波动市场 | -0.10% | -0.02 | 3.27% | 0.2次 |

## 五、优化目标

1. **提高收益**：当前收益偏低，需要提高交易频率
2. **提高夏普比率**：优化风险调整收益
3. **提高资金使用率**：当前保留资金过多
4. **优化强化学习**：改进奖励函数和探索策略
5. **实现分钟级交易**：达到日均100次以上交易

## 六、请求协助

请提供：
1. **强化学习优化建议**：如何改进Q-learning策略
2. **奖励函数优化**：更科学的奖励设计
3. **参数探索策略**：更高效的参数搜索方法
4. **策略组合优化**：不同市场状态下的最优策略权重
5. **分钟级交易实现**：高频交易的优化建议

请直接给出优化后的代码和配置建议。"""

def main():
    print("正在提交强化学习优化策略到DeepSeek Flash...")
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
        "temperature": 0.7,
        "max_tokens": 4000
    }

    try:
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=data, timeout=120)
        response.raise_for_status()

        result = response.json()
        content = result["choices"][0]["message"]["content"]

        print("DeepSeek Flash 分析结果：")
        print("=" * 80)
        print(content)
        print("=" * 80)

        output_path = r"D:\Gupiao\量化交易测试设备方案\攒机\最后评估01\DS-V3.2T量化交易专用工作站配置深度研判与采购决策报告02_files\攒机配置\Aurora\strategies\deepseek_rl_optimization_result.md"
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("# DeepSeek Flash 强化学习优化建议\n\n")
            f.write(f"生成时间：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(content)
        print(f"\n优化建议已保存至：{output_path}")

    except requests.exceptions.RequestException as e:
        print(f"请求失败：{e}")
    except KeyError as e:
        print(f"解析响应失败：{e}")
    except Exception as e:
        print(f"发生错误：{e}")

if __name__ == "__main__":
    main()