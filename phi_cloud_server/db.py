import uuid
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import Request
from tortoise.transactions import atomic

from phi_cloud_server.models import (
    File,
    FileToken,
    GameSave,
    Session,
    UploadPart,
    UploadSession,
    User,
)
from phi_cloud_server.utils.datetime import get_utc_iso


# TortoiseDB 实现
class TortoiseDB:
    async def create(self, db_url: str = "sqlite://:memory:"):
        """初始化数据库连接"""
        from tortoise import Tortoise

        await Tortoise.init(
            db_url=db_url, modules={"models": ["phi_cloud_server.models"]}
        )
        await Tortoise.generate_schemas()

    async def close(self):
        """关闭数据库连接"""
        from tortoise import Tortoise

        await Tortoise.close_connections()

    async def get_user_id(self, session_token: str) -> Optional[str]:
        session = await Session.filter(session_token=session_token).first()
        if session:
            return str(session.user_id)
        return None

    @atomic()
    async def update_game_save(self, object_id: str, update_data: Dict) -> bool:
        game_save = await GameSave.get_or_none(id=object_id)
        if not game_save:
            return False

        # 更新存档数据
        save_data = game_save.save_data
        save_data.update(update_data)
        save_data["updatedAt"] = get_utc_iso()

        game_save.save_data = save_data
        await game_save.save()

        return True

    @atomic()
    async def create_game_save(self, user_id: str, save_data: Dict) -> Dict:
        file_data = save_data.get("gameFile", {})
        file_id = file_data.get("objectId")

        # 修复：确保使用实际保存的文件 ID
        file = await File.get_or_none(id=file_id) if file_id else None
        if not file:
            raise ValueError(f"File with ID {file_id} not found")

        object_id = save_data.get("objectId", str(uuid.uuid4()))
        now = get_utc_iso()

        game_save = await GameSave.create(
            id=object_id,
            user_id=user_id,
            game_file_id=file.id,
            save_data=save_data,
        )

        result = {
            "objectId": str(game_save.id),
            "gameFile": {
                "__type": "File",
                "objectId": str(file.id),  # 确保 objectId 正确
                "url": file.url,           # 确保 URL 正确
                "metaData": file.meta_data,
            },
            "createdAt": now,
            "updatedAt": now,
            **save_data,
        }

        return result

    async def get_game_save_by_id(self, object_id: str) -> Optional[Dict]:
        game_save = await GameSave.get_or_none(
            id=object_id
        ).prefetch_related("game_file")
        if not game_save:
            return None

        # 确保 metaData 中有 _checksum
        meta_data = game_save.game_file.meta_data
        if "_checksum" not in meta_data:
            meta_data["_checksum"] = ""

        result = {
            "objectId": str(game_save.id),
            "gameFile": {
                "__type": "File",
                "objectId": str(game_save.game_file.id),
                "url": game_save.game_file.url,
                "metaData": meta_data,
            },
            "createdAt": game_save.created_at.isoformat() + "Z",
            "updatedAt": game_save.updated_at.isoformat() + "Z",
            **game_save.save_data,
        }

        return result

    async def get_latest_game_save(self, user_id: str) -> Optional[Dict]:
        game_save = (
            await GameSave.filter(user_id=user_id)
            .prefetch_related("game_file")
            .order_by("-created_at")
            .first()
        )
        if not game_save:
            return None

        # 确保 metaData 中有 _checksum
        meta_data = game_save.game_file.meta_data
        if "_checksum" not in meta_data:
            meta_data["_checksum"] = ""

        result = {
            "objectId": str(game_save.id),
            "gameFile": {
                "__type": "File",
                "objectId": str(game_save.game_file.id),
                "url": game_save.game_file.url,
                "metaData": meta_data,
            },
            "createdAt": game_save.created_at.isoformat() + "Z",
            "updatedAt": game_save.updated_at.isoformat() + "Z",
            **game_save.save_data,
        }

        return result

    async def save_file(
        self, file_id: str, data: bytes, url: str, metadata: dict
    ) -> None:
        await File.update_or_create(
            id=file_id,
            defaults={"data": data, "meta_data": metadata, "url": url},
        )

    async def get_file(self, file_id: str) -> Optional[Dict]:
        file = await File.get_or_none(id=file_id)
        if not file:
            return None

        return {
            "objectId": str(file.id),
            "data": file.data,
            "metaData": file.meta_data,
            "url": file.url,
        }

    async def delete_file(self, file_id: str) -> bool:
        file = await File.get_or_none(id=file_id)
        if not file:
            return False

        await file.delete()
        return True

    async def create_file_token(
        self, token: str, key: str, object_id: str, url: str, created_at: str
    ) -> None:
        file = await File.get_or_none(id=object_id)
        if not file:
            file = await File.create(
                id=object_id, data=b"", meta_data={}, url=url
            )

        # 标准化时间字符串格式
        dt = datetime.fromisoformat(created_at.replace("Z", ""))

        await FileToken.create(
            id=uuid.uuid4(),
            token=token,
            key=key,
            file_id=file.id,
            url=url,
            created_at=dt,
        )

    async def get_file_token_by_token(self, token: str) -> Optional[Dict]:
        file_token = await FileToken.get_or_none(token=token).prefetch_related("file")
        if not file_token:
            return None

        return {
            "objectId": str(file_token.id),
            "token": file_token.token,
            "key": file_token.key,
            "url": file_token.url,
            "createdAt": file_token.created_at.isoformat() + "Z",
        }

    async def get_object_id_by_key(self, key: str) -> Optional[str]:
        file_token = await FileToken.get_or_none(key=key).prefetch_related("file")
        if not file_token:
            return None
        return str(file_token.file.id)  # 返回关联的 File ID

    async def create_upload_session(self, upload_id: str, key: str) -> None:
        await UploadSession.create(id=upload_id, key=key)

    async def get_upload_session(self, upload_id: str) -> Optional[Dict]:
        session = await UploadSession.get_or_none(
            id=upload_id
        ).prefetch_related("parts")
        if not session:
            return None

        parts = {}
        async for part in session.parts.all():
            parts[part.part_num] = {"data": part.data, "etag": part.etag}

        return {
            "key": session.key,
            "parts": parts,
            "createdAt": session.created_at.isoformat() + "Z",
        }

    async def add_upload_part(
        self, upload_id: str, part_num: int, data: bytes, etag: str
    ) -> None:
        session = await UploadSession.get_or_none(id=upload_id)
        if not session:
            return

        await UploadPart.update_or_create(
            id=uuid.uuid4(),  # 添加生成唯一ID
            session_id=session.id,
            part_num=part_num,
            defaults={"data": data, "etag": etag},
        )

    async def delete_upload_session(self, upload_id: str) -> None:
        session = await UploadSession.get_or_none(id=upload_id)
        if not session:
            return

        await session.delete()

    async def get_user_info(self, user_id: str) -> Dict:
        user = await User.get_or_none(id=user_id)
        if not user:
            user = await User.create(
                id=user_id, nickname=f"User_{user_id[:8]}"
            )

        return {
            "objectId": str(user.id),
            "nickname": user.nickname,
            "createdAt": user.created_at.isoformat() + "Z",
            "updatedAt": user.updated_at.isoformat() + "Z",
        }

    async def update_user_info(self, user_id: str, update_data: Dict) -> None:
        user = await User.get_or_none(id=user_id)
        if not user:
            user = await User.create(
                id=user_id, nickname=f"User_{user_id[:8]}"
            )

        if "nickname" in update_data:
            user.nickname = update_data["nickname"]
            await user.save()

    async def create_user(self, session_token: str, user_id: str) -> None:
        user, _ = await User.update_or_create(
            id=user_id, defaults={"nickname": f"User_{user_id[:8]}"}
        )

        await Session.create(
            id=uuid.uuid4(), session_token=session_token, user_id=user.id
        )

    async def get_all_game_saves(self, user_id: str) -> List[Dict]:
        user_uuid = user_id
        game_saves = await GameSave.filter(user_id=user_uuid).prefetch_related(
            "game_file"
        )

        results = []
        for save in game_saves:
            result = {
                "objectId": str(save.id),
                "gameFile": {
                    "__type": "File",
                    "objectId": str(save.game_file.id),
                    "url": save.game_file.url,
                    "metaData": save.game_file.meta_data,
                },
                "updatedAt": save.updated_at.isoformat() + "Z",
                **save.save_data,
            }
            results.append(result)

        return results

    async def get_all_game_saves_with_files(
        self, user_id: str, request: Request
    ) -> List[Dict]:
        saves = await self.get_all_game_saves(user_id)
        if not saves:
            return []

        file_infos = {
            save["gameFile"]["objectId"]: await self.get_file(
                save["gameFile"]["objectId"]
            )
            for save in saves if save["gameFile"].get("objectId")  # 确保 objectId 存在
        }

        for save in saves:
            save["user"] = {
                "__type": "Pointer",
                "className": "_User",
                "objectId": user_id,
            }

            file_id = save["gameFile"].get("objectId")
            file_info = file_infos.get(file_id)

            if file_info:
                meta_data = file_info.get("metaData", {})
                if "_checksum" not in meta_data:
                    meta_data["_checksum"] = ""
                save["gameFile"].update(
                    {
                        "metaData": meta_data,
                        "url": file_info.get("url", ""),  # 修复 URL
                        "objectId": file_info.get("objectId"),  # 修复 objectId
                    }
                )
            else:
                save["gameFile"].update(
                    {
                        "metaData": {"_checksum": "", "size": 0},
                        "url": request.url_for("get_file", file_id=file_id)._url if file_id else "",
                    }
                )

        return saves
