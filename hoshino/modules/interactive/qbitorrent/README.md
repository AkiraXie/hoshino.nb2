# qBittorrent 种子下载插件

基于 Hoshino 框架的 qBittorrent Web API 插件，支持通过群聊添加种子下载任务。

## 功能特性

- 🔧 配置 qBittorrent 连接信息
- ⬇️ 添加磁力链接、种子文件下载
- 📋 查看下载任务列表
- 🏷️ 支持自定义分类管理
- 🔒 管理员权限控制配置

## 命令使用

### 配置命令（需要管理员权限）

```
qbt配置 <服务器地址> <用户名> <密码> [分类]
```

示例：
```
qbt配置 http://192.168.1.100:8080 admin password123 hoshino
qbt配置 https://qbt.example.com admin mypass
```

### 显示配置
```
qbt显示配置
```

### 下载相关命令

#### 添加种子下载
```
添加种子 <下载链接> [分类]
```

支持的链接格式：
- 磁力链接：`magnet:?xt=urn:btih:...`
- 种子文件：`http://example.com/file.torrent`
- 其他下载链接

示例：
```
添加种子 magnet:?xt=urn:btih:c12fe1c06bba254a9dc9f519b335aa7c1367a88a
添加种子 https://example.com/movie.torrent movies
添加种子 http://tracker.com/download.php?id=12345
```

#### 查看下载列表
```
种子列表
```

显示当前下载任务的状态、进度、大小等信息。

## 别名命令

为方便使用，每个命令都有多个别名：

- `qbt配置` = `qbitorrent配置` = `qbtconfig`
- `qbt显示配置` = `qbitorrent显示配置` = `qbtshowconfig`
- `添加种子` = `下载种子` = `qbt下载` = `addtorrent`
- `种子列表` = `下载列表` = `qbt列表` = `torrents`

## 配置说明

### 服务器地址
- 支持 HTTP 和 HTTPS
- 如果不包含协议前缀，会自动添加 `http://`
- 示例：`192.168.1.100:8080` 或 `https://qbt.domain.com`

### 分类管理
- 默认分类为 `hoshino`
- 可以在配置时指定默认分类
- 添加种子时可以指定临时分类

### 权限控制
- 配置命令需要管理员权限
- 下载和查看命令所有用户可用
- 插件默认关闭，需要手动启用

## 技术实现

- 基于 qBittorrent Web API v2
- 使用 SQLite 存储配置信息
- 支持自动登录和会话管理
- 异步 HTTP 请求处理

## 安装使用

1. 确保 qBittorrent 开启了 Web UI 功能
2. 将插件文件放到 `hoshino/modules/interactive/qbitorrent/` 目录
3. 在群里发送配置命令设置连接信息
4. 开始使用下载功能

## 注意事项

- 请确保 qBittorrent 的 Web UI 已正确配置并可访问
- 建议为机器人创建专用的 qBittorrent 用户账户
- 下载任务会自动添加到指定分类，便于管理
- 插件会自动处理登录认证和会话保持