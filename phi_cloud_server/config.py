"""管理配置."""

import yaml
from pydantic import BaseModel, ConfigDict, Field
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

from phi_cloud_server.utils import default_dir, logger
from phi_cloud_server.utils.env import BLOCKED_DOMAINS


class DBConfig(BaseModel):
    """数据库配置."""

    db_url: str = Field(
        default=f"""sqlite://{default_dir / "sqlite3.db"!s}""",
        description="数据库连接URL,默认为SQLite",
    )


class ServerConfig(BaseModel):
    """服务器配置."""

    host: str = Field(
        default="127.0.0.1",
        description="服务器监听地址",
    )
    port: int = Field(default=443, description="服务器监听端口")
    access_key: str = Field(
        default="XBZecxb114514",
        description="鉴权key,不要放到公开客户端上",
    )
    taptap_login: bool = Field(
        default=False,
        description="兼容游戏内taptap登录,开启后会不安全(可能遭受CC攻击)",
    )
    docs: bool = Field(default=False, description="是否开启API文档")
    ssl_switch: bool = Field(default=False, description="SSL/TLS开关")
    ssl_certfile: str = Field(default="", description="SSL证书文件路径")
    ssl_keyfile: str = Field(default="", description="SSL密钥文件路径")


class DNSServerConfig(BaseModel):
    """DNS服务器配置."""

    upstream_dns: str = Field(default="223.5.5.5", description="上游DNS服务器地址")
    blocked_domains: dict = Field(
        default=BLOCKED_DOMAINS,
        description="域名劫持名单,将指定域名解析到特定IP",
    )
    port: int = Field(default=53, description="DNS服务器监听端口")
    host: str = Field(default="127.0.0.1", description="DNS服务器监听地址")


class LogConfig(BaseModel):
    """日志配置."""

    level: str = Field(default="INFO", description="日志等级")


class AppConfig(BaseModel):
    """总配置."""

    model_config = ConfigDict(extra="allow")

    server: ServerConfig = Field(
        default_factory=ServerConfig,
        description="Web服务器配置",
    )
    db: DBConfig = Field(default_factory=DBConfig, description="数据库配置")
    server_dns: DNSServerConfig = Field(
        default_factory=DNSServerConfig,
        description="DNS服务器配置",
    )
    log: LogConfig = Field(default_factory=LogConfig, description="日志设置")


def deep_merge(user_data: dict, default_data: AppConfig.model_dump) -> dict:
    """合并配置."""
    if isinstance(user_data, dict) and isinstance(default_data, dict):
        merged = user_data.copy()
        for key, default_value in default_data.items():
            if key in merged:
                merged[key] = deep_merge(merged[key], default_value)
            else:
                merged[key] = default_value
        return merged
    return user_data if user_data is not None else default_data


def model_to_commented_map(model: BaseModel) -> CommentedMap:
    """模型转换成CommentedMap."""
    commented = CommentedMap()
    fields = type(model).model_fields

    for name, field in fields.items():
        value = getattr(model, name)

        if isinstance(value, BaseModel):
            commented[name] = model_to_commented_map(value)
        else:
            commented[name] = value

        if field.description:
            # 只设置 comment,别加空格缩进
            commented.yaml_set_comment_before_after_key(name, before=field.description)

    return commented


def load_config() -> AppConfig:
    """加载配置."""
    config_path = default_dir / "config.yaml"
    config_dir = config_path.parent
    logger.info(f"配置文件路径: {config_path!s}")
    logger.info(f"数据目录: {default_dir!s}")
    config_dir.mkdir(parents=True, exist_ok=True)

    default_config = AppConfig()

    if not config_path.exists():
        yaml_obj = YAML()
        yaml_obj.indent(mapping=2, sequence=4, offset=2)
        commented_map = model_to_commented_map(default_config)

        with config_path.open("w", encoding="utf-8") as f:
            f.write("# 应用程序配置文件\n")
            f.write("# 注意: 修改后需要重启服务生效\n\n")
            yaml_obj.dump(commented_map, f)
        return default_config

    with config_path.open(encoding="utf-8") as f:
        user_dict = yaml.safe_load(f) or {}

    default_dict = default_config.model_dump()
    merged_dict = deep_merge(user_dict, default_dict)

    user_server_dns = user_dict.get("server_dns", {})
    user_blocked = user_server_dns.get("blocked_domains", "__ABSENT__")
    if user_blocked != "__ABSENT__":
        merged_dict["server_dns"]["blocked_domains"] = user_blocked
    else:
        merged_dict["server_dns"]["blocked_domains"] = default_dict["server_dns"][
            "blocked_domains"
        ]

    merged_config = AppConfig(**merged_dict)
    yaml_obj = YAML()
    yaml_obj.indent(mapping=2, sequence=4, offset=2)
    commented_map = model_to_commented_map(merged_config)

    with config_path.open("w", encoding="utf-8") as f:
        f.write("# 应用程序配置文件\n")
        f.write("# 注意: 修改后需要重启服务生效\n\n")
        yaml_obj.dump(commented_map, f)

    return merged_config


config = load_config()
