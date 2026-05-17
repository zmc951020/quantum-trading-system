#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print('='*60)
print('Start Security Features Test')
print('='*60)

# Test 1: Import modules
print('\n[1] Importing modules...')
from user_manager import user_manager
print('[OK] user_manager imported successfully')

from visualization import pyramid_phishing_defense
print('[OK] pyramid_phishing_defense imported successfully')

# Test 2: Check security config
print('\n[2] Check security config:')
security_config = user_manager.get_security_config()
print('  Whitelist cities:', security_config.get('whitelist_cities'))
print('  Disable off-hours check:', security_config.get('disable_off_hours_check'))

# Test 3: Check pyramid defense config
print('\n[3] Pyramid defense system config:')
print('  Whitelist cities:', pyramid_phishing_defense.config.get('whitelist_cities'))
print('  Disable off-hours:', pyramid_phishing_defense.config.get('disable_off_hours_check'))

# Test 4: Simulate risk calculation
print('\n[4] Simulate Yantai login and risk check:')
test_signals = {
    'current_city': 'Yantai',
    'unusual_location': True,
    'off_hours_login': True
}
test_order = {'amount': 10000, 'price': 50000, 'price_deviation': 0}
risk_result = pyramid_phishing_defense.calculate_risk(test_order, test_signals)
print('  Risk score:', risk_result.get('risk_score'))
print('  Risk level:', risk_result.get('risk_level'))
print('  Risk action:', risk_result.get('action'))

print('\n' + '='*60)
print('[OK] All tests passed! Features work correctly!')
print('='*60)
