# Phigros-Cloud-Server

基于 `FastAPI` 实现的 `Phigros` 云存档服务端。测试阶段，API 未全部实现，不代表生产可用。

## 食用方法

1. 安装
```bash
pip install phi-cloud-server
```

2. 启动
```bash
phi_cloud_server
```

3. 想办法替换 `Phigros` 客户端里的云存档服务器地址，本项目不提供教程。

## 扩展 API 食用教程

[查看扩展 API 食用教程](./asset/extended_interfaces.md)

或在`配置文件`中,把`docs`字段更改成`true`后,访问`FastAPI`自带的文档。

## 配置

配置路径均在软件输出，暂不提供更换配置路径。

## TODO

- [x] 上/下传存档
- [x] 上/下传存档 Summary
- [x] 上/下传用户信息（用户名、简介）
- [x] 主动推送响应事件（目前只有 ws 方式）
- [x] 注册新用户
- [x] 打包发布 `pypi`
- [x] 持久化数据库
- [ ] 修复第一次上传获取的存档为空