#!/usr/bin/env python3
"""
Aurora量化交易系统 - 自签名SSL证书生成器

用途：为开发/内网环境生成HTTPS自签名证书
生产环境建议使用 Let's Encrypt 或正规CA签发的证书

用法：
    python utils/gen_certs.py                # 生成到 certs/ 目录
    python utils/gen_certs.py --host 10.0.0.1  # 指定IP
    python utils/gen_certs.py --days 3650       # 指定有效期（10年）
"""

from __future__ import annotations

import datetime
import os
import sys
from pathlib import Path
from typing import Optional


def generate_self_signed_cert(
    cert_dir: Optional[str] = None,
    host: str = "localhost",
    days: int = 365,
    key_size: int = 2048,
) -> tuple[str, str]:
    """
    使用Python标准库生成自签名X.509证书

    Args:
        cert_dir: 证书存储目录，默认为项目根目录下的 certs/
        host:    证书CN（Common Name），通常是域名或IP
        days:    证书有效期（天）
        key_size: RSA密钥长度（2048或4096）

    Returns:
        (cert_path, key_path) 证书文件和私钥文件的绝对路径
    """
    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives.serialization import (
            Encoding,
            NoEncryption,
            PrivateFormat,
        )
    except ImportError:
        print("[ERROR] 缺少 cryptography 库，请执行: pip install cryptography")
        sys.exit(1)

    # 确定证书目录
    if cert_dir is None:
        project_root = Path(__file__).resolve().parent.parent
        cert_dir = str(project_root / "certs")
    cert_dir_path = Path(cert_dir)
    cert_dir_path.mkdir(parents=True, exist_ok=True)

    cert_path = str(cert_dir_path / "server.crt")
    key_path = str(cert_dir_path / "server.key")

    # 检查证书是否已存在且未过期
    if os.path.exists(cert_path) and os.path.exists(key_path):
        print(f"[INFO] 证书已存在: {cert_path}")
        print(f"[INFO] 私钥已存在: {key_path}")
        return cert_path, key_path

    print(f"[INFO] 生成RSA {key_size}位私钥...")
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=key_size,
    )

    print(f"[INFO] 构建证书主题（CN={host}）...")
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "CN"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Shanghai"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, "Shanghai"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Aurora Quant Trading"),
        x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "Engineering"),
        x509.NameAttribute(NameOID.COMMON_NAME, host),
    ])

    cert_builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
        .not_valid_after(
            datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=days)
        )
    )

    # Subject Alternative Name（SAN）— 支持多域名/IP
    san_entries = []
    try:
        import ipaddress
        ipaddress.ip_address(host)
        san_entries.append(x509.IPAddress(ipaddress.ip_address(host)))
    except ValueError:
        san_entries.append(x509.DNSName(host))

    # 添加常见主机名
    for alt_name in ("localhost", "127.0.0.1", "0.0.0.0"):
        if alt_name != host:
            try:
                ipaddress.ip_address(alt_name)
                san_entries.append(x509.IPAddress(ipaddress.ip_address(alt_name)))
            except ValueError:
                san_entries.append(x509.DNSName(alt_name))

    cert_builder = cert_builder.add_extension(
        x509.SubjectAlternativeName(san_entries),
        critical=False,
    )

    # 添加基本约束和密钥用途
    cert_builder = cert_builder.add_extension(
        x509.BasicConstraints(ca=False, path_length=None),
        critical=True,
    )
    cert_builder = cert_builder.add_extension(
        x509.KeyUsage(
            digital_signature=True,
            key_encipherment=True,
            data_encipherment=False,
            key_agreement=False,
            key_cert_sign=False,
            crl_sign=False,
            encipher_only=False,
            decipher_only=False,
            content_commitment=False,
        ),
        critical=True,
    )

    print(f"[INFO] 签署证书（有效期 {days} 天）...")
    certificate = cert_builder.sign(private_key, hashes.SHA256())

    # 保存私钥
    print(f"[INFO] 保存私钥: {key_path}")
    with open(key_path, "wb") as f:
        f.write(
            private_key.private_bytes(
                encoding=Encoding.PEM,
                format=PrivateFormat.PKCS8,
                encryption_algorithm=NoEncryption(),
            )
        )
    # 设置私钥权限（仅限Unix）
    try:
        os.chmod(key_path, 0o600)
    except (OSError, AttributeError):
        pass

    # 保存证书
    print(f"[INFO] 保存证书: {cert_path}")
    with open(cert_path, "wb") as f:
        f.write(certificate.public_bytes(Encoding.PEM))

    print(f"[OK] 自签名证书生成成功！")
    print(f"     证书: {cert_path}")
    print(f"     私钥: {key_path}")
    print(f"     CN:   {host}")
    print(f"     有效期: {days} 天 (约 {days // 365} 年)")
    print(f"     密钥: RSA {key_size} 位")
    print()
    print("  ⚠ 注意：自签名证书仅适用于开发/内网环境。")
    print("     浏览器访问时需要手动信任该证书。")
    print("     生产环境请使用 Let's Encrypt 或正规CA签发证书。")

    return cert_path, key_path


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="生成Aurora系统自签名SSL证书"
    )
    parser.add_argument(
        "--host",
        default="localhost",
        help="证书Common Name（域名或IP，默认 localhost）",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=3650,
        help="证书有效期天数（默认 3650 = 10年）",
    )
    parser.add_argument(
        "--key-size",
        type=int,
        default=2048,
        choices=[2048, 4096],
        help="RSA密钥长度（默认 2048）",
    )
    parser.add_argument(
        "--cert-dir",
        default=None,
        help="证书输出目录（默认 项目根目录/certs/）",
    )
    args = parser.parse_args()

    try:
        generate_self_signed_cert(
            cert_dir=args.cert_dir,
            host=args.host,
            days=args.days,
            key_size=args.key_size,
        )
    except Exception as e:
        print(f"[ERROR] 证书生成失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()