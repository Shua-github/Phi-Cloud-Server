from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from phi_cloud_server.utils import default_dir


class ServerConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    host: str = "0.0.0.0"
    port: int = 5000
    access_key: str = Field(default="XBZecxb114514")  # 用于注册用户和监听事件鉴权的密钥
    docs: bool = False


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    server: ServerConfig = ServerConfig()


def deep_merge(user_data: Any, default_data: Any) -> Any:
    """深度合并用户数据和默认数据，补全缺失字段"""
    if isinstance(user_data, dict) and isinstance(default_data, dict):
        merged = user_data.copy()
        for key, default_value in default_data.items():
            if key in merged:
                merged[key] = deep_merge(merged[key], default_value)
            else:
                merged[key] = default_value
        return merged
    return user_data if user_data is not None else default_data


def load_config() -> AppConfig:
    """加载配置文件，自动补全缺失字段并写回"""
    config_path = default_dir / "config.yaml"
    config_dir = config_path.parent
    print(f"Config.yml Path: {str(config_path)}")
    config_dir.mkdir(parents=True, exist_ok=True)

    # 生成默认配置
    default_config = AppConfig()
    default_dict = default_config.model_dump()

    # 配置文件不存在时直接写入默认配置
    if not config_path.exists():
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(default_dict, f, allow_unicode=True)
        return default_config

    # 加载用户配置
    with open(config_path, "r", encoding="utf-8") as f:
        user_dict = yaml.safe_load(f) or {}

    # 深度合并配置
    merged_dict = deep_merge(user_dict, default_dict)

    # 写回合并后的配置
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(merged_dict, f, allow_unicode=True, sort_keys=False)

    # 返回合并后的配置实例
    return AppConfig(**merged_dict)


config = load_config()
