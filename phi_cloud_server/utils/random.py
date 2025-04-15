"""随机工具."""

import secrets
import string
import uuid
from random import *  # noqa: F403

from phi_cloud_server.utils.env import SESSION_TOKEN_LEN


def object_id() -> str:
    """随机生成一个合法的objectId."""
    return str(uuid.uuid4()).replace("-", "")


def session_token() -> str:
    """随机生成一个合法的sessionToken."""
    characters = string.ascii_lowercase + string.digits
    # 使用secrets模块生成安全的随机字符串
    return "".join(secrets.choice(characters) for _ in range(SESSION_TOKEN_LEN))
