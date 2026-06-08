"""
Trae集成扩展 - 实现QS Robot与Trae IDE的深度融合

功能:
1. 注册LLM管理器到Trae的全局服务
2. 提供模型切换的API接口
3. 支持Trae插件系统集成
4. 实现Cline（命令行界面）集成
"""

import sys
import os
from typing import Dict, List, Any, Optional

class TraeIntegration:
    """Trae IDE集成管理器"""
    
    def __init__(self):
        self._llm_manager = None
        self._registered = False
        self._trae_services = {}
    
    def set_llm_manager(self, llm_manager):
        """设置LLM管理器"""
        self._llm_manager = llm_manager
        print("[Trae] LLM管理器已绑定")
    
    def register_to_trae(self):
        """注册到Trae IDE"""
        try:
            # 尝试获取Trae的全局上下文
            if hasattr(sys, '_getframe'):
                frame = sys._getframe(1)
                if frame and 'trae_context' in frame.f_globals:
                    trae_context = frame.f_globals['trae_context']
                    if hasattr(trae_context, 'register_service'):
                        trae_context.register_service('llm_manager', self._llm_manager)
                        self._registered = True
                        print("[Trae] 已注册LLM管理器到Trae服务")
            
            # 设置环境变量供其他模块访问
            os.environ['QS_ROBOT_LLM_AVAILABLE'] = 'true'
            print("[Trae] 环境变量已设置")
            
        except Exception as e:
            print(f"[Trae] 注册到Trae失败（非Trae环境）: {e}")
    
    def get_llm_status(self) -> Dict[str, Any]:
        """获取LLM状态信息"""
        if not self._llm_manager:
            return {"status": "error", "message": "LLM管理器未初始化"}
        
        try:
            return {
                "status": "success",
                "active_provider": self._llm_manager.active_provider.name if self._llm_manager.active_provider else None,
                "current_model": self._llm_manager.active_provider.model if self._llm_manager.active_provider else None,
                "providers": self._llm_manager.list_providers(),
                "auto_switch_enabled": self._llm_manager.is_auto_switch_enabled(),
                "available_models": self._llm_manager.get_available_models()
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def switch_provider(self, provider_name: str) -> bool:
        """切换LLM提供者"""
        if self._llm_manager:
            return self._llm_manager.set_active_provider(provider_name)
        return False
    
    def switch_model(self, model_name: str) -> bool:
        """切换LLM模型"""
        if self._llm_manager:
            return self._llm_manager.set_model(model_name)
        return False
    
    def enable_auto_switch(self, enabled: bool):
        """启用/禁用自动切换"""
        if self._llm_manager:
            self._llm_manager.enable_auto_switch(enabled)
    
    def suggest_models(self, task_type: str = None) -> List[Dict[str, Any]]:
        """获取推荐模型列表"""
        if self._llm_manager:
            return self._llm_manager.suggest_models(task_type)
        return []
    
    def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """调用LLM聊天接口"""
        if self._llm_manager:
            return self._llm_manager.chat(messages, **kwargs)
        return "[错误] LLM管理器未初始化"


# 全局Trae集成实例
trae_integration = TraeIntegration()


class ClineIntegration:
    """Cline（命令行界面）集成模块 - 在命令行中使用LLM切换功能"""
    
    def __init__(self, llm_manager):
        self.llm_manager = llm_manager
        self._commands = {
            'list': self._cmd_list_models,
            'switch': self._cmd_switch_model,
            'provider': self._cmd_switch_provider,
            'auto': self._cmd_toggle_auto,
            'status': self._cmd_status,
            'task': self._cmd_set_task,
            'help': self._cmd_help
        }
    
    def execute_command(self, command: str) -> str:
        """执行Cline命令"""
        parts = command.strip().split()
        if not parts:
            return "请输入命令，输入 'llm help' 查看帮助"
        
        cmd = parts[0].lower()
        
        if cmd in self._commands:
            try:
                return self._commands[cmd](parts[1:])
            except Exception as e:
                return f"命令执行失败: {str(e)}"
        else:
            return f"未知命令: {cmd}，输入 'llm help' 查看帮助"
    
    def _cmd_list_models(self, args: List[str]) -> str:
        """列出可用模型"""
        providers = self.llm_manager.list_providers()
        result = "📦 可用LLM提供者:\n"
        
        for provider_name in providers:
            provider = self.llm_manager.get_provider(provider_name)
            if provider:
                status = "✓" if provider.is_available() else "✗"
                result += f"  {status} {provider_name} ({provider.model})\n"
                
                models = provider.get_available_models()
                if models:
                    result += f"    模型: {', '.join(models[:5])}"
                    if len(models) > 5:
                        result += f"... (共{len(models)}个)"
                    result += "\n"
        
        return result
    
    def _cmd_switch_model(self, args: List[str]) -> str:
        """切换模型"""
        if not args:
            return "用法: llm switch <模型名称>"
        
        model_name = ' '.join(args)
        if self.llm_manager.set_model(model_name):
            return f"✅ 已切换到模型: {model_name}"
        else:
            return f"❌ 切换失败，模型不可用: {model_name}"
    
    def _cmd_switch_provider(self, args: List[str]) -> str:
        """切换提供者"""
        if not args:
            return "用法: llm provider <提供者名称>"
        
        provider_name = args[0]
        if self.llm_manager.set_active_provider(provider_name):
            return f"✅ 已切换到提供者: {provider_name}"
        else:
            return f"❌ 切换失败，提供者不可用: {provider_name}"
    
    def _cmd_toggle_auto(self, args: List[str]) -> str:
        """切换自动开关"""
        if args and args[0].lower() in ['on', 'off']:
            enabled = args[0].lower() == 'on'
        else:
            enabled = not self.llm_manager.is_auto_switch_enabled()
        
        self.llm_manager.enable_auto_switch(enabled)
        status = "开启" if enabled else "关闭"
        return f"✅ 智能自动切换已{status}"
    
    def _cmd_status(self, args: List[str]) -> str:
        """显示状态"""
        provider = self.llm_manager.active_provider
        result = "🤖 LLM状态:\n"
        result += f"  当前提供者: {provider.name if provider else '无'}\n"
        result += f"  当前模型: {provider.model if provider else '无'}\n"
        result += f"  自动切换: {'开启' if self.llm_manager.is_auto_switch_enabled() else '关闭'}\n"
        
        if provider:
            status = "可用" if provider.is_available() else "不可用"
            result += f"  服务状态: {status}\n"
        
        return result
    
    def _cmd_set_task(self, args: List[str]) -> str:
        """设置任务类型"""
        if not args:
            tasks = self.llm_manager.get_task_types()
            descriptions = [self.llm_manager.get_task_type_description(t) for t in tasks]
            return "可用任务类型:\n" + "\n".join(f"  - {d}" for d in descriptions)
        
        task_desc = ' '.join(args)
        
        # 查找匹配的任务类型
        tasks = self.llm_manager.get_task_types()
        for task_type in tasks:
            if self.llm_manager.get_task_type_description(task_type).lower().startswith(task_desc.lower()):
                self.llm_manager.set_task_type(task_type)
                
                if self.llm_manager.is_auto_switch_enabled():
                    self.llm_manager.switch_to_best_model(task_type)
                    return f"✅ 已设置任务类型: {task_desc}，已自动切换到最优模型"
                else:
                    return f"✅ 已设置任务类型: {task_desc}"
        
        return f"❌ 未找到匹配的任务类型: {task_desc}"
    
    def _cmd_help(self, args: List[str]) -> str:
        """显示帮助"""
        help_text = """
🤖 LLM命令行工具 (Cline集成)

用法: llm <命令> [参数]

命令列表:
  list           - 列出所有可用的LLM提供者和模型
  switch <模型>  - 切换到指定模型
  provider <名称>- 切换到指定提供者 (ollama/echobird)
  auto [on|off]  - 切换智能自动切换功能
  status         - 显示当前LLM状态
  task [类型]    - 查看或设置任务类型
  help           - 显示此帮助信息

示例:
  llm list
  llm switch gpt-4o
  llm provider echobird
  llm auto on
  llm task 量化策略
        """
        return help_text.strip()


# 全局Cline集成实例（延迟初始化）
cline_integration = None

def init_cline(llm_manager):
    """初始化Cline集成"""
    global cline_integration
    cline_integration = ClineIntegration(llm_manager)
    print("[Cline] 已初始化Cline集成")
    return cline_integration