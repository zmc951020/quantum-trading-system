#!/usr/bin/env python3
"""在 visualization.py 中添加 /api/strategy-info 端点"""
import os

script_dir = os.path.dirname(os.path.abspath(__file__))
filepath = os.path.join(script_dir, 'visualization.py')

with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

old = (
    "        return jsonify({'categories': {}, 'total_count': len(strategies), "
    "'active_count': 0, 'beta_count': 0})\n\n\n"
    "@app.route('/api/start-strategy', methods=['POST'])"
)

new = (
    "        return jsonify({'categories': {}, 'total_count': len(strategies), "
    "'active_count': 0, 'beta_count': 0})\n\n\n"
    "@app.route('/api/strategy-info')\n"
    "def get_strategy_info_api():\n"
    '    """获取单个策略的详细信息"""\n'
    "    strategy_name = request.args.get('name', '')\n"
    "    if not strategy_name:\n"
    "        return jsonify({'error': '请指定策略名称'}), 400\n\n"
    "    try:\n"
    "        from strategies.strategy_registry import get_strategy_info as get_info\n"
    "        info = get_info(strategy_name)\n"
    "        if info:\n"
    "            return jsonify(info)\n"
    "        return jsonify({'error': f'策略不存在: {strategy_name}'}), 404\n"
    "    except ImportError:\n"
    "        return jsonify({'error': '策略注册表不可用'}), 500\n\n\n"
    "@app.route('/api/start-strategy', methods=['POST'])"
)

if old in content:
    content = content.replace(old, new, 1)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print('SUCCESS: /api/strategy-info endpoint added to visualization.py')
else:
    print('ERROR: Could not find insertion point')
    idx = content.find('beta_count')
    if idx >= 0:
        print('Context around beta_count:')
        print(repr(content[idx:idx+400]))
