import ctypes
import socket
import sys
import time

import psutil
from dnslib import QTYPE, RR, A, DNSHeader, DNSRecord

from phi_cloud_server.config import DNSServerConfig, config


class DNSServer:
    def __init__(self, config: DNSServerConfig = DNSServerConfig()):
        self.config = config
        self.blocked_domains = self.config.blocked_domains
        self.upstream_dns = (self.config.upstream_dns, 53)
        self.port = self.config.port
        self.host = self.config.host

    def is_admin(self):
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except Exception:
            return False

    def check_port_in_use(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.bind((self.host, self.port))
            sock.close()
            return None, None
        except socket.error:
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    connections = proc.info.get("name") and psutil.net_connections()
                    for conn in connections:
                        if conn.laddr.port == self.port:
                            return proc.pid, proc.info["name"]
                except (
                    psutil.NoSuchProcess,
                    psutil.AccessDenied,
                    psutil.ZombieProcess,
                ):
                    continue
            return None, None

    def process_dns_query(self, data):
        request = DNSRecord.parse(data)
        reply = DNSRecord(
            DNSHeader(id=request.header.id, qr=1, aa=1, ra=1), q=request.q
        )

        qname = str(request.q.qname)

        for domain in self.blocked_domains:
            if domain in qname:
                reply.add_answer(
                    RR(
                        rname=request.q.qname,
                        rtype=QTYPE.A,
                        ttl=60,
                        rdata=A(self.blocked_domains[domain]),
                    )
                )
                print(f"Blocked domain: {qname} -> {self.blocked_domains[domain]}")
                return reply.pack()

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.sendto(data, self.upstream_dns)
            response, _ = sock.recvfrom(1024)
            return response
        except Exception as e:
            print(f"Error: {e}")
            return reply.pack()

    def start(self):
        if sys.platform.startswith("win") and not self.is_admin():
            print("正在请求管理员权限...")
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, " ".join(sys.argv), None, 1
            )
            sys.exit(0)

        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            pid, process_name = self.check_port_in_use()
            if not pid:
                break

            user_input = input(
                f"端口 {self.port} 已被进程 {process_name}(PID:{pid}) 占用。是否终止该进程？(yes/no): "
            )
            if user_input.lower() == "yes":
                try:
                    process = psutil.Process(pid)
                    process.terminate()
                    process.wait(timeout=3)
                    print(f"进程 {process_name} 已终止")
                    time.sleep(2)
                except Exception as e:
                    print(f"无法终止进程: {e}")
                    sys.exit(1)
            else:
                print("退出程序")
                sys.exit(1)

            retry_count += 1

        if retry_count >= max_retries:
            print("多次尝试后仍无法获取端口，退出程序")
            sys.exit(1)

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind((self.host, self.port))
            sock.settimeout(1.0)  # 设置超时避免阻塞导致无法 Ctrl+C 退出
            print(f"DNS Server running on {self.host}:{self.port}")
        except Exception as e:
            print(f"无法绑定端口: {e}")
            sys.exit(1)

        while True:
            try:
                data, addr = sock.recvfrom(1024)
                response = self.process_dns_query(data)
                sock.sendto(response, addr)
            except socket.timeout:
                continue
            except KeyboardInterrupt:
                print("\nShutting down DNS server")
                break
            except Exception as e:
                print(f"Error: {e}")


def main():
    server = DNSServer(config=config.server_dns)
    server.start()
