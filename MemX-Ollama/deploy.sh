#!/bin/bash

# Ollama权限系统部署脚本
# 工业级部署工具

echo "============================================"
echo "Ollama权限系统部署脚本"
echo "工业级部署工具 v1.0"
echo "============================================"

# 检查Python环境
check_python() {
    if ! command -v python3 &> /dev/null; then
        echo "错误: Python 3 未安装"
        return 1
    fi
    
    PYTHON_VERSION=$(python3 --version | awk '{print $2}')
    echo "Python 版本: $PYTHON_VERSION"
    return 0
}

# 检查依赖
check_dependencies() {
    echo "检查依赖..."
    
    # 检查pip
    if ! command -v pip3 &> /dev/null; then
        echo "错误: pip3 未安装"
        return 1
    fi
    
    # 检查bubblewrap (可选)
    if command -v bwrap &> /dev/null; then
        echo "✓ bubblewrap 已安装"
    else
        echo "⚠ bubblewrap 未安装 (可选)"
    fi
    
    # 检查Redis (可选)
    if command -v redis-cli &> /dev/null; then
        echo "✓ Redis 客户端已安装"
    else
        echo "⚠ Redis 客户端未安装 (可选)"
    fi
    
    return 0
}

# 安装依赖
install_dependencies() {
    echo "安装Python依赖..."
    
    # 创建requirements.txt
    cat > requirements.txt << EOF
fastapi
uvicorn
pydantic
cryptography
redis
prometheus-client
EOF
    
    pip3 install -r requirements.txt
    if [ $? -ne 0 ]; then
        echo "错误: 依赖安装失败"
        return 1
    fi
    
    echo "✓ 依赖安装成功"
    return 0
}

# 配置验证
validate_config() {
    echo "验证配置..."
    
    # 创建默认配置文件
    cat > .env << EOF
# Redis配置
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=2

# 日志配置
LOG_LEVEL=INFO

# 安全配置
HMAC_SECRET=your_hmac_secret_here
EOF
    
    echo "✓ 配置文件创建成功"
    echo "⚠ 请修改 .env 文件中的 HMAC_SECRET 为安全的随机密钥"
    return 0
}

# 启动服务
start_service() {
    echo "启动服务..."
    
    # 创建启动脚本
    cat > start.sh << EOF
#!/bin/bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
EOF
    
    chmod +x start.sh
    
    echo "启动脚本创建成功: ./start.sh"
    echo "使用以下命令启动服务:"
    echo "  ./start.sh"
    
    return 0
}

# 主流程
main() {
    check_python || return 1
    check_dependencies || return 1
    install_dependencies || return 1
    validate_config || return 1
    start_service || return 1
    
    echo ""
    echo "============================================"
    echo "部署完成!"
    echo "============================================"
    echo "下一步:"
    echo "1. 修改 .env 文件中的配置"
    echo "2. 运行 ./start.sh 启动服务"
    echo "3. 访问 http://localhost:8000/docs 查看API文档"
    echo "4. 访问 http://localhost:8001 查看监控指标"
    echo "============================================"
}

# 执行主流程
main
