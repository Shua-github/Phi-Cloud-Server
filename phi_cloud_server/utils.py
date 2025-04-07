import random
import string
import uuid
from base64 import b64decode
from os import getenv
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, Request

from phi_cloud_server.db import TortoiseDB


def decode_base64_key(encoded_key: str) -> str:
    try:
        return b64decode(encoded_key).decode("utf-8")
    except Exception:
        raise HTTPException(400, "Invalid base64 key")


def get_session_token(request: Request) -> Optional[str]:
    auth_header = request.headers.get("X-LC-Session")
    if not auth_header:
        return None
    return auth_header


async def verify_session(request: Request, db: TortoiseDB) -> str:
    session_token = get_session_token(request)
    if not session_token:
        raise HTTPException(401, "Session token required")
    user_id = await db.get_user_id(session_token)
    if not user_id:
        raise HTTPException(401, "Invalid session token")
    return user_id


def get_random_object_id() -> str:
    """
    随机生成一个合法的objectId
    """
    return str(uuid.uuid4()).replace('-', '')


def generateSessionToken() -> str:
    """
    随机生成一个合法的sessionToken
    """
    characters = string.ascii_lowercase + string.digits
    token = "".join(random.choices(characters, k=25))
    return token

dev_mode = getenv("DEV", "").lower() == "true"

def get_default_dir() -> Path:
    """获取默认配置文件目录"""
    import platform

    PACKNAME = "phi_cloud_server"
    system: str = platform.system()
    if system == "Windows":
        appdata: Optional[str] = getenv("APPDATA")
        if appdata:
            config_dir = Path(appdata) / PACKNAME
        else:
            config_dir = Path.home() / "AppData" / "Roaming" / PACKNAME
    else:
        # Linux, macOS, etc.
        config_dir = Path.home() / ".config" / PACKNAME
    if dev_mode:
        config_dir = Path.cwd() / "cache" / "config" / PACKNAME
    return config_dir


default_dir = get_default_dir()
