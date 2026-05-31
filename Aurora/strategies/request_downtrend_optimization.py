#!/usr/bin/env python3
"""
请求DeepSeek优化下跌市场策略
"""

import os
import requests

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
DEEPSEEK_API_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com") + "/chat/completions"

USER_PROMPT = """# 下跌市场策略优化请求

## 当前测试结果

| 市场类型 | 收益率 | 交易次数 | 胜率 |
|---------|--------|----------|------|
| 上涨市场 | 18.41% | 210 | 45.71% |
| 横盘市场 | 3.54% | 176 | 5.11% |
| 下跌市场 | -33.65% | 912 | 0.00% |
| 波动市场 | 8.07% | 632 | 6.01% |

## 下跌市场问题分析

当前下跌市场策略：
1. RSI < 35 作为反转信号（条件太严格，难以触发）
2. 金字塔承接：越跌越买
3. 止损阈值：1%
4. 止盈阈值：1.5%

问题：
- 912次交易全部止损
- RSI < 35 在持续下跌中几乎不可能达到
- 金字塔承接导致仓位越来越重，最后全部亏损

## 您的策略思想

1. **反转策略核心**：超跌反弹，不是抄底
2. **敢于承接**：在支撑位、关键点位买入
3. **金字塔策略**：分批建仓，越跌越买，但要控制总仓位
4. **严格止损**：保护资金

## 请求优化

请提供：
1. **改进的反转信号检测**：更灵敏的超跌检测方法
2. **金字塔承接优化**：如何避免持续下跌中的过度加仓
3. **支撑位买入策略**：如何识别关键支撑位
4. **仓位控制**：如何在下跌市场中控制总仓位
5. **完整代码**：Python实现

直接生成代码，不要描述。"""

def main():
    print("正在请求DeepSeek优化下跌市场策略...")
    
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "你是一位专业的量化交易策略专家，擅长优化下跌市场的交易策略。请直接生成完整的Python代码。"},
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

        # 保存
        output_path = "downtrend_optimized.py"
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)

        print(f"✅ 优化代码已保存到: {output_path}")

    except Exception as e:
        print(f"请求失败: {e}")

if __name__ == "__main__":
    main()