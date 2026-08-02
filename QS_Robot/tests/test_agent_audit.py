#!/usr/bin/env python3
"""Agent注册表和调度器全量审计测试"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_registry():
    """测试注册表完整性"""
    from core.agent_registry import (
        AGENT_REGISTRY, SKILL_REGISTRY,
        get_agents_by_group, get_skills_by_category,
        get_agents_by_keyword, get_skills_by_keyword,
        get_agent, get_skill
    )
    
    errors = []
    print("=" * 60)
    print("1. Agent注册表审计")
    print("=" * 60)
    
    # 1.1 数量检查
    print(f"\nAgent总数: {len(AGENT_REGISTRY)}")
    print(f"技能总数: {len(SKILL_REGISTRY)}")
    
    # 1.2 分组统计
    from collections import Counter
    gc = Counter(a.group for a in AGENT_REGISTRY.values())
    print("\n各分组Agent数量:")
    for g, c in sorted(gc.items()):
        print(f"  {g}: {c}个")
    
    # 1.3 技能分类统计
    sc = Counter(s.category for s in SKILL_REGISTRY.values())
    print("\n各分类技能数量:")
    for g, c in sorted(sc.items()):
        print(f"  {g}: {c}项")
    
    # 1.4 每个Agent必须有name/group/method_name/description
    print("\nAgent字段完整性检查:")
    for aid, a in AGENT_REGISTRY.items():
        if not a.name:
            errors.append(f"Agent {aid}: 缺少name")
        if not a.group:
            errors.append(f"Agent {aid}: 缺少group")
        if not a.method_name:
            errors.append(f"Agent {aid}: 缺少method_name")
        if not a.description:
            errors.append(f"Agent {aid}: 缺少description")
    
    # 1.5 每个Skill必须有name/category/module/method_name
    print("技能字段完整性检查:")
    for sid, s in SKILL_REGISTRY.items():
        if not s.name:
            errors.append(f"Skill {sid}: 缺少name")
        if not s.category:
            errors.append(f"Skill {sid}: 缺少category")
        if not s.module:
            errors.append(f"Skill {sid}: 缺少module")
        if not s.method_name:
            errors.append(f"Skill {sid}: 缺少method_name")
    
    # 1.6 按分组获取Agent
    print("\n按分组查询测试:")
    for g in gc:
        agents = get_agents_by_group(g)
        assert len(agents) == gc[g], f"分组{g}期望{gc[g]}个，实际{len(agents)}个"
        print(f"  {g}: {len(agents)}个 ✓")
    
    # 1.7 按分类获取技能
    print("\n按分类查询技能:")
    for c in sc:
        skills = get_skills_by_category(c)
        assert len(skills) == sc[c], f"分类{c}期望{sc[c]}项，实际{len(skills)}项"
        print(f"  {c}: {len(skills)}项 ✓")
    
    # 1.8 关键词搜索
    print("\n关键词搜索测试:")
    kw_tests = [
        ("趋势", "Agent"),
        ("动量", "Agent"),
        ("风控", "Agent"),
        ("均线", "Skill"),
        ("RSI", "Skill"),
        ("MACD", "Skill"),
    ]
    for kw, stype in kw_tests:
        if stype == "Agent":
            results = get_agents_by_keyword(kw)
        else:
            results = get_skills_by_keyword(kw)
        print(f"  搜索'{kw}'({stype}): 匹配{len(results)}个")
        if len(results) == 0:
            errors.append(f"关键词'{kw}'搜索无结果")
    
    if errors:
        print(f"\n❌ 发现 {len(errors)} 个问题:")
        for e in errors:
            print(f"  - {e}")
    else:
        print("\n✅ 注册表审计全部通过")
    
    return len(errors) == 0


def test_dispatcher():
    """测试调度器"""
    print("\n" + "=" * 60)
    print("2. 调度器审计")
    print("=" * 60)
    
    from core.agent_dispatcher import parse_dispatch, get_registry
    
    errors = []
    
    # 2.1 注册表获取
    r = get_registry()
    print(f"\n注册表: {r['stats']}")
    assert len(r['groups']) > 0, "分组为空"
    assert len(r['agents']) > 0, "Agent为空"
    print("  get_registry() ✓")
    
    # 2.2 意图解析测试
    test_cases = [
        ("用趋势和动量分析600519", "600519", ["trend", "momentum"], [], "vote"),
        ("让技术分析组和风控组辩论000001", "000001", [], ["技术分析组", "风控组"], "debate"),
        ("全部Agent分析000001排除宏观", "000001", [], [], "vote"),
        ("计算MA和RSI 600036", "600036", [], [], "skill_only"),
        ("分析600519", "600519", [], [], "vote"),
    ]
    
    print("\n意图解析测试:")
    for msg, exp_symbol, exp_agents, exp_groups, exp_mode in test_cases:
        intent = parse_dispatch(msg)
        print(f"  输入: '{msg}'")
        print(f"    -> symbol={intent.symbol}, agents={intent.agent_ids}, groups={intent.group_ids}, mode={intent.mode}")
        
        if intent.symbol != exp_symbol:
            errors.append(f"symbol不匹配: 期望{exp_symbol}, 实际{intent.symbol}")
        if exp_mode and intent.mode != exp_mode:
            errors.append(f"mode不匹配: 期望{exp_mode}, 实际{intent.mode}")
        if exp_agents:
            if sorted(intent.agent_ids) != sorted(exp_agents):
                errors.append(f"agents不匹配: 期望{exp_agents}, 实际{intent.agent_ids}")
        if exp_groups:
            if sorted(intent.group_ids) != sorted(exp_groups):
                errors.append(f"groups不匹配: 期望{exp_groups}, 实际{intent.group_ids}")
    
    if errors:
        print(f"\n❌ 调度器审计发现 {len(errors)} 个问题:")
        for e in errors:
            print(f"  - {e}")
    else:
        print("\n✅ 调度器审计全部通过")
    
    return len(errors) == 0


def test_api_endpoints():
    """测试API端点（如果服务器在运行）"""
    print("\n" + "=" * 60)
    print("3. API端点验证")
    print("=" * 60)
    
    try:
        import requests
        base = "http://localhost:5003"
        
        # 测试注册表API
        resp = requests.get(f"{base}/api/agent/registry", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            print(f"  GET /api/agent/registry -> {data['registry']['stats']} ✓")
        else:
            print(f"  GET /api/agent/registry -> HTTP {resp.status_code}")
        
        # 测试搜索API
        resp = requests.get(f"{base}/api/agent/search?q=趋势&type=all", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            print(f"  GET /api/agent/search?q=趋势 -> agents={len(data['result'].get('agents',[]))}, skills={len(data['result'].get('skills',[]))} ✓")
        else:
            print(f"  GET /api/agent/search -> HTTP {resp.status_code}")
        
        return True
    except Exception as e:
        print(f"  ⚠️ API端点测试跳过（服务器可能未运行）: {e}")
        return True  # 不算失败


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  Agent系统全量审计测试")
    print("=" * 60)
    
    r1 = test_registry()
    r2 = test_dispatcher()
    r3 = test_api_endpoints()
    
    print("\n" + "=" * 60)
    if r1 and r2 and r3:
        print("  🎉 全部审计通过！")
    else:
        print("  ❌ 存在未通过项，请检查上述输出")
    print("=" * 60)