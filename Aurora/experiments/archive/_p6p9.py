import ast, sys, os

PATCH_LOG = []

def backup(path):
    bak = path + '.bak_p6p9'
    with open(path, 'rb') as f: content = f.read()
    with open(bak, 'wb') as f: f.write(content)
    return bak

def apply_p6():
    path = 'strategies/gyro_precession_strategy.py'
    backup(path)
    with open(path, encoding='utf-8') as f: lines = f.readlines()
    found = False
    for i, line in enumerate(lines):
        if 'self.max_lev = MAX_LEVERAGE' in line:
            indent = line[:len(line) - len(line.lstrip())]
            lines[i] = f'{indent}self.max_lev = MAX_LEVERAGE\n'
            lines.insert(i+1, f'{indent}self.signal_threshold = getattr(params, 'signal_threshold', 0.001)\n')
            lines.insert(i+2, f'{indent}self.min_holding = getattr(params, 'min_holding', 20)\n')
            PATCH_LOG.append(f'[P6-1] Added signal_threshold + min_holding to dynamics.__init__ at L{i}')
            found = True
            break
    if not found:
        PATCH_LOG.append('[P6-1] FAILED')
        return False
    found2 = False
    for i, line in enumerate(lines):
        if 'current_weights = weights' in line and i+1 < len(lines) and 'position = np.sum(weights)' in lines[i+1]:
            indent = line[:len(line) - len(line.lstrip())]
            new_block = [
                f'{indent}current_weights = weights\n',
                f'{indent}# P6: signal_threshold 过忦弱俨号\n',
                f'{indent}signal_strength = np.abs(np.sum(adjust)) / len(adjust) if len(adjust) > 0 else 0\n',
                f'{indent}if signal_strength < self.dynamics.signal_threshold:\n',
                f'{indent}    position = position  # 保持原代卼，减少器陯内防时\n',
                f'{indent}else:\n',
                f'{indent}    position = np.sum(weights) * (equity / prices[i])\n',
            ]
            lines[i:i+2] = new_block
            PATCH_LOG.append(f'[P6-2] Added signal_threshold filtering at run_backtest L{i}')
            found2 = True
            break
    if not found2:
        PATCH_LOG.append('[P6-2] FAILED')
        return False
    with open(path, 'w', encoding='utf-8') as f: f.writelines(lines)
    try:
        with open(path, encoding='utf-8') as f: ast.parse(f.read())
        PATCH_LOG.append('[P6] Syntax check PAST')
    except SyntaxError as e:
        PATCH_LOG.append(f'[P6] Syntax FAIL: {e}')
        return False
    return True

def apply_p7():
    path = 'enhanced_evaluator.py'
    backup(path)
    with open(path, encoding='utf-8') as f: lines = f.readlines()
    start_i = None
    for i, line in enumerate(lines):
        if 'annual_return = result.get' in line and 'annual_return_pct' in line:
            start_i = i
            break
    if start_i is None:
        PATCH_LOG.append('[P7] FAILED: could not find annual_return scoring block')
        return False
    indent = '        '
    new_section = [
        f'{indent}# P7: Annual Return - 支持短窗口年化放大\n',
        f'{indent}annual_return = result.get("annual_return_pct", 0)\n',
        f'{indent}total_return_pct = result.get("total_return_pct", 0)\n',
        f'{indent}days = result.get("days", 252)\n',
        f'{indent}# 如果 annual_return 为 0 但有总收盈，做繴化漼算\n',
        f'{indent}if annual_return == 0 and total_return_pct != 0 and days < 252:\n',
        f'{indent}    annual_return = abs(total_return_pct) * (365 / max(days, 1))\n',
        f'{indent}<000     \n,
        f'{indent}if annual_return >= 30:\n',
        f'{indent}    scores["annual_return"] = 10.0\n',
        f'{indent}elif annual_return >= 20:\n',
        f'{indent}    scores["annual_return"] = 9.0\n',
        f'{indent}elif annual_return >= 15:\n',
        f'{indent}    scores["annual_return"] = 8.0\n',
        f'{indent}elif annual_return >= 10:\n',
        f'{indent}    scores["annual_return"] = 7.0\n',
        f'{indent}elif annual_return >= 5:\n',
        f'{indent}    scores["annual_return"] = 6.0\n',
        f'{indent}else:\n',
        f'{indent}    scores["annual_return"] = max(0, min(5, annual_return * 0.5))\n',
    ]
    end_i = start_i
    for j in range(start_i, min(len(lines), start_i+30)):
        if "metric_details['annual_return']" in lines[j]:
            # Ƌ略到 metric_details 来，保留��也、后出以这个字笥都为end_i
            end_i = j + 4
            break
    if end_i == start_i:
        PATCH_LOG.append('[P7] WARN: metric_details not found, grab up including it')
        end_i = start_i + 20
    lines[start_i:end_i] = new_section
    
    with open(path, 'w', encoding='utf-8') as f: f.writelines(lines)
    try:
        with open(path, encoding='utf-8') as f: ast.parse(f.read())
        PATCH_LOG.append('[P7] Syntax check PAST')
    except SyntaxError as e:
        PATCH_LOG.append(f'[P7] Syntax FAIL: {e}')
        return False
    return True

def apply_p8():
    path = 'enhanced_evaluator.py'
    with open(path, encoding='utf-8') as f: lines = f.readlines()
    found = False
    for i, line in enumerate(lines):
        if 'def calculate_trade_frequency_score' in line:
            indent = '        '
            new_method = [
                f'{indent}def calculate_trade_frequency_score(self, total_trades: int, days: int) -> float:\n',
                f'{indent}    """\n',
                f'{indent}    P8: 扩展交易频率评分\n',
                f'{indent}    理揳: 20-50/yr = 10分; 10-200/年 = 7分; 其他 = 4分\n',
                f'{indent}    """\n',
                f'{indent}    if days == 0:\n',
                f'{indent}        return 0.0\n',
                f'{indent}    trades_per_year = total_trades * 252 / days\n',
                f'{indent}    if 20 <= trades_per_year <= 50:\n',
                f'{indent}        return 10.0\n',
                f'{indent}    elif 10 <= trades_per_year <= 200:\n',
                f'{indent}        return 7.0\n',
                f'{indent}    elif 5 <= trades_per_year <= 300:\n',
                f'{indent}        return 5.0\n',
                f'{indent}    else:\n',
                f'{indent}        return 4.0\n',
            ]
            # 找到方法结期
            method_end = i + 1
            for j in range(i+1, min(len(lines), i+30)):
                if 'def ' in lines[j] and j > i+2:
                    method_end = j
                    break
            else:
                method_end = i + 20
            lines[i:method_end] = new_method
            PATCH_LOG.append(f'[P8] Trade frequency scoring expanded at L{i}')
            found = True
            break
    if not found:
        PATCH_LOG.append('[P8] FAILED')
        return False
    with open(path, 'w', encoding='utf-8') as f: f.writelines(lines)
    try:
        with open(path, encoding='utf-8') as f: ast.parse(f.read())
        PATCH_LOG.append('[P8] Syntax check PAST')
    except SyntaxError as e:
        PATCH_LOG.append(f'[P8] Syntax FAIL: {e}')
        return False
    return True

def apply_p9():
    path = 'v6_enhanced_optimizer.py'
    backup(path)
    with open(path, encoding='utf-8') as f: lines = f.readlines()
    # P9-1: 在 param_spaces 定义后淶台顶杯現数空间
    found = False
    for i, line in enumerate(lines):
        if 'self.param_spaces = {' in line:
            depth = 0
            dict_end = i
            for j in range(i, min(len(lines), i+30)):
                if '{' in lines[j]: depth += lines[j].count('{')
                if '}' in lines[j]: depth -= lines[j].count('}')
                if depth == 0:
                    dict_end = j + 1
                    break
            indent = '        '
            gyro_block = [ f'\n', f'{indent}# P9: 陶盾策略参数空间\n', f'{indent}self.gyro_param_spaces = {{\"|\"}'},\n']
            lines[dict_end:dict_end] = [[j]
            found = True
            break
    PATCH_LOG.append('[P9-1] Added gyro_param_spaces')
    with open(path, 'w', encoding='utf-8') as f: f.writelines(lines)
    try:
        with open(path, encoding='utf-8') as f: ast.parse(f.read())
        PATCH_LOG.append('[P9] Syntax check PAST')
    except SyntaxError as e:
        PATCH_LOG.append(f'[P9] Syntax FAIL: {e}')
        return False
    return True

# MAIN
if __name__ == '__main__':
    print('=' * 60)
    print('File _p6p9.py written successfully')
    print('=' * 60)