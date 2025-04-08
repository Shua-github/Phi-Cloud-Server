import base64
from functools import wraps

from fastapi import Request, Response

from phi_cloud_server.utils import get_session_token


def broadcast_route(manager):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 获取请求对象
            request = next(
                (arg for arg in args if isinstance(arg, Request)), kwargs.get("request")
            )
            if not request:
                return await func(*args, **kwargs)

            # 获取路由信息
            route = f"{request.method}:{request.url.path}"
            session_token = get_session_token(request) or ""

            # 执行原始处理函数
            response = await func(*args, **kwargs)

            # 处理响应内容
            if isinstance(response, Response):
                content = response.body
                content_type = response.headers.get("content-type", "")

                # 如果不是文本类型，转换为base64
                if not content_type.startswith(("text/", "application/json")):
                    content = base64.b64encode(content).decode("utf-8")
                    response_data = {
                        "content": content,
                        "content_type": content_type,
                        "encoding": "base64",
                    }
                else:
                    response_data = content
            else:
                response_data = response

            # 广播事件
            await manager.broadcast_event(route, response_data, session_token)

            return response

        return wrapper

    return decorator
