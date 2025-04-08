import random
import string
import uuid


def object_id() -> str:
    """
    随机生成一个合法的objectId
    """
    return str(uuid.uuid4()).replace("-", "")


def session_token() -> str:
    """
    随机生成一个合法的sessionToken
    """
    characters = string.ascii_lowercase + string.digits
    token = "".join(random.choices(characters, k=25))
    return token
