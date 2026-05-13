# TCP 多用户聊天系统 (Python + PyQt6)

这是一个基于 TCP 的多用户聊天系统，包含服务端和现代化 PyQt6 客户端。当前版本的客户端已经从旧的 Tkinter 版本升级为更美观的蓝白主题界面，并保留了表情头像与消息气泡样式。

## 核心功能

- 用户注册与登录
- 群聊消息广播
- 私聊消息发送
- 在线用户实时列表
- 登录后加载聊天历史
- 离线用户登录后仍能查看群聊历史记录
- 多窗口登录可同时模拟多个用户
- 蓝白主题可爱界面，支持 emoji 头像

## 当前目录结构

```
.
├── client_v2
│   ├── main.py          # PyQt6 客户端入口
│   ├── ui_login.py      # 登录/注册窗口
│   ├── ui_chat.py       # 主聊天窗口界面
│   └── network.py       # 客户端网络通信模块
├── database.py          # SQLite 数据库管理
├── server.py            # 聊天服务器
├── README.md            # 项目说明文档
└── chat_server.db       # SQLite 数据库文件（运行时自动创建）
```

## 运行环境

- Python 3.8+
- PyQt6
- SQLite3

建议先使用虚拟环境，安装 PyQt6：

```bash
python -m pip install PyQt6
```

## 运行方式

### 1. 启动服务器

```bash
python server.py
```

当前服务器默认监听端口：`8889`

### 2. 启动客户端

```bash
python client_v2/main.py
```

客户端会弹出登录窗口，输入服务器地址、端口、用户名、密码后点击“登录”或“注册”。

### 3. 多用户测试

直接在多个终端分别运行 `python client_v2/main.py`，即可打开多个客户端窗口模拟不同用户同时登录。

## 核心模块说明

### `server.py`

负责：
- TCP 连接管理
- 用户注册、登录验证
- 在线用户状态维护
- 群聊广播与私聊转发
- 聊天记录存储

该文件通过 SQLite 保存用户信息及消息历史，并在客户端连接后维持状态同步。

### `database.py`

负责数据库初始化及 SQL 访问封装。主要用于：
- 保存用户账号信息
- 保存群聊 / 私聊消息记录
- 查询历史消息
- 更新用户在线状态

### `client_v2/network.py`

负责客户端网络通信：
- 连接服务器
- 发送 JSON 消息
- 接收服务器响应并通过 PyQt 信号发送给 UI
- 处理连接断开事件

### `client_v2/ui_login.py`

负责登录与注册界面：
- 连接服务器
- 发送 `login` / `register` 请求
- 处理服务器返回结果
- 支持保留登录窗口以便开启多个用户窗口

### `client_v2/ui_chat.py`

负责聊天主窗口界面：
- 显示群聊与私聊两个 Tab
- 在线用户列表
- 富文本消息显示（含 emoji 头像、消息气泡）
- 发送群聊和私聊消息
- 刷新在线用户列表

## 交互协议简要说明

客户端与服务器通过 JSON 格式消息通信，每条消息以换行符 `\n` 分隔。典型消息类型包括：

- `login` / `register`
- `message` （群聊）
- `private_message` （私聊）
- `get_online_users`
- `get_group_history`
- `get_private_history`

### 登录请求示例

```json
{"type": "login", "username": "test1", "password": "1234"}
```

### 群聊消息示例

```json
{"type": "message", "content": "大家好！"}
```

### 私聊消息示例

```json
{"type": "private_message", "to": "user2", "content": "你好！"}
```

## 设计亮点

- `PyQt6` 现代界面，主题已调整为蓝白中性色
- 支持多个客户端窗口同时登录，可用于多用户测试
- 登录后自动加载历史消息、在线列表刷新
- UI 显示 emoji 头像，增强聊天趣味性

## 注意事项

- 服务器默认端口为 `8889`，请确保客户端登录时端口一致
- 需要先启动 `server.py`，再启动客户端
- 多客户端测试时可在不同终端中反复运行 `python client_v2/main.py`

## 后续扩展建议

- 增加未读消息计数与离线私聊提示
- 增加消息撤回、已读回执
- 支持自定义用户头像
- 支持群组创建与多频道聊天
- UI 进一步增加主题切换与动画效果


---

祝你聊天愉快！
