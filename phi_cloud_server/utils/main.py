"""主工具."""

from __future__ import annotations

import importlib.util
from base64 import b64decode
from os import getenv
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import HTTPException, Request

if TYPE_CHECKING:
    from phi_cloud_server.db import TortoiseDB


def get_package_name() -> str:
    """获取顶层包名."""
    spec = importlib.util.find_spec(__name__)
    if spec and spec.name:
        return spec.name.split(".")[0]
    return None


package_name = get_package_name()


def decode_base64_key(encoded_key: str) -> str:
    """解码base64编码的key."""
    try:
        return b64decode(encoded_key).decode("utf-8")
    except Exception as e:
        raise HTTPException(400, "Invalid base64 key") from e


def get_session_token(request: Request) -> str:
    """从请求体获取tk."""
    auth_header = request.headers.get("X-LC-Session")
    if not auth_header:
        return None
    return auth_header


async def verify_session(request: Request, db: TortoiseDB) -> str:
    """验证玩家tk."""
    session_token = get_session_token(request)
    if not session_token:
        raise HTTPException(401, "Session token required")
    user_id = await db.get_user_id(session_token)
    if not user_id:
        raise HTTPException(401, "Invalid session token")
    return user_id


dev_mode = getenv("DEV", "").lower() == "true"


def get_default_dir() -> Path:
    """获取默认配置文件目录."""
    import platform

    system: str = platform.system()
    if system == "Windows":
        appdata: str = getenv("APPDATA")
        if appdata:
            config_dir = Path(appdata) / package_name
        else:
            config_dir = Path.home() / "AppData" / "Roaming" / package_name
    else:
        # Linux, macOS, etc.
        config_dir = Path.home() / ".config" / package_name
    if dev_mode:
        config_dir = Path.cwd() / "cache" / "config" / package_name
    return config_dir


default_dir = get_default_dir()
