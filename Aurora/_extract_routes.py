import re
with open('visualization.py','r',encoding='utf-8') as f:
    content = f.read()
routes = re.findall(r'@app\.route\(["\']([^"\']+)["\'].*', content)
print('=== 路由数量:', len(routes))
for i, r in enumerate(routes):
    print(f'{i+1}. {r}')