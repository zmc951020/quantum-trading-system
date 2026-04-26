#!/usr/bin/env python3
"""
简化版量化交易仪表盘后端
使用Python标准库，无外部依赖
"""

import http.server
import socketserver
import json
import time
import random
from urllib.parse import urlparse, parse_qs

# 服务器端口
PORT = 8000

# 模拟数据
portfolio_data = {
    "total_value": 1000000.0,
    "total_pnl": 150000.0,
    "total_pnl_pct": 0.15,
    "sharpe_ratio": 1.5,
    "max_drawdown": -0.15
}

positions_data = {
    "positions": [
        {"symbol": "AAPL", "quantity": 100, "price": 150.0, "weight": 0.25, "pnl": 5000.0},
        {"symbol": "MSFT", "quantity": 50, "price": 300.0, "weight": 0.30, "pnl": 7500.0},
        {"symbol": "GOOG", "quantity": 20, "price": 1000.0, "weight": 0.40, "pnl": 10000.0},
    ],
    "cash": 50000.0,
    "total_positions": 3
}

history_data = {
    "dates": [f"2024-01-{i:02d}" for i in range(1, 101)],
    "values": [1000000.0 * (1 + 0.001 * i + random.normalvariate(0, 0.005)) for i in range(100)]
}

risk_data = {
    "var": -0.025,
    "cvar": -0.035,
    "confidence_level": 0.95,
    "method": "historical"
}

stress_test_data = {
    "2008_financial_crisis": {
        "scenario": "2008_financial_crisis",
        "estimated_loss": -400000.0,
        "estimated_loss_pct": -0.40,
        "stressed_var": -0.05
    },
    "2020_covid": {
        "scenario": "2020_covid",
        "estimated_loss": -350000.0,
        "estimated_loss_pct": -0.35,
        "stressed_var": -0.045
    }
}

performance_data = {
    "total_return": 0.15,
    "benchmark_return": 0.10,
    "alpha": 0.05,
    "information_ratio": 0.8,
    "selection_return": 0.03,
    "allocation_return": 0.02
}

metrics_data = {
    "sharpe_ratio": 1.5,
    "sortino_ratio": 1.8,
    "calmar_ratio": 2.0,
    "max_drawdown": -0.15,
    "win_rate": 0.6,
    "profit_factor": 1.8
}

health_data = {
    "status": "healthy",
    "uptime": 3600.0,
    "services": {
        "risk_service": "healthy",
        "performance_service": "healthy",
        "portfolio_service": "healthy",
        "database": "healthy"
    },
    "timestamp": time.time()
}

health_metrics_data = {
    "cpu_usage": 0.25,
    "memory_usage": 0.4,
    "disk_usage": 0.3,
    "api_response_time": 0.1,
    "error_rate": 0.01
}

class SimpleHTTPRequestHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        """处理GET请求"""
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        
        # 处理API请求
        if path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            response = {"message": "量化交易仪表盘API", "version": "1.0.0"}
            self.wfile.write(json.dumps(response).encode('utf-8'))
            return
            
        elif path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            response = {"status": "healthy"}
            self.wfile.write(json.dumps(response).encode('utf-8'))
            return
            
        elif path == '/api/risk/scenarios':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            scenarios = ["2008_financial_crisis", "2020_covid", "2015_stock_crash", "1987_black_monday", "2022_interest_rate_hike"]
            self.wfile.write(json.dumps(scenarios).encode('utf-8'))
            return
            
        elif path == '/api/portfolio/history':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(history_data).encode('utf-8'))
            return
            
        elif path == '/api/performance/metrics':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(metrics_data).encode('utf-8'))
            return
            
        elif path == '/api/health/status':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(health_data).encode('utf-8'))
            return
            
        elif path == '/api/health/metrics':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(health_metrics_data).encode('utf-8'))
            return
            
        # 404处理
        self.send_response(404)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        response = {"error": "Not found"}
        self.wfile.write(json.dumps(response).encode('utf-8'))
    
    def do_POST(self):
        """处理POST请求"""
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        
        # 读取请求体
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        
        try:
            data = json.loads(post_data.decode('utf-8'))
        except json.JSONDecodeError:
            data = {}
        
        # 处理API请求
        if path == '/api/risk/var':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(risk_data).encode('utf-8'))
            return
            
        elif path == '/api/risk/stress-test':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            scenario = data.get('scenario', '2008_financial_crisis')
            result = stress_test_data.get(scenario, stress_test_data['2008_financial_crisis'])
            self.wfile.write(json.dumps(result).encode('utf-8'))
            return
            
        elif path == '/api/performance/attribution':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(performance_data).encode('utf-8'))
            return
            
        elif path == '/api/portfolio/overview':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(portfolio_data).encode('utf-8'))
            return
            
        elif path == '/api/portfolio/positions':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(positions_data).encode('utf-8'))
            return
            
        # 404处理
        self.send_response(404)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        response = {"error": "Not found"}
        self.wfile.write(json.dumps(response).encode('utf-8'))
    
    def do_OPTIONS(self):
        """处理CORS预检请求"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

def main():
    """主函数"""
    print(f"启动简化版后端服务，端口: {PORT}")
    print(f"API地址: http://localhost:{PORT}")
    print(f"前端地址: http://localhost:3000")
    print("按 Ctrl+C 停止服务")
    
    with socketserver.TCPServer(("", PORT), SimpleHTTPRequestHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n服务已停止")

if __name__ == "__main__":
    main()
