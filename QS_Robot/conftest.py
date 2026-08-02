"""pytest 根配置

将项目根目录加入 sys.path，确保策略文件内部的
`from core.strategies.ths_strategies.base import THSBaseStrategy` 能正确导入。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
