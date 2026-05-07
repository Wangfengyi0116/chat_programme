# -*- coding: utf-8 -*-
"""
client.py - TCP多用户聊天客户端

功能：
- 图形用户界面（基于tkinter）
- 用户注册和登录
- 群聊消息发送和接收
- 私聊消息发送和接收
- 在线用户列表显示
- 聊天记录加载和显示
- 多客户端模拟器（支持本地多账号同时在线）

个性化特色可扩展点：
- 文件传输功能
- emoji表情支持
- 消息提示音
- 消息已读状态
- 主题换肤功能
"""

import socket
import threading
import json
import logging
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, Callable

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, simpledialog


def _font_height(window, font_spec, lines=1):
    """计算指定字体 n 行的像素高度（用于精确设置 widget 高度）。"""
    tmp = tk.Label(window, font=font_spec)
    tmp.update_idletasks()
    h = tmp.winfo_reqheight()
    tmp.destroy()
    return h * lines


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('client.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# 服务器配置
DEFAULT_HOST = 'localhost'
DEFAULT_PORT = 8888
BUFFER_SIZE = 4096


class ChatClient:
    """聊天客户端主类"""

    def __init__(self):
        self.socket: Optional[socket.socket] = None
        self.host = DEFAULT_HOST
        self.port = DEFAULT_PORT
        self.username: Optional[str] = None
        self.running = False
        self.receive_thread: Optional[threading.Thread] = None

        # 在线用户列表
        self.online_users: list = []
        self.online_users_callback: Optional[Callable] = None

        # 消息回调
        self.message_callback: Optional[Callable] = None

        # 窗口
        self.window: Optional[tk.Tk] = None
        self.current_target = None  # None表示群聊

        # 消息去重：已处理过的消息 ID 集合
        self._seen_msg_ids: set = set()
        # 待确认消息：{client_msg_id: {'status': 'sending'/'confirmed', 'msg': dict}}
        # 用于乐观渲染（发送中→已确认状态的替换）
        self._pending_msgs: dict = {}

        # 连接状态标志
        self._is_connecting = False

    def connect(self, host: str, port: int) -> bool:
        """连接到服务器"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((host, port))
            self.running = True
            logger.info(f"成功连接到服务器 {host}:{port}")
            return True
        except Exception as e:
            logger.error(f"连接服务器失败: {e}")
            return False

    def disconnect(self):
        """断开服务器连接"""
        self.running = False
        if self.socket:
            try:
                self.send_message({'type': 'logout'})
                self.socket.close()
            except:
                pass
        logger.info("已断开服务器连接")

    def send_message(self, message: dict):
        """发送消息到服务器"""
        try:
            if self.socket:
                data = json.dumps(message, ensure_ascii=False) + '\n'
                self.socket.send(data.encode('utf-8'))
        except Exception as e:
            logger.error(f"发送消息失败: {e}")

    def start_receive_thread(self):
        """启动接收消息线程"""
        self.receive_thread = threading.Thread(target=self._receive_messages, daemon=True)
        self.receive_thread.start()

    def _receive_messages(self):
        """接收服务器消息"""
        buffer = ""
        while self.running:
            try:
                if not self.socket:
                    break

                self.socket.settimeout(1.0)

                try:
                    data = self.socket.recv(BUFFER_SIZE)
                    if not data:
                        logger.info("服务器关闭了连接")
                        break

                    buffer += data.decode('utf-8', errors='ignore')

                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        if line.strip():
                            try:
                                message = json.loads(line)
                                self._handle_server_message(message)
                            except json.JSONDecodeError as e:
                                logger.error(f"JSON解析错误: {e}")

                except socket.timeout:
                    continue

            except Exception as e:
                if self.running:
                    logger.error(f"接收消息时出错: {e}")
                break

        logger.info("接收线程结束")

        if self.running and self.window:
            def notify_disconnect():
                if self.window:
                    messagebox.showwarning("连接断开", "与服务器的连接已断开")
            self.window.after(0, notify_disconnect)

    def _handle_server_message(self, message: dict):
        """处理服务器消息"""
        msg_type = message.get('type', '')

        handlers = {
            'group_message': self._handle_group_message,
            'private_message': self._handle_private_message,
            'system_message': self._handle_system_message,
            'online_users': self._handle_online_users,
            'login_response': self._handle_login_response,
            'register_response': self._handle_register_response,
            'group_history': self._handle_group_history,
            'private_history': self._handle_private_history,
            'login_policy': self._handle_login_policy,
            'unread_counts': self._handle_unread_counts,
            'unread_increment': self._handle_unread_increment,
        }

        handler = handlers.get(msg_type)
        if handler:
            handler(message)
        else:
            logger.warning(f"未知消息类型: {msg_type}")

    def _handle_group_message(self, message: dict):
        """处理群聊消息"""
        msg_id = message.get('client_msg_id', '')
        msg_data = {
            'type': 'group',
            'from': message.get('from', ''),
            'content': message.get('content', ''),
            'timestamp': message.get('timestamp', ''),
            '_server_id': msg_id,  # 服务器确认的 ID
        }
        if self.message_callback and self.window:
            self.window.after(0, lambda m=msg_data, mid=msg_id: self.message_callback(m, mid))

    def _handle_private_message(self, message: dict):
        """处理私聊消息"""
        msg_id = message.get('client_msg_id', '')
        msg_data = {
            'type': 'private',
            'from': message.get('from', ''),
            'to': message.get('to', ''),
            'content': message.get('content', ''),
            'timestamp': message.get('timestamp', ''),
            '_server_id': msg_id,
        }
        if self.message_callback and self.window:
            self.window.after(0, lambda m=msg_data, mid=msg_id: self.message_callback(m, mid))

    def _handle_system_message(self, message: dict):
        """处理系统消息"""
        msg_data = {
            'type': 'system',
            'content': message.get('content', ''),
            'timestamp': message.get('timestamp', '')
        }
        if self.message_callback and self.window:
            self.window.after(0, lambda m=msg_data: self.message_callback(m, ''))

    def _handle_online_users(self, message: dict):
        """处理在线用户列表更新"""
        import sys
        users = message.get('users', [])
        print(f"[客户端 _handle_online_users] 收到在线用户列表: {users}", file=sys.stderr)
        print(f"[客户端 _handle_online_users] self.window={self.window}, self.online_users_callback={self.online_users_callback}", file=sys.stderr)
        self.online_users = users
        if self.online_users_callback and self.window:
            print(f"[客户端 _handle_online_users] 调用回调函数", file=sys.stderr)
            self.window.after(0, lambda: self.online_users_callback(self.online_users))

    def _handle_login_response(self, message: dict):
        """处理登录响应"""
        success = message.get('success', False)
        msg = message.get('message', '')

        def callback():
            if success:
                self.username = message.get('username', '')
                # 隐藏登录窗口，创建聊天窗口
                self._hide_login_and_create_chat()
            else:
                messagebox.showerror("登录失败", msg)
                self._reset_connecting_state()

        if self.window:
            self.window.after(0, callback)

    def _handle_register_response(self, message: dict):
        """处理注册响应"""
        success = message.get('success', False)
        msg = message.get('message', '')

        def callback():
            if success:
                messagebox.showinfo("注册成功", "恭喜！注册成功，请登录！")
            else:
                messagebox.showerror("注册失败", msg)
            self._reset_connecting_state()

        if self.window:
            self.window.after(0, callback)

    def _handle_group_history(self, message: dict):
        """处理群聊历史消息"""
        messages = message.get('messages', [])
        if self.message_callback and self.window:
            for msg in messages:
                msg_id = f"db_{msg.get('id', '')}"  # 服务器 DB 主键作为唯一标识
                msg_data = {
                    'type': 'group',
                    'from': msg.get('sender', ''),
                    'content': msg.get('content', ''),
                    'timestamp': msg.get('timestamp', ''),
                    '_server_id': msg_id,
                }
                self.window.after(0, lambda m=msg_data, mid=msg_id: self.message_callback(m, mid))

    def _handle_private_history(self, message: dict):
        """处理私聊历史消息"""
        messages = message.get('messages', [])
        if self.message_callback and self.window:
            for msg in messages:
                msg_id = f"db_{msg.get('id', '')}"
                msg_data = {
                    'type': 'private',
                    'from': msg.get('sender', ''),
                    'to': msg.get('receiver', ''),
                    'content': msg.get('content', ''),
                    'timestamp': msg.get('timestamp', ''),
                    '_server_id': msg_id,
                }
                self.window.after(0, lambda m=msg_data, mid=msg_id: self.message_callback(m, mid))

    def _handle_login_policy(self, message: dict):
        """处理登录策略响应，控制密码框显隐"""
        needs_password = message.get('needs_password', True)
        msg = message.get('message', '')

        def callback():
            if hasattr(self, '_on_policy_received') and self._on_policy_received:
                self._on_policy_received(needs_password, msg)
        if self.window:
            self.window.after(0, callback)

    def _handle_unread_counts(self, message: dict):
        """处理未读计数响应"""
        counts = message.get('counts', {})

        def callback():
            if hasattr(self, '_on_unread_received') and self._on_unread_received:
                self._on_unread_received(counts)
        if self.window:
            self.window.after(0, callback)

    def _handle_unread_increment(self, message: dict):
        """收到新私聊时自动 +1 未读（未打开该私聊窗口时）"""
        sender = message.get('from', '')

        def callback():
            if hasattr(self, '_on_unread_increment') and self._on_unread_increment:
                self._on_unread_increment(sender)
        if self.window:
            self.window.after(0, callback)

    def set_message_callback(self, callback: Callable):
        """设置消息回调函数"""
        self.message_callback = callback

    def set_online_users_callback(self, callback: Callable):
        """设置在线用户列表回调函数"""
        self.online_users_callback = callback

    def request_online_users(self):
        """请求在线用户列表"""
        self.send_message({'type': 'get_online_users'})

    def request_group_history(self):
        """请求群聊历史"""
        self.send_message({'type': 'get_group_history'})

    def request_private_history(self, with_user: str):
        """请求私聊历史"""
        self.send_message({'type': 'get_private_history', 'with_user': with_user})

    def request_login_policy(self, username: str):
        """查询登录策略（本次是否需要密码）"""
        self.send_message({'type': 'check_login_policy', 'username': username})

    def request_unread_counts(self):
        """请求所有未读计数"""
        self.send_message({'type': 'get_unread_counts'})

    def clear_unread(self, from_user: str):
        """清零与某人的未读计数"""
        self.send_message({'type': 'clear_unread', 'from_user': from_user})

    def _reset_connecting_state(self):
        """重置连接状态"""
        self._is_connecting = False

    # ==================== 界面部分 ====================

    def run_login(self, on_success=None):
        """运行登录界面"""
        self.window = tk.Tk()
        self.window.withdraw()  # 隐藏根窗口

        self._login_frame = tk.Toplevel(self.window)
        self._login_frame.title("聊天系统 - 登录")
        self._login_frame.geometry("450x500")
        self._login_frame.resizable(False, False)
        self._login_frame.configure(bg='#f5f5f5')

        self._on_login_success = on_success
        self._create_login_ui()

        # 居中显示
        self._login_frame.update_idletasks()
        x = (self._login_frame.winfo_screenwidth() // 2) - (self._login_frame.winfo_width() // 2)
        y = (self._login_frame.winfo_screenheight() // 2) - (self._login_frame.winfo_height() // 2)
        self._login_frame.geometry(f"+{x}+{y}")

        self.window.mainloop()

    def _create_login_ui(self):
        """创建登录UI（无快速登录入口，密码框根据服务器策略动态显示）"""
        main_frame = tk.Frame(self._login_frame, bg='#f5f5f5')
        main_frame.pack(expand=True, fill='both', padx=40, pady=40)

        tk.Label(
            main_frame,
            text="多人聊天系统",
            font=("Microsoft YaHei", 22, "bold"),
            bg='#f5f5f5',
            fg='#1976d2'
        ).pack(pady=(0, 30))

        tk.Label(
            main_frame,
            text="TCP Multi-User Chat",
            font=("Arial", 10),
            bg='#f5f5f5',
            fg='#888888'
        ).pack(pady=(0, 40))

        # 服务器配置
        server_frame = tk.LabelFrame(
            main_frame, text="  服务器配置  ",
            bg='#f5f5f5', fg='#1976d2',
            padx=15, pady=10,
            font=("Microsoft YaHei", 10)
        )
        server_frame.pack(fill='x', pady=(0, 20))

        tk.Label(server_frame, text="地址:", bg='#f5f5f5', fg='#333333').grid(
            row=0, column=0, sticky='w', pady=5)
        self._host_entry = tk.Entry(server_frame, width=20, font=("Microsoft YaHei", 10))
        self._host_entry.insert(0, DEFAULT_HOST)
        self._host_entry.grid(row=0, column=1, padx=10, pady=5)

        tk.Label(server_frame, text="端口:", bg='#f5f5f5', fg='#333333').grid(
            row=1, column=0, sticky='w', pady=5)
        self._port_entry = tk.Entry(server_frame, width=20, font=("Microsoft YaHei", 10))
        self._port_entry.insert(0, str(DEFAULT_PORT))
        self._port_entry.grid(row=1, column=1, padx=10, pady=5)

        # 登录表单
        login_frame = tk.LabelFrame(
            main_frame, text="  用户登录  ",
            bg='#f5f5f5', fg='#1976d2',
            padx=15, pady=10,
            font=("Microsoft YaHei", 10)
        )
        login_frame.pack(fill='x', pady=(0, 20))

        tk.Label(login_frame, text="用户名:", bg='#f5f5f5', fg='#333333').grid(
            row=0, column=0, sticky='w', pady=8)
        self._username_entry = tk.Entry(login_frame, width=20, font=("Microsoft YaHei", 10))
        self._username_entry.grid(row=0, column=1, padx=10, pady=8)
        # 用户名失焦时查询登录策略
        self._username_entry.bind('<FocusOut>', lambda e: self._query_login_policy())
        self._username_entry.bind('<KeyRelease>', lambda e: self._query_login_policy())

        tk.Label(login_frame, text="密码:", bg='#f5f5f5', fg='#333333').grid(
            row=1, column=0, sticky='w', pady=8)
        self._password_entry = tk.Entry(login_frame, width=20, show='*', font=("Microsoft YaHei", 10))
        self._password_entry.grid(row=1, column=1, padx=10, pady=8)

        # 免密登录提示
        self._password_hint_label = tk.Label(
            login_frame, text="", bg='#f5f5f5', fg='#4caf50',
            font=("Microsoft YaHei", 8)
        )
        self._password_hint_label.grid(row=2, column=1, sticky='w', padx=10)

        # 按钮
        btn_frame = tk.Frame(main_frame, bg='#f5f5f5')
        btn_frame.pack(pady=10)

        self._login_btn = tk.Button(
            btn_frame,
            text="登 录",
            width=12,
            command=self._on_login_click,
            bg='#2196f3',
            fg='white',
            font=("Microsoft YaHei", 11, "bold"),
            relief='flat',
            cursor='hand2'
        )
        self._login_btn.pack(side='left', padx=8)

        tk.Button(
            btn_frame,
            text="注 册",
            width=12,
            command=self._on_register_click,
            bg='white',
            fg='#2196f3',
            font=("Microsoft YaHei", 11),
            relief='flat',
            cursor='hand2'
        ).pack(side='left', padx=8)

        self._username_entry.bind('<Return>', lambda e: self._on_login_click())
        self._password_entry.bind('<Return>', lambda e: self._on_login_click())

        tk.Label(
            main_frame,
            text="本地测试请确保服务器已启动",
            font=("Microsoft YaHei", 8),
            bg='#f5f5f5',
            fg='#888888'
        ).pack(side='bottom', pady=10)

    def _query_login_policy(self):
        """用户名变化后，向服务器查询本次是否需要密码"""
        username = self._username_entry.get().strip()
        if not username:
            self._password_hint_label.config(text="")
            self._password_entry.grid()
            return

        # 如果已连接，直接查询
        if self.socket and self.running:
            self.send_message({'type': 'check_login_policy', 'username': username})
            # 注册回调（收到响应时更新UI）
            self._on_policy_received = self._apply_login_policy
        else:
            # 尝试连接服务器后查询
            host = self._host_entry.get().strip()
            port_str = self._port_entry.get().strip()
            try:
                port = int(port_str)
            except ValueError:
                return
            self.host = host
            self.port = port
            if self.connect(host, port):
                self.send_message({'type': 'check_login_policy', 'username': username})
                self._on_policy_received = self._apply_login_policy
            else:
                self._password_hint_label.config(text="")
                self._password_entry.grid()

    def _apply_login_policy(self, needs_password: bool, message: str):
        """根据登录策略显示或隐藏密码框"""
        if needs_password:
            self._password_entry.grid()
            self._password_hint_label.config(text="")
            self._password_entry.focus()
        else:
            self._password_entry.delete(0, 'end')
            self._password_hint_label.config(
                text="今日第2-3次登录，无需密码")
            self._password_entry.grid_remove()
        self._password_policy_received = not needs_password

    def _on_login_click(self):
        """处理登录按钮点击"""
        if self._is_connecting:
            return
        self._is_connecting = True
        self._login_btn.config(state='disabled', text="连接中...")

        host = self._host_entry.get().strip()
        port_str = self._port_entry.get().strip()
        username = self._username_entry.get().strip()
        password = self._password_entry.get()
        skip_password = getattr(self, '_password_policy_received', False)

        if not all([host, port_str, username]):
            messagebox.showwarning("输入错误", "请填写服务器地址、端口和用户名")
            self._reset_connecting_state()
            self._login_btn.config(state='normal', text="登 录")
            return

        # 若未隐藏密码框，则必须输入密码
        if self._password_entry.winfo_viewable() and not password:
            messagebox.showwarning("输入错误", "请输入密码")
            self._reset_connecting_state()
            self._login_btn.config(state='normal', text="登 录")
            return

        try:
            port = int(port_str)
        except ValueError:
            messagebox.showerror("端口错误", "端口必须是有效数字")
            self._reset_connecting_state()
            self._login_btn.config(state='normal', text="登 录")
            return

        self.host = host
        self.port = port

        if not self.connect(host, port):
            messagebox.showerror("连接失败",
                f"无法连接到服务器 {host}:{port}\n\n请检查:\n1. 服务器是否已启动\n2. 服务器地址是否正确")
            self._reset_connecting_state()
            self._login_btn.config(state='normal', text="登 录")
            return

        self.send_message({
            'type': 'login',
            'username': username,
            'password': password,
            'skip_password': skip_password
        })

    def _on_register_click(self):
        """处理注册按钮点击"""
        if self._is_connecting:
            return
        self._is_connecting = True
        self._login_btn.config(state='disabled', text="注册中...")

        host = self._host_entry.get().strip()
        port_str = self._port_entry.get().strip()
        username = self._username_entry.get().strip()
        password = self._password_entry.get()

        if not all([host, port_str, username, password]):
            messagebox.showwarning("输入错误", "请填写所有字段")
            self._reset_connecting_state()
            self._login_btn.config(state='normal', text="登 录")
            return

        if len(username) < 2:
            messagebox.showwarning("用户名错误", "用户名至少2个字符")
            self._reset_connecting_state()
            self._login_btn.config(state='normal', text="登 录")
            return

        if len(password) < 4:
            messagebox.showwarning("密码错误", "密码至少4个字符")
            self._reset_connecting_state()
            self._login_btn.config(state='normal', text="登 录")
            return

        try:
            port = int(port_str)
        except ValueError:
            messagebox.showerror("端口错误", "端口必须是有效数字")
            self._reset_connecting_state()
            self._login_btn.config(state='normal', text="登 录")
            return

        self.host = host
        self.port = port

        if not self.connect(host, port):
            messagebox.showerror("连接失败", f"无法连接到服务器 {host}:{port}")
            self._reset_connecting_state()
            self._login_btn.config(state='normal', text="登 录")
            return

        self.send_message({
            'type': 'register',
            'username': username,
            'password': password
        })

    def _hide_login_and_create_chat(self):
        """隐藏登录窗口并创建聊天窗口"""
        # 销毁登录窗口
        self._login_frame.destroy()
        # 清除旧窗口内容，准备创建聊天界面
        for widget in self.window.winfo_children():
            widget.destroy()
        self._create_chat_window()

    def _create_chat_window(self):
        """创建聊天主窗口（群聊/私聊Tab切换）"""
        self.window.title(f"聊天系统 - {self.username}")
        self.window.geometry("900x750")
        self.window.minsize(700, 560)
        self.window.configure(bg='#eceff1')

        # 输入框使用固定像素高度（15px ≈ 10pt字体无内边距）
        entry_font = ("Microsoft YaHei", 10)
        self._entry_h = _font_height(self.window, entry_font)

        # ── 持久化历史记录 ──────────────────────────────────────────
        self._group_history: list = []      # 群聊消息列表（不重复）
        self._private_histories: dict = {}   # {username: [msg, ...]}

        # ── 未读计数 ───────────────────────────────────────────────
        self._unread_counts: dict = {}       # {from_user: count}
        self._active_private_user: Optional[str] = None  # 当前打开的私聊对象

        self._create_chat_ui()

        # 请求数据
        self.request_online_users()
        self.request_group_history()
        self.request_unread_counts()

        self.start_receive_thread()
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)
        self.window.mainloop()

    def _create_chat_ui(self):
        """创建聊天界面（顶部导航 + 主内容）"""
        # ── 顶部标题栏（固定高度）────────────────────────────────────
        top_frame = tk.Frame(self.window, bg='#1976d2', height=56)
        top_frame.pack(fill='x')
        top_frame.pack_propagate(False)

        tk.Label(top_frame, text=f"  {self.username}",
            font=("Microsoft YaHei", 15, "bold"),
            bg='#1976d2', fg='white').pack(side='left', pady=14)

        tk.Label(top_frame, text="● 在线",
            font=("Arial", 10), bg='#1976d2', fg='#90ee90').pack(side='left', padx=8, pady=14)

        tk.Button(top_frame, text="刷新用户", command=self.request_online_users,
            bg='#e3e8ee', fg='#546e7a', relief='flat', cursor='hand2',
            font=("Microsoft YaHei", 9), activebackground='#b0bec5',
            activeforeground='#263238', bd=0, padx=10, pady=4).pack(side='right', padx=15, pady=12)

        # ── Tab 切换栏 ─────────────────────────────────────────────
        self._tab_frame = tk.Frame(self.window, bg='#e3e8ee', height=44)
        self._tab_frame.pack(fill='x')
        self._tab_frame.pack_propagate(False)

        self._group_tab_btn = tk.Button(
            self._tab_frame, text="群聊",
            command=lambda: self._switch_tab('group'),
            bg='#1976d2', fg='white', relief='flat', cursor='hand2',
            font=("Microsoft YaHei", 11, "bold"), width=10, bd=0, pady=4,
            activebackground='#1565c0', activeforeground='white')
        self._group_tab_btn.pack(side='left', padx=(20, 5), pady=8)

        self._private_tab_btn = tk.Button(
            self._tab_frame, text="私聊",
            command=lambda: self._switch_tab('private'),
            bg='#cfd8dc', fg='#546e7a', relief='flat', cursor='hand2',
            font=("Microsoft YaHei", 11, "bold"), width=10, bd=0, pady=4,
            activebackground='#b0bec5', activeforeground='#37474f')
        self._private_tab_btn.pack(side='left', padx=5, pady=8)

        self._private_badge_label = tk.Label(
            self._tab_frame, text="", bg='#f44336', fg='white',
            font=("Arial", 8, "bold"), padx=4, pady=0)
        self._private_badge_label.pack(side='left', padx=0, pady=8)
        self._private_badge_label.pack_forget()  # 默认隐藏

        self._update_private_tab_badge()  # 初始化徽章

        # ── 主区域（群聊视图或私聊视图）── 动态切换 ─────────────────
        self._main_container = tk.Frame(self.window, bg='#eceff1')
        self._main_container.pack(fill='both', expand=True)

        # 群聊视图
        self._group_view = tk.Frame(self._main_container, bg='#eceff1')
        self._build_group_view(self._group_view)

        # 私聊视图（默认隐藏）
        self._private_view = tk.Frame(self._main_container, bg='#eceff1')
        self._build_private_view(self._private_view)
        self._private_view.pack_forget()

        self._current_tab = 'group'

        # 初始化时显示群聊视图
        self._group_view.pack(fill='both', expand=True)

    # ════════════════════════════════════════════════════════════════════
    #  群聊视图
    # ════════════════════════════════════════════════════════════════════

    def _build_group_view(self, parent: tk.Frame):
        """构建群聊视图：消息显示区 + 底部固定输入框（flex-grow 布局）"""
        # 外层容器：pack_propagate(False) 固定整体高度，
        # 内层结构：消息区 expand=True 填充剩余空间，输入框固定在底部
        container = tk.Frame(parent, bg='#eceff1')
        container.pack(fill='both', expand=True)

        # 消息显示区（flex-grow，填满剩余空间）
        msg_frame = tk.Frame(container, bg='#eceff1')
        msg_frame.pack(fill='both', expand=True, padx=10, pady=(10, 5))

        self._group_chat_area = scrolledtext.ScrolledText(
            msg_frame, wrap='word', font=("Microsoft YaHei", 13),
            bg='#fefefe', fg='#2d2d2d', insertbackground='#2d2d2d',
            relief='flat', state='disabled', bd=0,
            highlightthickness=0, borderwidth=0)
        self._group_chat_area.pack(fill='both', expand=True)

        self._group_chat_area.tag_configure('group', foreground='#1565c0',
            lmargin1=10, lmargin2=10)
        self._group_chat_area.tag_configure('system', foreground='#c62828',
            lmargin1=10, lmargin2=10, font=("Microsoft YaHei", 11, "italic"))
        self._group_chat_area.tag_configure('timestamp', foreground='#888888',
            font=("Microsoft YaHei", 10))
        self._group_chat_area.tag_configure('sender', foreground='#1565c0', font=("Microsoft YaHei", 13, 'bold'))

        # 输入区（固定高度，始终显示在底部）
        input_frame = tk.Frame(container, bg='white', height=self._entry_h)
        input_frame.pack(fill='x', side='bottom', padx=10, pady=(0, 10))
        input_frame.pack_propagate(False)

        self._group_input = tk.Entry(input_frame, font=("Microsoft YaHei", 10),
            bg='#f8f8f8', fg='#333333', insertbackground='#1976d2',
            relief='solid', bd=1, highlightthickness=1,
            highlightcolor='#2196f3', highlightbackground='#e0e0e0')
        self._group_input.pack(side='left', fill='x', expand=True,
            ipady=0, padx=(10, 6), pady=(7, 7))
        # 发送保护：防止 Enter 和按钮同时触发
        self._group_sending = False
        self._group_input.bind('<Return>', lambda e: self._do_send_group())
        self._group_send_btn = tk.Button(input_frame, text="发 送",
            bg='#2196f3', fg='white', relief='flat', cursor='hand2',
            font=("Microsoft YaHei", 10, "bold"), width=8,
            activebackground='#1565c0', activeforeground='white',
            bd=0, pady=4)
        self._group_send_btn.pack(side='right', padx=(0, 4), pady=7)

    def _do_send_group(self):
        """实际执行群聊发送（带防重复保护）"""
        if self._group_sending:
            return
        content = self._group_input.get().strip()
        if not content:
            return
        self._group_sending = True
        self._group_input.delete(0, 'end')

        # 生成临时消息 ID，用于乐观渲染 + 去重
        msg_id = str(uuid.uuid4())
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # 与服务器一致的全格式时间戳
        local_msg = {'type': 'group', 'from': self.username,
                     'content': content, 'timestamp': ts,
                     '_client_id': msg_id, '_status': 'sending'}

        # 乐观渲染：立即显示发送中消息
        self._pending_msgs[msg_id] = {'status': 'sending', 'msg': local_msg}
        self._add_group_message(local_msg, msg_id)

        self.send_message({'type': 'message', 'content': content, 'client_msg_id': msg_id})
        self._group_sending = False

    def _send_group_message(self):
        self._do_send_group()

    def _add_group_message(self, msg: dict, msg_id: str = ''):
        """向群聊历史追加消息（基于消息 ID 去重），刷新显示"""
        # 基于内容+时间戳去重（兼容历史消息没有 ID 的情况）
        dup_key = (msg.get('from'), msg.get('content'), msg.get('timestamp'))
        if hasattr(self, '_group_seen_keys') and dup_key in self._group_seen_keys:
            return
        if not hasattr(self, '_group_seen_keys'):
            self._group_seen_keys = set()
        self._group_seen_keys.add(dup_key)

        self._group_history.append(msg)
        self._render_group_history()

    def _render_group_history(self):
        """重新渲染群聊历史"""
        self._group_chat_area.config(state='normal')
        self._group_chat_area.delete(1.0, 'end')
        for m in self._group_history:
            ts = m.get('timestamp', '')
            sender = m.get('from', '')
            content = m.get('content', '')
            mt = m.get('type', '')
            if mt == 'system':
                self._group_chat_area.insert('end',
                    f"[{ts}] *** {content} ***\n\n", ('system', 'timestamp'))
            else:
                self._group_chat_area.insert('end', f"[{ts}] ", ('timestamp'))
                self._group_chat_area.insert('end', f"{sender}", ('sender'))
                self._group_chat_area.insert('end', f": {content}\n\n", ('group'))
        self._group_chat_area.see('end')
        self._group_chat_area.config(state='disabled')

    # ════════════════════════════════════════════════════════════════════
    #  私聊视图
    # ════════════════════════════════════════════════════════════════════

    def _build_private_view(self, parent: tk.Frame):
        """构建私聊视图：左侧用户列表（带未读徽章） + 右侧消息区"""
        # 左侧：用户列表
        left = tk.Frame(parent, bg='white', width=200)
        left.pack(side='left', fill='y')
        left.pack_propagate(False)

        tk.Label(left, text="联系人", font=("Microsoft YaHei", 11, "bold"),
            bg='white', fg='#2196f3', pady=10).pack()

        container = tk.Frame(left, bg='white')
        container.pack(fill='both', expand=True, padx=5, pady=5)

        self._users_canvas = tk.Canvas(container, bg='white', highlightthickness=0)
        scroll = tk.Scrollbar(container, orient='vertical', bg='white',
            command=self._users_canvas.yview)
        self._users_list_frame = tk.Frame(self._users_canvas, bg='white')

        self._users_canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self._users_canvas.pack(side='left', fill='both', expand=True)

        self._users_list_frame.bind('<Configure>',
            lambda e: self._users_canvas.configure(
                scrollregion=self._users_canvas.bbox('all')))
        self._users_canvas.bind('<Configure>',
            lambda e: self._users_canvas.itemconfig(
                self._users_window_id, width=e.width))

        self._users_window_id = self._users_canvas.create_window(
            (0, 0), window=self._users_list_frame, anchor='nw')

        self._no_user_label = tk.Label(left,
            text="暂无联系人\n向其他用户发送消息后出现",
            font=("Microsoft YaHei", 9), bg='white', fg='#aaaaaa',
            justify='center')
        self._no_user_label.pack(pady=20)

        # 右侧：消息区
        self._private_right = tk.Frame(parent, bg='#eceff1')
        self._private_right.pack(side='right', fill='both', expand=True)

        # 空状态提示
        self._private_empty = tk.Label(self._private_right,
            text="请从左侧选择一个联系人开始私聊",
            font=("Microsoft YaHei", 13), bg='#eceff1', fg='#90a4af',
            justify='center')
        self._private_empty.pack(fill='both', expand=True)

        self.set_online_users_callback(self._update_user_list_with_badges)

        # 未读增量回调
        self._on_unread_increment = self._handle_unread_inc

        # 收到未读计数响应的回调
        self._on_unread_received = self._apply_unread_counts

    def _update_private_tab_badge(self):
        """更新私聊Tab按钮的未读徽章"""
        total = sum(self._unread_counts.values())
        if total > 0:
            text = str(total) if total < 100 else '99+'
            self._private_badge_label.config(text=text)
            self._private_badge_label.pack(side='left', padx=0, pady=8)
        else:
            self._private_badge_label.pack_forget()

    def _handle_unread_inc(self, from_user: str):
        """收到来自某人的新私聊消息时更新未读计数"""
        if from_user == self._active_private_user:
            # 正在与他聊天，不计入未读
            return
        self._unread_counts[from_user] = self._unread_counts.get(from_user, 0) + 1
        self._refresh_user_buttons()
        self._update_private_tab_badge()

    def _apply_unread_counts(self, counts: dict):
        """从服务器拉取初始未读计数"""
        self._unread_counts = dict(counts)
        self._refresh_user_buttons()
        self._update_private_tab_badge()

    def _refresh_user_buttons(self):
        """刷新用户列表按钮（带/不带徽章）"""
        for widget in self._users_list_frame.winfo_children():
            widget.destroy()

        for user in self.online_users:
            if user == self.username:
                continue
            self._make_user_button(user)

        # 更新空状态提示可见性
        has_users = any(u != self.username for u in self.online_users)
        self._no_user_label.pack_forget() if has_users else self._no_user_label.pack(pady=20)

    def _make_user_button(self, user: str):
        """为单个用户创建带/不带徽章的按钮"""
        unread = self._unread_counts.get(user, 0)
        is_active = (user == self._active_private_user)
        bg = '#e3f2fd' if is_active else '#f5f5f5'
        fg = '#1565c0' if is_active else '#2e7d32'

        container = tk.Frame(self._users_list_frame, bg=bg)
        container.pack(fill='x', pady=1)

        name_label = tk.Label(container, text=f"  {user}",
            font=("Microsoft YaHei", 10), bg=bg, fg=fg,
            cursor='hand2', anchor='w')
        name_label.pack(side='left', fill='x', expand=True, ipady=6)
        name_label.bind('<Button-1>', lambda e, u=user: self._open_private_chat(u))
        name_label.bind('<Enter>', lambda e, lbl=name_label: lbl.config(bg='#e8f5e9'))
        name_label.bind('<Leave>',
            lambda e, lbl=name_label, b=bg: lbl.config(bg=b))

        if unread > 0:
            badge = tk.Label(container, text=str(unread) if unread < 100 else '99+',
                bg='#f44336', fg='white', font=("Arial", 8, "bold"),
                width=3 if unread < 10 else 4, height=1)
            badge.pack(side='right', padx=(0, 5), pady=3)

    def _open_private_chat(self, user: str):
        """打开与某人的私聊窗口"""
        # 切换激活用户
        self._active_private_user = user
        self._unread_counts[user] = 0
        self._refresh_user_buttons()

        # 通知服务器清零未读
        self.clear_unread(user)
        self._update_private_tab_badge()

        # 隐藏空状态，显示私聊消息区
        self._private_empty.pack_forget()
        for w in self._private_right.pack_slaves():
            if w != self._private_empty:
                w.destroy()

        # ── 顶部：私聊对象标签 ─────────────────────────────────
        header = tk.Frame(self._private_right, bg='#eceff1')
        header.pack(fill='x', padx=10, pady=(10, 5))

        self._private_header_label = tk.Label(header,
            text=f"正在与 {user} 私聊",
            font=("Microsoft YaHei", 12, "bold"),
            bg='#eceff1', fg='#1565c0')
        self._private_header_label.pack(side='left')

        tk.Button(header, text="返回联系人列表",
            command=self._close_private_chat,
            bg='white', fg='#2196f3', relief='flat', cursor='hand2',
            font=("Microsoft YaHei", 9)).pack(side='right')

        # ── 消息显示区 ─────────────────────────────────────────
        msg_area_frame = tk.Frame(self._private_right, bg='#eceff1')
        msg_area_frame.pack(fill='both', expand=True, padx=10, pady=5)

        self._private_chat_area = scrolledtext.ScrolledText(
            msg_area_frame, wrap='word', font=("Microsoft YaHei", 13),
            bg='#fefefe', fg='#2d2d2d', insertbackground='#1976d2',
            relief='flat', state='disabled', bd=0, highlightthickness=0, borderwidth=0)
        self._private_chat_area.pack(fill='both', expand=True)

        self._private_chat_area.tag_configure('private', foreground='#2e7d32',
            lmargin1=10, lmargin2=10)
        self._private_chat_area.tag_configure('timestamp', foreground='#888888',
            font=("Microsoft YaHei", 10))
        self._private_chat_area.tag_configure('private_sender', foreground='#2e7d32',
            font=("Microsoft YaHei", 13, "bold"))
        self._private_chat_area.tag_configure('private_receiver', foreground='#c62828',
            font=("Microsoft YaHei", 13, "bold"))

        # ── 输入区（固定高度）────────────────────────────────────
        input_f = tk.Frame(self._private_right, bg='white', height=self._entry_h)
        input_f.pack(fill='x', padx=10, pady=(0, 10))
        input_f.pack_propagate(False)

        self._private_input = tk.Entry(input_f, font=("Microsoft YaHei", 10),
            bg='#f8f8f8', fg='#333333', insertbackground='#1976d2',
            relief='solid', bd=1, highlightthickness=1,
            highlightcolor='#2196f3', highlightbackground='#e0e0e0')
        self._private_input.pack(side='left', fill='x', expand=True,
            ipady=0, padx=(10, 6), pady=(7, 7))
        self._private_sending = False
        self._private_input.bind('<Return>',
            lambda e: self._do_send_private(user))

        tk.Button(input_f, text="发 送",
            command=lambda: self._do_send_private(user),
            bg='#2196f3', fg='white', relief='flat', cursor='hand2',
            font=("Microsoft YaHei", 11, "bold"), width=8,
            activebackground='#1565c0', activeforeground='white',
            bd=0, pady=4).pack(side='right', padx=(0, 4), pady=8)

        # 加载历史记录
        self._render_private_history(user)

    def _close_private_chat(self):
        """关闭私聊视图，回到空状态"""
        self._active_private_user = None
        for w in self._private_right.pack_slaves():
            w.destroy()
        self._private_empty.pack(fill='both', expand=True)
        self._refresh_user_buttons()

    def _do_send_private(self, to_user: str):
        """实际执行私聊发送（带防重复保护）"""
        if self._private_sending:
            return
        content = self._private_input.get().strip()
        if not content:
            return
        self._private_sending = True
        self._private_input.delete(0, 'end')

        # 生成临时消息 ID，用于乐观渲染 + 去重
        msg_id = str(uuid.uuid4())
        ts = datetime.now().strftime("%H:%M:%S")
        local_msg = {'type': 'private', 'from': self.username, 'to': to_user,
                     'content': content, 'timestamp': ts,
                     '_client_id': msg_id, '_status': 'sending'}

        # 乐观渲染：立即显示发送中消息
        self._pending_msgs[msg_id] = {'status': 'sending', 'msg': local_msg}
        self._append_private_message(local_msg, msg_id)

        self.send_message({'type': 'private_message', 'to': to_user,
                           'content': content, 'client_msg_id': msg_id})
        self._private_sending = False

    def _append_private_message(self, msg: dict, msg_id: str = ''):
        """追加一条私聊消息到本地历史并刷新显示（内容去重）"""
        sender = msg.get('from', '')
        to_user = msg.get('to', '')
        other = to_user if sender == self.username else sender

        if other not in self._private_histories:
            self._private_histories[other] = []
        # 基于内容+时间戳去重
        dup_key = (sender, to_user, msg.get('content'), msg.get('timestamp'))
        if dup_key in getattr(self, '_priv_seen_keys', set()):
            return
        if not hasattr(self, '_priv_seen_keys'):
            self._priv_seen_keys = set()
        self._priv_seen_keys.add(dup_key)

        self._private_histories[other].append(msg)

        if other == self._active_private_user:
            self._render_private_history(other)

    def _render_private_history(self, user: str):
        """渲染某人的私聊历史"""
        history = self._private_histories.get(user, [])
        self._private_chat_area.config(state='normal')
        self._private_chat_area.delete(1.0, 'end')
        for m in history:
            ts = m.get('timestamp', '')
            sender = m.get('from', '')
            to_user = m.get('to', '')
            content = m.get('content', '')
            if sender == self.username:
                self._private_chat_area.insert('end', f"[{ts}] ", ('timestamp'))
                self._private_chat_area.insert('end', f"[我 -> {to_user}]",
                    ('private_sender'))
                self._private_chat_area.insert('end', f": {content}\n\n", ('private'))
            else:
                self._private_chat_area.insert('end', f"[{ts}] ", ('timestamp'))
                self._private_chat_area.insert('end', f"[{sender} -> 我]",
                    ('private_receiver'))
                self._private_chat_area.insert('end', f": {content}\n\n", ('private'))
        self._private_chat_area.see('end')
        self._private_chat_area.config(state='disabled')

    # ════════════════════════════════════════════════════════════════════
    #  Tab 切换
    # ════════════════════════════════════════════════════════════════════

    def _switch_tab(self, tab: str):
        """切换 Tab"""
        if tab == self._current_tab:
            return
        self._current_tab = tab

        self._group_tab_btn.config(bg='#1976d2' if tab == 'group' else '#cfd8dc',
            fg='white' if tab == 'group' else '#546e7a',
            activebackground='#1565c0' if tab == 'group' else '#b0bec5',
            activeforeground='white' if tab == 'group' else '#37474f')
        self._private_tab_btn.config(bg='#1976d2' if tab == 'private' else '#cfd8dc',
            fg='white' if tab == 'private' else '#546e7a',
            activebackground='#1565c0' if tab == 'private' else '#b0bec5',
            activeforeground='white' if tab == 'private' else '#37474f')

        for w in self._main_container.pack_slaves():
            w.pack_forget()

        if tab == 'group':
            self._group_view.pack(fill='both', expand=True)
        else:
            self._private_view.pack(fill='both', expand=True)
            self._refresh_user_buttons()
            self._update_private_tab_badge()

    # ════════════════════════════════════════════════════════════════════
    #  用户列表 & 消息分发
    # ════════════════════════════════════════════════════════════════════

    def _update_user_list_with_badges(self, users: list):
        """在线用户列表更新回调"""
        self.online_users = users
        self._refresh_user_buttons()

    # ── 统一消息分发中心 ────────────────────────────────────────────────
    def _display_message(self, msg: dict, msg_id: str = ''):
        """所有消息的统一入口（带消息 ID 去重）"""
        # ID 去重：已处理过的消息直接跳过
        if msg_id and msg_id in self._seen_msg_ids:
            return
        if msg_id:
            self._seen_msg_ids.add(msg_id)

        # 检查是否是待确认的乐观消息（服务器已回显，确认成功）
        server_id = msg.get('_server_id', '')
        client_id = msg.get('_client_id', '')
        pending_key = server_id or client_id

        if pending_key and pending_key in self._pending_msgs:
            # 服务器已确认，移除"发送中"状态
            del self._pending_msgs[pending_key]

        msg_type = msg.get('type', '')

        if msg_type == 'group':
            self._add_group_message(msg, msg_id)

        elif msg_type == 'private':
            sender = msg.get('from', '')
            to_user = msg.get('to', '')
            other = to_user if sender == self.username else sender
            self._append_private_message(msg, msg_id)

            if sender != self.username and other != self._active_private_user:
                self._unread_counts[other] = self._unread_counts.get(other, 0) + 1
                self._refresh_user_buttons()
                self._update_private_tab_badge()

        elif msg_type == 'system':
            self._add_group_message(msg, msg_id)

    def _on_close(self):
        """窗口关闭事件"""
        if messagebox.askokcancel("退出", "确定要退出聊天吗?"):
            self.disconnect()
            self.window.destroy()


class MultiClientLauncher:
    """多客户端启动器 - 支持同时启动多个聊天客户端"""

    def __init__(self):
        self.clients: list = []
        self.window: Optional[tk.Tk] = None
        self._chat_windows: set = set()  # 跟踪已打开的聊天窗口

    def launch(self):
        """启动多客户端管理器"""
        self.window = tk.Tk()
        self.window.title("多客户端模拟器")
        self.window.geometry("500x600")
        self.window.configure(bg='#f5f5f5')
        self.window.resizable(False, False)

        self._create_launcher_ui()

        # 居中
        self.window.update_idletasks()
        x = (self.window.winfo_screenwidth() // 2) - 250
        y = (self.window.winfo_screenheight() // 2) - 300
        self.window.geometry(f"+{x}+{y}")

        self.window.mainloop()

    def _create_launcher_ui(self):
        """创建启动器UI"""
        # 标题
        tk.Label(
            self.window,
            text="多人聊天模拟器",
            font=("Microsoft YaHei", 20, "bold"),
            bg='#f5f5f5',
            fg='#1976d2'
        ).pack(pady=20)

        tk.Label(
            self.window,
            text="可同时启动多个客户端账号进行聊天测试",
            font=("Microsoft YaHei", 9),
            bg='#f5f5f5',
            fg='#888888'
        ).pack(pady=(0, 20))

        # 单账号登录区域
        single_frame = tk.LabelFrame(
            self.window, text=" 单账号登录 ",
            bg='#f5f5f5', fg='#1976d2',
            padx=20, pady=15,
            font=("Microsoft YaHei", 10)
        )
        single_frame.pack(pady=10, padx=30, fill='x')

        # 服务器配置
        server_frame = tk.Frame(single_frame, bg='#f5f5f5')
        server_frame.pack(fill='x')

        tk.Label(server_frame, text="地址:", bg='#f5f5f5', fg='#333333', font=("Microsoft YaHei", 9)).grid(row=0, column=0, sticky='w', padx=5, pady=3)
        self._launcher_host = tk.Entry(server_frame, width=12, font=("Microsoft YaHei", 9))
        self._launcher_host.insert(0, DEFAULT_HOST)
        self._launcher_host.grid(row=0, column=1, padx=5, pady=3)

        tk.Label(server_frame, text="端口:", bg='#f5f5f5', fg='#333333', font=("Microsoft YaHei", 9)).grid(row=0, column=2, sticky='w', padx=(10, 5), pady=3)
        self._launcher_port = tk.Entry(server_frame, width=8, font=("Microsoft YaHei", 9))
        self._launcher_port.insert(0, str(DEFAULT_PORT))
        self._launcher_port.grid(row=0, column=3, padx=5, pady=3)

        # 用户名和密码输入
        cred_frame = tk.Frame(single_frame, bg='#f5f5f5')
        cred_frame.pack(fill='x', pady=(10, 0))

        tk.Label(cred_frame, text="用户名:", bg='#f5f5f5', fg='#333333', font=("Microsoft YaHei", 9)).grid(row=0, column=0, sticky='w', padx=5, pady=3)
        self._launcher_username = tk.Entry(cred_frame, width=15, font=("Microsoft YaHei", 9))
        self._launcher_username.grid(row=0, column=1, padx=5, pady=3)

        tk.Label(cred_frame, text="密码:", bg='#f5f5f5', fg='#333333', font=("Microsoft YaHei", 9)).grid(row=0, column=2, sticky='w', padx=(10, 5), pady=3)
        self._launcher_password = tk.Entry(cred_frame, width=10, show='*', font=("Microsoft YaHei", 9))
        self._launcher_password.grid(row=0, column=3, padx=5, pady=3)

        # 登录和注册按钮
        btn_frame = tk.Frame(single_frame, bg='#f5f5f5')
        btn_frame.pack(pady=(10, 0))

        tk.Button(
            btn_frame,
            text="登录",
            command=self._launcher_login,
            bg='#2196f3',
            fg='white',
            font=("Microsoft YaHei", 10, "bold"),
            relief='flat',
            cursor='hand2',
            width=8
        ).pack(side='left', padx=5)

        tk.Button(
            btn_frame,
            text="注册",
            command=self._launcher_register,
            bg='white',
            fg='#2196f3',
            font=("Microsoft YaHei", 10),
            relief='flat',
            cursor='hand2',
            width=8
        ).pack(side='left', padx=5)

        # 活跃客户端列表
        list_frame = tk.LabelFrame(
            self.window, text=" 活跃客户端 ",
            bg='#f5f5f5', fg='#1976d2',
            padx=15, pady=10,
            font=("Microsoft YaHei", 10)
        )
        list_frame.pack(pady=10, padx=30, fill='both', expand=True)

        self._client_listbox = tk.Listbox(
            list_frame,
            bg='white',
            fg='#333333',
            font=("Consolas", 10),
            relief='flat',
            selectbackground='#2196f3',
            selectforeground='white'
        )
        self._client_listbox.pack(fill='both', expand=True)

        btn_bottom_frame = tk.Frame(self.window, bg='#f5f5f5')
        btn_bottom_frame.pack(pady=10)

        tk.Button(
            btn_bottom_frame,
            text="关闭所有客户端",
            command=self._close_all_clients,
            bg='#f44336',
            fg='white',
            font=("Microsoft YaHei", 9),
            relief='flat',
            cursor='hand2'
        ).pack(side='left', padx=10)

        tk.Button(
            btn_bottom_frame,
            text="关闭管理器",
            command=self._on_launcher_close,
            bg='#9e9e9e',
            fg='white',
            font=("Microsoft YaHei", 9),
            relief='flat',
            cursor='hand2'
        ).pack(side='left', padx=10)

    def _get_launcher_config(self):
        """获取启动器配置"""
        host = self._launcher_host.get().strip() or DEFAULT_HOST
        try:
            port = int(self._launcher_port.get().strip())
        except ValueError:
            port = DEFAULT_PORT
        return host, port

    def _launcher_login(self):
        """启动器直接登录"""
        username = self._launcher_username.get().strip()
        password = self._launcher_password.get()

        if not username or not password:
            messagebox.showwarning("输入错误", "请输入用户名和密码")
            return

        host, port = self._get_launcher_config()
        self._do_launcher_login(host, port, username, password)

    def _launcher_register(self):
        """启动器注册新账号"""
        username = self._launcher_username.get().strip()
        password = self._launcher_password.get()

        if not username or not password:
            messagebox.showwarning("输入错误", "请输入用户名和密码")
            return

        if len(username) < 2:
            messagebox.showwarning("用户名错误", "用户名至少2个字符")
            return

        if len(password) < 4:
            messagebox.showwarning("密码错误", "密码至少4个字符")
            return

        host, port = self._get_launcher_config()

        def do_register():
            import time
            import sys
            print(f"[注册流程] 开始注册用户: {username}", file=sys.stderr)

            # 连接服务器
            client = ChatClient()
            if not client.connect(host, port):
                print(f"[注册流程] 连接服务器失败", file=sys.stderr)
                self.window.after(0, lambda: messagebox.showerror("连接失败", f"无法连接到服务器 {host}:{port}"))
                return

            print(f"[注册流程] 已连接，发送注册请求", file=sys.stderr)

            # 发送注册请求
            client.send_message({'type': 'register', 'username': username, 'password': password})

            # 等待注册响应
            time.sleep(0.5)

            # 接收注册响应
            try:
                client.socket.settimeout(2.0)
                data = b''
                while True:
                    try:
                        chunk = client.socket.recv(4096)
                        if not chunk:
                            break
                        data += chunk
                        if b'\n' in data:
                            break
                    except socket.timeout:
                        break

                register_success = False
                if data:
                    messages = data.decode('utf-8', errors='ignore').strip().split('\n')
                    for msg_str in messages:
                        if msg_str.strip():
                            try:
                                msg = json.loads(msg_str)
                                print(f"[注册流程] 收到消息: {msg.get('type')}", file=sys.stderr)
                                if msg.get('type') == 'register_response':
                                    if msg.get('success'):
                                        register_success = True
                                        print(f"[注册流程] 注册成功!", file=sys.stderr)
                                        self.window.after(0, lambda: messagebox.showinfo("注册成功", "恭喜！注册成功，请登录！"))
                                    else:
                                        error_msg = msg.get('message', '注册失败')
                                        print(f"[注册流程] 注册失败: {error_msg}", file=sys.stderr)
                                        self.window.after(0, lambda m=error_msg: messagebox.showerror("注册失败", m))
                                    break
                            except json.JSONDecodeError:
                                continue

                # 关闭注册连接
                client.disconnect()

                if register_success:
                    print(f"[注册流程] 等待后执行登录...", file=sys.stderr)
                    # 等待一小段时间
                    time.sleep(0.3)
                    # 登录新注册的账号
                    self._do_launcher_login(host, port, username, password)

            except Exception as e:
                print(f"[注册流程] 错误: {e}", file=sys.stderr)
                logger.error(f"注册过程出错: {e}")
                self.window.after(0, lambda: messagebox.showerror("错误", f"注册出错: {e}"))
                client.disconnect()

        threading.Thread(target=do_register, daemon=True).start()

    def _do_launcher_login(self, host, port, username, password, skip_password=False):
        # 检查是否已有该用户的聊天窗口
        if username in self._chat_windows:
            messagebox.showwarning("窗口已存在", f"{username} 的聊天窗口已打开")
            return

        def do_login():
            import time
            import sys

            print(f"[登录流程] 开始登录用户: {username}", file=sys.stderr)

            # 连接服务器
            client = ChatClient()
            if not client.connect(host, port):
                print(f"[登录流程] 连接服务器失败", file=sys.stderr)
                self.window.after(0, lambda: messagebox.showerror("连接失败", f"无法连接到服务器 {host}:{port}"))
                return

            print(f"[登录流程] 已连接服务器，发送登录请求", file=sys.stderr)

            # 发送登录请求
            client.send_message({'type': 'login', 'username': username,
                                 'password': password, 'skip_password': skip_password})

            # 等待一小段时间让服务器处理
            time.sleep(0.5)

            print(f"[登录流程] 等待服务器响应...", file=sys.stderr)

            # 尝试接收响应
            try:
                client.socket.settimeout(2.0)
                data = b''
                while True:
                    try:
                        chunk = client.socket.recv(4096)
                        if not chunk:
                            break
                        data += chunk
                        print(f"[登录流程] 收到数据: {chunk}", file=sys.stderr)
                        # 如果收到完整消息就停止
                        if b'\n' in data:
                            break
                    except socket.timeout:
                        break

                print(f"[登录流程] 收到数据长度: {len(data)}", file=sys.stderr)

                if data:
                    messages = data.decode('utf-8', errors='ignore').strip().split('\n')
                    print(f"[登录流程] 解析到 {len(messages)} 条消息", file=sys.stderr)
                    for msg_str in messages:
                        if msg_str.strip():
                            try:
                                msg = json.loads(msg_str)
                                print(f"[登录流程] 收到消息类型: {msg.get('type')}", file=sys.stderr)
                                if msg.get('type') == 'login_response':
                                    if msg.get('success'):
                                        # 登录成功
                                        print(f"[登录流程] 登录成功! 创建聊天窗口", file=sys.stderr)
                                        self.window.after(0, lambda c=client, u=username: self._create_independent_chat_window(c, u))
                                        return
                                    else:
                                        # 登录失败
                                        error_msg = msg.get('message', '用户名或密码错误')
                                        print(f"[登录流程] 登录失败: {error_msg}", file=sys.stderr)
                                        self.window.after(0, lambda m=error_msg: messagebox.showerror("登录失败", m))
                                        client.disconnect()
                                        return
                            except json.JSONDecodeError as e:
                                print(f"[登录流程] JSON解析错误: {e}", file=sys.stderr)
                                continue

                # 超时或没有收到有效响应
                print(f"[登录流程] 未收到有效响应", file=sys.stderr)
                self.window.after(0, lambda: messagebox.showerror("登录失败", "服务器响应超时"))
                client.disconnect()
                return

            except Exception as e:
                print(f"[登录流程] 错误: {e}", file=sys.stderr)
                logger.error(f"登录过程出错: {e}")
                self.window.after(0, lambda: messagebox.showerror("错误", f"登录出错: {e}"))
                client.disconnect()
                return

        threading.Thread(target=do_login, daemon=True).start()

    def _create_independent_chat_window(self, client: 'ChatClient', username: str):
        """创建独立的聊天窗口（Tab 切换式，带未读徽章）"""
        import sys
        self._chat_windows.add(username)

        chat_window = tk.Toplevel(self.window)
        chat_window.title(f"聊天系统 - {username}")
        chat_window.geometry("900x750")
        chat_window.minsize(700, 560)
        chat_window.configure(bg='#eceff1')

        # 输入框使用固定像素高度
        entry_font = ("Microsoft YaHei", 10)
        entry_h = _font_height(chat_window, entry_font)

        # ── 持久化历史记录 ────────────────────────────────────
        group_history = []
        private_histories = {}   # {user: [msg, ...]}
        unread_counts = {}        # {from_user: count}
        active_private_user = [None]
        # 去重：已处理过的消息 ID 集合
        seen_msg_ids = set()
        # 待确认消息（乐观渲染）
        pending_msgs = {}
        # 内容去重集合
        group_seen_keys = set()

        # ── 窗口关闭处理 ─────────────────────────────────────
        def on_close():
            self._chat_windows.discard(username)
            client.disconnect()
            chat_window.destroy()
            self._update_client_list()
        chat_window.protocol("WM_DELETE_WINDOW", on_close)

        # ══ 顶部标题栏 ════════════════════════════════════════
        top = tk.Frame(chat_window, bg='#1976d2', height=56)
        top.pack(fill='x', pady=0)
        tk.Label(top, text=f"  {username}",
            font=("Microsoft YaHei", 15, "bold"),
            bg='#1976d2', fg='white').pack(side='left', pady=14)
        tk.Label(top, text="● 在线",
            font=("Arial", 10), bg='#1976d2', fg='#90ee90').pack(side='left', padx=8, pady=14)
        tk.Button(top, text="刷新用户", command=client.request_online_users,
            bg='#e3e8ee', fg='#546e7a', relief='flat', cursor='hand2',
            font=("Microsoft YaHei", 9), activebackground='#b0bec5',
            activeforeground='#263238', bd=0, padx=10, pady=4).pack(side='right', padx=15, pady=12)

        # ══ Tab 切换栏 ════════════════════════════════════════
        tab_frame = tk.Frame(chat_window, bg='#e3e8ee', height=44)
        tab_frame.pack(fill='x')
        tab_frame.pack_propagate(False)

        group_tab = tk.Button(tab_frame, text="群聊",
            bg='#1976d2', fg='white', relief='flat', cursor='hand2',
            font=("Microsoft YaHei", 11, "bold"), width=10, bd=0, pady=4,
            activebackground='#1565c0', activeforeground='white')
        private_tab = tk.Button(tab_frame, text="私聊",
            bg='#cfd8dc', fg='#546e7a', relief='flat', cursor='hand2',
            font=("Microsoft YaHei", 11, "bold"), width=10, bd=0, pady=4,
            activebackground='#b0bec5', activeforeground='#37474f')
        group_tab.pack(side='left', padx=(20, 5), pady=8)
        private_tab.pack(side='left', padx=5, pady=8)

        priv_badge = tk.Label(tab_frame, text="", bg='#f44336', fg='white',
            font=("Arial", 8, "bold"), padx=4, pady=0)
        priv_badge.pack(side='left', padx=0, pady=8)
        priv_badge.pack_forget()

        def update_priv_badge():
            total = sum(unread_counts.values())
            if total > 0:
                priv_badge.config(text=str(total) if total < 100 else '99+')
                priv_badge.pack(side='left', padx=0, pady=8)
            else:
                priv_badge.pack_forget()

        update_priv_badge()

        # ══ 主容器 ════════════════════════════════════════════
        main_container = tk.Frame(chat_window, bg='#eceff1')
        main_container.pack(fill='both', expand=True)

        # ── 群聊视图 ───────────────────────────────────────
        group_view = tk.Frame(main_container, bg='#eceff1')

        g_msg_frame = tk.Frame(group_view, bg='#eceff1')
        g_msg_frame.pack(fill='both', expand=True, padx=10, pady=(10, 5))
        g_chat = scrolledtext.ScrolledText(g_msg_frame, wrap='word',
            font=("Microsoft YaHei", 13), bg='#fefefe', fg='#2d2d2d',
            insertbackground='#1976d2', relief='flat', state='disabled',
            bd=0, highlightthickness=0, borderwidth=0)
        g_chat.pack(fill='both', expand=True)
        g_chat.tag_configure('group', foreground='#1565c0', lmargin1=10, lmargin2=10)
        g_chat.tag_configure('system', foreground='#c62828', lmargin1=10, lmargin2=10,
            font=("Microsoft YaHei", 11, "italic"))
        g_chat.tag_configure('timestamp', foreground='#888888', font=("Microsoft YaHei", 10))
        g_chat.tag_configure('sender', foreground='#1565c0', font=("Microsoft YaHei", 13, "bold"))

        g_input_frame = tk.Frame(group_view, bg='white', height=entry_h)
        g_input_frame.pack(fill='x', side='bottom', padx=10, pady=(0, 10))
        g_input_frame.pack_propagate(False)
        g_input = tk.Entry(g_input_frame, font=("Microsoft YaHei", 10),
            bg='#f8f8f8', fg='#333333', insertbackground='#1976d2',
            relief='solid', bd=1, highlightthickness=1,
            highlightcolor='#2196f3', highlightbackground='#e0e0e0')
        g_input.pack(side='left', fill='x', expand=True, ipady=0,
            padx=(10, 6), pady=(7, 7))
        g_send_btn = tk.Button(g_input_frame, text="发 送",
            bg='#2196f3', fg='white', relief='flat', cursor='hand2',
            font=("Microsoft YaHei", 10, "bold"), width=8,
            activebackground='#1565c0', activeforeground='white', bd=0, pady=7)
        g_send_btn.pack(side='right', padx=(0, 4), pady=7)

        # ── 发送保护：防止 Enter 和按钮同时触发导致重复发送 ───────────────────
        _sending_guard = [False]

        def _do_send_group_independent():
            if _sending_guard[0]:
                return
            content = g_input.get().strip()
            if not content:
                return
            _sending_guard[0] = True
            g_input.delete(0, 'end')
            msg_id = str(uuid.uuid4())
            ts = datetime.now().strftime("%H:%M:%S")
            client.send_message({'type': 'message', 'content': content, 'client_msg_id': msg_id})
            # 乐观渲染：立即显示发送中消息（带ID用于后续去重）
            add_group_msg({'type': 'group', 'from': username,
                           'content': content, 'timestamp': ts,
                           '_client_id': msg_id, '_status': 'sending'}, msg_id)
            _sending_guard[0] = False

        g_input.bind('<Return>', lambda e: _do_send_group_independent())
        g_send_btn.config(command=_do_send_group_independent)

        # ── 私聊视图 ───────────────────────────────────────
        private_view = tk.Frame(main_container, bg='#eceff1')

        # 左侧：联系人列表
        priv_left = tk.Frame(private_view, bg='white', width=200)
        priv_left.pack(side='left', fill='y')
        priv_left.pack_propagate(False)
        tk.Label(priv_left, text="联系人",
            font=("Microsoft YaHei", 11, "bold"),
            bg='white', fg='#2196f3', pady=10).pack()

        p_users_container = tk.Frame(priv_left, bg='white')
        p_users_container.pack(fill='both', expand=True, padx=5, pady=5)
        p_canvas = tk.Canvas(p_users_container, bg='white', highlightthickness=0)
        p_scroll = tk.Scrollbar(p_users_container, orient='vertical', bg='white',
            command=p_canvas.yview)
        p_users_inner = tk.Frame(p_canvas, bg='white')
        p_canvas.configure(yscrollcommand=p_scroll.set)
        p_scroll.pack(side='right', fill='y')
        p_canvas.pack(side='left', fill='both', expand=True)
        p_win_id = p_canvas.create_window((0, 0), window=p_users_inner, anchor='nw')
        p_users_inner.bind('<Configure>',
            lambda e: p_canvas.configure(scrollregion=p_canvas.bbox('all')))
        p_canvas.bind('<Configure>',
            lambda e: p_canvas.itemconfig(p_win_id, width=e.width))

        priv_no_user = tk.Label(priv_left,
            text="暂无联系人\n向其他用户发消息后出现",
            font=("Microsoft YaHei", 9), bg='white', fg='#aaaaaa', justify='center')
        priv_no_user.pack(pady=20)

        # 右侧：消息区（空状态）
        priv_right = tk.Frame(private_view, bg='#eceff1')
        priv_right.pack(side='right', fill='both', expand=True)
        priv_empty = tk.Label(priv_right,
            text="请从左侧选择联系人开始私聊",
            font=("Microsoft YaHei", 13), bg='#eceff1', fg='#90a4af', justify='center')
        priv_empty.pack(fill='both', expand=True)

        current_tab = ['group']

        # ── 内部函数 ────────────────────────────────────────

        def add_group_msg(msg, msg_id=''):
            """追加群聊消息（基于消息 ID / 内容去重）"""
            # ID 去重
            if msg_id and msg_id in seen_msg_ids:
                return
            # 内容去重兜底（历史消息没有 ID）
            dup_key = (msg.get('from'), msg.get('content'), msg.get('timestamp'))
            if dup_key in group_seen_keys:
                return
            group_seen_keys.add(dup_key)
            if msg_id:
                seen_msg_ids.add(msg_id)
            if msg not in group_history:
                group_history.append(msg)
            render_group()

        def render_group():
            g_chat.config(state='normal')
            g_chat.delete(1.0, 'end')
            for m in group_history:
                ts = m.get('timestamp', '')
                sender = m.get('from', '')
                content = m.get('content', '')
                mt = m.get('type', '')
                if mt == 'system':
                    g_chat.insert('end', f"[{ts}] *** {content} ***\n\n", ('system', 'timestamp'))
                else:
                    g_chat.insert('end', f"[{ts}] ", ('timestamp'))
                    g_chat.insert('end', f"{sender}", ('sender'))
                    g_chat.insert('end', f": {content}\n\n", ('group'))
            g_chat.see('end')
            g_chat.config(state='disabled')

        # 私聊消息区 ScrolledText 的引用（mutable，open_private_chat 打开时赋值）
        p_area_ref = [None]

        def _render_priv(p_area, target):
            """渲染指定联系人的私聊历史到 ScrolledText"""
            hist = private_histories.get(target, [])
            p_area.config(state='normal')
            p_area.delete(1.0, 'end')
            for m in hist:
                ts = m.get('timestamp', '')
                s = m.get('from', '')
                t = m.get('to', '')
                c = m.get('content', '')
                if s == username:
                    p_area.insert('end', f"[{ts}] ", ('timestamp'))
                    p_area.insert('end', f"[我 -> {t}]", ('private_sender'))
                    p_area.insert('end', f": {c}\n\n", ('private'))
                else:
                    p_area.insert('end', f"[{ts}] ", ('timestamp'))
                    p_area.insert('end', f"[{s} -> 我]", ('private_receiver'))
                    p_area.insert('end', f": {c}\n\n", ('private'))
            p_area.see('end')
            p_area.config(state='disabled')

        def append_private_msg(msg, msg_id=''):
            """追加私聊消息（基于消息 ID / 内容去重）"""
            # ID 去重
            if msg_id and msg_id in seen_msg_ids:
                return
            sender = msg.get('from', '')
            to_user = msg.get('to', '')
            other = to_user if sender == username else sender
            if other not in private_histories:
                private_histories[other] = []
            # 内容去重
            dup_key = (sender, to_user, msg.get('content'), msg.get('timestamp'))
            priv_key_name = f'_priv_keys_{other}'
            if not hasattr(append_private_msg, priv_key_name):
                setattr(append_private_msg, priv_key_name, set())
            priv_keys = getattr(append_private_msg, priv_key_name)
            if dup_key in priv_keys:
                return
            priv_keys.add(dup_key)
            if msg_id:
                seen_msg_ids.add(msg_id)
            if msg not in private_histories[other]:
                private_histories[other].append(msg)
            if other == active_private_user[0] and p_area_ref[0]:
                _render_priv(p_area_ref[0], other)

        def refresh_user_buttons(online_users):
            for widget in p_users_inner.winfo_children():
                widget.destroy()
            has_users = False
            for u in online_users:
                if u == username:
                    continue
                has_users = True
                unread = unread_counts.get(u, 0)
                is_active = (u == active_private_user[0])
                bg = '#e3f2fd' if is_active else '#f5f5f5'
                fg = '#1565c0' if is_active else '#2e7d32'
                row = tk.Frame(p_users_inner, bg=bg)
                row.pack(fill='x', pady=1)
                lbl = tk.Label(row, text=f"  {u}", font=("Microsoft YaHei", 10),
                    bg=bg, fg=fg, cursor='hand2', anchor='w')
                lbl.pack(side='left', fill='x', expand=True, ipady=6)
                lbl.bind('<Button-1>', lambda e, u=u: open_private_chat(u))
                lbl.bind('<Enter>', lambda e, l=lbl: l.config(bg='#e8f5e9'))
                lbl.bind('<Leave>', lambda e, l=lbl, b=bg: l.config(bg=b))
                if unread > 0:
                    tk.Label(row, text=str(unread) if unread < 100 else '99+',
                        bg='#f44336', fg='white', font=("Arial", 8, 'bold'),
                        width=3 if unread < 10 else 4, height=1).pack(
                        side='right', padx=(0, 5), pady=3)
            priv_no_user.pack_forget() if has_users else priv_no_user.pack(pady=20)

        def open_private_chat(target):
            active_private_user[0] = target
            unread_counts[target] = 0
            client.clear_unread(target)
            online_users = getattr(client, 'online_users', [])
            refresh_user_buttons(online_users)

            for w in priv_right.pack_slaves():
                w.destroy()
            priv_empty.destroy()

            # 顶部标签
            hdr = tk.Frame(priv_right, bg='#eceff1')
            hdr.pack(fill='x', padx=10, pady=(10, 5))
            tk.Label(hdr, text=f"正在与 {target} 私聊",
                font=("Microsoft YaHei", 12, "bold"),
                bg='#eceff1', fg='#1565c0').pack(side='left')
            tk.Button(hdr, text="返回",
                command=lambda: close_private_chat(target),
                bg='white', fg='#2196f3', relief='flat', cursor='hand2',
                font=("Microsoft YaHei", 9)).pack(side='right')

            # 消息区
            p_area_frame = tk.Frame(priv_right, bg='#eceff1')
            p_area_frame.pack(fill='both', expand=True, padx=10, pady=5)
            p_area = scrolledtext.ScrolledText(p_area_frame, wrap='word',
                font=("Microsoft YaHei", 13), bg='#fefefe', fg='#2d2d2d',
                insertbackground='#1976d2', relief='flat', state='disabled',
                bd=0, highlightthickness=0, borderwidth=0)
            p_area.pack(fill='both', expand=True)
            p_area.tag_configure('private', foreground='#2e7d32', lmargin1=10, lmargin2=10)
            p_area.tag_configure('timestamp', foreground='#888888', font=("Microsoft YaHei", 10))
            p_area.tag_configure('private_sender', foreground='#2e7d32', font=("Microsoft YaHei", 13, "bold"))
            p_area.tag_configure('private_receiver', foreground='#c62828', font=("Microsoft YaHei", 13, 'bold'))

            # 更新外层引用，使 append_private_msg 能访问到当前 p_area
            p_area_ref[0] = p_area

            # 输入区（固定高度）
            p_input_f = tk.Frame(priv_right, bg='white', height=entry_h)
            p_input_f.pack(fill='x', padx=10, pady=(0, 10))
            p_input_f.pack_propagate(False)
            p_input = tk.Entry(p_input_f, font=("Microsoft YaHei", 10),
                bg='#f8f8f8', fg='#333333', insertbackground='#1976d2',
                relief='solid', bd=1, highlightthickness=1,
                highlightcolor='#2196f3', highlightbackground='#e0e0e0')
            p_input.pack(side='left', fill='x', expand=True, ipady=0,
                padx=(10, 6), pady=(7, 7))

            # 私聊发送保护：防止 Enter 和按钮同时触发导致重复发送
            _priv_sending = [False]

            def send_priv():
                if _priv_sending[0]:
                    return
                content = p_input.get().strip()
                if not content:
                    return
                _priv_sending[0] = True
                p_input.delete(0, 'end')
                ts = datetime.now().strftime("%H:%M:%S")
                msg_id = str(uuid.uuid4())
                client.send_message({'type': 'private_message', 'to': target,
                                    'content': content, 'client_msg_id': msg_id})
                msg = {'type': 'private', 'from': username, 'to': target,
                       'content': content, 'timestamp': ts,
                       '_client_id': msg_id, '_status': 'sending'}
                append_private_msg(msg, msg_id)
                _render_priv(p_area_ref[0], target)
                _priv_sending[0] = False

            p_input.bind('<Return>', lambda e: send_priv())
            p_send_btn = tk.Button(p_input_f, text="发 送", command=send_priv,
                bg='#2196f3', fg='white', relief='flat', cursor='hand2',
                font=("Microsoft YaHei", 11, "bold"), width=8,
                activebackground='#1565c0', activeforeground='white', bd=0, pady=4)
            p_send_btn.pack(side='right', padx=(0, 4), pady=8)

            _render_priv(p_area_ref[0], target)

        def close_private_chat(target=None):
            active_private_user[0] = None
            for w in priv_right.pack_slaves():
                w.destroy()
            p = tk.Label(priv_right, text="请从左侧选择联系人开始私聊",
                font=("Microsoft YaHei", 13), bg='#eceff1', fg='#90a4af', justify='center')
            p.pack(fill='both', expand=True)
            online_users = getattr(client, 'online_users', [])
            refresh_user_buttons(online_users)

        def switch_tab(tab):
            if tab == current_tab[0]:
                return
            current_tab[0] = tab
            group_tab.config(bg='#1976d2' if tab == 'group' else '#cfd8dc',
                fg='white' if tab == 'group' else '#546e7a',
                activebackground='#1565c0' if tab == 'group' else '#b0bec5',
                activeforeground='white' if tab == 'group' else '#37474f')
            private_tab.config(bg='#1976d2' if tab == 'private' else '#cfd8dc',
                fg='white' if tab == 'private' else '#546e7a',
                activebackground='#1565c0' if tab == 'private' else '#b0bec5',
                activeforeground='white' if tab == 'private' else '#37474f')
            for w in main_container.pack_slaves():
                w.pack_forget()
            if tab == 'group':
                group_view.pack(fill='both', expand=True)
            else:
                private_view.pack(fill='both', expand=True)
                online_users = getattr(client, 'online_users', [])
                refresh_user_buttons(online_users)

        def dispatch_message(msg, msg_id=''):
            """
            所有消息的统一分发入口（带消息 ID 去重）。
            msg_id: 服务器回传的 client_msg_id，或 DB 主键前缀 "db_"
            """
            # ── ID 去重 ───────────────────────────────────────────────────
            # 先尝试从 msg 本身提取 server_id / client_id
            sid = msg.get('_server_id', '') or msg.get('_client_id', '')
            eff_id = msg_id or sid
            if eff_id and eff_id in seen_msg_ids:
                return
            if eff_id:
                seen_msg_ids.add(eff_id)

            mt = msg.get('type', '')
            if mt == 'group':
                add_group_msg(msg)
            elif mt == 'private':
                sender = msg.get('from', '')
                to_user = msg.get('to', '')
                other = to_user if sender == username else sender
                append_private_msg(msg)
                if sender != username and other != active_private_user[0]:
                    unread_counts[other] = unread_counts.get(other, 0) + 1
                    online_users = getattr(client, 'online_users', [])
                    refresh_user_buttons(online_users)
            elif mt == 'system':
                add_group_msg(msg)
            elif mt == 'online_users':
                online = msg.get('users', [])
                client.online_users = online
                refresh_user_buttons(online)
            elif mt == 'unread_increment':
                sender = msg.get('from', '')
                if sender != active_private_user[0]:
                    unread_counts[sender] = unread_counts.get(sender, 0) + 1
                    online_users = getattr(client, 'online_users', [])
                    refresh_user_buttons(online_users)
            elif mt == 'unread_counts':
                counts = msg.get('counts', {})
                unread_counts.clear()
                unread_counts.update(counts)
                online_users = getattr(client, 'online_users', [])
                refresh_user_buttons(online_users)
            elif mt in ('group_history', 'private_history'):
                msgs = msg.get('messages', [])
                mt2 = 'group' if mt == 'group_history' else 'private'
                for m in msgs:
                    msg_id = f"db_{m.get('id', '')}"
                    if mt2 == 'group':
                        mdata = {'type': 'group', 'from': m.get('sender', ''),
                                 'content': m.get('content', ''),
                                 'timestamp': m.get('timestamp', ''),
                                 '_server_id': msg_id}
                    else:
                        mdata = {'type': 'private', 'from': m.get('sender', ''),
                                 'to': m.get('receiver', ''),
                                 'content': m.get('content', ''),
                                 'timestamp': m.get('timestamp', ''),
                                 '_server_id': msg_id}
                    if mt2 == 'group':
                        add_group_msg(mdata, msg_id)
                    else:
                        append_private_msg(mdata, msg_id)

        # 初始化：显示群聊视图
        group_view.pack(fill='both', expand=True)

        # 绑定 Tab 按钮事件
        group_tab.config(command=lambda: switch_tab('group'))
        private_tab.config(command=lambda: switch_tab('private'))

        # 设置回调
        client.set_message_callback(dispatch_message)
        client.username = username
        client.window = chat_window
        client._chat_window = chat_window

        client.start_receive_thread()
        client.request_online_users()
        client.request_group_history()
        client.request_unread_counts()

        self.clients.append(client)
        self._update_client_list()

    def _update_client_list(self):
        """更新客户端列表"""
        self._client_listbox.delete(0, 'end')
        for i, client in enumerate(self.clients):
            status = "在线" if client.running else "离线"
            uname = getattr(client, 'username', 'unknown')
            self._client_listbox.insert('end', f"[{i+1}] {uname} - {status}")

    def _close_all_clients(self):
        """关闭所有客户端"""
        for client in self.clients[:]:
            try:
                client.disconnect()
                if hasattr(client, '_chat_window') and client._chat_window:
                    try:
                        client._chat_window.destroy()
                    except Exception:
                        pass
            except Exception:
                pass
        self.clients.clear()
        self._chat_windows.clear()
        self._update_client_list()
        messagebox.showinfo("提示", "所有客户端已关闭")

    def _on_launcher_close(self):
        """关闭启动器窗口"""
        if self._chat_windows:
            messagebox.showwarning("仍有客户端", "请先关闭所有聊天窗口")
            return
        if self.clients:
            if not messagebox.askyesno("确认", "仍有客户端在线，确定关闭？"):
                return
            self._close_all_clients()
        self.window.destroy()


def main():
    """主函数"""
    print("\n" + "="*50)
    print("    TCP 多用户聊天客户端")
    print("="*50 + "\n")

    launcher = MultiClientLauncher()
    launcher.launch()


if __name__ == "__main__":
    main()
