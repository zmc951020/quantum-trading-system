import os
import logging
from typing import Optional, TypeVar
from dotenv import load_dotenv

T = TypeVar('T')
load_dotenv()
logger = logging.getLogger(__name__)

def validate_config(key: str, default: Optional[T] = None) -> T:
    value = os.getenv(key)
    if value is None:
        if default is not None:
            logger.warning(f"配置{key}缺失，使用默认值{default}")
            return default
        raise ValueError(f"致命错误：配置{key}缺失，服务无法启动")
    if isinstance(default, int):
        return int(value)
    if isinstance(default, float):
        return float(value)
    if isinstance(default, bool):
        return value.lower() in ('true', '1', 'yes')
    return value
