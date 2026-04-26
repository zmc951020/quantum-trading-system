from typing import Dict, List, Optional
import ollama
import json
import logging
import time
from dotenv import load_dotenv
from .utils import validate_config, desensitize, validate_input, circuit_breaker

load_dotenv()
logger = logging.getLogger(__name__)

class MemoryAbstractor:
    def __init__(self):
        self.primary_model = validate_config("PRIMARY_MODEL", "llama3.2:1b")
        self.backup_model = validate_config("BACKUP_MODEL", "qwen:1.8b")
        self.ollama_host = validate_config("OLLAMA_HOST", "http://localhost:11434")
        self.ollama_client = ollama.Client(host=self.ollama_host)
        self.retry_count = int(validate_config("RETRY_COUNT", "3"))
        self.retry_base_delay = int(validate_config("RETRY_BASE_DELAY", "1"))

    @circuit_breaker(failure_threshold=5, timeout=60)
    def extract(self, text: str, tenant_id: str, request_id: str) -> Dict[str, List]:
        text = validate_input(text)
        logger.info(f"租户{tenant_id}，请求{request_id}，开始抽象记忆，文本：{desensitize(text[:100])}")

        prompt = self._build_prompt(text)
        for i in range(self.retry_count):
            try:
                resp = self.ollama_client.generate(
                    model=self.primary_model,
                    prompt=prompt,
                    options={"temperature": 0.1, "num_predict": 2048}
                )
                result = self._parse_response(resp["response"], tenant_id, request_id)
                logger.info(f"租户{tenant_id}，请求{request_id}，抽象成功，实体数：{len(result['entities'])}")
                return result
            except json.JSONDecodeError as e:
                logger.warning(f"主模型解析失败，第{i+1}次重试，错误：{str(e)}")
                time.sleep(self.retry_base_delay * (2 ** i))
                if i == self.retry_count - 1:
                    try:
                        resp = self.ollama_client.generate(
                            model=self.backup_model,
                            prompt=prompt,
                            options={"temperature": 0.1, "num_predict": 2048}
                        )
                        return self._parse_response(resp["response"], tenant_id, request_id)
                    except Exception as backup_e:
                        logger.error(f"备份模型也失败，租户{tenant_id}，请求{request_id}")
                        raise Exception(f"记忆抽象失败：所有模型解析失败")
            except Exception as e:
                logger.warning(f"主模型调用失败，第{i+1}次重试，错误：{str(e)}")
                time.sleep(self.retry_base_delay * (2 ** i))
                if i == self.retry_count - 1:
                    logger.error(f"所有重试失败，租户{tenant_id}，请求{request_id}")
                    raise Exception(f"记忆抽象失败：{str(e)}")

    def _build_prompt(self, text: str) -> str:
        return f"""
        严格按照以下要求输出：
        1. 只输出JSON，不添加任何解释、备注、换行
        2. 字段必须完整，不可缺失
        3. 不要添加任何多余的字符，比如```json
        输出格式：
        {{
            "entities": [{{"name": "实体名", "type": "实体类型", "properties": {{"属性名": "属性值"}}}}],
            "relations": [{{"source": "源实体", "target": "目标实体", "type": "关系类型"}}],
            "events": [{{"name": "事件名", "time": "时间（无则填null）", "content": "事件内容"}}],
            "rules": [{{"condition": "条件", "action": "动作", "cycle": "周期（无则填null）"}}]
        }}
        输入文本：{text}
        """

    def _parse_response(self, response: str, tenant_id: str, request_id: str) -> Dict[str, List]:
        response = response.strip().replace("```json", "").replace("```", "").strip()
        try:
            result = json.loads(response)
            required_fields = ["entities", "relations", "events", "rules"]
            for field in required_fields:
                if field not in result or not isinstance(result[field], list):
                    result[field] = []
            return result
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败，租户{tenant_id}，请求{request_id}，响应：{desensitize(response[:100])}")
            return {"entities": [], "relations": [], "events": [], "rules": []}