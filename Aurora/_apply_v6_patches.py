#!/usr/bin/env python3
"""一次性应用V6全部10项补全"""
import re

with open('shepherd_v6_comprehensive.py', 'r', encoding='utf-8') as f:
    content = f.read()

orig = content
patches_applied = []

# ===================================================================
# 【1】docstring后插入架构总览注释框
# ===================================================================
arch_box = '''
# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  🏛️  V6 架构全景图（框架文档对应映射）                                      ║
# ║                                                                            ║
# ║  ┌─────────────────────────────────────────────────────────────────────┐   ║
# ║  │ Layer 0 — 数据感知层 (DataPerceptionLayer)                          │   ║
# ║  │   全量采集：回测/模拟/实盘/行情/风控/OMS延迟/盈亏/拟合误差           │   ║
# ║  ├─────────────────────────────────────────────────────────────────────┤   ║
# ║  │ Layer 1 — 自我诊断层 (DefectDiagnosisEngine)                        │   ║
# ║  │   10种缺陷识别 + 致命/严重/普通定级 + 逻辑缺陷vs参数缺陷区分         │   ║
# ║  ├─────────────────────────────────────────────────────────────────────┤   ║
# ║  │ Layer 安全 — 五行安全门禁 (FiveElementSecurityGate)                 │   ║
# ║  │   金(可持续) 木(资金) 水(风控) 火(策略) 土(兼容) 7条硬约束          │   ║
# ║  ├─────────────────────────────────────────────────────────────────────┤   ║
# ║  │ Layer 2 — 自主演化层 (SelfEvolutionEngine + GeneticEvolutionEngine) │   ║
# ║  │   逻辑∥参数解耦 + 基因进化(Pareto+协变熵) + 7条底层优化逻辑        │   ║
# ║  ├─────────────────────────────────────────────────────────────────────┤   ║
# ║  │ Layer 3 — 专家复审层 (ExpertReviewPanel)                            │   ║
# ║  │   四大专家(策略/风控/工程/成本) + 五维度百分制 + 四档落地措施       │   ║
# ║  ├─────────────────────────────────────────────────────────────────────┤   ║
# ║  │ Layer 4 — 落地归档层 (LandingArchiveLayer)                          │   ║
# ║  │   版本管理 + 迭代知识库 + 回滚机制 + 黑名单路径库                   │   ║
# ║  └─────────────────────────────────────────────────────────────────────┘   ║
# ║                                                                            ║
# ║  解耦架构: 自我优化逻辑(7条规则) ∥ 可调优参数(6大类40+参数)               ║
# ║  缺陷体系: 逻辑类5种 + 参数类4种 + 1种通用 = 10种缺陷全覆盖               ║
# ║  专家体系: 四大角色 × 五维度 × 百分制 → 四档措施(90+/70-89/60-69/<60)    ║
# ╚══════════════════════════════════════════════════════════════════════════════╝
'''

anchor1 = '# =============================================================================\n# 日志配置'
if anchor1 in content and '架构全景图' not in content:
    content = content.replace(anchor1, arch_box.strip() + '\n\n' + anchor1, 1)
    patches_applied.append('1-arch_box')

# ===================================================================
# 【2】MarketDataBundle补全timestamps, source
# ===================================================================
old_mdb = '''@dataclass
class MarketDataBundle:
    """市场数据束"""
    prices: Optional[Any] = None
    volumes: Optional[Any] = None
    fundamentals: Optional[Dict] = None
    regimes: Optional[Dict] = None
    events: Optional[List] = None
    microstructure: Optional[Dict] = None'''

new_mdb = '''@dataclass
class MarketDataBundle:
    """市场数据束"""
    prices: Optional[Any] = None
    volumes: Optional[Any] = None
    timestamps: Optional[List] = None
    source: str = "unknown"
    fundamentals: Optional[Dict] = None
    regimes: Optional[Dict] = None
    events: Optional[List] = None
    microstructure: Optional[Dict] = None'''

if old_mdb in content:
    content = content.replace(old_mdb, new_mdb)
    patches_applied.append('2-MarketDataBundle')
else:
    print('[WARN] MarketDataBundle anchor not found')
    # Try finding the class differently
    idx = content.find('class MarketDataBundle')
    if idx >= 0:
        print(f'  Found at index {idx}: ...{content[idx:idx+500]}...')

# ===================================================================
# 【3】TradingSnapshot补全oms_latency_ms, order_errors
# ===================================================================
old_ts = '''@dataclass
class TradingSnapshot:
    """交易快照"""
    active_orders: int = 0
    filled_orders: int = 0
    cancelled_orders: int = 0
    avg_fill_ms: float = 0.0
    total_commission: float = 0.0
    slippage_total: float = 0.0'''

new_ts = '''@dataclass
class TradingSnapshot:
    """交易快照"""
    active_orders: int = 0
    filled_orders: int = 0
    cancelled_orders: int = 0
    avg_fill_ms: float = 0.0
    oms_latency_ms: float = 0.0
    total_commission: float = 0.0
    slippage_total: float = 0.0
    order_errors: int = 0'''

if old_ts in content:
    content = content.replace(old_ts, new_ts, 1)
    patches_applied.append('3-TradingSnapshot')
elif 'oms_latency_ms' in content:
    patches_applied.append('3-TradingSnapshot (already done)')
else:
    print('[WARN] TradingSnapshot anchor not found')

# ===================================================================
# 【4】RiskSnapshot补全var_95, cvar_95, consecutive_losses, frozen
# ===================================================================
old_rs = '''@dataclass
class RiskSnapshot:
    """风控快照"""
    max_drawdown: float = 0.0
    current_drawdown: float = 0.0
    daily_pnl: float = 0.0
    position_ratio: float = 0.0
    margin_used: float = 0.0
    risk_alerts: int = 0'''

new_rs = '''@dataclass
class RiskSnapshot:
    """风控快照"""
    max_drawdown: float = 0.0
    current_drawdown: float = 0.0
    daily_pnl: float = 0.0
    var_95: float = 0.0
    cvar_95: float = 0.0
    position_ratio: float = 0.0
    margin_used: float = 0.0
    consecutive_losses: int = 0
    frozen: bool = False
    risk_alerts: int = 0'''

if old_rs in content:
    content = content.replace(old_rs, new_rs, 1)
    patches_applied.append('4-RiskSnapshot')
elif 'var_95' in content:
    patches_applied.append('4-RiskSnapshot (already done)')
else:
    print('[WARN] RiskSnapshot anchor not found')

# ===================================================================
# 【5】Genome补全lineage field
# ===================================================================
old_genome = '''@dataclass
class Genome:
    """基因型"""
    params: Dict[str, float] = field(default_factory=dict)
    fitness: float = 0.0
    generation: int = 0'''

new_genome = '''@dataclass
class Genome:
    """基因型"""
    params: Dict[str, float] = field(default_factory=dict)
    fitness: float = 0.0
    generation: int = 0
    lineage: Optional[str] = None'''

if old_genome in content:
    content = content.replace(old_genome, new_genome, 1)
    patches_applied.append('5-Genome')
else:
    print('[WARN] Genome anchor not found')

# ===================================================================
# 【6】DefectReport补全patches_log field
# ===================================================================
old_dr = '''@dataclass
class DefectReport:
    """缺陷报告"""
    defect_id: str
    defect_type: str
    severity: DefectSeverity
    description: str
    source_location: str
    related_rule: str
    suggested_patch: str
    metrics_evidence: Dict
    detected_at: datetime = field(default_factory=datetime.now)'''

new_dr = '''@dataclass
class DefectReport:
    """缺陷报告"""
    defect_id: str
    defect_type: str
    severity: DefectSeverity
    description: str
    source_location: str
    related_rule: str
    suggested_patch: str
    metrics_evidence: Dict
    patches_log: List[str] = field(default_factory=list)
    detected_at: datetime = field(default_factory=datetime.now)'''

if old_dr in content:
    content = content.replace(old_dr, new_dr, 1)
    patches_applied.append('6-DefectReport')
else:
    print('[WARN] DefectReport anchor not found')

# ===================================================================
# 【7】blacklisted_paths反馈 → 在diagnose()方法中追加黑名单检测
# ===================================================================
old_blacklist = '        else:\n            direction = "无缺陷，可正常迭代"\n\n        result = DiagnosisResult('
new_blacklist = '''        else:
            direction = "无缺陷，可正常迭代"

        # ── 黑名单路径检测 ──
        blacklisted_triggered = []
        for bp in self.blacklisted_paths:
            if bp in str(optimization_proposal) or bp in str(strategy_performance):
                blacklisted_triggered.append(bp)
                defects.append(self._new_defect("逻辑类", DefectSeverity.FATAL,
                    f"触发黑名单路径: {bp}",
                    "演化层·黑名单检测", "反向约束机制",
                    f"该路径已被禁止，需使用替代方案", {"blacklisted_path": bp}))
        if blacklisted_triggered:
            direction = f"黑名单触发({len(blacklisted_triggered)}条)，强制冻结迭代"

        result = DiagnosisResult('''

if old_blacklist in content:
    content = content.replace(old_blacklist, new_blacklist, 1)
    patches_applied.append('7-blacklist')
else:
    print('[WARN] blacklist anchor not found')
    # Try fuzzy match
    idx = content.find('direction = "无缺陷，可正常迭代"')
    if idx >= 0:
        print(f'  Found at {idx}: ...{content[idx:idx+200]}...')

# ===================================================================
# 【8】_generate_logic_patch补全反向约束+压力测试触发+版本日志
# ===================================================================
old_lp = '''    def _generate_logic_patch(self, defect: LogicDefect) -> str:
        mapping = {
            LogicDefectType.SINGLE_DIM_OPTIMIZATION: "新增多维权衡约束规则(收益+回撤+成本)",
            LogicDefectType.POOR_GENERALIZATION: "新增跨行情泛化校验逻辑(震荡/趋势/牛熊)",
            LogicDefectType.PRIORITY_CHAOS: "修复迭代优先级: 逻辑缺陷 > 参数缺陷 > 微调",
            LogicDefectType.COMPLIANCE_MISSING: "新增合规硬约束逻辑(交易频率/仓位限制)",
            LogicDefectType.ENGINEERING_DEFECT: "新增OMS兼容性前置校验逻辑",
        }
        return mapping.get(defect.defect_type, f"自动补丁: {defect.description}")'''

# Broader search to find it
idx_lp = content.find('def _generate_logic_patch(self, defect: LogicDefect) -> str:')
if idx_lp >= 0:
    print(f'[DEBUG] _generate_logic_patch found at {idx_lp}')
    print(f'  Context: ...{content[idx_lp:idx_lp+600]}...')

# ===================================================================
# 【9】internal_validation补全模拟盘试运行
# ===================================================================
idx_iv = content.find('def internal_validation(self, logic_patches: List[str]')
if idx_iv >= 0:
    print(f'[DEBUG] internal_validation found at {idx_iv}')
    print(f'  Context: ...{content[idx_iv:idx_iv+500]}...')

# ===================================================================
# 【10】为SelfEvolutionEngine添加_stress_test_log属性
# ===================================================================
idx_se = content.find('class SelfEvolutionEngine')
if idx_se >= 0:
    print(f'[DEBUG] SelfEvolutionEngine found at {idx_se}')
    print(f'  Context: ...{content[idx_se:idx_se+400]}...')

# ===================================================================
# 写入结果
# ===================================================================
if content != orig:
    with open('shepherd_v6_comprehensive.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print(f'\nPatches applied: {patches_applied}')
    print('File written successfully.')
else:
    print('\nNo changes made to file.')
    print(f'Attempted patches: {patches_applied}')

# 验证
with open('shepherd_v6_comprehensive.py', 'r', encoding='utf-8') as f:
    final = f.read()

print('\n=== Verification ===')
print(f'Total lines: {len(final.splitlines())}')
print(f'arch_box: {"架构全景图" in final}')
print(f'MarketDataBundle_timestamps: {"timestamps: Optional[List]" in final}')
print(f'TradingSnapshot_oms: {"oms_latency_ms" in final}')
print(f'RiskSnapshot_var: {"var_95: float = 0.0" in final}')
print(f'Genome_lineage: {"lineage: Optional[str]" in final}')
print(f'DefectReport_patches: {"patches_log: List[str]" in final}')
print(f'blacklisted_triggered: {"blacklisted_triggered" in final}')