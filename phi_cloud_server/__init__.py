"""主."""

from __future__ import annotations

import sys

from uvicorn import run

from phi_cloud_server.config import config
from phi_cloud_server.main import app
from phi_cloud_server.utils import dev_mode, logger, package_name

# ---------------------- 启动 ----------------------


def main() -> None:
    """主启动函数."""
    # 在开发模式下启用热重载
    logger.setLevel(config.log.level)
    logger.info(f"当前Python版本:{sys.version}")
    if sys.version_info < (3, 10):
        logger.warning("小于3.10版本的Python可能会出现问题,建议更新至最新Python版本")
    if dev_mode:

        def to_my_logger(event: Exception | str) -> None:
            if isinstance(event, Exception):
                logger.error(f"Jurigged Error:{event!r}", exc_info=event)
            else:
                event = str(event)
                if event.startswith("Watch"):
                    event = event.replace("Watch", "监听文件:")
                if event.startswith("Update"):
                    event = event.replace("Update", "更新模块:")
                logger.info(event)

        import jurigged

        jurigged.watch(pattern=package_name, logger=to_my_logger)

    # 设置服务器运行参数
    server_params = {
        "host": config.server.host,
        "port": config.server.port,
        "log_config": None,
    }

    # 如果启用 SSL 配置,添加 SSL 参数
    if config.server.ssl_switch:
        ssl_config = {
            "ssl_certfile": config.server.ssl_certfile,
            "ssl_keyfile": config.server.ssl_keyfile,
        }
        server_params = {**server_params, **ssl_config}

    # 启动 Uvicorn 服务器
    run(app, **server_params)
