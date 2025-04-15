"""主功能."""

import asyncio
import hashlib
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from re import match
from typing import Annotated, Union

from fastapi import (
    Body,
    FastAPI,
    Header,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field, field_validator

from phi_cloud_server.config import config
from phi_cloud_server.db import TortoiseDB
from phi_cloud_server.decorators import broadcast_route
from phi_cloud_server.utils import (
    decode_base64_key,
    dev_mode,
    get_session_token,
    logger,
    random,
    verify_session,
)
from phi_cloud_server.utils.env import SESSION_TOKEN_LEN
from phi_cloud_server.utils.time import get_utc_iso

db = TortoiseDB(config.db.db_url)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:  # noqa: ARG001
    """启动和关闭函数."""
    # 启动
    await db.create()
    yield
    # 关闭数据库连接
    await db.close()


app = FastAPI(
    lifespan=lifespan,
    debug=dev_mode,
    docs_url=None if not config.server.docs else "/docs",
    redoc_url=None if not config.server.docs else "/redoc",
    openapi_url=None if not config.server.docs else "/openapi.json",
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:  # noqa: ARG001
    """错误捕获器."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.status_code, "error": exc.detail},
    )


# ---------------------- WebSocket管理器 ----------------------
class ConnectionManager:
    """ws管理器."""

    def __init__(self) -> None:
        """初始化."""
        self.active_connections: dict[
            WebSocket,
            set[str],
        ] = {}  # websocket -> 订阅的路由集合
        self.lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, routes: list[str]) -> None:
        """连接."""
        await websocket.accept()
        self.active_connections[websocket] = set(routes)

    async def disconnect(self, websocket: WebSocket) -> None:
        """断开."""
        if websocket in self.active_connections:
            del self.active_connections[websocket]

    async def broadcast_event(self, route: str, data: dict, session_token: str) -> None:
        """广播事件."""
        async with self.lock:
            for ws, routes in self.active_connections.items():
                if route in routes:
                    try:
                        await ws.send_json(
                            {
                                "event": "route_accessed",
                                "code": 200,
                                "data": {
                                    "route": route,
                                    "sessionToken": session_token,
                                    "raw_response": data,
                                    "timestamp": get_utc_iso(),
                                },
                            },
                        )
                    except WebSocketDisconnect as e:
                        logger.info(f"WebSocket 已断开:{e!r}")
                    except TimeoutError as e:
                        logger.warning(f"WebSocket 连接已超时:{e!r}")
                    except ConnectionResetError as e:
                        logger.warning(f"WebSocket 连接已重置:{e!r}")
                    except Exception as e:  # noqa: BLE001
                        await self.disconnect(ws)
                        logger.error(f"发生未知错误:{e!r}")


manager = ConnectionManager()


@app.websocket("/ws/event")
async def websocket_endpoint(
    websocket: WebSocket,
    routes: Union[str, None] = None,  # noqa: FA100
    Authorization: str = Header(...),  # noqa: N803
) -> None:
    """订阅响应事件WebSocket连接.

    详细说明:
    - routes: 要订阅的路由列表,以逗号分隔
    - 事件消息格式见示例
    """
    if Authorization != config.server.access_key:
        await websocket.close(code=4003)
        return

    route_list = routes.split(",") if routes else []
    await manager.connect(websocket, route_list)
    try:
        while True:
            await websocket.receive_text()
            await asyncio.sleep(30)
    except WebSocketDisconnect as e:
        logger.info(f"WebSocket 已断开:{e!r}")
    except TimeoutError as e:
        logger.warning(f"WebSocket 连接已超时:{e!r}")
    except ConnectionResetError as e:
        logger.warning(f"WebSocket 连接已重置:{e!r}")
    except Exception as e:  # noqa: BLE001
        logger.error(f"发生未知错误:{e!r}")


# ---------------------- 扩展/taptap接口 ----------------------
class RegisterUserBody(BaseModel):
    """注册用户请求体定义."""

    sessionToken: str = Field(default_factory=random.session_token)  # noqa: N815
    name: str = None
    objectId: str = Field(default_factory=random.object_id)  # noqa: N815

    @field_validator("sessionToken")
    @classmethod
    def check_session_token(cls, value: str) -> str:
        """校验tk."""
        if len(value) != SESSION_TOKEN_LEN:
            msg = f"sessionToken长度错误,应该是{SESSION_TOKEN_LEN}位"
            raise ValueError(msg)

        if not match(rf"^[0-9a-z]{{{SESSION_TOKEN_LEN}}}$", value):
            msg = "sessionToken不合法,只能有小写字母和数字"
            raise ValueError(msg)

        return value


RegisterUserBody.model_rebuild()


@app.post(
    "/1.1/users",
    responses={
        201: {
            "description": "成功创建新用户",
            "content": {
                "application/json": {
                    "example": {
                        "sessionToken": "<generated_session_token>",
                        "objectId": "<generated_user_id>",
                    },
                    "schema": {
                        "type": "object",
                        "properties": {
                            "sessionToken": {
                                "type": "string",
                                "description": "新用户的会话令牌",
                            },
                            "objectId": {
                                "type": "string",
                                "description": "新用户的唯一标识符",
                            },
                            "name": {"type": "string", "description": "新用户昵称"},
                        },
                    },
                },
            },
        },
        401: {
            "description": "未授权访问",
            "content": {
                "application/json": {"example": {"code": 401, "error": "No access"}},
            },
        },
    },
)
@broadcast_route(manager)
async def register_user(
    request: Request,  # noqa: ARG001
    body: Annotated[Union[RegisterUserBody, None], Body()] = None,  # noqa: FA100
    Authorization: Annotated[Union[str, None], Header()] = None,  # noqa: FA100, N803
) -> JSONResponse:
    """注册新用户.

    该接口用于创建新用户并返回会话令牌

    需要在请求头中提供access_key进行身份验证
    """
    if config.server.taptap_login:
        pass
    elif Authorization != config.server.access_key:
        raise HTTPException(401, "No access")

    session_token = body.sessionToken
    user_id = body.objectId

    await db.create_user(session_token, user_id, body.name)  # 移除不必要的时间参数
    return JSONResponse(
        {"sessionToken": session_token, "objectId": user_id},
        status_code=201,
    )


# ---------------------- TapTap/LeanCloud云存档接口 ----------------------


@app.put("/1.1/users/{object_id}/refreshSessionToken")
@broadcast_route(manager)
async def refresh_session_token(object_id: str) -> JSONResponse:
    """刷新玩家tk路由."""
    new_session_token = random.session_token()
    result = await db.refresh_session_token(
        user_id=object_id,
        new_session_token=new_session_token,
    )
    if result:
        return JSONResponse(
            {
                "objectId": object_id,
                "sessionToken": new_session_token,
                "updatedAt": get_utc_iso(),
            },
        )
    raise HTTPException(404, "objectId not found or empty")


@app.get("/1.1/classes/_GameSave")
@broadcast_route(manager)
async def get_game_save(request: Request) -> JSONResponse:
    """获取玩家存档路由."""
    user_id = await verify_session(request, db)
    saves = await db.get_all_game_saves_with_files(user_id)
    return JSONResponse({"results": saves})


@app.post("/1.1/classes/_GameSave")
@broadcast_route(manager)
async def create_game_save(request: Request) -> JSONResponse:
    """创建玩家存档路由."""
    user_id = await verify_session(request, db)
    data = await request.json()
    new_save = {
        "objectId": random.object_id(),  # 修改
        "createdAt": get_utc_iso(),
        "updatedAt": get_utc_iso(),
        "modifiedAt": get_utc_iso(),
        **data,
    }
    try:
        result = await db.create_game_save(user_id, new_save)
    except ValueError as e:
        raise HTTPException(400, detail=str(e)) from e
    return JSONResponse(
        {"objectId": result["objectId"], "createdAt": result["createdAt"]},
        status_code=201,
    )


@app.put("/1.1/classes/_GameSave/{object_id}")
@broadcast_route(manager)
async def update_game_save(object_id: str, request: Request) -> JSONResponse:
    """更新玩家存档路由."""
    data = await request.json()
    current_time = get_utc_iso()
    data["updatedAt"] = current_time
    data["modifiedAt"] = current_time
    if not await db.update_game_save(object_id, data):
        raise HTTPException(404, "Object not found")
    return JSONResponse({"updatedAt": current_time})  # 修改


@app.post("/1.1/fileTokens")
@broadcast_route(manager)
async def create_file_token(request: Request) -> JSONResponse:
    """创建文件上传令牌路由."""
    session_token = get_session_token(request)  # 获取 session_token
    data = await request.json()

    # 提取客户端传递的参数
    name = data.get("name", ".save")
    prefix = data.get("prefix", "gamesaves")
    meta_data = data.get("metaData", {})
    size = meta_data.get("size", 0)
    checksum = meta_data.get("_checksum", hashlib.md5(b"").hexdigest())  # noqa: S324

    # 生成必要的标识符
    token = random.object_id()
    key = f"{prefix}/{random.object_id()}/{name}"
    object_id = random.object_id()
    upload_url = str(request.base_url)[:-1]  # 不能返回带/的url
    file_url = f"{request.base_url!s}{key}"

    # 存储文件令牌信息
    await db.create_file_token(
        token,
        key,
        object_id,
        file_url,
        session_token,
    )  # 添加 session_token

    # 构造响应数据
    response_data = {
        "bucket": "rAK3Ffdi",
        "createdAt": get_utc_iso(),
        "key": key,
        "metaData": {
            "_checksum": checksum,
            "prefix": prefix,
            "size": size,
        },
        "mime_type": "application/octet-stream",
        "name": name,
        "objectId": object_id,
        "provider": "qiniu",
        "token": token,
        "upload_url": upload_url,
        "url": file_url,
    }

    return JSONResponse(response_data, status_code=201)


@app.delete("/1.1/files/{file_id}")
@broadcast_route(manager)
async def delete_file(file_id: str) -> Response:
    """删除文件路由."""
    if not await db.delete_file(file_id):
        raise HTTPException(404, detail="File not found")
    return Response(status_code=204)


@app.post("/1.1/fileCallback")
async def file_callback(request: Request) -> JSONResponse:  # noqa: ARG001
    """文件回调路由(有...有用吗)."""
    return JSONResponse({"result": True})  # 修改


# 兼容部分查分API
@app.get("/1.1/users/me")
@broadcast_route(manager)
async def get_current_user(request: Request) -> JSONResponse:
    """兼容性."""
    user_id = await verify_session(request, db)
    user_info = await db.get_user_info(user_id)
    return JSONResponse(user_info)  # 修改


# 兼容部分查分API
@app.put("/1.1/users/{user_id}")
@broadcast_route(manager)
async def update_user0(user_id: str, request: Request) -> JSONResponse:
    """兼容性."""
    await verify_session(request, db)
    data = await request.json()

    if "nickname" not in data:
        raise HTTPException(400, "Missing nickname field")

    nickname = data["nickname"]
    await db.update_user_info(user_id, {"nickname": nickname})

    return JSONResponse({})  # 修改


# 官方更新用户名
@app.put("/1.1/classes/_User/{user_id}")
@broadcast_route(manager)
async def update_user1(user_id: str, request: Request) -> JSONResponse:
    """更新用户名接口."""
    await verify_session(request, db)
    data = await request.json()

    if "nickname" not in data:
        raise HTTPException(400, "Missing nickname field")

    nickname = data["nickname"]
    await db.update_user_info(user_id, {"nickname": nickname})

    return JSONResponse({})  # 修改


# ---------------------- 七牛云接口 ----------------------
@app.post("/buckets/rAK3Ffdi/objects/{encoded_key}/uploads")
@broadcast_route(manager)
async def start_upload(encoded_key: str) -> JSONResponse:
    """七牛云开始上传接口."""
    raw_key = decode_base64_key(encoded_key)
    file_token = await db.get_file_token_by_key(raw_key)  # 从数据库获取 file_token
    if not file_token:
        raise HTTPException(404, "Key not found")

    session_token = file_token["session_token"]  # 从 file_token 获取 session_token
    upload_id = random.object_id()
    await db.create_upload_session(
        upload_id,
        raw_key,
        session_token,
    )  # 使用 session_token
    return JSONResponse({"uploadId": upload_id})


@app.put("/buckets/rAK3Ffdi/objects/{encoded_key}/uploads/{upload_id}/{part_num}")
@broadcast_route(manager)
async def upload_part(
    encoded_key: str,
    upload_id: str,
    part_num: int,
    request: Request,
) -> JSONResponse:
    """七牛云上传文件分片接口."""
    raw_key = decode_base64_key(encoded_key)
    upload_session = await db.get_upload_session(upload_id)
    if not upload_session:
        raise HTTPException(404, "Upload session not found")
    if upload_session["key"] != raw_key:
        raise HTTPException(400, "Key mismatch")

    data = await request.body()
    etag = hashlib.md5(data).hexdigest()  # noqa: S324
    await db.add_upload_part(upload_id, part_num, data, etag)
    return JSONResponse({"etag": etag})


@app.post("/buckets/rAK3Ffdi/objects/{encoded_key}/uploads/{upload_id}")
@broadcast_route(manager)
async def complete_upload(
    encoded_key: str,
    upload_id: str,
    request: Request,
) -> JSONResponse:
    """七牛云上传完成接口."""
    raw_key = decode_base64_key(encoded_key)
    upload_session = await db.get_upload_session(upload_id)
    if not upload_session:
        raise HTTPException(404, "Upload session not found")
    if upload_session["key"] != raw_key:
        raise HTTPException(400, "Key mismatch")

    session_token = upload_session["session_token"]
    user_id = await db.get_user_id(session_token)
    if not user_id:
        raise HTTPException(401, "Unauthorized: Invalid session token")

    file_id = await db.get_object_id_by_key(raw_key)
    if not file_id:
        raise HTTPException(404, "No file associated with this upload key")

    file_info = await db.get_file(file_id)
    if not file_info:
        raise HTTPException(404, "File record not found")

    data = await request.json()
    parts = sorted(data["parts"], key=lambda x: x["partNumber"])

    combined_data = b""
    for part in parts:
        part_info = upload_session["parts"].get(part["partNumber"])
        if not part_info or not part_info["data"]:
            raise HTTPException(400, "Missing part data")
        combined_data += part_info["data"]

    if not combined_data:
        raise HTTPException(400, "No data to save")

    metadata = {
        "_checksum": hashlib.md5(combined_data).hexdigest(),  # noqa: S324
        "size": len(combined_data),
    }
    file_url = str(request.url_for("get_file", file_id=file_id))
    await db.save_file(file_id, combined_data, file_url, metadata)

    latest_save = await db.get_latest_game_save(user_id)
    if latest_save:
        save_id = latest_save["objectId"]
        update_data = {
            "gameFile": {
                "__type": "File",
                "objectId": file_id,
                "url": file_url,
                "metaData": metadata,
            },
            "updatedAt": get_utc_iso(),
        }
        await db.update_game_save(save_id, update_data)

    await db.delete_upload_session(upload_id)
    return JSONResponse({"key": encoded_key})


# ---------------------- 文件访问接口 ----------------------
@app.get("/1.1/files/{file_id}", name="get_file")
@broadcast_route(manager)
async def get_file(file_id: str) -> JSONResponse:
    """获取文件接口."""
    file_info = await db.get_file(file_id)
    if not file_info or not file_info["data"]:
        raise HTTPException(404, detail="File not found or empty")
    return StreamingResponse(
        iter([file_info["data"]]),
        media_type="application/octet-stream",
    )
