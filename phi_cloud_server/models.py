from tortoise import fields, models


# Tortoise ORM 模型定义
class User(models.Model):
    """用户模型"""
    id = fields.UUIDField(pk=True)
    nickname = fields.CharField(max_length=255)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    class Meta:
        table = "users"


class Session(models.Model):
    """用户会话模型"""
    id = fields.UUIDField(pk=True)
    session_token = fields.CharField(max_length=255, unique=True)
    user = fields.ForeignKeyField("models.User", related_name="sessions")
    created_at = fields.DatetimeField(auto_now_add=True)
    
    class Meta:
        table = "sessions"


class File(models.Model):
    """文件模型"""
    id = fields.UUIDField(pk=True)
    data = fields.BinaryField()
    meta_data = fields.JSONField(default={})
    url = fields.CharField(max_length=255)
    created_at = fields.DatetimeField(auto_now_add=True)
    
    class Meta:
        table = "files"


class FileToken(models.Model):
    """文件令牌模型"""
    id = fields.UUIDField(pk=True)
    token = fields.CharField(max_length=255, unique=True)
    key = fields.CharField(max_length=255, unique=True)
    file = fields.ForeignKeyField("models.File", related_name="tokens")
    url = fields.CharField(max_length=255)
    created_at = fields.DatetimeField(auto_now_add=True)
    
    class Meta:
        table = "file_tokens"


class UploadSession(models.Model):
    """上传会话模型"""
    id = fields.UUIDField(pk=True)
    key = fields.CharField(max_length=255)
    created_at = fields.DatetimeField(auto_now_add=True)
    
    class Meta:
        table = "upload_sessions"


class UploadPart(models.Model):
    """上传分片模型"""
    id = fields.UUIDField(pk=True)
    session = fields.ForeignKeyField("models.UploadSession", related_name="parts")
    part_num = fields.IntField()
    data = fields.BinaryField()
    etag = fields.CharField(max_length=255)
    
    class Meta:
        table = "upload_parts"
        unique_together = (("session", "part_num"),)


class GameSave(models.Model):
    """游戏存档模型"""
    id = fields.UUIDField(pk=True)
    user = fields.ForeignKeyField("models.User", related_name="game_saves")
    game_file = fields.ForeignKeyField("models.File", related_name="game_saves")
    save_data = fields.JSONField()
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    class Meta:
        table = "game_saves"
