# 量化策略代码规范（Quant Code Standards）

适用于：本项目所有 Python 代码（策略、回测、优化、UI、工具）

## 1. 代码结构规范

### 1.1 文件头部
- 必须包含 `#!/usr/bin/env python3` 声明
- 必须包含 docstring 模块说明（功能、依赖、关键方法）
- 必须包含类型注解导入：`from typing import Dict, List, Optional, Any, Tuple`

### 1.2 函数规范
- 所有公开函数必须有 docstring，说明：输入参数、返回值、副作用
- 所有公开函数必须有完整类型注解
- 所有可能抛出异常的操作必须包含 try/except

```python
# 正确示例
def optimize_strategy(strategy_name: str, iterations: int = 50) -> Dict[str, Any]:
    """对指定策略执行参数优化

    Args:
        strategy_name: 策略名称（必须在策略管理器中注册）
        iterations: 最大评估次数，默认 50

    Returns:
        dict: {success, best_params, best_score, elapsed_seconds}
    """
    try:
        ...
    except Exception as e:
        logger.error(f"优化失败: {e}")
        return {"success": False, "error": str(e)}
```

### 1.3 日志规范
- 使用标准 logging 模块，禁止使用 `print()` 输出业务信息
- 三个级别必须覆盖：INFO（正常流程）、ERROR（异常）、DEBUG（调试）
- 日志必须包含上下文信息（策略名、函数名、关键参数）

## 2. 策略模块规范

### 2.1 策略类必须实现
- `name` / `category` / `description` 属性
- `params` 参数字典（可被优化器读取/写入）
- `run_backtest()` 方法（接收参数，返回标准化 BacktestResult）

### 2.2 优化器集成
- 策略参数必须是数值类型（float/int），可被韬定律优化器搜索
- 必须支持 `apply_optimized_params()` —— 从 StrategyParameterStore 读取最佳参数并应用
- 回测方法必须自动加载优化参数（use_optimized_params=True 为默认）

### 2.3 持久化规范
- 所有优化结果必须写入 StrategyParameterStore（调用 `record_optimization()`）
- 所有交易配置必须支持从 JSON 文件读取/写入
- 参数版本号必须严格递增，不可覆盖历史记录

## 3. 风控与安全

### 3.1 强制性检查
- 任何策略启动前，必须调用风控模块检查参数合理性
- 止损/止盈/最大仓位等风控参数必须有默认值和上限约束
- 回测结果必须包含 max_drawdown / win_rate / sharpe_ratio 三项指标

### 3.2 异常处理
- 网络请求/API 调用必须包含超时（timeout）和重试机制
- 文件 I/O 必须包含异常捕获和错误提示
- 任何失败不得导致整个系统崩溃（必须返回可处理的错误结果）

## 4. 集成总线流程规范

### 4.1 固定流程顺序（不可更改）
```
策略优化 → 参数持久化 → 策略管理器刷新缓存 → 回测验证 → 股票池匹配 → 交易配置生成
```

### 4.2 每个流程必须返回
- `success: bool` —— 是否成功
- `elapsed_seconds: float` —— 耗时
- `message: str` —— 可读说明
- `data: dict` —— 结构化结果数据

## 5. 测试规范

- 新增模块必须包含最小 smoke test（import 不报错、关键方法可调用）
- 优化器必须在 exit_code=0 后才能视为通过
- 新增策略必须在 test_auto_flow.py 中添加验证用例

## 6. 命名规范

- 策略类：`XxxStrategy`（如 `GyroStrategyV7`）
- 优化器模块：`tau_xxx.py`（韬定律前缀）
- 工具脚本：`tool_xxx.py`
- 测试脚本：`test_xxx.py`（pytest 自动发现）
- GUI 文件：`*_desktop*.py` 或 `*_ui.py`

## 7. 禁止事项

❌ 禁止在代码中硬编码密钥、密码、API Token  
❌ 禁止覆盖历史优化参数（StrategyParameterStore 的 record 不可回退）  
❌ 禁止使用 `eval()` / `exec()` 执行用户输入  
❌ 禁止在 GUI 主线程执行耗时操作（必须用子线程）  
❌ 禁止修改他人策略的默认参数值（需经过优化流程）
