#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
增强版本地向量记忆存储
不依赖外部服务，使用本地JSON文件存储
"""

from typing import List, Dict, Optional
import logging
import time
import hashlib
import json
import os
from pathlib import Path
from .utils import desensitize, clamp_priority

logger = logging.getLogger(__name__)

class LocalVectorMemory:
    def __init__(self, storage_dir: Optional[str] = None):
        self.storage_dir = Path(storage_dir) if storage_dir else Path(__file__).parent.parent / "data" / "local_memory"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._memories: Dict[str, List[Dict]] = {}
        self._load_all_memories()

    def _get_tenant_file(self, tenant_id: str) -> Path:
        return self.storage_dir / f"memories_{tenant_id}.json"

    def _load_all_memories(self):
        for file in self.storage_dir.glob("memories_*.json"):
            tenant_id = file.stem.replace("memories_", "")
            self._load_memories(tenant_id)

    def _load_memories(self, tenant_id: str):
        try:
            file = self._get_tenant_file(tenant_id)
            if file.exists():
                with open(file, 'r', encoding='utf-8') as f:
                    self._memories[tenant_id] = json.load(f)
                logger.info(f"加载租户{tenant_id}记忆成功，共{len(self._memories[tenant_id])}条")
            else:
                self._memories[tenant_id] = []
        except Exception as e:
            logger.error(f"加载租户{tenant_id}记忆失败：{str(e)}")
            self._memories[tenant_id] = []

    def _save_memories(self, tenant_id: str):
        try:
            file = self._get_tenant_file(tenant_id)
            with open(file, 'w', encoding='utf-8') as f:
                json.dump(self._memories[tenant_id], f, ensure_ascii=False, indent=2)
            logger.info(f"保存租户{tenant_id}记忆成功")
        except Exception as e:
            logger.error(f"保存租户{tenant_id}记忆失败：{str(e)}")

    def _simple_hash_vector(self, text: str) -> List[float]:
        hash_digest = hashlib.md5(text.encode()).digest()
        vector = []
        for i in range(384):
            vector.append(float(hash_digest[i % len(hash_digest)]) / 255.0)
        return vector

    def _calculate_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        if len(vec1) != len(vec2):
            return 0.0
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = sum(a * a for a in vec1) ** 0.5
        norm2 = sum(a * a for a in vec2) ** 0.5
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot_product / (norm1 * norm2)

    def _keyword_match_score(self, text: str, query: str) -> float:
        text_lower = text.lower()
        query_lower = query.lower()
        if query_lower in text_lower:
            return 1.0
        words = query_lower.split()
        match_count = sum(1 for word in words if word in text_lower)
        return match_count / max(len(words), 1)

    def search(self, tenant_id: str, query: str, limit: int = 3) -> List[Dict]:
        try:
            if tenant_id not in self._memories:
                self._load_memories(tenant_id)
            
            memories = self._memories.get(tenant_id, [])
            if not memories:
                return []
            
            query_vector = self._simple_hash_vector(query)
            results = []
            
            for memory in memories:
                keyword_score = self._keyword_match_score(memory.get("content", ""), query)
                vector_score = self._calculate_similarity(query_vector, memory.get("vector", []))
                combined_score = 0.7 * keyword_score + 0.3 * vector_score
                
                if combined_score > 0:
                    results.append({
                        "id": memory["id"],
                        "content": desensitize(memory.get("content", "")),
                        "priority": memory.get("priority", 0.5),
                        "relevance": combined_score,
                        "timestamp": memory.get("timestamp", 0)
                    })
            
            results.sort(key=lambda x: (x["relevance"], x["priority"]), reverse=True)
            return results[:limit]
            
        except Exception as e:
            logger.error(f"本地向量检索失败，租户{tenant_id}，错误：{str(e)}")
            return []

    def add(self, tenant_id: str, content: str, metadata: Optional[Dict] = None) -> str:
        try:
            if tenant_id not in self._memories:
                self._load_memories(tenant_id)
            
            memory_id = hashlib.md5(content.encode()).hexdigest()
            timestamp = time.time()
            priority = clamp_priority(metadata.get("priority", 0.5)) if metadata else 0.5
            
            memory = {
                "id": memory_id,
                "content": content,
                "priority": priority,
                "timestamp": timestamp,
                "vector": self._simple_hash_vector(content),
                "metadata": metadata or {}
            }
            
            self._memories[tenant_id].append(memory)
            self._save_memories(tenant_id)
            
            logger.info(f"本地向量记忆添加成功，租户{tenant_id}，ID：{memory_id}")
            return memory_id
            
        except Exception as e:
            logger.error(f"本地向量记忆添加失败，租户{tenant_id}，错误：{str(e)}")
            return ""

    def delete(self, tenant_id: str, memory_id: str) -> bool:
        try:
            if tenant_id not in self._memories:
                self._load_memories(tenant_id)
            
            original_length = len(self._memories[tenant_id])
            self._memories[tenant_id] = [
                m for m in self._memories[tenant_id] if m["id"] != memory_id
            ]
            
            if len(self._memories[tenant_id]) < original_length:
                self._save_memories(tenant_id)
                logger.info(f"本地向量记忆删除成功，租户{tenant_id}，ID：{memory_id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"本地向量记忆删除失败，租户{tenant_id}，ID：{memory_id}，错误：{str(e)}")
            return False

    def get_all_memories(self, tenant_id: str) -> List[Dict]:
        if tenant_id not in self._memories:
            self._load_memories(tenant_id)
        return self._memories.get(tenant_id, [])

    def clear_memories(self, tenant_id: str) -> bool:
        try:
            self._memories[tenant_id] = []
            self._save_memories(tenant_id)
            logger.info(f"清空租户{tenant_id}记忆成功")
            return True
        except Exception as e:
            logger.error(f"清空租户{tenant_id}记忆失败：{str(e)}")
            return False
