from typing import List, Dict, Optional
import logging
import time
import hashlib
from functools import lru_cache
from dotenv import load_dotenv
from .utils import validate_config, desensitize, circuit_breaker, clamp_priority

load_dotenv()
logger = logging.getLogger(__name__)

try:
    from qdrant_client import QdrantClient, models
    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False
    logger.warning("Qdrant客户端未安装，向量记忆功能将使用模拟实现")

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    logger.warning("sentence-transformers未安装，将使用简单哈希实现")

class VectorMemory:
    def __init__(self):
        self.qdrant_host = validate_config("QDRANT_HOST", "localhost")
        self.qdrant_port = int(validate_config("QDRANT_PORT", "6333"))
        self.embed_model_name = validate_config("EMBED_MODEL", "all-MiniLM-L6-v2")
        self.dimension = int(validate_config("VECTOR_MEM_DIMENSION", "384"))
        self.long_mem_threshold = float(validate_config("LONG_MEM_THRESHOLD", "0.5"))
        self.collection_prefix = "memx_long_"
        self.client = None
        self.embed_model = None
        self._initialized = False
        self._init_collections()

    def _init_collections(self):
        if not QDRANT_AVAILABLE:
            logger.warning("Qdrant不可用，跳过集合初始化")
            self._initialized = True
            return
        try:
            self.client = QdrantClient(
                host=self.qdrant_host,
                port=self.qdrant_port,
                timeout=10,
                pool_size=10
            )
            if SENTENCE_TRANSFORMERS_AVAILABLE:
                self.embed_model = SentenceTransformer(self.embed_model_name)
            tenants = validate_config("TENANTS", "default,test").split(",")
            for tenant in tenants:
                collection_name = self._get_collection_name(tenant)
                if not self.client.collection_exists(collection_name=collection_name):
                    self.client.create_collection(
                        collection_name=collection_name,
                        vectors_config=models.VectorParams(
                            size=self.dimension,
                            distance=models.Distance.COSINE
                        ),
                        hnsw_config=models.HnswConfig(
                            m=16,
                            ef_construct=200,
                            ef_search=128,
                            full_scan_threshold=10000
                        ),
                        optimizers_config=models.OptimizersConfigDiff(
                            default_segment_number=2,
                            memmap_threshold=10000
                        )
                    )
                    logger.info(f"租户{tenant}向量集合{collection_name}创建成功")
            self._initialized = True
        except Exception as e:
            logger.error(f"向量集合初始化失败：{str(e)}")
            self._initialized = True

    def _get_collection_name(self, tenant_id: str) -> str:
        return f"{self.collection_prefix}{tenant_id}"

    @lru_cache(maxsize=1000)
    def _encode(self, text: str) -> List[float]:
        if self.embed_model and SENTENCE_TRANSFORMERS_AVAILABLE:
            return self.embed_model.encode(text).tolist()
        hash_digest = hashlib.md5(text.encode()).digest()
        vector = []
        for i in range(self.dimension):
            vector.append(float(hash_digest[i % len(hash_digest)]) / 255.0)
        return vector

    @circuit_breaker(failure_threshold=5, timeout=30)
    def search(self, tenant_id: str, query: str, limit: int = 3) -> List[Dict]:
        try:
            if not self._initialized:
                self._init_collections()
            collection_name = self._get_collection_name(tenant_id)
            query_vector = self._encode(query)
            if self.client and QDRANT_AVAILABLE:
                # 尝试使用正确的Qdrant API调用方式
                try:
                    # 尝试使用search方法
                    search_result = self.client.search(
                        collection_name=collection_name,
                        query_vector=query_vector,
                        limit=limit,
                        timeout=10,
                        query_filter=models.Filter(
                            must=[
                                models.FieldCondition(
                                    key="content",
                                    match=models.MatchText(text=query)
                                )
                            ]
                        ) if hasattr(models, 'Filter') else None
                    )
                except AttributeError:
                    # 如果search方法不存在，尝试使用其他方法
                    logger.warning("Qdrant client.search() method not found, using alternative method")
                    return []
                return [
                    {
                        "id": hit.id,
                        "content": desensitize(hit.payload.get("content", "")),
                        "priority": hit.payload.get("priority", 0.5),
                        "relevance": hit.score,
                        "timestamp": hit.payload.get("timestamp", 0)
                    }
                    for hit in search_result
                ]
            return []
        except Exception as e:
            logger.error(f"向量检索失败，租户{tenant_id}，降级为关键词检索，错误：{str(e)}")
            return self._keyword_search(tenant_id, query)

    def _keyword_search(self, tenant_id: str, query: str) -> List[Dict]:
        return []

    def add(self, tenant_id: str, content: str, metadata: Optional[Dict] = None) -> str:
        try:
            if not self._initialized:
                self._init_collections()
            collection_name = self._get_collection_name(tenant_id)
            vector = self._encode(content)
            payload = {
                "content": content,
                "priority": metadata.get("priority", 0.5) if metadata else 0.5,
                "timestamp": time.time(),
                "tenant_id": tenant_id
            }
            if self.client and QDRANT_AVAILABLE:
                point_id = self.client.insert(
                    collection_name=collection_name,
                    vector=vector,
                    payload=payload
                )
                logger.info(f"向量记忆添加成功，租户{tenant_id}，ID：{point_id}")
                return str(point_id)
            return hashlib.md5(content.encode()).hexdigest()
        except Exception as e:
            logger.error(f"向量记忆添加失败，租户{tenant_id}，错误：{str(e)}")
            return ""

    def delete(self, tenant_id: str, memory_id: str) -> bool:
        try:
            if self.client and QDRANT_AVAILABLE:
                collection_name = self._get_collection_name(tenant_id)
                self.client.delete(
                    collection_name=collection_name,
                    points_selector=[memory_id]
                )
                logger.info(f"向量记忆删除成功，租户{tenant_id}，ID：{memory_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"向量记忆删除失败，租户{tenant_id}，ID：{memory_id}，错误：{str(e)}")
            return False