# Gunicorn配置文件
# 用于生产环境部署

import os

# 服务器设置
bind = '0.0.0.0:8000'
workers = 4
worker_class = 'gevent'  # 使用gevent提高并发性能
timeout = 30
keepalive = 2

# 进程名称
proc_name = 'aurora_quant'

# 日志配置
accesslog = 'logs/gunicorn_access.log'
errorlog = 'logs/gunicorn_error.log'
loglevel = 'info'

# 安全设置
trusted_proxies = ['127.0.0.1']
forwarded_allow_ips = '*'

# 性能设置
buffer_size = 4096
worker_connections = 1000
max_requests = 10000
max_requests_jitter = 500

# ══════════════════════════════════════════════
# HTTPS/SSL 配置（P1-6修补项）
# ══════════════════════════════════════════════
# 启用HTTPS时将 bind 改为 0.0.0.0:443
# 开发环境可保留8000端口并使用 --certfile/--keyfile 参数
# 生产环境建议使用Nginx反向代理SSL终结

_cert_dir = os.path.join(os.path.dirname(__file__), 'certs')
_certfile = os.path.join(_cert_dir, 'server.crt')
_keyfile = os.path.join(_cert_dir, 'server.key')

# 自动检测证书是否存在，存在则启用HTTPS
if os.path.exists(_certfile) and os.path.exists(_keyfile):
    certfile = _certfile
    keyfile = _keyfile
    # 如果证书可用，切换端口为443（取消下面注释即可启用）
    # bind = '0.0.0.0:443'
    print(f"[Gunicorn] SSL证书已加载: {_certfile}")
else:
    print(f"[Gunicorn] 未检测到SSL证书，以HTTP模式运行")
    print(f"[Gunicorn] 运行 python utils/gen_certs.py 生成自签名证书")