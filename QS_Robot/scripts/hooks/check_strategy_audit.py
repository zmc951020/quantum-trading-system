# -*- coding: utf-8 -*-
"""pre-commit 钩子：策略入口审查（22 节点）。
原内联 -c 脚本迁移至此（2026-10-21，规避 YAML 引号转义问题）。
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.strategy_entry_auditor import StrategyEntryAuditor

auditor = StrategyEntryAuditor()
result = auditor.run_all()
print(f'通过率:{result["pass_rate"]}')
assert str(result['pass_rate']).startswith('100'), f'审查未通过:{result["pass_rate"]}'
