"""日志."""

import logging

from rich.logging import RichHandler

from phi_cloud_server.utils.env import SUPPRESS_LOGGERS

logging.basicConfig(
    level="INFO",
    format="%(message)s",
    datefmt="[%Y-%m-%d %H:%M:%S]",
    handlers=[  # 只需要保留 handlers 参数
        RichHandler(
            rich_tracebacks=True,
            markup=False,
            show_time=True,
            show_level=True,
            show_path=True,
            log_time_format="[%Y-%m-%d %H:%M:%S]",
            tracebacks_show_locals=True,
            omit_repeated_times=False,
        ),
    ],
)

logger = logging.getLogger("rich")


for logger_name in SUPPRESS_LOGGERS:
    lib_logger = logging.getLogger(logger_name)
    lib_logger.handlers.clear()
    lib_logger.propagate = True  # 将日志传播到根logger
