from typing import Dict, List, Optional
import logging
import time
from dotenv import load_dotenv
from .utils import validate_config, desensitize, circuit_breaker

load_dotenv()
logger = logging.getLogger(__name__)

try:
    from neo4j import GraphDatabase
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False
    logger.warning("Neo4j驱动未安装，知识图谱功能将使用模拟实现")

class GraphMemory:
    def __init__(self):
        self.neo4j_uri = validate_config("NEO4J_URI", "bolt://localhost:7687")
        self.neo4j_user = validate_config("NEO4J_USER", "neo4j")
        self.neo4j_password = validate_config("NEO4J_PASSWORD", "password")
        self.driver = None
        self._initialized = False
        self._init_driver()

    def _init_driver(self):
        if not NEO4J_AVAILABLE:
            logger.warning("Neo4j不可用，跳过驱动初始化")
            self._initialized = True
            return
        try:
            self.driver = GraphDatabase.driver(
                self.neo4j_uri,
                auth=(self.neo4j_user, self.neo4j_password)
            )
            self.driver.verify_connectivity()
            self._initialized = True
            logger.info("Neo4j连接成功")
        except Exception as e:
            logger.error(f"Neo4j连接失败：{str(e)}")
            self.driver = None
            self._initialized = True

    def add_entity(self, name: str, entity_type: str, properties: Dict, tenant_id: str = "default") -> bool:
        try:
            if not self._initialized:
                self._init_driver()
            if not self.driver:
                logger.warning("Neo4j不可用，跳过实体添加")
                return False
            with self.driver.session() as session:
                result = session.run("""
                    MERGE (e:Entity {name: $name, tenant_id: $tenant_id})
                    SET e.type = $type, e += $props, e.updated_at = $updated_at
                    RETURN e.name as name
                """, name=name, tenant_id=tenant_id, type=entity_type, props=properties, updated_at=time.time())
                record = result.single()
                if record:
                    logger.info(f"知识图谱实体添加成功，租户{tenant_id}，实体：{name}")
                    return True
            return False
        except Exception as e:
            logger.error(f"知识图谱实体添加失败，租户{tenant_id}，实体：{name}，错误：{str(e)}")
            return False

    def add_relation(self, source: str, target: str, relation_type: str, properties: Dict = None, tenant_id: str = "default") -> bool:
        try:
            if not self._initialized:
                self._init_driver()
            if not self.driver:
                logger.warning("Neo4j不可用，跳过关系添加")
                return False
            props = properties or {}
            with self.driver.session() as session:
                result = session.run("""
                    MATCH (s:Entity {name: $source, tenant_id: $tenant_id})
                    MATCH (t:Entity {name: $target, tenant_id: $tenant_id})
                    MERGE (s)-[r:RELATES {type: $rel_type}]->(t)
                    SET r += $props, r.updated_at = $updated_at
                    RETURN s.name as source, t.name as target
                """, source=source, target=target, tenant_id=tenant_id, rel_type=relation_type, props=props, updated_at=time.time())
                record = result.single()
                if record:
                    logger.info(f"知识图谱关系添加成功，租户{tenant_id}，{source}->{target}")
                    return True
            return False
        except Exception as e:
            logger.error(f"知识图谱关系添加失败，租户{tenant_id}，{source}->{target}，错误：{str(e)}")
            return False

    @circuit_breaker(failure_threshold=5, timeout=30)
    def query_related(self, query: str, tenant_id: str = "default", limit: int = 5) -> List[Dict]:
        try:
            if not self._initialized:
                self._init_driver()
            if not self.driver:
                logger.warning("Neo4j不可用，返回空结果")
                return []
            keywords = query.split()[:3]
            with self.driver.session() as session:
                result = session.run("""
                    MATCH (e:Entity)
                    WHERE e.tenant_id = $tenant_id AND (
                        any(keyword IN $keywords WHERE e.name CONTAINS keyword OR e.type CONTAINS keyword)
                    )
                    OPTIONAL MATCH (e)-[r]-(related)
                    WHERE related.tenant_id = $tenant_id
                    RETURN e.name as entity, e.type as type, e, collect({rel: type(r), target: related.name}) as relations
                    LIMIT $limit
                """, tenant_id=tenant_id, keywords=keywords, limit=limit)
                entities = []
                for record in result:
                    entities.append({
                        "name": record["entity"],
                        "type": record["type"],
                        "properties": dict(record["e"]) if record["e"] else {},
                        "relations": [r for r in record["relations"] if r.get("target")]
                    })
                logger.info(f"知识图谱查询成功，租户{tenant_id}，查询：{query}，结果：{len(entities)}个实体")
                return entities
        except Exception as e:
            logger.error(f"知识图谱查询失败，租户{tenant_id}，查询：{query}，错误：{str(e)}")
            return []

    def delete_entity(self, name: str, tenant_id: str = "default") -> bool:
        try:
            if not self.driver:
                return False
            with self.driver.session() as session:
                session.run("""
                    MATCH (e:Entity {name: $name, tenant_id: $tenant_id})
                    DETACH DELETE e
                """, name=name, tenant_id=tenant_id)
                logger.info(f"知识图谱实体删除成功，租户{tenant_id}，实体：{name}")
                return True
        except Exception as e:
            logger.error(f"知识图谱实体删除失败，租户{tenant_id}，实体：{name}，错误：{str(e)}")
            return False

    def delete_user_data(self, tenant_id: str) -> bool:
        try:
            if not self.driver:
                return False
            with self.driver.session() as session:
                session.run("""
                    MATCH (e:Entity {tenant_id: $tenant_id})
                    DETACH DELETE e
                """, tenant_id=tenant_id)
                logger.info(f"租户{tenant_id}的所有知识图谱数据已删除")
                return True
        except Exception as e:
            logger.error(f"租户{tenant_id}知识图谱数据删除失败，错误：{str(e)}")
            return False

    def close(self):
        if self.driver:
            self.driver.close()
            logger.info("Neo4j连接已关闭")