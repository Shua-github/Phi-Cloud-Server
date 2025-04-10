from typing import ClassVar, List, Optional  # 添加导入

from pydantic import BaseModel  # 添加导入
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.orm import joinedload
from sqlmodel import Field, SQLModel, select, update
from sqlmodel.ext.asyncio.session import AsyncSession

from phi_cloud_server.utils import random
from phi_cloud_server.utils.datetime import get_utc_iso


class User(SQLModel, table=True):
    id: str = Field(
        default_factory=random.object_id, primary_key=True
    )  # 修复：移除括号
    nickname: str
    created_at: str = Field(default_factory=get_utc_iso)  # 确保 get_utc_iso 是函数
    updated_at: str = Field(default_factory=get_utc_iso)


class GameSave(SQLModel, table=True):
    id: str = Field(
        default_factory=random.object_id, primary_key=True
    )  # 修复：移除括号
    user_id: str = Field(foreign_key="user.id")
    game_file_id: str
    save_data: dict = Field(sa_column=Column(JSON))
    created_at: str = Field(default_factory=get_utc_iso)
    updated_at: str = Field(default_factory=get_utc_iso)


class File(SQLModel, table=True):
    id: str = Field(
        default_factory=random.object_id, primary_key=True
    )  # 修复：移除括号
    data: bytes
    url: str
    meta_data: dict = Field(sa_column=Column(JSON))


class FileToken(SQLModel, table=True):
    id: str = Field(
        default_factory=random.object_id, primary_key=True
    )  # 修复：移除括号
    token: str
    key: str
    file_id: str
    url: str
    created_at: str = Field(default_factory=get_utc_iso)


class UploadSession(SQLModel, table=True):
    id: str = Field(
        default_factory=random.object_id, primary_key=True
    )  # 修复：移除括号
    key: str
    created_at: str = Field(default_factory=get_utc_iso)


class UploadPart(SQLModel, table=True):
    id: str = Field(
        default_factory=random.object_id, primary_key=True
    )  # 修复：移除括号
    upload_id: str = Field(foreign_key="uploadsession.id")
    part_num: int
    data: bytes
    etag: str


class Session(SQLModel, table=True):
    id: str = Field(
        default_factory=random.object_id, primary_key=True
    )  # 修复：移除括号
    session_token: str
    user_id: str = Field(foreign_key="user.id")
    created_at: str = Field(default_factory=get_utc_iso)


# 添加 SQLModel 配置
class Config(BaseModel):
    arbitrary_types_allowed: ClassVar[bool] = True  # 添加类型注解


class SQLModelDB:
    def __init__(self, db_url: str = "sqlite://:memory:"):
        self.db_url = db_url

    async def create(self):
        self.engine: AsyncEngine = create_async_engine(self.db_url, echo=True)
        async with self.engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)

    async def close(self) -> bool:
        if self.engine:
            await self.engine.dispose()
            return True
        return False

    def get_session(self):
        return AsyncSession(self.engine)

    async def get_user(self, user_id: str) -> Optional[User]:
        async with self.get_session() as session:
            return await session.get(User, user_id)

    async def update_user_info(self, user_id: str, update_data: dict) -> Optional[User]:
        async with self.get_session() as session:
            user = await session.get(User, user_id)
            if not user:
                return None
            for key, value in update_data.items():
                setattr(user, key, value)
            await session.commit()
            return user

    async def get_user_info(self, user_id: str) -> dict:
        async with self.get_session() as session:
            user = await session.get(User, user_id)
            if not user:
                user = User(id=user_id, nickname=f"User_{user_id[:8]}")
                session.add(user)
                await session.commit()
                await session.refresh(user)

            return {
                "objectId": user.id,
                "nickname": user.nickname,
                "createdAt": user.created_at,
                "updatedAt": user.updated_at,
            }

    async def create_user(self, session_token: str, user_id: str) -> None:
        async with self.get_session() as session:
            user = await session.get(User, user_id)
            if not user:
                user = User(id=user_id, nickname=f"User_{user_id[:8]}")
                session.add(user)

            session_obj = Session(
                id=random.object_id(), session_token=session_token, user_id=user.id
            )
            session.add(session_obj)
            await session.commit()

    async def create_game_save(
        self,
        user_id: str,
        game_file_id: str,
        save_data: dict,
        created_at: str,
        updated_at: str,
    ) -> GameSave:
        async with self.get_session() as session:
            save = GameSave(
                user_id=user_id,
                game_file_id=game_file_id,
                save_data=save_data,
                created_at=created_at,
                updated_at=updated_at,
            )
            session.add(save)
            await session.commit()
            await session.refresh(save)
            return save

    async def update_game_save(
        self, save_id: str, update_data: dict
    ) -> Optional[GameSave]:
        async with self.get_session() as session:
            save = await session.get(GameSave, save_id)
            if not save:
                return None
            save.save_data.update(update_data)
            await session.commit()
            return save

    async def get_game_save(self, save_id: str) -> Optional[GameSave]:
        async with self.get_session() as session:
            return await session.get(GameSave, save_id)

    async def get_game_save_by_id(self, object_id: str) -> Optional[dict]:
        async with self.get_session() as session:
            save = await session.get(GameSave, object_id)
            if not save:
                return None

            file = await session.get(File, save.game_file_id)
            meta_data = file.meta_data if file else {}
            if "_checksum" not in meta_data:
                meta_data["_checksum"] = ""

            return {
                "objectId": save.id,
                "gameFile": {
                    "__type": "File",
                    "objectId": save.game_file_id,
                    "url": file.url if file else "",
                    "metaData": meta_data,
                },
                "createdAt": save.created_at,
                "updatedAt": save.updated_at,
                **save.save_data,
            }

    async def get_latest_game_save(self, user_id: str) -> Optional[GameSave]:
        async with self.get_session() as session:
            statement = (
                select(GameSave)
                .where(GameSave.user_id == user_id)
                .order_by(GameSave.created_at.desc())
            )
            result = await session.exec(statement)
            return result.first()

    async def get_all_game_saves(self, user_id: str) -> List[dict]:
        async with self.get_session() as session:
            statement = select(GameSave).where(GameSave.user_id == user_id)
            result = await session.exec(statement)
            saves = result.all()

            return [
                {
                    "objectId": save.id,
                    "gameFile": {
                        "__type": "File",
                        "objectId": save.game_file_id,
                        "url": "",
                        "metaData": {},
                    },
                    "updatedAt": save.updated_at,
                    **save.save_data,
                }
                for save in saves
            ]

    async def create_file(self, data: bytes, url: str, meta_data: dict) -> File:
        async with self.get_session() as session:
            file = File(data=data, url=url, meta_data=meta_data)
            session.add(file)
            await session.commit()
            await session.refresh(file)
            return file

    async def get_file(self, file_id: str) -> Optional[File]:
        async with self.get_session() as session:
            return await session.get(File, file_id)

    async def delete_file(self, file_id: str) -> bool:
        async with self.get_session() as session:
            file = await session.get(File, file_id)
            if file:
                await session.delete(file)
                await session.commit()
                return True
            return False

    async def create_file_token(
        self, token: str, key: str, object_id: str, url: str, created_at: str
    ) -> FileToken:
        async with self.get_session() as session:
            file_token = FileToken(
                token=token, key=key, file_id=object_id, url=url, created_at=created_at
            )
            session.add(file_token)
            await session.commit()
            await session.refresh(file_token)
            return file_token

    async def get_file_token_by_token(self, token: str) -> Optional[FileToken]:
        async with self.get_session() as session:
            statement = select(FileToken).where(FileToken.token == token)
            result = await session.exec(statement)
            return result.first()

    async def get_object_id_by_key(self, key: str) -> Optional[str]:
        async with self.get_session() as session:
            statement = select(FileToken).where(FileToken.key == key)
            result = await session.exec(statement)
            token = result.first()
            return token.file_id if token else None

    async def create_upload_session(self, upload_id: str, key: str) -> None:
        async with self.get_session() as session:
            session_obj = UploadSession(id=upload_id, key=key)
            session.add(session_obj)
            await session.commit()

    async def get_upload_session(self, upload_id: str) -> Optional[dict]:
        async with self.get_session() as session:
            session_obj = await session.get(UploadSession, upload_id)
            if not session_obj:
                return None

            # 加载关联的上传部分数据
            statement = select(UploadPart).where(UploadPart.upload_id == upload_id)
            result = await session.exec(statement)
            parts = {
                part.part_num: {"data": part.data, "etag": part.etag}
                for part in result.all()
            }

            return {
                "key": session_obj.key,
                "parts": parts,
                "createdAt": session_obj.created_at,
            }

    async def get_upload_parts(self, upload_id: str) -> List[UploadPart]:
        async with self.get_session() as session:
            statement = select(UploadPart).where(UploadPart.upload_id == upload_id)
            result = await session.exec(statement)
            return result.all()

    async def add_upload_part(
        self, upload_id: str, part_num: int, data: bytes, etag: str
    ) -> None:
        async with self.get_session() as session:
            part = UploadPart(
                upload_id=upload_id, part_num=part_num, data=data, etag=etag
            )
            session.add(part)
            await session.commit()

    async def delete_upload_session(self, upload_id: str) -> None:
        async with self.get_session() as session:
            session_obj = await session.get(UploadSession, upload_id)
            if session_obj:
                statement = select(UploadPart).where(UploadPart.upload_id == upload_id)
                result = await session.exec(statement)
                for part in result.all():
                    await session.delete(part)
                await session.delete(session_obj)
                await session.commit()

    async def get_user_id(self, session_token: str) -> Optional[str]:
        async with self.get_session() as session:
            statement = select(Session).where(Session.session_token == session_token)
            result = await session.exec(statement)
            session_obj = result.first()
            return session_obj.user_id if session_obj else None

    async def get_all_game_saves_with_files(self, user_id: str) -> List[dict]:
        async with self.get_session() as session:
            statement = (
                select(GameSave)
                .where(GameSave.user_id == user_id)
                .options(joinedload(GameSave.game_file_id))
            )
            result = await session.exec(statement)
            saves = result.all()

            file_infos = {
                save.game_file_id: await self.get_file(save.game_file_id)
                for save in saves
                if save.game_file_id
            }

            results = []
            for save in saves:
                file_info = file_infos.get(save.game_file_id, {})
                meta_data = file_info.get("metaData", {})
                if "_checksum" not in meta_data:
                    meta_data["_checksum"] = ""

                results.append(
                    {
                        "objectId": save.id,
                        "gameFile": {
                            "__type": "File",
                            "objectId": save.game_file_id,
                            "url": file_info.get("url", ""),
                            "metaData": meta_data,
                        },
                        "updatedAt": save.updated_at,
                        **save.save_data,
                    }
                )
            return results

    async def save_file(
        self, file_id: str, data: bytes, url: str, metadata: dict
    ) -> None:
        async with self.get_session() as session:
            statement = (
                update(File)
                .where(File.id == file_id)
                .values(data=data, url=url, meta_data=metadata)
            )
            await session.exec(statement)
            await session.commit()
