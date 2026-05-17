#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
地理位置检测模块
获取真实IP地址并查询地理位置（带缓存优化）
"""
import requests
import json
import time
from typing import Dict, Optional

class GeoLocation:
    """地理位置检测类"""
    
    def __init__(self):
        self.ip_api_url = "http://ip-api.com/json/"
        self.ipinfo_url = "https://ipinfo.io/json"
        self.ip_cache = {}  # IP缓存 {ip: (city, timestamp)}
        self.cache_duration = 3600  # 缓存1小时
    
    def get_client_ip(self, request) -> Optional[str]:
        """从请求中获取客户端真实IP地址（<1ms）"""
        # 尝试从各种代理头获取真实IP
        ip_headers = [
            'X-Forwarded-For', 'X-Real-IP', 'X-Forwarded-Host', 
            'X-Forwarded-Server', 'Forwarded-For', 'Forwarded', 
            'X-Cluster-Client-IP', 'Client-IP', 'Proxy-Client-IP', 
            'WL-Proxy-Client-IP'
        ]
        
        for header in ip_headers:
            if request.headers.get(header):
                ip = request.headers.get(header)
                if ',' in ip:
                    ip = ip.split(',')[0].strip()
                return ip
        
        return request.remote_addr
    
    def get_location_from_ip(self, ip: str = None) -> Dict:
        """通过IP地址查询地理位置（带缓存）"""
        # 1. 先查缓存 (<1ms)
        if ip and ip in self.ip_cache:
            cached_city, cache_time = self.ip_cache[ip]
            if time.time() - cache_time < self.cache_duration:
                return {
                    'success': True,
                    'ip': ip,
                    'city': cached_city,
                    'from_cache': True
                }
        
        # 2. 缓存未命中，查询API (200-2000ms)
        try:
            url = self.ip_api_url
            if ip:
                url += ip
            response = requests.get(url, timeout=2)  # 缩短超时到2秒
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'success':
                    city = data.get('city', '')
                    # 保存到缓存
                    if ip:
                        self.ip_cache[ip] = (city, time.time())
                    return {
                        'success': True,
                        'ip': data.get('query', ip),
                        'country': data.get('country', ''),
                        'region': data.get('regionName', ''),
                        'city': city
                    }
        except Exception as e:
            print(f"IP查询失败: {e}")
        return {'success': False, 'city': '未知'}


geo_location = GeoLocation()
