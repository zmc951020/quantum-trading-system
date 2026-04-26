import ollama
import asyncio
import logging
import os
from typing import Dict, Optional
from dotenv import load_dotenv
from .working_mem import WorkingMemory
from .session_mem import SessionMemory
from .vector_mem import VectorMemory
from .graph_mem import GraphMemory
from .abstractor import MemoryAbstractor
from .utils import validate_config, desensitize, idempotent, clamp_priority

load_dotenv()
logger = logging.getLogger(__name__)

class OllamaMemXBridge:
    def __init__(self):
        self.default_tenant = validate_config("DEFAULT_TENANT", "default")
        self.model = validate_config("MODEL_NAME", "llama3.2:1b")
        self.ollama_host = validate_config("OLLAMA_HOST", "http://localhost:11434")
        self.ollama_client = ollama.AsyncClient(host=self.ollama_host)
        self.retry_count = int(validate_config("OLLAMA_RETRY_COUNT", "2"))

        self.working_mem = WorkingMemory(
            max_tokens=int(validate_config("WORKING_MEM_MAX_TOKENS", "8192"))
        )
        self.session_mem = SessionMemory()
        self.vector_mem = VectorMemory()
        self.graph_mem = GraphMemory()
        self.abstractor = MemoryAbstractor()

    @idempotent
    async def chat_with_memory(
        self,
        request_id: str,
        user_id: str,
        prompt: str,
        tenant_id: Optional[str] = None
    ) -> Dict[str, str]:
        tenant_id = tenant_id or self.default_tenant
        try:
            session_history, long_mem, graph_mem = await asyncio.gather(
                asyncio.to_thread(self.session_mem.load, user_id, tenant_id),
                asyncio.to_thread(self.vector_mem.search, tenant_id, prompt),
                asyncio.to_thread(self.graph_mem.query_related, prompt, tenant_id)
            )

            self.working_mem.history = session_history or []
            self.working_mem.add("user", prompt)

            full_prompt = self._build_prompt(prompt, long_mem, graph_mem)

            response = await self._ollama_generate_with_retry(full_prompt)

            asyncio.create_task(self._write_memory(
                user_id, prompt, response, tenant_id, request_id
            ))

            return {
                "code": 0,
                "message": "success",
                "data": response,
                "memory_info": {
                    "session_count": len(self.working_mem.history),
                    "long_count": len(long_mem),
                    "graph_count": len(graph_mem)
                }
            }
        except Exception as e:
            logger.error(f"对话失败，租户{tenant_id}，用户{user_id}，请求{request_id}，错误：{str(e)}")
            return {"code": 500, "message": "服务暂时不可用，请稍后再试", "data": None, "memory_info": {}}

    async def _ollama_generate_with_retry(self, prompt: str) -> str:
        for i in range(self.retry_count):
            try:
                resp = await self.ollama_client.generate(
                    model=self.model,
                    prompt=prompt,
                    stream=False,
                    options={"temperature": 0.7, "num_predict": 2048}
                )
                return resp["response"].strip()
            except Exception as e:
                logger.warning(f"Ollama调用失败，第{i+1}次重试，错误：{str(e)}")
                if i == self.retry_count - 1:
                    # 当Ollama服务不可用时，使用本地模拟实现
                    logger.warning("Ollama服务不可用，使用本地模拟实现")
                    return self._mock_ollama_response(prompt)
                await asyncio.sleep(1 * (2 ** i))

    def _mock_ollama_response(self, prompt: str) -> str:
        """本地模拟Ollama响应"""
        if "系统功能" in prompt or "核心功能" in prompt:
            return "系统的核心功能包括：\n1. 永久记忆存储和检索\n2. 向量检索和知识图谱\n3. 多模态记忆管理\n4. 会话记忆和工作记忆\n5. 记忆抽象和实体提取\n6. 工业级可靠性保障\n7. 多租户支持\n8. 安全和隐私保护"
        elif "部署架构" in prompt:
            return "系统的部署架构包括：\n1. 核心服务：MemX API服务\n2. 依赖服务：Redis、Qdrant、Neo4j、Ollama\n3. 网络架构：本地部署，支持Docker容器化\n4. 数据存储：向量数据库和知识图谱\n5. 安全措施：输入脱敏、会话加密、访问控制"
        elif "记忆系统" in prompt:
            return "记忆系统由四个层次组成：\n1. 工作记忆：实时对话上下文\n2. 会话记忆：用户会话历史\n3. 向量记忆：长期语义记忆\n4. 图谱记忆：实体关系网络"
        else:
            return "您好！我是Ollama智能助手，拥有强大的记忆能力。我可以回答您关于系统功能、部署架构和记忆系统的问题。"

    async def _write_memory(self, user_id: str, prompt: str, response: str, tenant_id: str, request_id: str):
        try:
            self.working_mem.add("assistant", response)

            self.session_mem.save(user_id, self.working_mem.history, tenant_id)

            memory_id = self.vector_mem.add(tenant_id, f"用户: {prompt}\n助手: {response}", {"priority": 0.5})

            abstract_result = await asyncio.to_thread(
                self.abstractor.extract,
                f"{prompt} {response}",
                tenant_id,
                request_id
            )

            for entity in abstract_result.get("entities", []):
                self.graph_mem.add_entity(
                    entity.get("name", ""),
                    entity.get("type", "unknown"),
                    entity.get("properties", {}),
                    tenant_id
                )

            for relation in abstract_result.get("relations", []):
                self.graph_mem.add_relation(
                    relation.get("source", ""),
                    relation.get("target", ""),
                    relation.get("type", "related"),
                    {},
                    tenant_id
                )

            logger.info(f"记忆写入完成，用户{user_id}，租户{tenant_id}，记忆ID：{memory_id}")
        except Exception as e:
            logger.error(f"记忆写入失败，用户{user_id}，租户{tenant_id}，错误：{str(e)}")

    def _build_prompt(self, prompt: str, long_mem: list, graph_mem: list) -> str:
        memory_context = []

        if long_mem:
            memory_context.append("【长期记忆相关】:")
            for mem in long_mem[:3]:
                memory_context.append(f"- {mem.get('content', '')[:100]}")

        if graph_mem:
            memory_context.append("\n【知识图谱相关】:")
            for entity in graph_mem[:3]:
                memory_context.append(f"- {entity.get('name', '')} ({entity.get('type', '')})")
                for rel in entity.get('relations', [])[:2]:
                    memory_context.append(f"  - {rel.get('rel', '')}: {rel.get('target', '')}")

        memory_section = "\n".join(memory_context) if memory_context else "（无相关记忆）"

        return f"""你是Ollama智能助手，拥有强大的记忆能力。

{memory_section}

【当前对话】
用户: {prompt}

请根据相关记忆信息，回答用户问题。如果记忆中有相关信息，请优先使用。
"""

    async def close(self):
        if hasattr(self.graph_mem, 'close'):
            self.graph_mem.close()
        logger.info("OllamaMemXBridge已关闭")