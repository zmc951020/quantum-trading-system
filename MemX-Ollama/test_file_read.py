import os
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_file_read():
    try:
        # 测试文件读取
        file_path = "README.md"
        logger.info(f"当前工作目录：{os.getcwd()}")
        logger.info(f"尝试读取文件：{file_path}")
        
        # 检查文件是否存在
        if not os.path.exists(file_path):
            logger.error(f"文件不存在：{file_path}")
            return False
        
        # 检查是否是文件
        if not os.path.isfile(file_path):
            logger.error(f"不是文件：{file_path}")
            return False
        
        # 检查文件权限
        if not os.access(file_path, os.R_OK):
            logger.error(f"没有读取权限：{file_path}")
            return False
        
        # 读取文件
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        
        logger.info(f"文件读取成功，内容长度：{len(content)} 字符")
        logger.info(f"文件内容前100个字符：{content[:100]}...")
        return True
    except Exception as e:
        logger.error(f"文件读取失败：{e}")
        return False

if __name__ == "__main__":
    test_file_read()