
# QS Robot 完整架构设计 v3.0

## 机器人核心定位

**QS Robot = 系统神经中枢 + 智能助手平台 + 可扩展生态**

- **P0 - 核心**: 系统神经中枢（系统模块集成 + 深度优化）
- **P1 - 增益**: 6个专家系统（小功能）
- **P2 - 增益**: 技能克隆器（小功能）
- **P3 - 生态**: 扩展模块和接口（插件化架构）

---

## 一、机器人完整架构（6层 + 扩展接口）

```
┌─────────────────────────────────────────────────────────────────────┐
│  L6 - 用户交互层 (User Interface)                                    │
│  - Web UI / CLI / API / 悬浮窗                                       │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
┌────────────────────────────────┴────────────────────────────────────┐
│  L5 - 指挥调度层 (Orchestration Layer)                              │
│  - NLU理解 + 路由决策 + 对话管理 + 工具调度                         │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
┌────────────────────────────────┴────────────────────────────────────┐
│  L4 - 能力层 (Capability Layer)                                      │
│  ┌─────────────────────────────┐  ┌─────────────────────────────┐  │
│  │ P0 - 核心能力             │  │ P1/P2 - 增益能力           │  │
│  │ - 系统神经中枢            │  │ - 6个专家系统              │  │
│  │   - 系统模块集成          │  │ - 技能克隆器               │  │
│  │   - 深度优化引擎          │  │ - [扩展能力] ← 接口        │  │
│  └─────────────────────────────┘  └─────────────────────────────┘  │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
┌────────────────────────────────┴────────────────────────────────────┐
│  L3 - 工具层 (Tools Layer)                                          │
│  - 内置工具集: 系统集成工具 + 分析工具 + 操作工具                  │
│  - 外部技能: 克隆的技能                                            │
│  - [扩展工具] ← 接口，支持自定义工具注册                           │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
┌────────────────────────────────┴────────────────────────────────────┐
│  L2 - 记忆层 (Memory Layer)                                         │
│  - L0: Meta Rules (宪法)                                           │
│  - L1: Insight Index (快速索引)                                    │
│  - L2: Global Facts (全局知识)                                    │
│  - L3: Task Skills (可复用技能)                                    │
│  - L4: Session Archive (会话归档)                                  │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
┌────────────────────────────────┴────────────────────────────────────┐
│  L1 - 基础设施层 (Infrastructure Layer)                            │
│  - LLM接口层: Ollama / DeepSeek / [扩展LLM接口]                    │
│  - 监控钩子层: Pre/Post Hook + 信号检测 + [扩展钩子]               │
│  - 数据层: 系统状态 + 缓存 + [扩展数据源]                         │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
┌────────────────────────────────┴────────────────────────────────────┐
│  L0 - 外部系统层 (External System)                                  │
│  - 我们的量化系统: 策略、优化器、回测、风控等                      │
│  - [扩展外部系统接口] ← 支持连接第三方系统                        │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 二、扩展功能模块体系

### 2.1 插件化架构设计

```
qs_robot/
├── plugins/                          # 扩展插件目录
│   ├── official/                     # 官方插件
│   │   ├── plugin_market.py          # 插件市场
│   │   ├── plugin_backup.py          # 备份恢复
│   │   └── plugin_scheduler.py       # 定时任务
│   ├── community/                    # 社区插件（第三方）
│   └── local/                        # 本地自定义插件
│
├── extensions/                       # 扩展接口定义
│   ├── llm_providers/                # LLM提供者扩展
│   │   ├── base_llm.py               # 基类
│   │   ├── ollama_provider.py        # Ollama实现
│   │   ├── deepseek_provider.py      # DeepSeek实现
│   │   └── [custom_llm.py]           # 自定义实现
│   │
│   ├── tools/                        # 工具扩展
│   │   ├── base_tool.py              # 工具基类
│   │   └── [custom_tool.py]          # 自定义工具
│   │
│   ├── hooks/                        # 钩子扩展
│   │   ├── base_hook.py              # 钩子基类
│   │   └── [custom_hook.py]          # 自定义钩子
│   │
│   ├── data_sources/                 # 数据源扩展
│   │   ├── base_data_source.py       # 基类
│   │   └── [custom_source.py]        # 自定义数据源
│   │
│   └── capabilities/                 # 能力扩展
│       ├── base_capability.py        # 能力基类
│       └── [custom_capability.py]    # 自定义能力
│
└── plugin_manager.py                 # 插件管理器
```

### 2.2 核心扩展接口定义

#### 扩展接口1: LLM提供者接口

```python
# qs_robot/extensions/llm_providers/base_llm.py
from abc import ABC, abstractmethod
from typing import Generator

class BaseLLMProvider(ABC):
    """LLM提供者基类"""
    
    @abstractmethod
    def chat(self, messages: list, stream: bool = False) -&gt; str | Generator:
        """聊天接口"""
        pass
    
    @abstractmethod
    def get_available_models(self) -&gt; list:
        """获取可用模型列表"""
        pass
    
    @abstractmethod
    def set_model(self, model_name: str):
        """设置模型"""
        pass
```

**实现示例: 自定义LLM提供者**
```python
# qs_robot/extensions/llm_providers/my_llm_provider.py
from .base_llm import BaseLLMProvider

class MyLLMProvider(BaseLLMProvider):
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.current_model = "my-model-1.0"
    
    def chat(self, messages: list, stream: bool = False):
        # 实现你的LLM调用逻辑
        pass
    
    def get_available_models(self) -&gt; list:
        return ["my-model-1.0", "my-model-2.0"]
    
    def set_model(self, model_name: str):
        self.current_model = model_name
```

**注册接口**
```python
# 在配置文件或启动时注册
from qs_robot.extensions.llm_providers import register_llm_provider
from my_llm_provider import MyLLMProvider

register_llm_provider("my_llm", MyLLMProvider(api_key="..."))
```

---

#### 扩展接口2: 自定义工具接口

```python
# qs_robot/extensions/tools/base_tool.py
from abc import ABC, abstractmethod
from typing import Any

class BaseTool(ABC):
    """工具基类"""
    
    name: str = "tool_name"
    description: str = "工具描述"
    
    @abstractmethod
    def call(self, parameters: dict) -&gt; Any:
        """调用工具"""
        pass
```

**实现示例: 自定义分析工具**
```python
# qs_robot/extensions/tools/my_analysis_tool.py
from .base_tool import BaseTool

class MyAnalysisTool(BaseTool):
    name = "my_analysis"
    description = "我的自定义分析工具"
    
    def call(self, parameters: dict) -&gt; Any:
        # 实现你的分析逻辑
        data = parameters.get("data")
        result = self._analyze(data)
        return result
    
    def _analyze(self, data):
        # 分析算法
        pass
```

**注册接口**
```python
from qs_robot.extensions.tools import register_tool
from my_analysis_tool import MyAnalysisTool

register_tool(MyAnalysisTool())
```

---

#### 扩展接口3: 钩子接口

```python
# qs_robot/extensions/hooks/base_hook.py
from abc import ABC, abstractmethod
from typing import Optional

class BaseHook(ABC):
    """钩子基类"""
    
    @abstractmethod
    def before_tool_call(self, tool_name: str, params: dict) -&gt; Optional[dict]:
        """工具调用前的钩子
        返回值会作为新的参数传递给工具
        """
        pass
    
    @abstractmethod
    def after_tool_call(self, tool_name: str, params: dict, result: Any):
        """工具调用后的钩子"""
        pass
    
    @abstractmethod
    def before_llm_call(self, messages: list) -&gt; Optional[list]:
        """LLM调用前的钩子"""
        pass
    
    @abstractmethod
    def after_llm_call(self, messages: list, response: str):
        """LLM调用后的钩子"""
        pass
```

**实现示例: 日志钩子**
```python
# qs_robot/extensions/hooks/logging_hook.py
from .base_hook import BaseHook
import logging

class LoggingHook(BaseHook):
    def before_tool_call(self, tool_name: str, params: dict):
        logging.info(f"Calling tool: {tool_name} with params: {params}")
        return None  # 返回None表示不修改参数
    
    def after_tool_call(self, tool_name: str, params: dict, result):
        logging.info(f"Tool {tool_name} returned: {result}")
    
    def before_llm_call(self, messages: list):
        logging.info(f"LLM input: {messages}")
        return None
    
    def after_llm_call(self, messages: list, response: str):
        logging.info(f"LLM output: {response}")
```

**注册接口**
```python
from qs_robot.extensions.hooks import register_hook
from logging_hook import LoggingHook

register_hook(LoggingHook())
```

---

#### 扩展接口4: 能力接口

```python
# qs_robot/extensions/capabilities/base_capability.py
from abc import ABC, abstractmethod
from typing import Any

class BaseCapability(ABC):
    """能力基类"""
    
    name: str = "capability_name"
    description: str = "能力描述"
    trigger_keywords: list = []  # 触发关键词
    
    @abstractmethod
    def can_handle(self, user_query: str) -&gt; bool:
        """判断是否能处理这个查询"""
        pass
    
    @abstractmethod
    def handle(self, user_query: str, context: dict) -&gt; Any:
        """处理查询"""
        pass
```

**实现示例: 自定义分析能力**
```python
# qs_robot/extensions/capabilities/my_custom_capability.py
from .base_capability import BaseCapability

class MyCustomCapability(BaseCapability):
    name = "my_custom"
    description = "我的自定义分析能力"
    trigger_keywords = ["分析", "统计", "计算"]
    
    def can_handle(self, user_query: str) -&gt; bool:
        return any(keyword in user_query for keyword in self.trigger_keywords)
    
    def handle(self, user_query: str, context: dict) -&gt; Any:
        # 实现你的自定义处理逻辑
        result = self._process(user_query, context)
        return result
```

**注册接口**
```python
from qs_robot.extensions.capabilities import register_capability
from my_custom_capability import MyCustomCapability

register_capability(MyCustomCapability())
```

---

#### 扩展接口5: 外部系统接口

```python
# qs_robot/extensions/data_sources/base_data_source.py
from abc import ABC, abstractmethod
from typing import Any

class BaseDataSource(ABC):
    """数据源基类"""
    
    name: str = "data_source_name"
    
    @abstractmethod
    def get_data(self, query: dict) -&gt; Any:
        """获取数据"""
        pass
    
    @abstractmethod
    def send_command(self, command: str, params: dict) -&gt; Any:
        """发送命令到系统"""
        pass
```

**实现示例: 连接到你的自定义系统**
```python
# qs_robot/extensions/data_sources/my_system_source.py
from .base_data_source import BaseDataSource
import requests

class MySystemSource(BaseDataSource):
    name = "my_quant_system"
    
    def __init__(self, api_url: str, api_key: str):
        self.api_url = api_url
        self.api_key = api_key
    
    def get_data(self, query: dict) -&gt; Any:
        # 调用你的系统API获取数据
        response = requests.get(
            f"{self.api_url}/data",
            params=query,
            headers={"X-API-Key": self.api_key}
        )
        return response.json()
    
    def send_command(self, command: str, params: dict) -&gt; Any:
        # 发送命令到你的系统
        response = requests.post(
            f"{self.api_url}/{command}",
            json=params,
            headers={"X-API-Key": self.api_key}
        )
        return response.json()
```

**注册接口**
```python
from qs_robot.extensions.data_sources import register_data_source
from my_system_source import MySystemSource

register_data_source(MySystemSource("http://my-system/api", "my-key"))
```

---

## 三、配置与扩展管理

### 3.1 配置文件

```json
{
  "llm_providers": {
    "ollama": {
      "enabled": true,
      "api_base": "http://localhost:11434",
      "default_model": "qwen2.5-coder:1.5b"
    },
    "deepseek": {
      "enabled": true,
      "api_key": "your-api-key",
      "default_model": "deepseek-chat"
    },
    "my_llm": {
      "enabled": true,
      "api_key": "your-key"
    }
  },
  
  "plugins": {
    "plugin_market": {
      "enabled": true
    },
    "my_custom_plugin": {
      "enabled": true,
      "config": {}
    }
  },
  
  "extensions": {
    "tools": ["my_analysis_tool"],
    "hooks": ["logging_hook"],
    "capabilities": ["my_custom"],
    "data_sources": ["my_quant_system"]
  }
}
```

### 3.2 插件管理器

```python
# qs_robot/plugin_manager.py
class PluginManager:
    """插件管理器"""
    
    def __init__(self, config: dict):
        self.config = config
        self.plugins = {}
        self.load_plugins()
    
    def load_plugins(self):
        """加载启用的插件"""
        for plugin_name, plugin_config in self.config.get("plugins", {}).items():
            if plugin_config.get("enabled", False):
                self.load_plugin(plugin_name, plugin_config)
    
    def load_plugin(self, plugin_name: str, plugin_config: dict):
        """加载单个插件"""
        pass  # 实现插件加载逻辑
    
    def install_plugin(self, plugin_url: str):
        """安装插件（从插件市场）"""
        pass
    
    def uninstall_plugin(self, plugin_name: str):
        """卸载插件"""
        pass
    
    def list_plugins(self) -&gt; list:
        """列出所有插件"""
        return list(self.plugins.keys())
```

---

## 四、能力边界定义

### 机器人做什么（能力范围）

| 层级 | 能力类型 | 说明 | 可扩展 |
|------|---------|------|--------|
| **P0 - 核心** | 系统神经中枢 | 集成使用系统各模块 + 深度优化 | ❌ 核心固定 |
| **P1 - 增益** | 6个专家系统 | 专业分析和建议 | ✅ 可新增专家 |
| **P2 - 增益** | 技能克隆器 | 获取外部技能 | ✅ 可扩展克隆源 |
| **P3 - 生态** | 扩展模块 | 插件、自定义工具、LLM、数据源等 | ✅ 完全开放 |

### 机器人不做什么（边界）

1. **不替换现有系统** - 保持现有系统原样，机器人作为增益层
2. **不直接执行交易** - 只提供建议，不干涉交易执行
3. **不做通用对话** - 专注量化领域，不闲聊
4. **不随意修改系统配置** - 所有操作都需要用户确认

---

## 五、实施路线图

### 阶段1: P0 - 系统神经中枢基础（MVP）
- [ ] 探索现有系统，了解各模块接口
- [ ] 搭建机器人目录结构和基础设施层
- [ ] 实现指挥调度层基础
- [ ] 实现系统模块集成层（1-2个模块开始）
- [ ] 实现基础深度优化建议
- [ ] 搭建基础UI（悬浮窗框架）
- [ ] 定义核心扩展接口框架

### 阶段2: P0 - 系统神经中枢完整
- [ ] 集成所有主要系统模块
- [ ] 完善深度优化引擎
- [ ] 系统状态管理

### 阶段3: P1 - 专家系统
- [ ] 实现6个专家系统
- [ ] 专业分析能力

### 阶段4: P2 - 技能克隆器
- [ ] 实现技能克隆器
- [ ] 技能市场

### 阶段5: P3 - 扩展生态
- [ ] 完善插件管理系统
- [ ] 插件市场上线
- [ ] 开发者文档

### 阶段6: 自我进化（可选）
- [ ] 本能记录器
- [ ] 技能结晶器
- [ ] 进化引擎

---

## 六、下一步实施建议

1. **继续完善架构**: 确认细节
2. **探索现有系统**: 了解量化系统的API接口
3. **搭建骨架**: 从阶段1开始实现

---

**设计日期**: 2026-05-29

