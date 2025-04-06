# 用户注册
## 请求方法
- **HTTP 方法**：`POST`
- **URL 路径**：`/1.1/users`
- **请求头**：
  - `Authorization`：必须提供一个有效的 `access_key`,可以在服务端进行配置,该密钥用于身份验证。

## 请求示例

```bash
curl -X 'POST' \
  'http://localhost:8000/1.1/users' \
  -H 'Authorization: <your_access_key>'
```
## 响应示例
```json
{
  "sessionToken": "<generated_session_token>",
  "objectId": "<generated_user_id>"
}
```
- sessionToken：新用户的会话令牌，用于后续验证。
- objectId：新用户的唯一标识符。

# 订阅响应事件
## 连接方式
- **WebSocket URL**：`/ws/event`
- **请求头**：
  - `Authorization`：必须提供一个有效的 `access_key`,同上。

## 请求参数
- **routes**：要订阅的路由列表,为字符串类型,以逗号分隔。例如：`POST:/1.1/users,GET:/1.1/classes/_GameSave`

## 示例代码
可以在仓库的`tests\ws.py`找到。

## 事件消息示例
### 文本或JSON
```json
{
    "event": "route_accessed",
    "code": 200,
    "data": {
        "route": "POST:/1.1/users",
        "sessionToken": "<session_token>", // 触发响应的用户的sessionToken,可为空字符串
        "raw_response": {
            "sessionToken": "<generated_session_token>", // 此处为示例,可能是字典(对象),也可能是字符串
            "objectId": "<generated_user_id>"
        },
        "timestamp": "2024-01-01T12:00:00.000Z" // 为响应时间
    }
}
```

### 二进制/其他
```json
{
    "event": "route_accessed",
    "code": 200,
    "data": {
        "route": "POST:/1.1/users",
        "sessionToken": "<session_token>", // 同上。
        "raw_response": {
            "content": "base64_encoded_content", // 为encoding字段编码过的数据
            "content_type": "application/octet-stream", // 为原始响应的MIME类型
            "encoding": "base64" // 编码方式,目前只有base64
        },
        "timestamp": "2024-01-01T12:00:00.000Z" // 同上。
    }
}
```

- event：事件名称
- code: 状态码
- data: 数据部分
  - route: 路由名称
  - sessionToken: 触发响应请求的sessionToken
  - raw_response: 原始响应,详情看示例。
  - timestamp: 响应时间