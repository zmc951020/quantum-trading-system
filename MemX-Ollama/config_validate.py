#!/usr/bin/env python3

"""
Ollama权限系统配置验证工具
工业级配置验证器
"""

import os
import sys
import json
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def check_env_file():
    """检查环境配置文件"""
    logger.info("检查环境配置文件...")
    
    if not os.path.exists('.env'):
        logger.error(".env 文件不存在")
        return False
    
    try:
        with open('.env', 'r', encoding='utf-8') as f:
            content = f.read()
        
        if 'HMAC_SECRET' in content:
            logger.info("✓ HMAC_SECRET 配置存在")
        else:
            logger.error("✗ HMAC_SECRET 配置缺失")
            return False
        
        if 'REDIS_HOST' in content:
            logger.info("✓ Redis 配置存在")
        else:
            logger.warning("⚠ Redis 配置缺失 (可选)")
        
        return True
    except Exception as e:
        logger.error(f"读取 .env 文件失败: {e}")
        return False


def check_directory_structure():
    """检查目录结构"""
    logger.info("检查目录结构...")
    
    required_dirs = [
        './data',
        './data/auth',
        './data/auth/analytics'
    ]
    
    for dir_path in required_dirs:
        if not os.path.exists(dir_path):
            try:
                os.makedirs(dir_path, exist_ok=True)
                logger.info(f"✓ 创建目录: {dir_path}")
            except Exception as e:
                logger.error(f"创建目录失败 {dir_path}: {e}")
                return False
        else:
            logger.info(f"✓ 目录存在: {dir_path}")
    
    return True


def check_python_dependencies():
    """检查Python依赖"""
    logger.info("检查Python依赖...")
    
    required_packages = [
        'fastapi',
        'uvicorn',
        'pydantic',
        'cryptography',
        'redis',
        'prometheus_client'
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package)
            logger.info(f"✓ {package} 已安装")
        except ImportError:
            missing_packages.append(package)
            logger.error(f"✗ {package} 未安装")
    
    if missing_packages:
        logger.error(f"缺少依赖包: {', '.join(missing_packages)}")
        logger.info("请运行: pip install -r requirements.txt")
        return False
    
    return True


def check_redis_connection():
    """检查Redis连接"""
    logger.info("检查Redis连接...")
    
    try:
        import redis
        
        # 从环境变量读取配置
        host = os.getenv('REDIS_HOST', 'localhost')
        port = int(os.getenv('REDIS_PORT', 6379))
        db = int(os.getenv('REDIS_DB', 2))
        
        client = redis.Redis(
            host=host,
            port=port,
            db=db,
            socket_timeout=3
        )
        
        client.ping()
        logger.info(f"✓ Redis 连接成功: {host}:{port}/{db}")
        return True
    except Exception as e:
        logger.warning(f"⚠ Redis 连接失败 (可选): {e}")
        logger.info("系统将使用本地缓存作为降级方案")
        return True


def check_kms_setup():
    """检查KMS设置"""
    logger.info("检查KMS设置...")
    
    try:
        from memx.auth import get_kms_manager
        
        kms = get_kms_manager()
        keys = kms.list_keys()
        logger.info(f"✓ KMS 初始化成功，已存储 {len(keys)} 个密钥")
        
        if 'hmac_secret' in keys:
            logger.info("✓ HMAC密钥已设置")
        else:
            logger.warning("⚠ HMAC密钥未设置，系统将自动生成")
        
        if 'cache_encryption_key' in keys:
            logger.info("✓ 缓存加密密钥已设置")
        else:
            logger.warning("⚠ 缓存加密密钥未设置，系统将自动生成")
        
        return True
    except Exception as e:
        logger.error(f"KMS 初始化失败: {e}")
        return False


def generate_validation_report():
    """生成验证报告"""
    logger.info("生成验证报告...")
    
    report = {
        "timestamp": datetime.utcnow().isoformat(),
        "checks": {
            "env_file": check_env_file(),
            "directory_structure": check_directory_structure(),
            "python_dependencies": check_python_dependencies(),
            "redis_connection": check_redis_connection(),
            "kms_setup": check_kms_setup()
        },
        "status": ""
    }
    
    # 计算总体状态
    all_passed = all(report["checks"].values())
    report["status"] = "PASS" if all_passed else "FAIL"
    
    # 保存报告
    report_file = f'validation_report_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.json'
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    logger.info(f"验证报告已保存: {report_file}")
    
    # 打印摘要
    print("\n" + "="*60)
    print("验证报告摘要")
    print("="*60)
    print(f"时间: {report['timestamp']}")
    print(f"状态: {report['status']}")
    print("\n检查结果:")
    for check, passed in report["checks"].items():
        status = "[OK] PASS" if passed else "[ERROR] FAIL"
        print(f"  {check}: {status}")
    print("="*60)
    
    if all_passed:
        print("\n🎉 所有检查通过！系统已准备就绪。")
        print("您可以运行 ./start.sh 或 ./start.bat 启动服务。")
    else:
        print("\n❌ 部分检查失败，请修复后再启动服务。")
    
    return all_passed


def main():
    """主函数"""
    print("============================================")
    print("Ollama权限系统配置验证工具")
    print("工业级配置验证器 v1.0")
    print("============================================")
    
    success = generate_validation_report()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
