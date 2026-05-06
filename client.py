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
from datetime import datetime
from typing import Optional, Dict, Any, Callable

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, simpledialog

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
        }

        handler = handlers.get(msg_type)
        if handler:
            handler(message)
        else:
            logger.warning(f"未知消息类型: {msg_type}")

    def _handle_group_message(self, message: dict):
        """处理群聊消息"""
        msg_data = {
            'type': 'group',
            'from': message.get('from', ''),
            'content': message.get('content', ''),
            'timestamp': message.get('timestamp', '')
        }
        if self.message_callback and self.window:
            self.window.after(0, lambda: self.message_callback(msg_data))

    def _handle_private_message(self, message: dict):
        """处理私聊消息"""
        msg_data = {
            'type': 'private',
            'from': message.get('from', ''),
            'to': message.get('to', ''),
            'content': message.get('content', ''),
            'timestamp': message.get('timestamp', '')
        }
        if self.message_callback and self.window:
            self.window.after(0, lambda: self.message_callback(msg_data))

    def _handle_system_message(self, message: dict):
        """处理系统消息"""
        msg_data = {
            'type': 'system',
            'content': message.get('content', ''),
            'timestamp': message.get('timestamp', '')
        }
        if self.message_callback and self.window:
            self.window.after(0, lambda: self.message_callback(msg_data))

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
                msg_data = {
                    'type': 'group',
                    'from': msg.get('sender', ''),
                    'content': msg.get('content', ''),
                    'timestamp': msg.get('timestamp', '')
                }
                self.window.after(0, lambda m=msg_data: self.message_callback(m))

    def _handle_private_history(self, message: dict):
        """处理私聊历史消息"""
        messages = message.get('messages', [])
        if self.message_callback and self.window:
            for msg in messages:
                msg_data = {
                    'type': 'private',
                    'from': msg.get('sender', ''),
                    'to': msg.get('receiver', ''),
                    'content': msg.get('content', ''),
                    'timestamp': msg.get('timestamp', '')
                }
                self.window.after(0, lambda m=msg_data: self.message_callback(m))

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
        """创建登录UI"""
        main_frame = tk.Frame(self._login_frame, bg='#f5f5f5')
        main_frame.pack(expand=True, fill='both', padx=40, pady=40)

        # 标题
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

        # 服务器设置
        server_frame = tk.LabelFrame(
            main_frame, text="  服务器配置  ",
            bg='#f5f5f5', fg='#1976d2',
            padx=15, pady=10,
            font=("Microsoft YaHei", 10)
        )
        server_frame.pack(fill='x', pady=(0, 20))

        tk.Label(server_frame, text="地址:", bg='#f5f5f5', fg='#333333').grid(row=0, column=0, sticky='w', pady=5)
        self._host_entry = tk.Entry(server_frame, width=20, font=("Microsoft YaHei", 10))
        self._host_entry.insert(0, DEFAULT_HOST)
        self._host_entry.grid(row=0, column=1, padx=10, pady=5)

        tk.Label(server_frame, text="端口:", bg='#f5f5f5', fg='#333333').grid(row=1, column=0, sticky='w', pady=5)
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
        login_frame.pack(fill='x', pady=(0, 25))

        tk.Label(login_frame, text="用户名:", bg='#f5f5f5', fg='#333333').grid(row=0, column=0, sticky='w', pady=8)
        self._username_entry = tk.Entry(login_frame, width=20, font=("Microsoft YaHei", 10))
        self._username_entry.grid(row=0, column=1, padx=10, pady=8)

        tk.Label(login_frame, text="密码:", bg='#f5f5f5', fg='#333333').grid(row=1, column=0, sticky='w', pady=8)
        self._password_entry = tk.Entry(login_frame, width=20, show='*', font=("Microsoft YaHei", 10))
        self._password_entry.grid(row=1, column=1, padx=10, pady=8)

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

        register_btn = tk.Button(
            btn_frame,
            text="注 册",
            width=12,
            command=self._on_register_click,
            bg='white',
            fg='#2196f3',
            font=("Microsoft YaHei", 11),
            relief='flat',
            cursor='hand2'
        )
        register_btn.pack(side='left', padx=8)

        # 绑定回车键
        self._username_entry.bind('<Return>', lambda e: self._on_login_click())
        self._password_entry.bind('<Return>', lambda e: self._on_login_click())

        # 底部提示
        tk.Label(
            main_frame,
            text="本地测试请确保服务器已启动",
            font=("Microsoft YaHei", 8),
            bg='#f5f5f5',
            fg='#888888'
        ).pack(side='bottom', pady=10)

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

        if not all([host, port_str, username, password]):
            messagebox.showwarning("输入错误", "请填写所有字段")
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
            messagebox.showerror("连接失败", f"无法连接到服务器 {host}:{port}\n\n请检查:\n1. 服务器是否已启动\n2. 服务器地址是否正确")
            self._reset_connecting_state()
            self._login_btn.config(state='normal', text="登 录")
            return

        self.send_message({
            'type': 'login',
            'username': username,
            'password': password
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
        """创建聊天主窗口"""
        # 使用已有的窗口，设置标题
        self.window.title(f"聊天系统 - {self.username}")
        self.window.geometry("1000x650")
        self.window.minsize(800, 550)
        self.window.configure(bg='#f5f5f5')

        self._create_chat_ui()

        # 请求数据
        self.request_online_users()
        self.request_group_history()

        # 启动接收线程
        self.start_receive_thread()

        # 关闭回调
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)

        self.window.mainloop()

    def _create_chat_ui(self):
        """创建聊天界面"""
        # 顶部标题栏
        top_frame = tk.Frame(self.window, bg='#2196f3', height=60)
        top_frame.pack(fill='x')
        top_frame.pack_propagate(False)

        tk.Label(
            top_frame,
            text=f"  {self.username}",
            font=("Microsoft YaHei", 16, "bold"),
            bg='#2196f3',
            fg='white'
        ).pack(side='left', pady=15)

        tk.Label(
            top_frame,
            text="● 在线",
            font=("Arial", 10),
            bg='#2196f3',
            fg='#90ee90'
        ).pack(side='left', padx=10, pady=15)

        # 刷新按钮
        tk.Button(
            top_frame,
            text="刷新用户",
            command=self.request_online_users,
            bg='white',
            fg='#2196f3',
            relief='flat',
            cursor='hand2',
            font=("Microsoft YaHei", 9)
        ).pack(side='right', padx=15, pady=12)

        # 主内容区域
        main_frame = tk.Frame(self.window, bg='#f5f5f5')
        main_frame.pack(fill='both', expand=True)

        # 左侧用户列表
        left_frame = tk.Frame(main_frame, bg='white', width=200)
        left_frame.pack(side='left', fill='y')
        left_frame.pack_propagate(False)

        tk.Label(
            left_frame,
            text="在线用户",
            font=("Microsoft YaHei", 11, "bold"),
            bg='white',
            fg='#2196f3',
            pady=10
        ).pack()

        # 用户列表容器
        users_container = tk.Frame(left_frame, bg='white')
        users_container.pack(fill='both', expand=True, padx=5, pady=5)

        self._users_canvas = tk.Canvas(users_container, bg='white', highlightthickness=0)
        users_scrollbar = tk.Scrollbar(users_container, orient='vertical', bg='white',
                                        command=self._users_canvas.yview)
        self._users_frame = tk.Frame(self._users_canvas, bg='white')

        self._users_canvas.configure(yscrollcommand=users_scrollbar.set)
        users_scrollbar.pack(side='right', fill='y')
        self._users_canvas.pack(side='left', fill='both', expand=True)

        self._users_window = self._users_canvas.create_window((0, 0), window=self._users_frame, anchor='nw')
        self._users_frame.bind('<Configure>',
                               lambda e: self._users_canvas.configure(scrollregion=self._users_canvas.bbox('all')))
        self._users_canvas.bind('<Configure>',
                                lambda e: self._users_canvas.itemconfig(self._users_window, width=e.width))

        self.set_online_users_callback(self._update_user_list)

        # 群聊按钮
        self._group_btn = tk.Button(
            left_frame,
            text="进入群聊",
            command=lambda: self._select_chat_target(None),
            bg='#2196f3',
            fg='white',
            relief='flat',
            cursor='hand2',
            font=("Microsoft YaHei", 10, "bold"),
            width=15
        )
        self._group_btn.pack(pady=10, padx=10)

        # 右侧聊天区域
        right_frame = tk.Frame(main_frame, bg='#f5f5f5')
        right_frame.pack(side='right', fill='both', expand=True)

        # 聊天模式标签
        mode_frame = tk.Frame(right_frame, bg='white')
        mode_frame.pack(fill='x', padx=10, pady=(10, 5))

        self._chat_mode_label = tk.Label(
            mode_frame,
            text="群聊模式",
            font=("Microsoft YaHei", 10, "bold"),
            bg='white',
            fg='#2196f3',
            padx=15,
            pady=8
        )
        self._chat_mode_label.pack(side='left')

        # 消息显示区域
        chat_frame = tk.Frame(right_frame, bg='#f5f5f5')
        chat_frame.pack(fill='both', expand=True, padx=10, pady=5)

        self._chat_area = scrolledtext.ScrolledText(
            chat_frame,
            wrap='word',
            font=("Microsoft YaHei", 13),
            bg='white',
            fg='#333333',
            insertbackground='#333333',
            relief='flat',
            state='disabled'
        )
        self._chat_area.pack(fill='both', expand=True)

        # 配置消息样式
        self._chat_area.tag_configure('group', foreground='#1565c0', lmargin1=10, lmargin2=10)
        self._chat_area.tag_configure('private', foreground='#2e7d32', lmargin1=10, lmargin2=10)
        self._chat_area.tag_configure('system', foreground='#c62828', lmargin1=10, lmargin2=10,
                                      font=("Microsoft YaHei", 11, "italic"))
        self._chat_area.tag_configure('timestamp', foreground='#888888', font=("Microsoft YaHei", 10))
        self._chat_area.tag_configure('sender', foreground='#1565c0', font=("Microsoft YaHei", 13, "bold"))
        self._chat_area.tag_configure('private_sender', foreground='#2e7d32', font=("Microsoft YaHei", 13, "bold"))
        self._chat_area.tag_configure('private_receiver', foreground='#c62828', font=("Microsoft YaHei", 13, "bold"))

        # 消息输入区域
        input_frame = tk.Frame(right_frame, bg='white')
        input_frame.pack(fill='x', padx=10, pady=(5, 10))

        self._message_entry = tk.Entry(
            input_frame,
            font=("Microsoft YaHei", 14),
            bg='#f5f5f5',
            fg='#333333',
            insertbackground='#333333',
            relief='solid',
            bd=1
        )
        self._message_entry.pack(side='left', fill='x', expand=True, ipady=12, padx=(10, 10), pady=10)
        self._message_entry.bind('<Return>', lambda e: self._send_message())

        tk.Button(
            input_frame,
            text="发 送",
            command=self._send_message,
            bg='#2196f3',
            fg='white',
            relief='flat',
            cursor='hand2',
            font=("Microsoft YaHei", 11, "bold"),
            width=8
        ).pack(side='right', padx=10, pady=8)

        self.set_message_callback(self._display_message)

    def _update_user_list(self, users: list):
        """更新用户列表"""
        for widget in self._users_frame.winfo_children():
            widget.destroy()

        for user in users:
            if user == self.username:
                continue

            color = '#2e7d32' if user != self.username else '#1565c0'
            tk.Button(
                self._users_frame,
                text=f"  {user}",
                command=lambda u=user: self._select_chat_target(u),
                bg='#f5f5f5',
                fg=color,
                relief='flat',
                cursor='hand2',
                font=("Microsoft YaHei", 9),
                anchor='w',
                width=18
            ).pack(pady=2, fill='x')

        self.online_users = users

    def _select_chat_target(self, target: Optional[str]):
        """选择聊天目标"""
        self.current_target = target

        if target:
            self._chat_mode_label.config(text=f"私聊: {target}")
            self._group_btn.config(bg='#e0e0e0', fg='#2196f3')
            self._clear_chat_area()
            self.request_private_history(target)
        else:
            self._chat_mode_label.config(text="群聊模式")
            self._group_btn.config(bg='#2196f3', fg='white')
            self._clear_chat_area()
            self.request_group_history()

    def _clear_chat_area(self):
        """清空聊天区域"""
        self._chat_area.config(state='normal')
        self._chat_area.delete(1.0, 'end')
        self._chat_area.config(state='disabled')

    def _send_message(self):
        """发送消息"""
        content = self._message_entry.get().strip()
        if not content:
            return

        self._message_entry.delete(0, 'end')

        timestamp = datetime.now().strftime("%H:%M:%S")

        if self.current_target:
            self.send_message({
                'type': 'private_message',
                'to': self.current_target,
                'content': content
            })
            # 本地显示私聊消息
            msg_data = {
                'type': 'private',
                'from': self.username,
                'to': self.current_target,
                'content': content,
                'timestamp': timestamp
            }
            self._display_message(msg_data)
        else:
            self.send_message({
                'type': 'message',
                'content': content
            })
            # 本地显示群聊消息
            msg_data = {
                'type': 'group',
                'from': self.username,
                'content': content,
                'timestamp': timestamp
            }
            self._display_message(msg_data)

    def _display_message(self, msg: dict):
        """显示消息"""
        msg_type = msg.get('type', '')
        timestamp = msg.get('timestamp', datetime.now().strftime("%H:%M:%S"))
        content = msg.get('content', '')
        sender = msg.get('from', '')

        self._chat_area.config(state='normal')

        if msg_type == 'group':
            # 显示时间戳 + 用户名 + 消息，使用更清晰的格式
            self._chat_area.insert('end', f"[{timestamp}] ", ('timestamp'))
            self._chat_area.insert('end', f"{sender}", ('sender'))
            self._chat_area.insert('end', f": {content}\n\n", ('group'))

        elif msg_type == 'private':
            to_user = msg.get('to', '')
            if sender == self.username:
                self._chat_area.insert('end', f"[{timestamp}] ", ('timestamp'))
                self._chat_area.insert('end', f"[私聊 -> {to_user}]", ('private_sender'))
                self._chat_area.insert('end', f": {content}\n\n", ('private'))
            else:
                self._chat_area.insert('end', f"[{timestamp}] ", ('timestamp'))
                self._chat_area.insert('end', f"[私聊 <- {sender}]", ('private_receiver'))
                self._chat_area.insert('end', f": {content}\n\n", ('private'))

        elif msg_type == 'system':
            self._chat_area.insert('end', f"[{timestamp}] *** {content} ***\n\n", ('system', 'timestamp'))

        self._chat_area.see('end')
        self._chat_area.config(state='disabled')

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

        # 分隔线
        tk.Frame(self.window, height=2, bg='#e0e0e0').pack(fill='x', padx=30, pady=15)

        # 已有账号快速登录区域
        existing_frame = tk.LabelFrame(
            self.window, text=" 已有账号快速登录 ",
            bg='#f5f5f5', fg='#1976d2',
            padx=15, pady=10,
            font=("Microsoft YaHei", 10)
        )
        existing_frame.pack(pady=10, padx=30, fill='x')

        # 下拉选择已有用户
        tk.Label(existing_frame, text="选择账号:", bg='#f5f5f5', fg='#333333', font=("Microsoft YaHei", 9)).pack(side='left', padx=5)

        self._existing_user_var = tk.StringVar()
        self._existing_user_combo = ttk.Combobox(
            existing_frame,
            textvariable=self._existing_user_var,
            width=12,
            font=("Microsoft YaHei", 9),
            state='readonly'
        )
        self._existing_user_combo.pack(side='left', padx=5)

        tk.Button(
            existing_frame,
            text="登录",
            command=self._login_existing_user,
            bg='#4caf50',
            fg='white',
            font=("Microsoft YaHei", 9, "bold"),
            relief='flat',
            cursor='hand2',
            width=6
        ).pack(side='left', padx=5)

        # 刷新用户列表
        tk.Button(
            existing_frame,
            text="刷新",
            command=self._refresh_existing_users,
            bg='white',
            fg='#1976d2',
            font=("Microsoft YaHei", 8),
            relief='flat',
            cursor='hand2'
        ).pack(side='left', padx=5)

        # 加载已有用户
        self._refresh_existing_users()

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

    def _refresh_existing_users(self):
        """刷新并显示已有用户列表"""
        try:
            import sqlite3
            conn = sqlite3.connect("chat_server.db", timeout=1)
            cursor = conn.cursor()
            cursor.execute("SELECT username FROM users ORDER BY last_login_time DESC, register_time DESC LIMIT 50")
            users = [row[0] for row in cursor.fetchall()]
            conn.close()
            self._existing_user_combo['values'] = users
            if users:
                self._existing_user_combo.current(0)
        except Exception as e:
            logger.warning(f"获取用户列表失败: {e}")
            self._existing_user_combo['values'] = []

    def _login_existing_user(self):
        """登录选中的已有用户"""
        username = self._existing_user_var.get()
        if not username:
            messagebox.showwarning("选择用户", "请选择一个账号")
            return

        password = simpledialog.askstring("输入密码", f"请输入 {username} 的密码：", show='*')
        if not password:
            return

        host, port = self._get_launcher_config()
        self._do_launcher_login(host, port, username, password)

    def _do_launcher_login(self, host, port, username, password):
        """执行启动器登录"""
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
            client.send_message({'type': 'login', 'username': username, 'password': password})

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
        """创建独立的聊天窗口（不受主窗口控制）"""
        import sys
        print(f"[窗口创建] 开始创建聊天窗口 for {username}", file=sys.stderr)

        # 标记窗口已打开
        self._chat_windows.add(username)

        # 创建新窗口
        chat_window = tk.Toplevel(self.window)
        chat_window.title(f"聊天系统 - {username}")
        chat_window.geometry("900x600")
        chat_window.minsize(700, 500)
        chat_window.configure(bg='#f5f5f5')

        # 设置窗口关闭处理
        def on_chat_close():
            self._chat_windows.discard(username)
            client.disconnect()
            chat_window.destroy()
            self._update_client_list()

        chat_window.protocol("WM_DELETE_WINDOW", on_chat_close)

        # 顶部标题栏
        top_frame = tk.Frame(chat_window, bg='#2196f3', height=50)
        top_frame.pack(fill='x')
        top_frame.pack_propagate(False)

        tk.Label(
            top_frame,
            text=f"  {username}",
            font=("Microsoft YaHei", 16, "bold"),
            bg='#2196f3',
            fg='white'
        ).pack(side='left', pady=12)

        tk.Label(
            top_frame,
            text="● 在线",
            font=("Arial", 10),
            bg='#2196f3',
            fg='#90ee90'
        ).pack(side='left', padx=10, pady=12)

        # 刷新按钮
        tk.Button(
            top_frame,
            text="刷新用户",
            command=client.request_online_users,
            bg='white',
            fg='#2196f3',
            relief='flat',
            cursor='hand2',
            font=("Microsoft YaHei", 9)
        ).pack(side='right', padx=15, pady=10)

        # 主内容区域
        main_frame = tk.Frame(chat_window, bg='#f5f5f5')
        main_frame.pack(fill='both', expand=True)

        # 左侧用户列表
        left_frame = tk.Frame(main_frame, bg='white', width=180)
        left_frame.pack(side='left', fill='y')
        left_frame.pack_propagate(False)

        tk.Label(
            left_frame,
            text="在线用户",
            font=("Microsoft YaHei", 11, "bold"),
            bg='white',
            fg='#2196f3',
            pady=10
        ).pack()

        users_container = tk.Frame(left_frame, bg='white')
        users_container.pack(fill='both', expand=True, padx=5, pady=5)

        users_canvas = tk.Canvas(users_container, bg='white', highlightthickness=0)
        users_scrollbar = tk.Scrollbar(users_container, orient='vertical', bg='white', command=users_canvas.yview)
        users_inner_frame = tk.Frame(users_canvas, bg='white')

        users_canvas.configure(yscrollcommand=users_scrollbar.set)
        users_scrollbar.pack(side='right', fill='y')
        users_canvas.pack(side='left', fill='both', expand=True)

        users_canvas.create_window((0, 0), window=users_inner_frame, anchor='nw')
        users_inner_frame.bind('<Configure>', lambda e: users_canvas.configure(scrollregion=users_canvas.bbox('all')))
        users_canvas.bind('<Configure>', lambda e: users_canvas.itemconfig(users_canvas.create_window((0, 0), window=users_inner_frame, anchor='nw'), width=e.width))

        # 群聊按钮
        group_btn = tk.Button(
            left_frame,
            text="进入群聊",
            bg='#2196f3',
            fg='white',
            relief='flat',
            cursor='hand2',
            font=("Microsoft YaHei", 10, "bold"),
            width=15
        )

        # 右侧聊天区域
        right_frame = tk.Frame(main_frame, bg='#f5f5f5')
        right_frame.pack(side='right', fill='both', expand=True)

        # 聊天模式标签
        mode_frame = tk.Frame(right_frame, bg='white')
        mode_frame.pack(fill='x', padx=10, pady=(10, 5))

        chat_mode_label = tk.Label(
            mode_frame,
            text="群聊模式",
            font=("Microsoft YaHei", 10, "bold"),
            bg='white',
            fg='#2196f3',
            padx=15,
            pady=8
        )
        chat_mode_label.pack(side='left')

        # 消息显示区域
        chat_frame = tk.Frame(right_frame, bg='#f5f5f5')
        chat_frame.pack(fill='both', expand=True, padx=10, pady=5)

        chat_area = scrolledtext.ScrolledText(
            chat_frame,
            wrap='word',
            font=("Microsoft YaHei", 13),
            bg='white',
            fg='#333333',
            insertbackground='#333333',
            relief='flat',
            state='disabled'
        )
        chat_area.pack(fill='both', expand=True)

        # 配置消息样式
        chat_area.tag_configure('group', foreground='#1565c0', lmargin1=10, lmargin2=10)
        chat_area.tag_configure('private', foreground='#2e7d32', lmargin1=10, lmargin2=10)
        chat_area.tag_configure('system', foreground='#c62828', lmargin1=10, lmargin2=10, font=("Microsoft YaHei", 11, "italic"))
        chat_area.tag_configure('timestamp', foreground='#888888', font=("Microsoft YaHei", 10))
        chat_area.tag_configure('sender', foreground='#1565c0', font=("Microsoft YaHei", 13, "bold"))
        chat_area.tag_configure('private_sender', foreground='#2e7d32', font=("Microsoft YaHei", 13, "bold"))
        chat_area.tag_configure('private_receiver', foreground='#c62828', font=("Microsoft YaHei", 13, "bold"))

        # 消息输入区域
        input_frame = tk.Frame(right_frame, bg='white')
        input_frame.pack(fill='x', padx=10, pady=(5, 10))

        message_entry = tk.Entry(
            input_frame,
            font=("Microsoft YaHei", 14),
            bg='#f5f5f5',
            fg='#333333',
            insertbackground='#333333',
            relief='solid',
            bd=1
        )
        message_entry.pack(side='left', fill='x', expand=True, ipady=12, padx=(10, 10), pady=10)

        # 状态变量
        current_target = [None]  # 使用列表以便在闭包中修改

        # 用于保存群聊历史记录（不随切换而丢失）
        group_history_messages = []

        def _do_display(msg):
            """内部显示消息函数"""
            msg_type = msg.get('type', '')
            timestamp = msg.get('timestamp', datetime.now().strftime("%H:%M:%S"))
            content = msg.get('content', '')
            sender = msg.get('from', '')

            chat_area.config(state='normal')

            if msg_type == 'group':
                chat_area.insert('end', f"[{timestamp}] ", ('timestamp'))
                chat_area.insert('end', f"{sender}", ('sender'))
                chat_area.insert('end', f": {content}\n\n", ('group'))
                # 保存到群聊历史
                if msg not in group_history_messages:
                    group_history_messages.append(msg)
            elif msg_type == 'private':
                to_user = msg.get('to', '')
                if sender == username:
                    chat_area.insert('end', f"[{timestamp}] ", ('timestamp'))
                    chat_area.insert('end', f"[私聊 -> {to_user}]", ('private_sender'))
                    chat_area.insert('end', f": {content}\n\n", ('private'))
                else:
                    chat_area.insert('end', f"[{timestamp}] ", ('timestamp'))
                    chat_area.insert('end', f"[私聊 <- {sender}]", ('private_receiver'))
                    chat_area.insert('end', f": {content}\n\n", ('private'))
            elif msg_type == 'system':
                chat_area.insert('end', f"[{timestamp}] *** {content} ***\n\n", ('system', 'timestamp'))

            chat_area.see('end')
            chat_area.config(state='disabled')

        def select_target(target):
            if current_target[0] == target:
                return

            current_target[0] = target
            if target:
                chat_mode_label.config(text=f"私聊: {target}")
                group_btn.config(bg='#e0e0e0', fg='#2196f3')
                # 清空并加载私聊历史
                chat_area.config(state='normal')
                chat_area.delete(1.0, 'end')
                chat_area.config(state='disabled')
                client.request_private_history(target)
            else:
                chat_mode_label.config(text="群聊模式")
                group_btn.config(bg='#2196f3', fg='white')
                # 切换到群聊时，恢复群聊历史
                chat_area.config(state='normal')
                chat_area.delete(1.0, 'end')
                for msg in group_history_messages:
                    _do_display(msg)
                chat_area.config(state='disabled')
                chat_area.see('end')

        def send_message():
            content = message_entry.get().strip()
            if not content:
                return

            message_entry.delete(0, 'end')
            timestamp = datetime.now().strftime("%H:%M:%S")

            if current_target[0]:
                client.send_message({'type': 'private_message', 'to': current_target[0], 'content': content})
                msg_data = {'type': 'private', 'from': username, 'to': current_target[0], 'content': content, 'timestamp': timestamp}
            else:
                client.send_message({'type': 'message', 'content': content})
                msg_data = {'type': 'group', 'from': username, 'content': content, 'timestamp': timestamp}

            _do_display(msg_data)

        def display_message(msg):
            import sys
            # 处理所有消息类型
            msg_type = msg.get('type', '')
            target_user = msg.get('to', '')
            print(f"[消息回调] 收到消息类型: {msg_type}", file=sys.stderr)

            # 在线用户列表更新
            if msg_type == 'online_users':
                users = msg.get('users', [])
                update_user_list(users)
                return

            # 系统消息始终显示
            if msg_type == 'system':
                _do_display(msg)
                return

            # 群聊消息
            if msg_type == 'group':
                if current_target[0] is None:
                    _do_display(msg)
                return

            # 私聊消息
            if msg_type == 'private':
                sender = msg.get('from', '')
                if current_target[0] == sender:
                    _do_display(msg)
                elif current_target[0] is None and (sender == username or target_user == username):
                    _do_display(msg)
                return

            # 群聊/私聊历史消息
            if msg_type in ('group_history', 'private_history'):
                messages = msg.get('messages', [])
                for m in messages:
                    m_type = 'group' if msg_type == 'group_history' else 'private'
                    if m_type == 'group':
                        m_data = {
                            'type': 'group',
                            'from': m.get('sender', ''),
                            'content': m.get('content', ''),
                            'timestamp': m.get('timestamp', '')
                        }
                    else:
                        m_data = {
                            'type': 'private',
                            'from': m.get('sender', ''),
                            'to': m.get('receiver', ''),
                            'content': m.get('content', ''),
                            'timestamp': m.get('timestamp', '')
                        }
                    if m_data not in group_history_messages and m_type == 'group':
                        group_history_messages.append(m_data)
                    if current_target[0] is None:
                        if m_type == 'group':
                            _do_display(m_data)

        def update_user_list(users):
            for widget in users_inner_frame.winfo_children():
                widget.destroy()

            for user in users:
                if user == username:
                    continue
                color = '#2e7d32'
                tk.Button(
                    users_inner_frame,
                    text=f"  {user}",
                    command=lambda u=user: select_target(u),
                    bg='#f5f5f5',
                    fg=color,
                    relief='flat',
                    cursor='hand2',
                    font=("Microsoft YaHei", 9),
                    anchor='w',
                    width=16
                ).pack(pady=2, fill='x')

        # 绑定事件
        group_btn.config(command=lambda: select_target(None))
        group_btn.pack(pady=10, padx=10)

        message_entry.bind('<Return>', lambda e: send_message())

        tk.Button(
            input_frame,
            text="发 送",
            command=send_message,
            bg='#2196f3',
            fg='white',
            relief='flat',
            cursor='hand2',
            font=("Microsoft YaHei", 11, "bold"),
            width=8
        ).pack(side='right', padx=10, pady=8)

        # 设置回调
        print(f"[窗口创建] 设置消息回调", file=sys.stderr)
        client.set_message_callback(display_message)
        client.set_online_users_callback(update_user_list)
        client.username = username
        client.window = self.window  # 重要：设置window以便回调中使用window.after()

        # 保存对窗口的引用
        client._chat_window = chat_window

        # 启动接收线程并请求数据
        print(f"[窗口创建] 启动接收线程", file=sys.stderr)
        client.start_receive_thread()

        print(f"[窗口创建] 请求在线用户列表", file=sys.stderr)
        client.request_online_users()

        print(f"[窗口创建] 请求群聊历史", file=sys.stderr)
        client.request_group_history()

        # 更新客户端列表
        self.clients.append(client)
        self._update_client_list()
        print(f"[窗口创建] 聊天窗口创建完成", file=sys.stderr)

    def _update_client_list(self):
        """更新客户端列表"""
        self._client_listbox.delete(0, 'end')
        for i, client in enumerate(self.clients):
            status = "在线" if client.running else "离线"
            username_str = getattr(client, 'username', 'unknown')
            self._client_listbox.insert('end', f"[{i+1}] {username_str} - {status}")

    def _close_all_clients(self):
        """关闭所有客户端"""
        for client in self.clients[:]:
            try:
                client.disconnect()
                if hasattr(client, '_chat_window') and client._chat_window:
                    try:
                        client._chat_window.destroy()
                    except:
                        pass
            except:
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

    def _update_client_list(self):
        """更新客户端列表"""
        self._client_listbox.delete(0, 'end')
        for i, client in enumerate(self.clients):
            status = "在线" if client.running else "离线"
            self._client_listbox.insert('end', f"[{i+1}] {client.username} - {status}")

    def _close_all_clients(self):
        """关闭所有客户端"""
        for client in self.clients[:]:
            try:
                client.disconnect()
            except:
                pass
        self.clients.clear()
        self._update_client_list()
        messagebox.showinfo("提示", "所有客户端已关闭")


def main():
    """主函数"""
    print("\n" + "="*50)
    print("    TCP 多用户聊天客户端")
    print("="*50 + "\n")

    launcher = MultiClientLauncher()
    launcher.launch()


if __name__ == "__main__":
    main()
