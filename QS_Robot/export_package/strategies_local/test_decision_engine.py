#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试公转自转决策引擎
"""

import sys
import os
sys.path.insert(0, r'D:\Gupiao\升级vscode\QS_Robot')

from core.decision_engine import DecisionEngine

def test_engine():
    eng = DecisionEngine()
    
    # 测试Top 3候选股票
    test_stocks = ['000823', '000993', '601988']
    
    for code in test_stocks:
        print(f"\n{'='*50}")
        print(f"测试股票: {code}")
        print(f"{'='*50}")
        
        result = eng.evaluate(code)
        
        if 'error' in result:
            print(f"错误: {result['error']}")
            continue
        
        print(f"日期: {result.get('asof_date')}")
        print(f"regime: {result.get('regime')}")
        print(f"Q_pos: {result.get('Q_pos'):.3f}")
        print(f"zone: {result.get('zone')}")
        print(f"vol: {result.get('vol')}")
        print(f"tradable: {result.get('tradable')}")
        
        # 打印触发的NO_TRADE
        notrade = result.get('notrade', {})
        triggered = [k for k, v in notrade.items() if v.get('triggered')]
        if triggered:
            print(f"触发NO_TRADE: {triggered}")
        else:
            print("无NO_TRADE触发")

if __name__ == '__main__':
    test_engine()
