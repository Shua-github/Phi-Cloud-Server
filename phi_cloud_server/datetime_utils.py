from datetime import datetime, timezone


def get_utc_iso() -> str:
    """
    返回UTC ISO格式的当前时间字符串，包含Z后缀
    """
    return datetime.now(timezone.utc).isoformat() + "Z"
