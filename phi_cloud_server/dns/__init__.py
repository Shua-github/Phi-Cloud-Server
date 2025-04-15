"""DNS服务器."""

import ctypes
import socket
import sys
import time
from typing import Union

import dns.exception
import dns.flags
import dns.message
import dns.query
import dns.rcode
import dns.rdataclass
import dns.rdatatype
import dns.rrset
import psutil
from dns.rdtypes.IN.A import A

from phi_cloud_server.config import DNSServerConfig, config
from phi_cloud_server.utils import logger


class DNSServer:
    """DNS服务器."""

    def __init__(self, config: DNSServerConfig) -> None:
        """初始化配置."""
        self.config = config
        self.blocked_domains = self.config.blocked_domains
        self.upstream_dns = (self.config.upstream_dns, 53)
        self.port = self.config.port
        self.host = self.config.host

    def is_admin(self) -> bool:
        """检查windows的管理员权限."""
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except Exception:  # noqa: BLE001
            return False

    def check_port_in_use(self) -> Union[tuple[str, str], tuple[None, None]]:  # noqa: FA100
        """检查端口是否被占用."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.bind((self.host, self.port))
            sock.close()
        except OSError:
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    connections = proc.info.get("name") and psutil.net_connections()
                    for conn in connections:
                        if conn.laddr.port == self.port:
                            return (str(proc.pid), proc.info["name"])
                except (  # noqa: PERF203
                    psutil.NoSuchProcess,
                    psutil.AccessDenied,
                    psutil.ZombieProcess,
                ):
                    continue
            return (None, None)
        else:
            return (None, None)

    def process_dns_query(self, data: bytes) -> bytes:
        """处理DNS请求."""
        try:
            request = dns.message.from_wire(data)
        except dns.exception.DNSException:
            return b""

        if len(request.question) == 0:
            return b""

        question = request.question[0]
        qname = str(question.name).lower()
        response = dns.message.make_response(request)

        # 处理拦截逻辑
        for domain in self.blocked_domains:
            if domain in qname:
                rrset = dns.rrset.RRset(
                    question.name,
                    dns.rdataclass.IN,
                    dns.rdatatype.A,
                )
                rrset.add(
                    A(dns.rdataclass.IN, dns.rdatatype.A, self.blocked_domains[domain]),
                )
                response.answer.append(rrset)
                response.flags |= dns.flags.AA
                logger.info(
                    f"Blocked domain: {qname} -> {self.blocked_domains[domain]}",
                )
                return response.to_wire()

        # 转发到上游DNS
        try:
            response_data = dns.query.tcp(
                dns.message.from_wire(data),
                self.upstream_dns[0],
            )
            return response_data.to_wire()
        except Exception as e:  # noqa: BLE001
            logger.error(f"上游 DNS 查询失败: {e!r}", exc_info=e)
            response.set_rcode(dns.rcode.SERVFAIL)
            return response.to_wire()

    def start(self) -> None:  # noqa: C901, PLR0912
        """启动服务器."""
        if sys.platform.startswith("win") and not self.is_admin():
            ctypes.windll.shell32.ShellExecuteW(
                None,
                "runas",
                sys.executable,
                " ".join(sys.argv),
                None,
                1,
            )
            sys.exit(0)

        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            pid, process_name = self.check_port_in_use()
            if not pid:
                break

            user_input = input(
                f"端口 {self.port} 已被进程 {process_name}(PID:{pid}) 占用。是否终止该进程?(yes/no): ",
            )
            if user_input.lower() == "yes":
                try:
                    process = psutil.Process(int(pid))
                    process.terminate()
                    process.wait(timeout=3)
                    logger.info(f"进程 {process_name} 已终止")
                    time.sleep(2)
                except Exception as e:  # noqa: BLE001
                    logger.error(f"无法终止进程: {e!r}")
                    sys.exit(1)
            else:
                logger.info("退出程序")
                sys.exit(1)
            retry_count += 1

        if retry_count >= max_retries:
            logger.error("多次尝试后仍无法获取端口,将退出程序")
            sys.exit(1)

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind((self.host, self.port))
            sock.settimeout(1.0)
            logger.info(f"DNS Server running on {self.host}:{self.port}")
        except Exception as e:  # noqa: BLE001
            logger.error(f"无法绑定端口: {e!r}", exc_info=e)
            sys.exit(1)

        try:
            while True:
                try:
                    data, addr = sock.recvfrom(512)
                    response = self.process_dns_query(data)
                    if response:
                        sock.sendto(response, addr)
                except socket.timeout:  # noqa: PERF203
                    continue
        except KeyboardInterrupt:
            logger.info("\n正在关闭DNS服务器")
        finally:
            sock.close()


def main() -> None:
    """主函数."""
    server = DNSServer(config=config.server_dns)
    server.start()


if __name__ == "__main__":
    main()
