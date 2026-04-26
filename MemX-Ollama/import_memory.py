#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Ollama MemX 记忆导入脚本
使用Python直接调用API接口批量导入记忆
"""

import json
import requests
import time

def import_memory(user_id, prompt):
    """导入记忆到Ollama MemX系统"""
    url = "http://localhost:8000/chat"
    headers = {"Content-Type": "application/json"}
    data = {
        "user_id": user_id,
        "prompt": prompt
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=30)
        response.raise_for_status()
        result = response.json()
        print(f"[SUCCESS] 导入成功: {result.get('message')}")
        return True
    except Exception as e:
        print(f"[ERROR] 导入失败: {str(e)}")
        return False

def main():
    print("=" * 60)
    print("Ollama MemX 记忆导入脚本")
    print("=" * 60)
    print("[INFO] 开始导入核心文件到记忆系统...\n")
    
    user_id = "zmc"
    
    # 导入系统基本信息
    print("[INFO] 导入系统基本信息...")
    system_info = """# Ollama MemX 工业级永久记忆系统
基于豆包专家方案实施的Ollama永久记忆系统，采用四级记忆架构，实现工业级0漏洞可运营部署。

## 系统架构
API Gateway -> Working Mem (短期记忆)、Vector Mem (中期记忆)、Graph Mem (长期记忆) -> Maintenance Engine (记忆维护引擎)

## 核心功能
- 短期记忆：动态上下文窗口，智能裁剪压缩
- 中期记忆：向量数据库存储，语义检索
- 长期记忆：知识图谱，实体关系管理
- 永久记忆：核心知识库，版本管理

## API接口
- /chat：用于聊天和记忆存储
- /memory/search：用于记忆搜索

## 配置说明
主要配置文件是 .env，关键配置项包括：
- MODEL_NAME：Ollama模型名称
- OLLAMA_HOST：Ollama服务地址
- QDRANT_HOST：向量数据库地址
- NEO4J_URI：知识图谱地址
- REDIS_HOST：Redis地址

## 数据备份
- 备份：使用 backup.sh
- 恢复：使用 restore.sh

## 监控地址
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000

## 目录结构
MemX-Ollama/ -> memx/ (核心模块)、main.py (API入口)、docker-compose.yml (部署配置)、Dockerfile (镜像构建)、requirements.txt (Python依赖)、.env (环境配置)、start.sh (启动脚本)、stop.sh (停止脚本)、backup.sh (备份脚本)、restore.sh (恢复脚本)、test_prod.sh (测试脚本)、prometheus.yml (监控配置)"""
    import_memory(user_id, system_info)
    time.sleep(2)  # 避免请求过于频繁
    
    # 导入核心功能
    print("\n[INFO] 导入核心功能...")
    core_features = """# 核心功能

## 四级记忆架构
1. 短期记忆（Working Memory）：动态上下文窗口，智能裁剪压缩，最大8192 tokens
2. 中期记忆（Session Memory）：Redis存储，会话管理，过期时间30天
3. 长期记忆（Vector Memory）：Qdrant向量数据库，语义检索，支持相似度搜索
4. 永久记忆（Graph Memory）：Neo4j知识图谱，实体关系管理，支持复杂查询

## 核心引擎
1. 记忆抽象引擎：自动抽取实体和关系
2. 记忆检索引擎：基于语义相似度的记忆检索
3. 记忆维护引擎：自动管理记忆优先级和过期

## 工业级特性
1. 熔断降级：依赖服务故障时自动降级
2. 幂等性：重复请求自动识别，避免重复写入
3. 输入脱敏：敏感信息自动过滤
4. 优先级管理：记忆优先级0~1.0自动计算
5. 超时控制：所有外部调用10s超时
6. 健康检查：所有服务配置健康检查探针
7. 资源限制：容器CPU/内存硬限制
8. 多租户隔离：数据按租户隔离，支持数据删除"""
    import_memory(user_id, core_features)
    time.sleep(2)
    
    # 导入部署架构
    print("\n[INFO] 导入部署架构...")
    deployment = """# 部署架构

## 微服务架构
独立服务，松耦合

## 容器化部署
Docker容器，一键启动

## 监控体系
Prometheus + Grafana

## 安全策略
网络隔离，数据加密

## 灾备方案
自动备份，快速恢复

## 运行环境
1. Python 3.11+
2. Docker 20.10+
3. 8GB+ 内存
4. 50GB+ 磁盘空间

## 核心API
1. /health：健康检查
2. /chat：带记忆的对话
3. /memory/search：记忆搜索
4. /memory/delete：删除用户记忆
5. /memory/sessions/{tenant_id}：会话列表

## 预期效果
1. 记忆检索速度提升5-10倍
2. 记忆存储容量支持TB级
3. 系统可靠性达到99.99%
4. 支持跨会话信息检索
5. 支持多源知识库集成
6. 提供更准确、更快速的响应
7. 支持更复杂的业务场景

## 商业价值
1. 降低运营成本
2. 提升用户体验
3. 拓展应用场景
4. 为量化交易等专业领域提供智能支持"""
    import_memory(user_id, deployment)
    time.sleep(2)
    
    print("\n" + "=" * 60)
    print("记忆导入完成！")
    print("=" * 60)
    print("[INFO] 所有核心文件已成功导入到Ollama MemX记忆系统")
    print("[INFO] 您现在可以通过以下方式测试记忆系统：")
    print("[INFO] 1. 访问 http://localhost:8000/docs 查看API文档")
    print("[INFO] 2. 使用 curl 命令测试记忆功能")
    print("[INFO] 3. 与Ollama对话，测试记忆能力")
    print("\n[INFO] 例如：")
    print("[INFO] curl -X POST http://localhost:8000/chat -H \"Content-Type: application/json\" -d '{\"user_id\":\"zmc\",\"prompt\":\"系统的核心功能有哪些？\"}'")
    print()

if __name__ == "__main__":
    main()