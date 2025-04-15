"""装饰器."""

from __future__ import annotations

import base64
import sys
from functools import wraps
from typing import TYPE_CHECKING, Callable, TypeVar, cast

if sys.version_info < (3, 10):
    from typing_extensions import ParamSpec
else:
    from typing import ParamSpec

from fastapi import Request, Response
from starlette.requests import Request as StarletteRequest

from phi_cloud_server.utils import get_session_token, logger

if TYPE_CHECKING:
    from collections.abc import Awaitable

    from phi_cloud_server.main import ConnectionManager

P = ParamSpec("P")
R = TypeVar("R")


def broadcast_route(
    manager: ConnectionManager,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """广播路由."""

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            request = next(
                (arg for arg in args if isinstance(arg, Request)),
                kwargs.get("request"),
            )

            if not request:
                return await func(*args, **kwargs)

            route = f"{request.method}:{request.url.path}"
            session_token = get_session_token(request) or ""

            # 缓存请求体
            request_body = await request.body()
            getattr(request, "_receive", None)

            async def patched_receive() -> dict:
                return {
                    "type": "http.request",
                    "body": request_body,
                    "more_body": False,
                }

            if isinstance(request, StarletteRequest):
                request._receive = patched_receive  # noqa: SLF001

            # 执行原始函数
            response = await func(*args, **kwargs)

            # 提取响应数据
            try:
                response_data = await _extract_response_data(
                    cast("Response", response),
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"发生未知错误: {e}", exc_info=e)
                response_data = {}

            # 广播事件
            await manager.broadcast_event(route, response_data, session_token)

            logger.info(
                f"路由: {route}\n"
                f"响应数据: {response_data!s}\n"
                f"请求头: {dict(request.headers)}\n"
                f"请求体: {request_body.decode(errors='ignore')}",
            )

            return response

        return wrapper

    return decorator


async def _extract_response_data(response: Response) -> dict | list | str:
    if isinstance(response, Response):
        content = response.body
        content_type = response.headers.get("content-type", "")

        if not content_type.startswith(("text/", "application/json")):
            return {
                "content": base64.b64encode(content).decode("utf-8"),
                "content_type": content_type,
                "encoding": "base64",
            }
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            return content
    return response
