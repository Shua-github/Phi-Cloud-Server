import jurigged  # 如果开发模式启用，才需要
import uvicorn

from phi_cloud_server.config import config
from phi_cloud_server.main import app
from phi_cloud_server.utils import dev_mode

# ---------------------- 启动 ----------------------

RELOAD_DIR = "./phi_cloud_server"


def main():
    # 在开发模式下启用热重载
    if dev_mode:
        jurigged.watch(pattern=RELOAD_DIR)

    # 设置服务器运行参数
    server_params = {"host": config.server.host, "port": config.server.port}

    # 如果启用 SSL 配置，添加 SSL 参数
    if config.server.ssl_switch:
        ssl_config = {
            "ssl_certfile": config.server.ssl_certfile,
            "ssl_keyfile": config.server.ssl_keyfile,
        }
        server_params = {**server_params, **ssl_config}

    # 启动 Uvicorn 服务器
    uvicorn.run(app, **server_params)
