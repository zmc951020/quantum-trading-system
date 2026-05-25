#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V6 Ultra Optimizer - Bernoulli-Coanda Strategy
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
log("V6 Ultra Optimizer - Starting...")
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

log("\n1. Generating test data...")

np.random.seed(42)
n_days = 500
dates = pd.date_range(start='2021-01-01', periods=n_days, freq='D')

prices = np.zeros(n_days)
prices[0] = 100.0
for i in range(1, n_days):
    if i < 150: dr = np.random.normal(0.002, 0.015)
    elif i < 300: dr = np.random.normal(-0.0015, 0.02)
    elif i < 420: dr = np.random.normal(0.0008, 0.012)
    else: dr = np.random.normal(0.0015, 0.016)
    prices[i] = prices[i-1] * (1 + dr)

data = pd.DataFrame({
    'Open': prices*(1+np.random.randn(n_days)*0.003),
    'High': np.maximum(prices, prices*(1+np.random.randn(n_days)*0.003))*(1+np.random.rand(n_days)*0.005),
    'Low': np.minimum(prices, prices*(1+np.random.randn(n_days)*0.003))*(1-np.random.rand(n_days)*0.005),
    'Close': prices,
    'Volume': np.random.randint(2000000, 15000000, n_days)
}, index=dates)

log(f"   Data: {n_days} days")

log("\n2. V6 Optimization started...")

class V6Opt:
    def __init__(self, data, ev):
        self.data = data
        self.ev = ev
        self.best_score = 0
        self.best_params = None
        self.best_result = None
        self.iter = 0
        
    def run(self, p):
        self.iter += 1
        try:
            params = BernoulliCoandaParameters()
            for k, v in p.items():
                if hasattr(params, k): setattr(params, k, v)
            strat = bernoulli_coanda_strategy(name=f"V6_{self.iter}", params=params)
            res = strat.run_backtest(self.data, 100000)
            score, ds = self.ev.eval(res)
            return score, ds, res
        except: return 0, {}, {}
    
    def optimize(self, max_iter=300):
        start = time.time()
        
        spaces = {
            'short_velocity_window': list(range(2,8)),
            'long_velocity_window': list(range(10,30)),
            'pressure_threshold': [round(x*0.05,2) for x in range(20,80)],
            'curve_window': list(range(10,25)),
            'adhere_threshold': [round(x*0.005,4) for x in range(10,50)],
            'stop_loss_atr_multiplier': [round(x*0.5,1) for x in range(20,50)],
            'take_profit_risk_reward': [round(x*0.5,1) for x in range(30,60)],
            'max_holding_days': list(range(15,40)),
        }
        
        cur = {
            'short_velocity_window': 4, 'long_velocity_window': 18,
            'pressure_threshold': 0.4, 'curve_window': 15,
            'adhere_threshold': 0.02, 'stop_loss_atr_multiplier': 2.0,
            'take_profit_risk_reward': 2.5, 'max_holding_days': 25,
        }
        
        no_improve = 0
        
        while self.iter < max_iter:
            score, ds, res = self.run(cur)
            
            if score > self.best_score:
                self.best_score = score
                self.best_params = cur.copy()
                self.best_result = res
                no_improve = 0
            else:
                no_improve += 1
            
            if self.iter % 10 == 0:
                log(f"   Iter {self.iter:3d} | Score: {score:5.2f} | Best: {self.best_score:5.2f} | "
                    f"Sp: {res.get('sharpe_ratio',0):.2f} | DD: {res.get('max_drawdown_pct',0):.1f}% | "
                    f"WR: {res.get('win_rate_pct',0):.1f}% | NoImp: {no_improve}")
            
            if self.best_score >= 9.0:
                log("\n   [SUCCESS] Target 9.0 reached!")
                break
            
            if no_improve >= 15:
                log(f"\n   [MUTATION] No improvement for {no_improve} rounds")
                k = random.choice(list(spaces.keys()))
                cur[k] = random.choice(spaces[k])
                no_improve = 0
                continue
            
            if ds:
                if ds.get('sharpe',0) < 7: cur['pressure_threshold'] *= 1.05
                if ds.get('dd',0) < 7: cur['stop_loss_atr_multiplier'] *= 0.92
                if ds.get('wr',0) < 7: cur['pressure_threshold'] *= 0.97
                if ds.get('pf',0) < 7: cur['take_profit_risk_reward'] *= 1.08
                
                cur['pressure_threshold'] = max(0.15, min(0.75, cur['pressure_threshold']))
                cur['stop_loss_atr_multiplier'] = max(1.0, min(4.5, cur['stop_loss_atr_multiplier']))
                cur['take_profit_risk_reward'] = max(1.5, min(5.5, cur['take_profit_risk_reward']))
        
        return self.best_score, self.best_params, self.best_result

ev = FGE()
opt = V6Opt(data, ev)
best_score, best_params, best_result = opt.optimize(300)

log("\n" + "="*90)
log("3. RESULTS")
log("="*90)

if best_result:
    fs, fds = ev.eval(best_result)
    grade = "S+" if fs>=9.5 else "S" if fs>=9.0 else "A" if fs>=8.0 else "B" if fs>=7.0 else "C"
    
    log(f"\n   Final Score: {fs:.2f} (Grade: {grade})")
    log("\n   Score Breakdown:")
    log(f"   {'Metric':<20} {'Score':<8} {'Target':<12} {'Actual':<12}")
    log("   " + "-"*55)
    
    names = {'sharpe':'Sharpe','dd':'Max DD','wr':'Win Rate','pf':'Profit Factor','ar':'Annual Ret','cr':'Calmar'}
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
        log(f"   {names[k]:<20} {fds[k]:<8.1f} {tgts[k]:<12} {acts[k]:<12}")
    
    log(f"\n   Total Return: {best_result.get('total_return_pct',0):+.2f}%")
    log(f"   Sharpe: {best_result.get('sharpe_ratio',0):.2f}")
    log(f"   Max DD: {best_result.get('max_drawdown_pct',0):.2f}%")
    log(f"   Trades: {best_result.get('total_trades',0)}")
    
    log("\n   Best Parameters:")
    for k, v in best_params.items():
        log(f"   {k}: {v}")
    
    os.makedirs('optimization_configs', exist_ok=True)
    with open('optimization_configs/BCQ_V6_Final.json','w') as f:
        json.dump({
            'time': datetime.now().isoformat(),
            'score': fs, 'grade': grade,
            'params': best_params,
            'metrics': {k: best_result.get(v,0) for k,v in 
                       {'sharpe_ratio':'sharpe_ratio','max_drawdown':'max_drawdown_pct',
                        'win_rate':'win_rate_pct','profit_factor':'profit_factor'}.items()}
        }, f, indent=2)
    
    log("\n   [SAVED] optimization_configs/BCQ_V6_Final.json")

log("\n" + "="*90)
log("V6 Optimization Complete!")
log("="*90)
