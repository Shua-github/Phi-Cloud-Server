"""常量文件."""

# 默认的阻塞域名映射
BLOCKED_DOMAINS = {
    "rak3ffdi.cloud.tds1.tapapis.cn": "127.0.0.1",
}
# 需要替换日志的库
SUPPRESS_LOGGERS = ["uvicorn", "uvicorn.error", "uvicorn.access"]

# tk长度
SESSION_TOKEN_LEN = 25
