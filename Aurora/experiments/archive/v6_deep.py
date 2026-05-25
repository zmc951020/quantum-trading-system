#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V6 Ultra Optimizer - Deep Iteration
Target: Financial Grade 9.0
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pandas as pd
from datetime import datetime
import json
import time
import random

def log(msg):
    print(msg)
    sys.stdout.flush()

log("="*90)
log("V6 ULTRA OPTIMIZER - DEEP ITERATION")
log("Target: Financial Grade 9.0")
log("="*90)

from strategies.bernoulli_coanda_strategy import (
    bernoulli_coanda_strategy,
    BernoulliCoandaParameters
)

# Evaluator
class FGE:
    def __init__(self):
        self.w = {'sharpe':0.25, 'dd':0.20, 'wr':0.15, 'pf':0.15, 'ar':0.15, 'cr':0.10}
        
    def eval(self, r):
        s = {}
        sp = r.get('sharpe_ratio', 0)
        s['sharpe'] = 10 if sp>=2.5 else 9 if sp>=2.0 else 8 if sp>=1.5 else 7 if sp>=1.0 else max(0,sp*6)
        
        dd = abs(r.get('max_drawdown_pct', 0))
        s['dd'] = 10 if dd<=3 else 9 if dd<=5 else 8 if dd<=8 else 7 if dd<=10 else max(0,10-(dd-10)*0.3)
        
        wr = r.get('win_rate_pct', 0)
        s['wr'] = 10 if wr>=70 else 9 if wr>=60 else 8 if wr>=55 else 7 if wr>=50 else max(0,(wr-40)*0.7)
        
        pf = r.get('profit_factor', 0)
        s['pf'] = 10 if pf>=3.0 else 9 if pf>=2.5 else 8 if pf>=2.0 else 7 if pf>=1.5 else max(0,pf*4)
        
        ar = r.get('annual_return_pct', 0)
        s['ar'] = 10 if ar>=30 else 9 if ar>=20 else 8 if ar>=15 else 7 if ar>=10 else max(0,ar*0.6)
        
        cr = ar/dd if dd>0 else 0
        s['cr'] = 10 if cr>=4.0 else 9 if cr>=3.0 else 8 if cr>=2.0 else 7 if cr>=1.5 else max(0,cr*4)
        
        return sum(s[k]*self.w[k] for k in self.w), s

log("\n1. Preparing enhanced test data...")

np.random.seed(123)
n_days = 600
dates = pd.date_range(start='2020-01-01', periods=n_days, freq='D')

prices = np.zeros(n_days)
prices[0] = 100.0
for i in range(1, n_days):
    if i < 120: dr = np.random.normal(0.0025, 0.012)
    elif i < 240: dr = np.random.normal(-0.0018, 0.018)
    elif i < 360: dr = np.random.normal(0.0005, 0.010)
    elif i < 480: dr = np.random.normal(0.0018, 0.014)
    else: dr = np.random.normal(0.0022, 0.016)
    prices[i] = prices[i-1] * (1 + dr)

data = pd.DataFrame({
    'Open': prices*(1+np.random.randn(n_days)*0.0025),
    'High': np.maximum(prices, prices*(1+np.random.randn(n_days)*0.0025))*(1+np.random.rand(n_days)*0.006),
    'Low': np.minimum(prices, prices*(1+np.random.randn(n_days)*0.0025))*(1-np.random.rand(n_days)*0.006),
    'Close': prices,
    'Volume': np.random.randint(2000000, 15000000, n_days)
}, index=dates)

log(f"   Data: {n_days} days, more volatility cycles")

log("\n2. Starting DEEP V6 optimization...")

class V6DeepOpt:
    def __init__(self, data, ev):
        self.data = data
        self.ev = ev
        self.best_score = 0
        self.best_params = None
        self.best_result = None
        self.iter = 0
        self.history = []
        
    def run(self, p):
        self.iter += 1
        try:
            params = BernoulliCoandaParameters()
            for k, v in p.items():
                if hasattr(params, k): setattr(params, k, v)
            strat = bernoulli_coanda_strategy(name=f"V6D_{self.iter}", params=params)
            res = strat.run_backtest(self.data, 100000)
            score, ds = self.ev.eval(res)
            return score, ds, res
        except Exception as e:
            return 0, {}, {}
    
    def optimize(self, max_iter=500):
        start = time.time()
        
        spaces = {
            'short_velocity_window': list(range(2, 9)),
            'long_velocity_window': list(range(8, 35)),
            'pressure_threshold': [round(x*0.04, 2) for x in range(15, 85)],
            'curve_window': list(range(8, 28)),
            'adhere_threshold': [round(x*0.004, 4) for x in range(8, 55)],
            'stop_loss_atr_multiplier': [round(x*0.4, 1) for x in range(18, 55)],
            'take_profit_risk_reward': [round(x*0.4, 1) for x in range(28, 70)],
            'max_holding_days': list(range(12, 45)),
            'curve_type': ['ema', 'kalman']
        }
        
        cur = {
            'short_velocity_window': 4, 'long_velocity_window': 21,
            'pressure_threshold': 0.75, 'curve_window': 18,
            'adhere_threshold': 0.11, 'stop_loss_atr_multiplier': 2.0,
            'take_profit_risk_reward': 5.5, 'max_holding_days': 25,
            'curve_type': 'ema'
        }
        
        no_improve = 0
        no_improve_limit = 25
        phase = 1
        
        while self.iter < max_iter:
            score, ds, res = self.run(cur)
            
            self.history.append({'iter': self.iter, 'score': score, 'params': cur.copy()})
            
            if score > self.best_score:
                self.best_score = score
                self.best_params = cur.copy()
                self.best_result = res
                no_improve = 0
                log(f"   [NEW BEST] Iter {self.iter:3d} | Score: {score:5.2f} | Sp: {res.get('sharpe_ratio',0):.2f} | DD: {res.get('max_drawdown_pct',0):.1f}% | WR: {res.get('win_rate_pct',0):.1f}%")
            else:
                no_improve += 1
            
            if self.iter % 15 == 0:
                elapsed = time.time() - start
                grade = "S+" if self.best_score>=9.5 else "S" if self.best_score>=9.0 else "A" if self.best_score>=8.0 else "B" if self.best_score>=7.0 else "C"
                log(f"   Progress {self.iter:3d}/{max_iter} | Best: {self.best_score:5.2f} ({grade}) | Cur: {score:5.2f} | NoImp: {no_improve} | Elapsed: {elapsed:.0f}s")
            
            if self.best_score >= 9.0:
                log(f"\n   [SUCCESS] Financial Grade 9.0 ACHIEVED at iteration {self.iter}!")
                break
            
            if no_improve >= no_improve_limit:
                phase += 1
                log(f"\n   [MUTATION PHASE {phase}] No improvement for {no_improve} rounds")
                
                for _ in range(min(phase, 3)):
                    k = random.choice(list(spaces.keys()))
                    cur[k] = random.choice(spaces[k])
                no_improve = 0
                continue
            
            if ds:
                if ds.get('sharpe',0) < 7.5:
                    cur['pressure_threshold'] *= 1.03 if random.random() > 0.5 else 0.97
                if ds.get('dd',0) < 7.5:
                    cur['stop_loss_atr_multiplier'] *= 0.94 if random.random() > 0.5 else 1.06
                if ds.get('wr',0) < 7.5:
                    cur['pressure_threshold'] *= 0.96 if random.random() > 0.5 else 1.04
                if ds.get('pf',0) < 7.5:
                    cur['take_profit_risk_reward'] *= 1.05 if random.random() > 0.5 else 0.95
                
                cur['pressure_threshold'] = max(0.10, min(0.85, cur['pressure_threshold']))
                cur['stop_loss_atr_multiplier'] = max(0.8, min(5.0, cur['stop_loss_atr_multiplier']))
                cur['take_profit_risk_reward'] = max(1.2, min(6.0, cur['take_profit_risk_reward']))
        
        return self.best_score, self.best_params, self.best_result

ev = FGE()
opt = V6DeepOpt(data, ev)
best_score, best_params, best_result = opt.optimize(500)

log("\n" + "="*90)
log("3. DEEP OPTIMIZATION RESULTS")
log("="*90)

if best_result:
    fs, fds = ev.eval(best_result)
    grade = "S+" if fs>=9.5 else "S" if fs>=9.0 else "A" if fs>=8.0 else "B" if fs>=7.0 else "C"
    
    log(f"\n   Final Score: {fs:.2f} (Grade: {grade})")
    log("\n   Score Breakdown:")
    log(f"   {'Metric':<20} {'Score':<8} {'Target':<12} {'Actual':<12}")
    log("   " + "-"*55)
    
    names = {'sharpe':'Sharpe Ratio','dd':'Max Drawdown','wr':'Win Rate','pf':'Profit Factor','ar':'Annual Return','cr':'Calmar Ratio'}
    tgts = {'sharpe':'>=2.0','dd':'<=5%','wr':'>=60%','pf':'>=2.0','ar':'>=20%','cr':'>=3.0'}
    acts = {
        'sharpe': f"{best_result.get('sharpe_ratio',0):.2f}",
        'dd': f"{best_result.get('max_drawdown_pct',0):.1f}%",
        'wr': f"{best_result.get('win_rate_pct',0):.1f}%",
        'pf': f"{best_result.get('profit_factor',0):.2f}",
        'ar': f"{best_result.get('annual_return_pct',0):.1f}%",
        'cr': f"{best_result.get('annual_return_pct',0)/max(abs(best_result.get('max_drawdown_pct',0)),0.01):.2f}"
    }
    
    for k in names:
        status = "[OK]" if fds[k] >= 8 else "[!]" if fds[k] >= 7 else "[X]"
        log(f"   {status} {names[k]:<17} {fds[k]:<8.1f} {tgts[k]:<12} {acts[k]:<12}")
    
    log(f"\n   Total Return: {best_result.get('total_return_pct',0):+.2f}%")
    log(f"   Sharpe: {best_result.get('sharpe_ratio',0):.2f}")
    log(f"   Max DD: {best_result.get('max_drawdown_pct',0):.2f}%")
    log(f"   Trades: {best_result.get('total_trades',0)}")
    log(f"   Win Rate: {best_result.get('win_rate_pct',0):.1f}%")
    log(f"   Profit Factor: {best_result.get('profit_factor',0):.2f}")
    
    log("\n   Best Parameters:")
    for k, v in best_params.items():
        log(f"   {k}: {v}")
    
    os.makedirs('optimization_configs', exist_ok=True)
    config_file = 'optimization_configs/BCQ_V6_Deep_Grade9.json'
    with open(config_file, 'w') as f:
        json.dump({
            'optimization_time': datetime.now().isoformat(),
            'final_score': fs, 'grade': grade,
            'parameters': best_params,
            'metrics': {
                'total_return': best_result.get('total_return_pct', 0),
                'sharpe_ratio': best_result.get('sharpe_ratio', 0),
                'max_drawdown': best_result.get('max_drawdown_pct', 0),
                'win_rate': best_result.get('win_rate_pct', 0),
                'profit_factor': best_result.get('profit_factor', 0),
                'annual_return': best_result.get('annual_return_pct', 0),
                'trades': best_result.get('total_trades', 0)
            }
        }, f, indent=2, ensure_ascii=False)
    
    log(f"\n   [SAVED] {config_file}")

log("\n" + "="*90)
log("V6 DEEP OPTIMIZATION COMPLETE!")
log("="*90)
