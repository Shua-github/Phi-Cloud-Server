from typing import Dict, List, Optional

from pydantic import BaseModel

from phi_cloud_server.models import Database
from phi_cloud_server.utils import get_utc_iso


# ---------------------- MockDB实现 ----------------------
class UserInfo(BaseModel):
    objectId: str
    nickname: str
    createdAt: str = ""
    updatedAt: str = ""


class MockDB(Database):
    def __init__(self):
        self.game_saves: Dict[str, List[Dict]] = {}  # 用user_id作为key
        self.users: Dict[str, str] = {}  # session_token -> user_id 映射
        self.files: Dict[str, Dict] = {}
        self.file_tokens: Dict[str, Dict] = {}
        self.key_to_object_id: Dict[str, str] = {}
        self.uploads: Dict[str, Dict] = {}
        self._user_info: Dict[str, UserInfo] = {}

    def get_user_id(self, session_token: str) -> Optional[str]:
        return self.users.get(session_token)

    def get_all_game_saves(self, user_id: str) -> List[Dict]:
        return [save.copy() for save in self.game_saves.get(user_id, [])]

    def create_game_save(self, user_id: str, save_data: Dict) -> Dict:
        if user_id not in self.game_saves:
            self.game_saves[user_id] = []
        new_save = save_data.copy()
        self.game_saves[user_id].append(new_save)
        return new_save

    def update_game_save(self, object_id: str, update_data: Dict) -> bool:
        for user_saves in self.game_saves.values():
            for save in user_saves:
                if save.get("objectId") == object_id:
                    save.update(update_data)
                    save["updatedAt"] = get_utc_iso()
                    return True
        return False

    def get_game_save_by_id(self, object_id: str) -> Optional[Dict]:
        for user_saves in self.game_saves.values():
            for save in user_saves:
                if save.get("objectId") == object_id:
                    return save.copy()
        return None

    def get_latest_game_save(self, user_id: str) -> Optional[Dict]:
        user_saves = self.game_saves.get(user_id, [])
        return user_saves[-1].copy() if user_saves else None

    def save_file(self, file_id: str, data: bytes, meta_data: Dict, url: str) -> None:
        self.files[file_id] = {
            "objectId": file_id,
            "data": data,
            "metaData": meta_data,
            "url": url,
        }

    def get_file(self, file_id: str) -> Optional[Dict]:
        return self.files.get(file_id, {}).copy()

    def delete_file(self, file_id: str) -> bool:
        if file_id in self.files:
            del self.files[file_id]
            return True
        return False

    def create_file_token(
        self, token: str, key: str, object_id: str, url: str, created_at: str
    ) -> None:
        self.file_tokens[token] = {
            "objectId": object_id,
            "token": token,
            "key": key,
            "url": url,
            "createdAt": created_at,
        }
        self.key_to_object_id[key] = object_id

    def get_file_token_by_token(self, token: str) -> Optional[Dict]:
        return self.file_tokens.get(token, {}).copy()

    def get_object_id_by_key(self, key: str) -> Optional[str]:
        return self.key_to_object_id.get(key)

    def create_upload_session(self, upload_id: str, key: str) -> None:
        self.uploads[upload_id] = {"key": key, "parts": {}, "createdAt": get_utc_iso()}

    def get_upload_session(self, upload_id: str) -> Optional[Dict]:
        return self.uploads.get(upload_id, {}).copy()

    def add_upload_part(
        self, upload_id: str, part_num: int, data: bytes, etag: str
    ) -> None:
        if upload_id in self.uploads:
            self.uploads[upload_id]["parts"][part_num] = {"data": data, "etag": etag}

    def delete_upload_session(self, upload_id: str) -> None:
        if upload_id in self.uploads:
            del self.uploads[upload_id]

    def get_user_info(self, user_id: str) -> Dict:
        if user_id not in self._user_info:
            self._user_info[user_id] = UserInfo(
                objectId=user_id, nickname=f"User_{user_id[:8]}"
            )
        return self._user_info[user_id].model_dump()

    def update_user_info(self, user_id: str, update_data: Dict) -> None:
        if user_id not in self._user_info:
            self._user_info[user_id] = UserInfo(
                objectId=user_id, nickname=f"User_{user_id[:8]}"
            )
        current_info = self._user_info[user_id]
        updated_info = current_info.model_copy(update=update_data)
        self._user_info[user_id] = updated_info

    def create_user(self, session_token: str, user_id: str) -> None:
        self.users[session_token] = user_id
        self._user_info[user_id] = UserInfo(
            objectId=user_id,
            nickname=f"User_{user_id[:8]}",
            createdAt=get_utc_iso(),
            updatedAt=get_utc_iso(),
        )
