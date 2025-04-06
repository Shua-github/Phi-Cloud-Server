from abc import ABC, abstractmethod
from typing import Dict, List, Optional


class Database(ABC):
    @abstractmethod
    def get_user_id(self, session_token: str) -> Optional[str]:
        pass

    # Game Saves 相关方法
    @abstractmethod
    def get_all_game_saves(self, user_id: str) -> List[Dict]:
        pass

    @abstractmethod
    def create_game_save(self, user_id: str, save_data: Dict) -> Dict:
        pass

    @abstractmethod
    def update_game_save(self, object_id: str, update_data: Dict) -> bool:
        pass

    @abstractmethod
    def get_game_save_by_id(self, object_id: str) -> Optional[Dict]:
        pass

    @abstractmethod
    def get_latest_game_save(self, user_id: str) -> Optional[Dict]:
        pass

    # 文件存储相关方法
    @abstractmethod
    def save_file(self, file_id: str, data: bytes, meta_data: Dict, url: str) -> None:
        pass

    @abstractmethod
    def get_file(self, file_id: str) -> Optional[Dict]:
        pass

    @abstractmethod
    def delete_file(self, file_id: str) -> bool:
        pass

    # 文件令牌和Key映射
    @abstractmethod
    def create_file_token(
        self, token: str, key: str, object_id: str, url: str, created_at: str
    ) -> None:
        pass

    @abstractmethod
    def get_file_token_by_token(self, token: str) -> Optional[Dict]:
        pass

    @abstractmethod
    def get_object_id_by_key(self, key: str) -> Optional[str]:
        pass

    # 分片上传管理
    @abstractmethod
    def create_upload_session(self, upload_id: str, key: str) -> None:
        pass

    @abstractmethod
    def get_upload_session(self, upload_id: str) -> Optional[Dict]:
        pass

    @abstractmethod
    def add_upload_part(
        self, upload_id: str, part_num: int, data: bytes, etag: str
    ) -> None:
        pass

    @abstractmethod
    def delete_upload_session(self, upload_id: str) -> None:
        pass

    @abstractmethod
    def get_user_info(self, user_id: str) -> Dict:
        pass

    @abstractmethod
    def update_user_info(self, user_id: str, update_data: Dict) -> None:
        pass

    @abstractmethod
    def create_user(self, session_token: str, user_id: str) -> None:
        pass
