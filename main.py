import uuid
from datetime import datetime
import hashlib
from base64 import b64decode
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.responses import StreamingResponse
from db import MockDB
from typing import Optional

# ---------------------- 服务端实现 ----------------------

app = FastAPI()
db = MockDB()
db.users["xbzecxb114514"] = "71cb529d-af0d-4999-8ede-394292ae4999"  # 测试用户sessionToken,需要手动添加
# ---------------------- 辅助函数 ----------------------
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

def verify_session(request: Request) -> str:
    session_token = get_session_token(request)
    if not session_token:
        raise HTTPException(401, "Session token required")
    user_id = db.get_user_id(session_token)
    if not user_id:
        raise HTTPException(401, "Invalid session token")
    return user_id

# ---------------------- TapTap/LeanCloud云存档接口 ----------------------
@app.get("/1.1/classes/_GameSave")
async def get_game_save(request: Request):
    user_id = verify_session(request)
    saves = db.get_all_game_saves(user_id)
    if saves:
        for save in saves:
            # 添加user字段
            save["user"] = {
                "__type": "Pointer",
                "className": "_User",
                "objectId": user_id
            }
            file_id = save["gameFile"]["objectId"]
            file_info = db.get_file(file_id)
            if file_info:
                save["gameFile"]["metaData"] = file_info.get("metaData", {})
                save["gameFile"]["url"] = file_info.get("url", "")
            else:
                save["gameFile"]["metaData"] = {"_checksum": "", "size": 0}
                save["gameFile"]["url"] = request.url_for("get_file", file_id=file_id)._url
        return {"results": saves}
    return {"results": []}

@app.post("/1.1/classes/_GameSave")
async def create_game_save(request: Request):
    user_id = verify_session(request)
    data = await request.json()
    new_save = {
        "objectId": str(uuid.uuid4()),
        "createdAt": datetime.utcnow().isoformat() + "Z",
        "updatedAt": datetime.utcnow().isoformat() + "Z",
        **data
    }
    db.create_game_save(user_id, new_save)
    return {"objectId": new_save["objectId"], "createdAt": new_save["createdAt"]}

@app.put("/1.1/classes/_GameSave/{object_id}")
async def update_game_save(object_id: str, request: Request):
    data = await request.json()
    if not db.update_game_save(object_id, data):
        raise HTTPException(404, "Object not found")
    return {"updatedAt": datetime.utcnow().isoformat() + "Z"}

@app.post("/1.1/fileTokens")
async def create_file_token(request: Request):
    verify_session(request)
    token = str(uuid.uuid4())
    key = hashlib.md5(token.encode()).hexdigest()
    object_id = str(uuid.uuid4())
    url = str(request.url_for("get_file", file_id=object_id))
    
    db.create_file_token(token, key, object_id, url, datetime.utcnow().isoformat() + "Z")
    return {
        "objectId": object_id,
        "token": token,
        "key": key,
        "url": url,
        "createdAt": datetime.utcnow().isoformat() + "Z"
    }

@app.delete("/1.1/files/{file_id}")
async def delete_file(file_id: str):
    if not db.delete_file(file_id):
        raise HTTPException(404, detail={"code": 404, "error": "File not found"})
    return {"code": 200, "data": {}}

@app.post("/1.1/fileCallback")
async def file_callback(request: Request):
    return {"result": True}

# ---------------------- 七牛云接口 ----------------------
@app.post("/buckets/rAK3Ffdi/objects/{encoded_key}/uploads")
async def start_upload(encoded_key: str):
    raw_key = decode_base64_key(encoded_key)
    if not db.get_object_id_by_key(raw_key):
        raise HTTPException(404, "Key not found")
    
    upload_id = str(uuid.uuid4())
    db.create_upload_session(upload_id, raw_key)
    return {"uploadId": upload_id}

@app.put("/buckets/rAK3Ffdi/objects/{encoded_key}/uploads/{upload_id}/{part_num}")
async def upload_part(
    encoded_key: str, 
    upload_id: str, 
    part_num: int, 
    request: Request,
    content_length: int = Header(...)
):
    raw_key = decode_base64_key(encoded_key)
    upload_session = db.get_upload_session(upload_id)
    if not upload_session:
        raise HTTPException(404, "Upload session not found")
    if upload_session["key"] != raw_key:
        raise HTTPException(400, "Key mismatch")
    
    data = await request.body()
    etag = hashlib.md5(data).hexdigest()
    db.add_upload_part(upload_id, part_num, data, etag)
    return {"etag": etag}

@app.post("/buckets/rAK3Ffdi/objects/{encoded_key}/uploads/{upload_id}")
async def complete_upload(
    encoded_key: str, 
    upload_id: str, 
    request: Request
):
    user_id = verify_session(request)
    raw_key = decode_base64_key(encoded_key)
    upload_session = db.get_upload_session(upload_id)
    if not upload_session:
        raise HTTPException(404, "Upload session not found")
    if upload_session["key"] != raw_key:
        raise HTTPException(400, "Key mismatch")
    
    data = await request.json()
    parts = sorted(data["parts"], key=lambda x: x["partNumber"])
    
    combined_data = b""
    for part in parts:
        part_info = upload_session["parts"].get(part["partNumber"])
        if not part_info:
            raise HTTPException(400, "Missing part")
        combined_data += part_info["data"]
    
    file_id = db.get_object_id_by_key(raw_key)
    if not file_id:
        raise HTTPException(404, "Key not found")
    
    meta_data = {
        "_checksum": hashlib.md5(combined_data).hexdigest(),
        "size": len(combined_data)
    }
    file_url = str(request.url_for("get_file", file_id=file_id))
    db.save_file(file_id, combined_data, meta_data, file_url)
    
    latest_save = db.get_latest_game_save(user_id)
    if latest_save:
        latest_save["gameFile"] = {
            "__type": "Pointer",
            "className": "_File",
            "objectId": file_id,
            "metaData": meta_data,
            "url": file_url
        }
        db.update_game_save(latest_save["objectId"], latest_save)
    
    db.delete_upload_session(upload_id)
    return {"key": encoded_key}

# ---------------------- 文件访问接口 ----------------------
@app.get("/files/{file_id}", name="get_file")
async def get_file(file_id: str):
    file_info = db.get_file(file_id)
    if not file_info:
        raise HTTPException(404, detail={"code": 404, "error": "File not found"})
    return StreamingResponse(
        iter([file_info["data"]]), 
        media_type="application/octet-stream"
    )

# ---------------------- 启动 ----------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)