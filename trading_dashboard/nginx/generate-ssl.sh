#!/bin/bash
# SSL Certificate Generation Script
# 生成自签名 SSL 证书（用于测试环境）

set -e

CERT_DIR="$(dirname "$0")/ssl"
mkdir -p "$CERT_DIR"

echo "Generating SSL certificate..."

# 生成私钥
openssl genrsa -out "$CERT_DIR/server.key" 2048 2>/dev/null

# 生成证书签名请求 (CSR)
openssl req -new -key "$CERT_DIR/server.key" -out "$CERT_DIR/server.csr" \
    -subj "/C=CN/ST=Beijing/L=Beijing/O=MemX/OU=DevOps/CN=localhost" 2>/dev/null

# 生成自签名证书（有效期1年）
openssl x509 -req -days 365 -in "$CERT_DIR/server.csr" \
    -signkey "$CERT_DIR/server.key" -out "$CERT_DIR/server.crt" 2>/dev/null

# 设置权限
chmod 600 "$CERT_DIR/server.key"
chmod 644 "$CERT_DIR/server.crt"

# 清理 CSR
rm -f "$CERT_DIR/server.csr"

echo "SSL certificate generated successfully!"
echo "Certificate: $CERT_DIR/server.crt"
echo "Private Key: $CERT_DIR/server.key"
echo ""
echo "For production, please use Let's Encrypt or commercial CA certificates."
