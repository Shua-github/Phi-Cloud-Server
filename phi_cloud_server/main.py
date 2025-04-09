import asyncio
import hashlib
from contextlib import asynccontextmanager
from typing import Dict, List, Set

from fastapi import FastAPI, Header, HTTPException, Request, WebSocket
from fastapi.responses import JSONResponse, StreamingResponse

from phi_cloud_server.config import config

#from phi_cloud_server.db import TortoiseDB as DB
from phi_cloud_server.db1 import SQLModelDB as DB
from phi_cloud_server.decorators import broadcast_route
from phi_cloud_server.utils import (
    decode_base64_key,
    dev_mode,
    random,
    verify_session,
)
from phi_cloud_server.utils.datetime import get_utc_iso

db = DB(config.db.db_url)

@asynccontextmanager
async def lifespan(app: FastAPI):
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




# ---------------------- WebSocket管理器 ----------------------
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[
            WebSocket, Set[str]
        ] = {}  # websocket -> 订阅的路由集合
        self.lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, routes: List[str]):
        await websocket.accept()
        self.active_connections[websocket] = set(routes)

    async def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            del self.active_connections[websocket]

    async def broadcast_event(self, route: str, data: dict, session_token: str):
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
                            }
                        )
                    except:
                        await self.disconnect(ws)


manager = ConnectionManager()


@app.websocket("/ws/event")
async def websocket_endpoint(
    websocket: WebSocket, routes: str = None, Authorization: str = Header(...)
):
    """
    订阅响应事件WebSocket连接

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
    except:
        await manager.disconnect(websocket)


# ---------------------- 扩展接口 ----------------------
@app.post(
    "/1.1/users",
    responses={
        200: {
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
                        },
                    },
                }
            },
        },
        401: {
            "description": "未授权访问",
            "content": {"application/json": {"example": {"detail": "No access"}}},
        },
    },
)
@broadcast_route(manager)
async def register_user(Authorization: str = Header(...)):
    """
    注册新用户

    该接口用于创建新用户并返回会话令牌

    需要在请求头中提供access_key进行身份验证
    """
    if Authorization != config.server.access_key:
        raise HTTPException(401, "No access")
    session_token = random.session_token()
    user_id = random.object_id()  # 修改

    await db.create_user(session_token, user_id)  # 移除不必要的时间参数
    return JSONResponse({"sessionToken": session_token, "objectId": user_id})


# ---------------------- TapTap/LeanCloud云存档接口 ----------------------
@app.get("/1.1/classes/_GameSave")
@broadcast_route(manager)
async def get_game_save(request: Request):
    user_id = await verify_session(request, db)
    saves = await db.get_all_game_saves_with_files(user_id)
    return JSONResponse({"results": saves})


@app.post("/1.1/classes/_GameSave")
@broadcast_route(manager)
async def create_game_save(request: Request):
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
        raise HTTPException(400, detail=str(e))
    return JSONResponse(
        {"objectId": result["objectId"], "createdAt": result["createdAt"]}
    )


@app.put("/1.1/classes/_GameSave/{object_id}")
@broadcast_route(manager)
async def update_game_save(object_id: str, request: Request):
    data = await request.json()
    current_time = get_utc_iso()
    data["updatedAt"] = current_time
    data["modifiedAt"] = current_time
    if not await db.update_game_save(object_id, data):
        raise HTTPException(404, "Object not found")
    return JSONResponse({"updatedAt": current_time})  # 修改


@app.post("/1.1/fileTokens")
@broadcast_route(manager)
async def create_file_token(request: Request):
    await verify_session(request, db)
    token = random.object_id()
    key = hashlib.md5(token.encode()).hexdigest()
    object_id = random.object_id()  # 修改
    url = str(request.url_for("get_file", file_id=object_id))

    await db.create_file_token(token, key, object_id, url, get_utc_iso())
    return JSONResponse(
        {  # 修改
            "objectId": object_id,
            "token": token,
            "key": key,
            "url": url,
            "createdAt": get_utc_iso(),
        }
    )


@app.delete("/1.1/files/{file_id}")
@broadcast_route(manager)
async def delete_file(file_id: str):
    if not await db.delete_file(file_id):
        raise HTTPException(404, detail={"code": 404, "error": "File not found"})
    return JSONResponse({"code": 200, "data": {}})  # 修改


@app.post("/1.1/fileCallback")
async def file_callback(request: Request):
    return JSONResponse({"result": True})  # 修改


@app.get("/1.1/users/me")
@broadcast_route(manager)
async def get_current_user(request: Request):
    user_id = await verify_session(request, db)
    user_info = await db.get_user_info(user_id)
    return JSONResponse(user_info)  # 修改


@app.put("/1.1/users/{user_id}")
@broadcast_route(manager)
async def update_user(user_id: str, request: Request):
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
async def start_upload(encoded_key: str):
    raw_key = decode_base64_key(encoded_key)
    if not await db.get_object_id_by_key(raw_key):
        raise HTTPException(404, "Key not found")

    upload_id = random.object_id()  # 修改
    await db.create_upload_session(upload_id, raw_key)
    return JSONResponse({"uploadId": upload_id})  # 修改


@app.put("/buckets/rAK3Ffdi/objects/{encoded_key}/uploads/{upload_id}/{part_num}")
@broadcast_route(manager)
async def upload_part(
    encoded_key: str,
    upload_id: str,
    part_num: int,
    request: Request,
    content_length: int = Header(...),
):
    raw_key = decode_base64_key(encoded_key)
    upload_session = await db.get_upload_session(upload_id)
    if not upload_session:
        raise HTTPException(404, "Upload session not found")
    if upload_session["key"] != raw_key:
        raise HTTPException(400, "Key mismatch")

    data = await request.body()
    etag = hashlib.md5(data).hexdigest()
    await db.add_upload_part(upload_id, part_num, data, etag)
    return JSONResponse({"etag": etag})  # 修改


@app.post("/buckets/rAK3Ffdi/objects/{encoded_key}/uploads/{upload_id}")
@broadcast_route(manager)
async def complete_upload(encoded_key: str, upload_id: str, request: Request):
    user_id = await verify_session(request, db)
    raw_key = decode_base64_key(encoded_key)
    upload_session = await db.get_upload_session(upload_id)
    if not upload_session:
        raise HTTPException(404, "Upload session not found")
    if upload_session["key"] != raw_key:
        raise HTTPException(400, "Key mismatch")

    # 获取关联的 File ID
    file_id = await db.get_object_id_by_key(raw_key)
    if not file_id:
        raise HTTPException(404, "No file associated with this upload key")

    # 验证文件记录存在
    file_info = await db.get_file(file_id)
    if not file_info:
        raise HTTPException(404, "File record not found")

    data = await request.json()
    parts = sorted(data["parts"], key=lambda x: x["partNumber"])

    # 合并数据
    combined_data = b""
    for part in parts:
        part_info = upload_session["parts"].get(part["partNumber"])
        if not part_info or not part_info["data"]:
            raise HTTPException(400, "Missing part data")
        combined_data += part_info["data"]

    if not combined_data:
        raise HTTPException(400, "No data to save")

    # 更新文件元数据和内容
    metadata = {
        "_checksum": hashlib.md5(combined_data).hexdigest(),
        "size": len(combined_data),
    }
    file_url = str(request.url_for("get_file", file_id=file_id))
    await db.save_file(file_id, combined_data, file_url, metadata)

    # 更新最新存档的文件关联
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

    # 清理上传会话
    await db.delete_upload_session(upload_id)
    return JSONResponse({"key": encoded_key})


# ---------------------- 文件访问接口 ----------------------
@app.get("/files/{file_id}", name="get_file")
@broadcast_route(manager)
async def get_file(file_id: str):
    file_info = await db.get_file(file_id)
    if not file_info or not file_info["data"]:
        raise HTTPException(
            404, detail={"code": 404, "error": "File not found or empty"}
        )
    return StreamingResponse(
        iter([file_info["data"]]), media_type="application/octet-stream"
    )
