"""
API接口签名 + HMAC-SHA256 + 防重放攻击
==========================================
修补项 P0-4：API接口签名 ✅

功能：
- HMAC-SHA256 请求签名
- Nonce防重放攻击
- 时间戳窗口验证（默认5分钟）
- 请求体MD5校验
- 签名生成 + 验证双接口
- Nonce缓存管理
"""

import os
import time
import hmac
import hashlib
import logging
from typing import Optional, Dict, Tuple
from urllib.parse import urlencode, quote
from collections import OrderedDict
from threading import Lock

logger = logging.getLogger(__name__)

# ============================================================
# 配置
# ============================================================
API_SECRET = os.environ.get("API_SIGN_SECRET", "aurora-api-sign-secret-change-me")
DEFAULT_EXPIRE_SECONDS = 300  # 签名有效期5分钟
MAX_NONCE_CACHE = 10000       # Nonce缓存上限

# Nonce缓存（防重放）
_nonce_cache: Dict[str, float] = {}
_nonce_lock = Lock()

# 定期清理过期Nonce
_last_cleanup = time.time()
CLEANUP_INTERVAL = 300  # 每5分钟清理一次


# ============================================================
# 签名生成
# ============================================================
def generate_signature(
    method: str,
    path: str,
    params: Optional[Dict[str, str]] = None,
    body: Optional[str] = None,
    secret: Optional[str] = None,
    nonce: Optional[str] = None,
    timestamp: Optional[int] = None,
) -> Tuple[str, Dict[str, str]]:
    """
    生成API请求签名
    
    Args:
        method: HTTP方法（GET/POST/PUT/DELETE）
        path: API路径（如 /api/v1/order）
        params: URL查询参数
        body: 请求体JSON字符串
        secret: 签名密钥（默认使用环境变量）
        nonce: 随机数（不传则自动生成）
        timestamp: Unix时间戳（不传则使用当前时间）
    
    Returns:
        (signature, headers_dict): 签名hex字符串 + 请求头字典
    """
    if secret is None:
        secret = API_SECRET
    
    if timestamp is None:
        timestamp = int(time.time())
    
    if nonce is None:
        nonce = hashlib.sha256(os.urandom(32)).hexdigest()[:16]
    
    # 构造签名字符串
    canonical_str = _build_canonical_string(
        method=method.upper(),
        path=path,
        params=params or {},
        body=body,
        nonce=nonce,
        timestamp=str(timestamp),
    )
    
    # HMAC-SHA256签名
    signature = hmac.new(
        secret.encode('utf-8'),
        canonical_str.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    headers = {
        "X-Api-Signature": signature,
        "X-Api-Timestamp": str(timestamp),
        "X-Api-Nonce": nonce,
    }
    
    if body:
        headers["X-Api-Body-MD5"] = hashlib.md5(body.encode('utf-8')).hexdigest()
    
    logger.debug(f"生成签名: {signature[:8]}... path={path} ts={timestamp}")
    
    return signature, headers


def _build_canonical_string(
    method: str,
    path: str,
    params: Dict[str, str],
    body: Optional[str],
    nonce: str,
    timestamp: str,
) -> str:
    """
    构造规范化的签名字符串
    
    格式:
    {METHOD}\n
    {PATH}\n
    {SORTED_PARAMS}\n
    {BODY_MD5}\n
    {NONCE}\n
    {TIMESTAMP}
    """
    # 参数排序（保证双方签名一致）
    sorted_params = ""
    if params:
        sorted_items = sorted(params.items(), key=lambda x: x[0])
        sorted_params = "&".join(
            f"{quote(k, safe='')}={quote(v, safe='')}" for k, v in sorted_items
        )
    
    # 请求体MD5
    body_md5 = hashlib.md5(body.encode('utf-8')).hexdigest() if body else ""
    
    canonical = "\n".join([
        method.upper(),
        path,
        sorted_params,
        body_md5,
        nonce,
        timestamp,
    ])
    
    return canonical


# ============================================================
# 签名验证
# ============================================================
def verify_signature(
    method: str,
    path: str,
    signature: str,
    nonce: str,
    timestamp: str,
    params: Optional[Dict[str, str]] = None,
    body: Optional[str] = None,
    secret: Optional[str] = None,
    expire_seconds: int = DEFAULT_EXPIRE_SECONDS,
) -> Tuple[bool, str]:
    """
    验证API请求签名
    
    Args:
        method: HTTP方法
        path: API路径
        signature: 客户端传来的签名
        nonce: 客户端传来的Nonce
        timestamp: 客户端传来的时间戳
        params: URL参数
        body: 请求体
        secret: 签名密钥
        expire_seconds: 签名有效期（秒）
    
    Returns:
        (is_valid, error_message): 验证结果 + 错误信息
    """
    # 1. 时间戳校验
    try:
        ts = int(timestamp)
    except (ValueError, TypeError):
        return False, "无效的时间戳格式"
    
    current_ts = int(time.time())
    time_diff = abs(current_ts - ts)
    
    if time_diff > expire_seconds:
        return False, f"签名已过期（时间差: {time_diff}秒，最大允许: {expire_seconds}秒）"
    
    # 2. Nonce防重放检查
    if not _check_nonce(nonce, current_ts):
        return False, "Nonce已被使用（重放攻击）"
    
    # 3. 本地计算签名并比对
    if secret is None:
        secret = API_SECRET
    
    expected_signature, _ = generate_signature(
        method=method,
        path=path,
        params=params,
        body=body,
        secret=secret,
        nonce=nonce,
        timestamp=ts,
    )
    
    # 常量时间比较（防时序攻击）
    if not hmac.compare_digest(expected_signature, signature):
        logger.warning(f"签名验证失败: path={path}, nonce={nonce}")
        return False, "签名不匹配"
    
    # 4. 记录Nonce
    _record_nonce(nonce)
    
    logger.debug(f"签名验证通过: path={path}, nonce={nonce[:8]}...")
    return True, ""


def _check_nonce(nonce: str, current_ts: int) -> bool:
    """
    检查Nonce是否已被使用
    
    返回False表示重放攻击
    """
    with _nonce_lock:
        # 定期清理过期Nonce
        _cleanup_expired_nonces(current_ts)
        
        if nonce in _nonce_cache:
            return False
        return True


def _record_nonce(nonce: str):
    """记录Nonce到缓存"""
    with _nonce_lock:
        if len(_nonce_cache) >= MAX_NONCE_CACHE:
            # LRU: 清理一半旧Nonce
            sorted_items = sorted(_nonce_cache.items(), key=lambda x: x[1])
            for old_nonce, _ in sorted_items[:MAX_NONCE_CACHE // 2]:
                del _nonce_cache[old_nonce]
        
        _nonce_cache[nonce] = time.time()


def _cleanup_expired_nonces(current_ts: int):
    """清理过期的Nonce记录"""
    global _last_cleanup
    
    if current_ts - _last_cleanup < CLEANUP_INTERVAL:
        return
    
    expire_threshold = current_ts - DEFAULT_EXPIRE_SECONDS * 2
    expired = [n for n, t in _nonce_cache.items() if t < expire_threshold]
    
    for n in expired:
        del _nonce_cache[n]
    
    if expired:
        logger.debug(f"清理了 {len(expired)} 个过期Nonce")
    
    _last_cleanup = current_ts


# ============================================================
# Flask中间件
# ============================================================
def init_api_signer(app, require_sign: bool = False,
                    excluded_paths: Optional[list] = None):
    """
    为Flask应用注册API签名中间件
    
    Args:
        app: Flask应用实例
        require_sign: 是否强制要求签名（False时仅在提供了签名头时验证）
        excluded_paths: 不需要签名的路径
    
    用法:
    from utils.api_signer import init_api_signer
    init_api_signer(app, require_sign=True, excluded_paths=["/api/health"])
    """
    if excluded_paths is None:
        excluded_paths = ["/api/health", "/api/status", "/api/auth/login"]
    
    @app.before_request
    def check_api_signature():
        """请求前：验证API签名"""
        from flask import request, jsonify
        
        path = request.path
        
        # 排除路径
        for excluded in excluded_paths:
            if path.startswith(excluded):
                return None
        
        # 提取签名头
        signature = request.headers.get("X-Api-Signature", "")
        nonce = request.headers.get("X-Api-Nonce", "")
        timestamp = request.headers.get("X-Api-Timestamp", "")
        
        # 如果没有签名头 & 不强制要求 → 跳过
        if not signature and not require_sign:
            return None
        
        # 如果强制要求但缺少签名头
        if require_sign and not (signature and nonce and timestamp):
            return jsonify({
                "error": "missing_signature",
                "message": "缺少API签名头 (X-Api-Signature/X-Api-Nonce/X-Api-Timestamp)",
                "code": 401,
            }), 401
        
        # 验证签名
        body = request.get_data(as_text=True) or None
        params = dict(request.args)
        
        is_valid, err_msg = verify_signature(
            method=request.method,
            path=path,
            signature=signature,
            nonce=nonce,
            timestamp=timestamp,
            params=params,
            body=body,
        )
        
        if not is_valid:
            logger.warning(f"API签名验证失败: {path} - {err_msg}")
            return jsonify({
                "error": "invalid_signature",
                "message": f"API签名验证失败: {err_msg}",
                "code": 401,
            }), 401
        
        # 可选：将API密钥标识存入g对象
        # g.api_client = identify_client(signature)
    
    logger.info(f"API签名中间件已注册，强制模式: {require_sign}")


# ============================================================
# 便捷验证装饰器
# ============================================================
def require_api_sign(func):
    """
    要求API签名的装饰器（单个路由级别）
    
    用法:
    @app.route("/api/v1/order", methods=["POST"])
    @require_api_sign
    def create_order():
        ...
    """
    from functools import wraps
    from flask import request, jsonify
    
    @wraps(func)
    def wrapper(*args, **kwargs):
        signature = request.headers.get("X-Api-Signature", "")
        nonce = request.headers.get("X-Api-Nonce", "")
        timestamp = request.headers.get("X-Api-Timestamp", "")
        
        if not (signature and nonce and timestamp):
            return jsonify({
                "error": "missing_signature",
                "message": "此接口需要API签名",
                "code": 401,
            }), 401
        
        body = request.get_data(as_text=True) or None
        params = dict(request.args)
        
        is_valid, err_msg = verify_signature(
            method=request.method,
            path=request.path,
            signature=signature,
            nonce=nonce,
            timestamp=timestamp,
            params=params,
            body=body,
        )
        
        if not is_valid:
            return jsonify({
                "error": "invalid_signature",
                "message": f"API签名验证失败: {err_msg}",
                "code": 401,
            }), 401
        
        return func(*args, **kwargs)
    return wrapper


# ============================================================
# 客户端辅助函数
# ============================================================
def create_signed_headers(
    method: str,
    path: str,
    params: Optional[Dict[str, str]] = None,
    body: Optional[str] = None,
    secret: Optional[str] = None,
) -> Dict[str, str]:
    """
    为HTTP请求添加签名头（客户端使用）
    
    用法:
    import requests
    headers = create_signed_headers("POST", "/api/v1/order", body='{"symbol":"000001"}')
    resp = requests.post(url, headers=headers, json={"symbol": "000001"})
    """
    _, headers = generate_signature(
        method=method,
        path=path,
        params=params,
        body=body,
        secret=secret,
    )
    return headers


def get_nonce_cache_size() -> int:
    """获取当前Nonce缓存大小（用于监控）"""
    with _nonce_lock:
        return len(_nonce_cache)


def clear_nonce_cache():
    """清空Nonce缓存（用于测试）"""
    with _nonce_lock:
        _nonce_cache.clear()
        logger.info("Nonce缓存已清空")