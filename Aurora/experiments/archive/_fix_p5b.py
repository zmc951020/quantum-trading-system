import re
path = "strategies/gyro_precession_strategy.py"
with open(path, "r", encoding="utf-8") as f:
    lines = f.readlines()

found_cov = []
for i in range(len(lines)):
    if "np.cov(ret" in lines[i]:
        found_cov.append((i, lines[i].rstrip()))

for idx, line in found_cov:
    print(f"L{idx}: {line}")

# Search and replace
for i in range(len(lines)):
    s = lines[i]
    if "np.cov(ret" in s and "Ledoit" not in s and "Ledoit" not in lines[i-1] if i>0 else True:
        indent = s[:len(s)-len(s.lstrip())]
        lines[i] = (
            indent + "# P5: Ledoit-Wolf 协方差收缩\n" +
            indent + "T,N=ret.shape; sc=np.cov(ret,rowvar=False)\n" +
            indent + "mu=np.trace(sc)/N; d2=np.sum((sc-mu*np.eye(N))**2)/N\n" +
            indent + "b2=min(d2,np.sum(sc**2)/N); sh=b2/d2 if d2>0 else 0.0\n" +
            indent + "cov=sh*mu*np.eye(N)+(1-sh)*sc\n"
        )
        print(f"[P5b] Ledoit-Wolf applied at line {i}")
        break

with open(path, "w", encoding="utf-8") as f:
    f.writelines(lines)
print("Done")
