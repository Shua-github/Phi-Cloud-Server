import copy
import uuid
from collections import defaultdict
from typing import Dict, List, Optional

from phi_cloud_server.utils.datetime import get_utc_iso


# 纯内存模型
class InMemoryDB:
    def __init__(self, db_url: str = "sqlite://:memory:"):
        self.users: Dict[str, dict] = {}
        self.sessions: Dict[str, dict] = {}
        self.files: Dict[str, dict] = {}
        self.file_tokens: Dict[str, dict] = {}
        self.upload_sessions: Dict[str, dict] = {}
        self.upload_parts: Dict[str, List[dict]] = defaultdict(list)
        self.game_saves: Dict[str, dict] = {}

    async def create(self):
        pass  # no-op

    async def close(self):
        pass  # no-op

    async def get_user_id(self, session_token: str) -> Optional[str]:
        session = self.sessions.get(session_token)
        return session["user_id"] if session else None

    async def update_game_save(self, object_id: str, update_data: Dict) -> bool:
        save = self.game_saves.get(object_id)
        if not save:
            return False
        save_data = save["save_data"]
        save_data.update(update_data)
        save_data["updatedAt"] = get_utc_iso()
        save["save_data"] = save_data
        return True

    async def create_game_save(self, user_id: str, save_data: Dict) -> Dict:
        file_data = save_data.get("gameFile", {})
        file_id = file_data.get("objectId")
        file = self.files.get(file_id)
        if not file:
            raise ValueError(f"File with ID {file_id} not found")

        object_id = save_data.get("objectId", str(uuid.uuid4()))
        now = get_utc_iso()
        game_save = {
            "id": object_id,
            "user_id": user_id,
            "game_file_id": file_id,
            "save_data": copy.deepcopy(save_data),
            "created_at": now,
            "updated_at": now,
        }
        self.game_saves[object_id] = game_save
        return {
            "objectId": object_id,
            "gameFile": {
                "__type": "File",
                "objectId": file_id,
                "url": file["url"],
                "metaData": file["metaData"],
            },
            "createdAt": now,
            "updatedAt": now,
            **save_data,
        }

    async def get_game_save_by_id(self, object_id: str) -> Optional[Dict]:
        save = self.game_saves.get(object_id)
        if not save:
            return None
        file = self.files.get(save["game_file_id"], {})
        meta_data = file.get("metaData", {})
        meta_data.setdefault("_checksum", "")
        return {
            "objectId": object_id,
            "gameFile": {
                "__type": "File",
                "objectId": file.get("id"),
                "url": file.get("url"),
                "metaData": meta_data,
            },
            "createdAt": save["created_at"],
            "updatedAt": save["updated_at"],
            **save["save_data"],
        }

    async def get_latest_game_save(self, user_id: str) -> Optional[Dict]:
        saves = [v for v in self.game_saves.values() if v["user_id"] == user_id]
        if not saves:
            return None
        latest = max(saves, key=lambda s: s["created_at"])
        return await self.get_game_save_by_id(latest["id"])

    async def save_file(
        self, file_id: str, data: bytes, url: str, metadata: dict
    ) -> None:
        self.files[file_id] = {
            "id": file_id,
            "data": data,
            "url": url,
            "metaData": metadata,
        }

    async def get_file(self, file_id: str) -> Optional[Dict]:
        return self.files.get(file_id)

    async def delete_file(self, file_id: str) -> bool:
        return self.files.pop(file_id, None) is not None

    async def create_file_token(
        self,
        token: str,
        key: str,
        object_id: str,
        url: str,
        created_at: str,
        session_token: str,
    ) -> None:
        self.files.setdefault(
            object_id,
            {
                "id": object_id,
                "data": b"",
                "metaData": {},
                "url": url,
            },
        )
        self.file_tokens[token] = {
            "id": str(uuid.uuid4()),
            "token": token,
            "key": key,
            "file_id": object_id,
            "url": url,
            "created_at": created_at,
            "session_token": session_token,  # 存储 session_token
        }

    async def get_file_token_by_token(self, token: str) -> Optional[Dict]:
        ft = self.file_tokens.get(token)
        if not ft:
            return None
        return {
            "objectId": ft["id"],
            "token": ft["token"],
            "key": ft["key"],
            "url": ft["url"],
            "createdAt": ft["created_at"],
        }

    async def get_file_token_by_key(self, key: str) -> Optional[Dict]:
        for token in self.file_tokens.values():
            if token["key"] == key:
                return token
        return None

    async def get_object_id_by_key(self, key: str) -> Optional[str]:
        for ft in self.file_tokens.values():
            if ft["key"] == key:
                return ft["file_id"]
        return None

    async def create_upload_session(
        self, upload_id: str, key: str, session_token: str
    ) -> None:
        self.upload_sessions[upload_id] = {
            "id": upload_id,
            "key": key,
            "session_token": session_token,  # 绑定 session_token
            "created_at": get_utc_iso(),
        }

    async def get_upload_session(self, upload_id: str) -> Optional[Dict]:
        session = self.upload_sessions.get(upload_id)
        if not session:
            return None
        parts = {
            p["part_num"]: {"data": p["data"], "etag": p["etag"]}
            for p in self.upload_parts.get(upload_id, [])
        }
        return {
            "key": session["key"],
            "session_token": session["session_token"],  # 返回 session_token
            "parts": parts,
            "createdAt": session["created_at"],
        }

    async def add_upload_part(
        self, upload_id: str, part_num: int, data: bytes, etag: str
    ) -> None:
        self.upload_parts[upload_id].append(
            {"part_num": part_num, "data": data, "etag": etag}
        )

    async def delete_upload_session(self, upload_id: str) -> None:
        self.upload_sessions.pop(upload_id, None)
        self.upload_parts.pop(upload_id, None)

    async def get_user_info(self, user_id: str) -> Dict:
        user = self.users.setdefault(
            user_id,
            {
                "id": user_id,
                "nickname": f"User_{user_id[:8]}",
                "created_at": get_utc_iso(),
                "updated_at": get_utc_iso(),
            },
        )
        return {
            "objectId": user["id"],
            "nickname": user["nickname"],
            "createdAt": user["created_at"],
            "updatedAt": user["updated_at"],
        }

    async def update_user_info(self, user_id: str, update_data: Dict) -> None:
        user = self.users.setdefault(
            user_id,
            {
                "id": user_id,
                "nickname": f"User_{user_id[:8]}",
                "created_at": get_utc_iso(),
                "updated_at": get_utc_iso(),
            },
        )
        if "nickname" in update_data:
            user["nickname"] = update_data["nickname"]
            user["updated_at"] = get_utc_iso()

    async def create_user(self, session_token: str, user_id: str) -> None:
        self.users[user_id] = {
            "id": user_id,
            "nickname": f"User_{user_id[:8]}",
            "created_at": get_utc_iso(),
            "updated_at": get_utc_iso(),
        }
        self.sessions[session_token] = {"user_id": user_id}

    async def get_all_game_saves(self, user_id: str) -> List[Dict]:
        saves = [s for s in self.game_saves.values() if s["user_id"] == user_id]
        result = []
        for s in saves:
            file = self.files.get(s["game_file_id"], {})
            result.append(
                {
                    "objectId": s["id"],
                    "gameFile": {
                        "__type": "File",
                        "objectId": file.get("id"),
                        "url": file.get("url"),
                        "metaData": file.get("metaData", {}),
                    },
                    "updatedAt": s["updated_at"],
                    **s["save_data"],
                }
            )
        return result

    async def get_all_game_saves_with_files(self, user_id: str) -> List[Dict]:
        saves = await self.get_all_game_saves(user_id)
        for save in saves:
            save["user"] = {
                "__type": "Pointer",
                "className": "_User",
                "objectId": user_id,
            }
            file_id = save["gameFile"]["objectId"]
            file_info = self.files.get(file_id, {})
            meta_data = file_info.get("metaData", {})
            meta_data.setdefault("_checksum", "")
            save["gameFile"].update(
                {
                    "metaData": meta_data,
                    "url": file_info.get("url", ""),
                    "objectId": file_info.get("id", file_id),
                }
            )
        return saves
