import argparse  # noqa: D100
import datetime
import re
import secrets
import shutil
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from phi_cloud_server.config import default_dir
from phi_cloud_server.utils import logger


def generate_ca_cert(
    export_dir: Path,
) -> tuple[rsa.RSAPrivateKey, x509.Certificate, Path, Path]:
    """生成CA证书."""
    # 生成CA私钥
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    # 设置CA证书信息
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "CN"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Beijing"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "My CA"),
            x509.NameAttribute(NameOID.COMMON_NAME, "My CA"),
        ],
    )

    now = datetime.datetime.now(datetime.timezone.utc)
    serial_number = secrets.randbelow(2**64)
    # 构建CA证书
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(ca_key.public_key())
        .serial_number(serial_number)
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=365 * 10))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(ca_key, hashes.SHA256())
    )

    # 导出路径
    ca_key_path = export_dir / "ca.key"
    ca_crt_path = export_dir / "ca.crt"

    # 保存CA证书和私钥
    with ca_key_path.open("wb") as f:
        f.write(
            ca_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            ),
        )

    with ca_crt_path.open("wb") as f:
        f.write(ca_cert.public_bytes(serialization.Encoding.PEM))

    return ca_key, ca_cert, ca_key_path, ca_crt_path


def issue_certificate(
    domain_name: str,
    ca_key: rsa.RSAPrivateKey,
    ca_cert: x509.Certificate,
    export_dir: Path,
) -> None:
    """生成域名证书."""
    # 生成服务器私钥
    server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    # 生成证书签名请求(CSR)  # noqa: ERA001
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(
            x509.Name(
                [
                    x509.NameAttribute(NameOID.COUNTRY_NAME, "CN"),
                    x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Beijing"),
                    x509.NameAttribute(NameOID.ORGANIZATION_NAME, "My Company"),
                    x509.NameAttribute(NameOID.COMMON_NAME, domain_name),
                ],
            ),
        )
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(domain_name)]),
            critical=False,
        )
        .sign(server_key, hashes.SHA256())
    )

    now = datetime.datetime.now(datetime.timezone.utc)
    serial_number = secrets.randbelow(2**64)

    # 用CA证书签名生成最终证书
    server_cert = (
        x509.CertificateBuilder()
        .subject_name(csr.subject)
        .issuer_name(ca_cert.subject)
        .public_key(csr.public_key())
        .serial_number(serial_number)
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=365 * 10))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(domain_name)]),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )

    # 替换非法字符为下划线(避免 Windows 路径问题)
    valid_domain_name = re.sub(r'[<>:"/\\|?*]', "_", domain_name)

    # 保存服务器证书和私钥
    server_key_path = export_dir / f"{valid_domain_name}.key"
    server_crt_path = export_dir / f"{valid_domain_name}.crt"

    # 保存私钥到文件
    with server_key_path.open("wb") as f:
        f.write(
            server_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            ),
        )

    # 保存证书到文件
    with server_crt_path.open("wb") as f:
        f.write(server_cert.public_bytes(serialization.Encoding.PEM))


def main() -> None:
    """主函数."""
    parser = argparse.ArgumentParser(description="生成或重用CA证书来签发证书")
    parser.add_argument(
        "domain",
        help="为指定域名生成证书,或者输入 'export_ca' 导出CA证书",
    )
    parser.add_argument(
        "--ca-cert",
        help="现有的CA证书路径(如果不生成新的CA证书)",
        type=str,
    )
    parser.add_argument(
        "--ca-key",
        help="现有的CA私钥路径(如果不生成新的CA私钥)",
        type=str,
    )
    args = parser.parse_args()

    # 默认导出路径
    export_dir = default_dir

    # 如果用户提供了CA证书和私钥路径,加载它们
    if args.ca_cert and args.ca_key:
        logger.info("使用提供的CA证书和私钥。")
        with Path(args.ca_key).open("rb") as f:
            ca_key = serialization.load_pem_private_key(f.read(), password=None)
        with Path(args.ca_cert).open("rb") as f:
            ca_cert = x509.load_pem_x509_certificate(f.read())
        ca_key_path = args.ca_key
        ca_crt_path = args.ca_cert
    else:
        # 检查CA证书是否已经存在,如果不存在则生成
        ca_key_path = export_dir / "ca.key"
        ca_crt_path = export_dir / "ca.crt"

        if ca_key_path.exists() and ca_crt_path.exists():
            logger.info("检测到已有的CA证书和私钥,直接加载它们。")
            with ca_key_path.open("rb") as f:
                ca_key = serialization.load_pem_private_key(f.read(), password=None)
            with ca_crt_path.open("rb") as f:
                ca_cert = x509.load_pem_x509_certificate(f.read())
        else:
            logger.info("正在生成新的CA证书和私钥。")
            ca_key, ca_cert, ca_key_path, ca_crt_path = generate_ca_cert(export_dir)

    # 导出CA证书
    if args.domain == "export_ca":
        # 获取当前工作目录
        cwd = Path.cwd()

        # 定义目标路径
        ca_key_copy_path = cwd / "ca.key"
        ca_crt_copy_path = cwd / "ca.crt"

        # 复制文件到当前工作目录
        shutil.copy(ca_key_path, ca_key_copy_path)
        shutil.copy(ca_crt_path, ca_crt_copy_path)

        logger.info(
            f"CA证书已导出到:\n  私钥: {ca_key_copy_path}\n  证书: {ca_crt_copy_path}",
        )

    else:
        issue_certificate(args.domain, ca_key, ca_cert, export_dir)


if __name__ == "__main__":
    main()
