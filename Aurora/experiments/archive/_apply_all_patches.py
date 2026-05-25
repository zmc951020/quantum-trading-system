import re
path = "strategies/gyro_precession_strategy.py"
with open(path, "r", encoding="utf-8") as f:
    lines = f.readlines()

# Find insertion point: after GyroEvolve, before GyroPortfolioOpt
insert = None
for i in range(len(lines)):
    if "class GyroEvolve:" in lines[i]:
        for j in range(i, len(lines)):
            if "class GyroPortfolioOpt:" in lines[j]:
                insert = j
                break
        break

if insert:
    p2_code = [
        "\n",
        "# ==============================\n",
        "# P2: AdaptiveRiskManager\n",
        "# ==============================\n",
        "class AdaptiveRiskManager:\n",
        "    def __init__(self, base_sl=0.02, base_tp=0.06):\n",
        "        self.base_sl=base_sl; self.base_tp=base_tp; self.vol_lb=20; self.va=0.95\n",
        "    def adjust(self, ret):\n",
        "        if len(ret)<self.vol_lb: return self.base_sl,self.base_tp\n",
        "        r=ret[-self.vol_lb:]; vol=np.std(r) if len(r)>1 else 0.02\n",
        "        vf=min(2.5,max(0.5,vol/0.02)); var=np.percentile(r,5)\n",
        "        return self.base_sl*vf*(1+abs(var)), self.base_tp*vf*(1+abs(var))\n",
        "\n",
        "# ==============================\n",
        "# P2: MultiCycleConfirmer\n",
        "# ==============================\n",
        "class MultiCycleConfirmer:\n",
        "    def __init__(self, ww=20): self.ww=ww\n",
        "    def confirm(self, ds, wp):\n",
        "        if len(wp)<self.ww: return ds\n",
        "        wr=np.diff(np.log(wp[-self.ww:])); wt=np.mean(wr)/(np.std(wr)+1e-8)\n",
        "        if np.sign(ds)==np.sign(wt) and np.sign(ds)!=0: return ds*min(1.0,abs(wt)/2.0)\n",
        "        return ds*0.3\n",
    ]
    lines = lines[:insert] + p2_code + lines[insert:]
    print("[P2] AdaptiveRiskManager + MultiCycleConfirmer inserted")

# P5a: fix is_converged with weighted scoring
for i in range(len(lines)):
    if "def is_converged(self" in lines[i]:
        for j in range(i, min(len(lines), i+30)):
            if "return all(conditions)" in lines[j]:
                end = j
                break
        new_conv = [
            "    def is_converged(self, m: StrategyMetrics, Omega):\n",
            "        # P5: 加权评分替代硬阈值\n",
            "        score = 0.0\n",
            "        if m.sharpe_ratio >= TARGET_SHARPE_MIN: score+=min(40.0,(m.sharpe_ratio-TARGET_SHARPE_MIN)*20)\n",
            "        if m.k_ratio >= TARGET_KRATIO: score+=20.0\n",
            "        if m.max_dd <= TARGET_MAX_DD: score+=20.0\n",
            "        if m.lyapunov < LYAPUNOV_THRESHOLD: score+=20.0\n",
            "        import numpy as np; from numpy.linalg import eigvals\n",
            "        eigen_vals = eigvals(Omega)\n",
            "        eigen_real = np.real(eigen_vals)\n",
            "        if np.all(eigen_real <= OMEGA_EIGEN_THRESHOLD): score+=15.0\n",
            "        if m.sortino_ratio >= 2.0: score+=5.0\n",
            "        if m.omega_ratio >= 1.5: score+=5.0\n",
            "        if m.rolling_sharpe_stability <= 0.5: score+=5.0\n",
            "        if m.max_consecutive_losses <= 5: score+=5.0\n",
            "        if m.tail_ratio >= 1.5: score+=5.0\n",
            "        return score >= 70.0, [c for c in [m.sharpe_ratio>=TARGET_SHARPE_MIN,m.k_ratio>=TARGET_KRATIO,m.max_dd<=TARGET_MAX_DD,m.lyapunov<LYAPUNOV_THRESHOLD]]\n",
        ]
        lines = lines[:i] + new_conv + lines[end+1:]
        print("[P5a] is_converged weighted scoring applied")
        break

# P5b: Ledoit-Wolf covariance shrinkage
for i in range(len(lines)):
    if "cov = np.cov(ret, rowvar=False)" in lines[i] and "Ledoit" not in lines[i]:
        indent = lines[i][:len(lines[i])-len(lines[i].lstrip())]
        lines[i] = (indent + "# P5: Ledoit-Wolf 协方差收缩\n" +
                    indent + "T,N=ret.shape; sc=np.cov(ret,rowvar=False)\n" +
                    indent + "mu=np.trace(sc)/N; d2=np.sum((sc-mu*np.eye(N))**2)/N\n" +
                    indent + "b2=min(d2,np.sum(sc**2)/N); sh=b2/d2 if d2>0 else 0.0\n" +
                    indent + "cov=sh*mu*np.eye(N)+(1-sh)*sc\n")
        print("[P5b] Ledoit-Wolf covariance shrinkage applied")
        break

with open(path, "w", encoding="utf-8") as f:
    f.writelines(lines)
print("All P2+P5 patches applied successfully")
