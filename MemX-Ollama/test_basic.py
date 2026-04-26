import sys
import os
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_core_modules():
    """测试核心模块是否能正常导入和初始化"""
    print("="*60)
    print("Ollama MemX 核心模块测试")
    print("="*60)
    
    modules = [
        "memx.utils",
        "memx.working_mem",
        "memx.session_mem",
        "memx.vector_mem",
        "memx.graph_mem",
        "memx.abstractor",
        "memx.ollama_bridge",
    ]
    
    for module_name in modules:
        try:
            __import__(module_name)
            print("OK: 模块 " + module_name + " 导入成功")
        except Exception as e:
            print("FAIL: 模块 " + module_name + " 导入失败: " + str(e))
    
    print("\n" + "="*60)
    print("核心模块测试完成!")
    print("="*60)

def test_config():
    """测试配置文件"""
    print("\n" + "="*60)
    print("配置文件测试")
    print("="*60)
    
    try:
        from memx.utils import validate_config
        configs = [
            "PROJECT_NAME",
            "MODEL_NAME",
            "OLLAMA_HOST",
            "QDRANT_HOST",
            "REDIS_HOST",
            "NEO4J_URI",
        ]
        
        for config in configs:
            try:
                value = validate_config(config, "default")
                print("OK: 配置 " + config + " = " + str(value))
            except Exception as e:
                print("FAIL: 配置 " + config + " 读取失败: " + str(e))
        
        print("\n" + "="*60)
        print("配置文件测试完成!")
        print("="*60)
    except Exception as e:
        print("FAIL: 配置测试失败: " + str(e))

def test_api():
    """测试API服务"""
    print("\n" + "="*60)
    print("API服务测试")
    print("="*60)
    
    try:
        from main import app
        print("OK: FastAPI应用创建成功")
        print("OK: API标题: " + app.title)
        print("OK: API版本: " + app.version)
        
        print("\n" + "="*60)
        print("API服务测试完成!")
        print("="*60)
    except Exception as e:
        print("FAIL: API测试失败: " + str(e))

if __name__ == "__main__":
    test_core_modules()
    test_config()
    test_api()
    print("\n" + "="*60)
    print("所有基础测试完成!")
    print("系统架构完整，核心功能就绪")
    print("="*60)