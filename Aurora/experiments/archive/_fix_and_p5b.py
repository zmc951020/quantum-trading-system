lines = open("strategies/gyro_precession_strategy.py", encoding="utf-8").readlines()
# Remove junk lines 0-4
lines = lines[5:]

# Find np.cov(ret in GyroPortfolioOpt.calc()
for i in range(len(lines)):
    if "class GyroPortfolioOpt:" in lines[i]:
        for j in range(i, min(len(lines), i+100)):
            if "np.cov(ret" in lines[j] and "Ledoit" not in lines[j-1] if j>0 else True:
                indent = lines[j][:len(lines[j])-len(lines[j].lstrip())]
                lines[j] = (
                    indent + "# P5: Ledoit-Wolf 协方差收缩\n"
                    + indent + "T,N=ret.shape; sc=np.cov(ret,rowvar=False)\n"
                    + indent + "mu=np.trace(sc)/N; d2=np.sum((sc-mu*np.eye(N))**2)/N\n"
                    + indent + "b2=min(d2,np.sum(sc**2)/N); sh=b2/d2 if d2>0 else 0.0\n"
                    + indent + "cov=sh*mu*np.eye(N)+(1-sh)*sc\n"
                )
                print(f"[P5b] Ledoit-Wolf injected at line {j} in GyroPortfolioOpt")
                break
        break

with open("strategies/gyro_precession_strategy.py", "w", encoding="utf-8") as f:
    f.writelines(lines)
print(f"Fixed. Total lines: {len(lines)}")
