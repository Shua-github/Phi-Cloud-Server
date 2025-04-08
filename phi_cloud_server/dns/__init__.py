import ctypes
import socket
import sys

import psutil
from dnslib import QTYPE, RR, A, DNSHeader, DNSRecord

BLOCKED_DOMAINS = {
    "rak3ffdi.cloud.tds1.tapapis.cn": "127.0.0.1",
    "upload.qiniup.com": "127.0.0.1",
}

class DNSServer:
    def __init__(self,upstream:str = "119.29.29.29",blocked_domains:dict = BLOCKED_DOMAINS):
        # 需要拦截的域名列表
        self.blocked_domains = blocked_domains
        # 上游DNS服务器地址
        self.upstream = upstream
        
    def process_dns_query(self, data):
        request = DNSRecord.parse(data)
        reply = DNSRecord(DNSHeader(id=request.header.id, qr=1, aa=1, ra=1), q=request.q)
        
        qname = str(request.q.qname)
        # qtype = request.q.qtype
        
        # 检查是否是需要拦截的域名
        for domain in self.blocked_domains:
            if domain in qname:
                reply.add_answer(RR(
                    rname=request.q.qname,
                    rtype=QTYPE.A,
                    ttl=60,
                    rdata=A(self.blocked_domains[domain])
                ))
                return reply.pack()
        
        # 如果不是被拦截的域名,转发到上游DNS服务器
        try:
            upstream_dns = (self.upstream, 53)
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.sendto(data, upstream_dns)
            response, _ = sock.recvfrom(1024)
            return response
        except Exception as e:
            print(f"Error: {e}")
            return reply.pack()

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False

def check_port_in_use(port):
    try:
        # 创建测试用socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(('0.0.0.0', port))
        sock.close()
        return None, None
    except socket.error:
        # 如果端口被占用，查找占用进程
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                connections = proc.info.get('name') and psutil.net_connections()
                for conn in connections:
                    if conn.laddr.port == port:
                        return proc.pid, proc.info['name']
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        return None, None

def main():
    if sys.platform.startswith("win"):
        if not is_admin():
            print("正在请求管理员权限...")
            # 使用管理员权限重新启动程序
            ctypes.windll.shell32.ShellExecuteW(
                None,
                "runas",
                sys.executable,
                " ".join(sys.argv),
                None,
                1
            )
            sys.exit(0)
    port = 53
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        pid, process_name = check_port_in_use(port)
        if not pid:
            break
            
        user_input = input(f"端口 {port} 已被进程 {process_name}(PID:{pid}) 占用。是否终止该进程？(yes/no): ")
        if user_input.lower() == 'yes':
            try:
                process = psutil.Process(pid)
                process.terminate()
                process.wait(timeout=3)  # 等待进程终止
                print(f"进程 {process_name} 已终止")
                import time
                time.sleep(2)  # 额外等待2秒确保端口释放
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

    server = DNSServer()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(("0.0.0.0", port))
        print(f"DNS Server running on 0.0.0.0:{port}")
    except Exception as e:
        print(f"无法绑定端口: {e}")
        sys.exit(1)
    
    while True:
        try:
            data, addr = sock.recvfrom(1024)
            response = server.process_dns_query(data)
            sock.sendto(response, addr)
        except KeyboardInterrupt:
            print("\nShutting down DNS server")
            break
        except Exception as e:
            print(f"Error: {e}")
