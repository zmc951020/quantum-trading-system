from typing import Dict, List, Optional, Any
from .base_llm import BaseLLMProvider

class TaskType:
    """任务类型枚举"""
    CODE_ANALYSIS = "code_analysis"
    QUANT_STRATEGY = "quant_strategy"
    MARKET_ANALYSIS = "market_analysis"
    RISK_ASSESSMENT = "risk_assessment"
    DATA_ANALYSIS = "data_analysis"
    GENERAL_CHAT = "general_chat"
    LONG_CONTEXT = "long_context"
    LOW_LATENCY = "low_latency"

class ModelCapability:
    """模型能力评估"""
    
    def __init__(self, model_name: str, provider_name: str):
        self.model_name = model_name
        self.provider_name = provider_name
        self.code_quality = 0.0
        self.quant_understanding = 0.0
        self.market_analysis = 0.0
        self.risk_assessment = 0.0
        self.data_analysis = 0.0
        self.context_window = 0
        self.latency_ms = 1000
        self.cost_per_token = 0.0
        
    def get_score(self, task_type: str) -> float:
        """获取模型在特定任务类型上的分数"""
        scores = {
            TaskType.CODE_ANALYSIS: self.code_quality,
            TaskType.QUANT_STRATEGY: self.quant_understanding,
            TaskType.MARKET_ANALYSIS: self.market_analysis,
            TaskType.RISK_ASSESSMENT: self.risk_assessment,
            TaskType.DATA_ANALYSIS: self.data_analysis,
            TaskType.GENERAL_CHAT: (self.code_quality + self.market_analysis + self.data_analysis) / 3,
            TaskType.LONG_CONTEXT: float(self.context_window) / 1000000,
            TaskType.LOW_LATENCY: 1.0 - (self.latency_ms / 1000.0)
        }
        return scores.get(task_type, 0.5)

class SmartModelSelector:
    """智能模型选择器 - 根据任务类型自动选择最优模型"""
    
    def __init__(self, llm_manager):
        self.llm_manager = llm_manager
        self._capabilities: Dict[str, ModelCapability] = {}
        self._auto_switch_enabled = True
        self._current_task_type = TaskType.GENERAL_CHAT
        self._learn_from_feedback = True
        self._init_model_capabilities()
    
    def _init_model_capabilities(self):
        """初始化内置模型能力评估"""
        default_capabilities = [
            # Ollama本地模型
            {"name": "qwen2.5-coder:1.5b", "provider": "ollama", 
             "code_quality": 0.75, "quant_understanding": 0.7, "market_analysis": 0.65,
             "risk_assessment": 0.6, "data_analysis": 0.65, "context_window": 128000,
             "latency_ms": 500, "cost_per_token": 0.0},
            {"name": "qwen2.5-coder:7b", "provider": "ollama",
             "code_quality": 0.85, "quant_understanding": 0.8, "market_analysis": 0.75,
             "risk_assessment": 0.7, "data_analysis": 0.75, "context_window": 128000,
             "latency_ms": 1500, "cost_per_token": 0.0},
            {"name": "deepseek-coder:6.7b", "provider": "ollama",
             "code_quality": 0.88, "quant_understanding": 0.82, "market_analysis": 0.7,
             "risk_assessment": 0.65, "data_analysis": 0.72, "context_window": 128000,
             "latency_ms": 1800, "cost_per_token": 0.0},
            {"name": "llama3.3:70b", "provider": "ollama",
             "code_quality": 0.92, "quant_understanding": 0.88, "market_analysis": 0.85,
             "risk_assessment": 0.8, "data_analysis": 0.82, "context_window": 128000,
             "latency_ms": 3000, "cost_per_token": 0.0},
            
            # EchoBird代理模型
            {"name": "gpt-4o", "provider": "echobird",
             "code_quality": 0.95, "quant_understanding": 0.9, "market_analysis": 0.92,
             "risk_assessment": 0.88, "data_analysis": 0.9, "context_window": 128000,
             "latency_ms": 800, "cost_per_token": 0.0015},
            {"name": "gpt-4o-mini", "provider": "echobird",
             "code_quality": 0.88, "quant_understanding": 0.82, "market_analysis": 0.85,
             "risk_assessment": 0.8, "data_analysis": 0.85, "context_window": 128000,
             "latency_ms": 400, "cost_per_token": 0.00015},
            {"name": "claude-3-5-sonnet", "provider": "echobird",
             "code_quality": 0.93, "quant_understanding": 0.92, "market_analysis": 0.9,
             "risk_assessment": 0.9, "data_analysis": 0.91, "context_window": 200000,
             "latency_ms": 1000, "cost_per_token": 0.0011},
            {"name": "gemini-1.5-flash", "provider": "echobird",
             "code_quality": 0.85, "quant_understanding": 0.8, "market_analysis": 0.88,
             "risk_assessment": 0.75, "data_analysis": 0.82, "context_window": 1000000,
             "latency_ms": 600, "cost_per_token": 0.00012},
            {"name": "deepseek-chat:latest", "provider": "echobird",
             "code_quality": 0.82, "quant_understanding": 0.78, "market_analysis": 0.75,
             "risk_assessment": 0.7, "data_analysis": 0.78, "context_window": 128000,
             "latency_ms": 300, "cost_per_token": 0.0}
        ]
        
        for cap in default_capabilities:
            mc = ModelCapability(cap["name"], cap["provider"])
            mc.code_quality = cap["code_quality"]
            mc.quant_understanding = cap["quant_understanding"]
            mc.market_analysis = cap["market_analysis"]
            mc.risk_assessment = cap["risk_assessment"]
            mc.data_analysis = cap["data_analysis"]
            mc.context_window = cap["context_window"]
            mc.latency_ms = cap["latency_ms"]
            mc.cost_per_token = cap["cost_per_token"]
            self._capabilities[cap["name"]] = mc
    
    def enable_auto_switch(self, enabled: bool):
        """启用/禁用自动切换"""
        self._auto_switch_enabled = enabled
    
    def is_auto_switch_enabled(self) -> bool:
        """检查是否启用自动切换"""
        return self._auto_switch_enabled
    
    def set_task_type(self, task_type: str):
        """设置当前任务类型"""
        self._current_task_type = task_type
    
    def get_task_type(self) -> str:
        """获取当前任务类型"""
        return self._current_task_type
    
    def detect_task_type(self, prompt: str) -> str:
        """根据提示内容自动检测任务类型"""
        prompt_lower = prompt.lower()
        
        # 量化策略相关
        quant_keywords = ["策略", "回测", "优化", "参数", "指标", "均线", 
                          "MACD", "RSI", "布林带", "仓位", "止损", "止盈"]
        if any(kw in prompt_lower for kw in quant_keywords):
            return TaskType.QUANT_STRATEGY
        
        # 代码分析相关
        code_keywords = ["代码", "function", "def", "class", "bug", "error", 
                        "debug", "python", "java", "cpp", "实现", "算法"]
        if any(kw in prompt_lower for kw in code_keywords):
            return TaskType.CODE_ANALYSIS
        
        # 市场分析相关
        market_keywords = ["市场", "股票", "行情", "走势", "预测", "分析",
                          "板块", "热点", "资金", "成交量"]
        if any(kw in prompt_lower for kw in market_keywords):
            return TaskType.MARKET_ANALYSIS
        
        # 风险评估相关
        risk_keywords = ["风险", "风控", "评估", "合规", "安全", "审计"]
        if any(kw in prompt_lower for kw in risk_keywords):
            return TaskType.RISK_ASSESSMENT
        
        # 数据分析相关
        data_keywords = ["数据", "统计", "图表", "可视化", "报表", "指标"]
        if any(kw in prompt_lower for kw in data_keywords):
            return TaskType.DATA_ANALYSIS
        
        # 长上下文相关
        if len(prompt) > 8000:
            return TaskType.LONG_CONTEXT
        
        return TaskType.GENERAL_CHAT
    
    def select_best_model(self, task_type: str = None) -> Optional[str]:
        """
        根据任务类型选择最优模型
        
        Args:
            task_type: 任务类型，默认为当前设置的任务类型
            
        Returns:
            最优模型名称，如果没有可用模型则返回None
        """
        if not self._auto_switch_enabled:
            return None
        
        target_task = task_type or self._current_task_type
        available_providers = self.llm_manager.list_providers()
        
        best_model = None
        best_score = -1.0
        
        for provider_name in available_providers:
            provider = self.llm_manager.get_provider(provider_name)
            if not provider or not provider.is_available():
                continue
            
            available_models = provider.get_available_models()
            for model_name in available_models:
                if model_name in self._capabilities:
                    cap = self._capabilities[model_name]
                    if cap.provider_name == provider_name:
                        score = cap.get_score(target_task)
                        if score > best_score:
                            best_score = score
                            best_model = model_name
        
        return best_model
    
    def switch_to_best_model(self, task_type: str = None) -> bool:
        """
        自动切换到最优模型
        
        Args:
            task_type: 任务类型
            
        Returns:
            是否切换成功
        """
        best_model = self.select_best_model(task_type)
        if best_model:
            # 找到模型所属的提供者
            for provider_name in self.llm_manager.list_providers():
                provider = self.llm_manager.get_provider(provider_name)
                if provider and best_model in provider.get_available_models():
                    # 切换提供者
                    self.llm_manager.set_active_provider(provider_name)
                    # 切换模型
                    self.llm_manager.set_model(best_model)
                    print(f"[Auto] 已自动切换到模型: {provider_name}/{best_model}")
                    return True
        return False
    
    def suggest_models(self, task_type: str = None, top_n: int = 3) -> List[Dict[str, Any]]:
        """
        获取推荐的模型列表
        
        Args:
            task_type: 任务类型
            top_n: 返回前N个推荐模型
            
        Returns:
            推荐模型列表，包含模型名称、提供者、分数等信息
        """
        target_task = task_type or self._current_task_type
        available_providers = self.llm_manager.list_providers()
        
        candidates = []
        
        for provider_name in available_providers:
            provider = self.llm_manager.get_provider(provider_name)
            if not provider or not provider.is_available():
                continue
            
            available_models = provider.get_available_models()
            for model_name in available_models:
                if model_name in self._capabilities:
                    cap = self._capabilities[model_name]
                    if cap.provider_name == provider_name:
                        score = cap.get_score(target_task)
                        candidates.append({
                            "model_name": model_name,
                            "provider_name": provider_name,
                            "score": score,
                            "latency_ms": cap.latency_ms,
                            "context_window": cap.context_window,
                            "cost_per_token": cap.cost_per_token
                        })
        
        # 按分数排序
        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates[:top_n]
    
    def get_task_types(self) -> List[str]:
        """获取所有支持的任务类型"""
        return [
            TaskType.CODE_ANALYSIS,
            TaskType.QUANT_STRATEGY,
            TaskType.MARKET_ANALYSIS,
            TaskType.RISK_ASSESSMENT,
            TaskType.DATA_ANALYSIS,
            TaskType.GENERAL_CHAT,
            TaskType.LONG_CONTEXT,
            TaskType.LOW_LATENCY
        ]
    
    def get_task_type_description(self, task_type: str) -> str:
        """获取任务类型的描述"""
        descriptions = {
            TaskType.CODE_ANALYSIS: "代码分析 - 适合编程、调试、代码审查",
            TaskType.QUANT_STRATEGY: "量化策略 - 适合策略开发、回测分析",
            TaskType.MARKET_ANALYSIS: "市场分析 - 适合行情解读、趋势预测",
            TaskType.RISK_ASSESSMENT: "风险评估 - 适合风控分析、合规检查",
            TaskType.DATA_ANALYSIS: "数据分析 - 适合数据处理、报表生成",
            TaskType.GENERAL_CHAT: "通用对话 - 适合日常问答、知识查询",
            TaskType.LONG_CONTEXT: "长上下文 - 适合处理超长文本",
            TaskType.LOW_LATENCY: "低延迟 - 适合实时响应场景"
        }
        return descriptions.get(task_type, "未知任务类型")