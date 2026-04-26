# Gunicorn配置文件
# 用于生产环境部署

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