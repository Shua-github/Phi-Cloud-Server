# Phigros-Cloud-Server

基于 `FastAPI` 实现的 `Phigros` 云存档服务端。测试阶段，不代表生产可用。

[![PyPI](https://img.shields.io/pypi/v/phi-cloud-server.svg?label=phi-cloud-server)](https://pypi.org/project/phi-cloud-server/)

## 食用方法(使用)

1. 安装
```bash
pip install phi-cloud-server
```

2. 启动
```bash
phi_cloud_server
```

3. 想办法替换 `Phigros` 客户端里的云存档服务器地址，本项目不提供教程。

## 配置

配置路径均在软件输出，暂不提供更换配置路径。

## TODO

### 已知问题:
- [x] 修复第一次上传获取的存档为空~~毕竟给我折腾了2天写在这里也合理吧~~
- [ ] 必须新建存档2次后才能正常上传存档(不太影响正常客户端,只会丢失第一次云存档,后续不会丢失)

### API实现:
- [x] 上/下传存档
- [x] 上/下传存档 Summary
- [x] 上/下传用户信息
- [ ] 刷新用户sessionToken

### API扩展:
- [x] 注册新用户
- [x] 主动推送响应事件（目前仅支持 WebSocket 方式）
[查看扩展 API 食用教程](./asset/extended_interfaces.md),或在`配置文件`中,把`docs`字段更改成`true`后,访问`FastAPI`自带的文档。

### 其他
- [x] 打包并发布到 `PyPI`
- [x] 使用持久化数据库
- [ ] 更多功能请开`issue`