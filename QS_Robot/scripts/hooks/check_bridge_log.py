# -*- coding: utf-8 -*-
"""pre-commit 钩子：优化器桥接日志完整性检查。
原内联 -c 脚本迁移至此（2026-10-21，规避 YAML 引号转义问题）。
"""
import sys
import os

# 保证可从 QS_Robot 根目录导入 core 包
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.optimizer_bridge_log_analyzer import generate_mock_logs, parse_logs, analyze

logs = generate_mock_logs()
events = parse_logs(logs)
result = analyze(events)
coverage = result['coverage']
health = result['health_score']
print(f'覆盖率:{coverage} 健康评分:{health}/100')
assert health >= 60, f'审查未通过:健康评分 {health} < 60'
