from PyQt6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QTextEdit, QLineEdit, QPushButton, QLabel, QTabWidget, QListWidgetItem, QMenu, QGraphicsDropShadowEffect
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QPalette
import uuid

def get_avatar(username):
    avatars = ['🐱', '🐶', '🦊', '🐻', '🐼', '🐨', '🐰', '🐯', '🐸', '🐹', '🦁', '🐮', '🐷']
    if not username: return '👻'
    idx = sum(ord(c) for c in username) % len(avatars)
    return avatars[idx]

# 状态颜色配置
STATUS_COLORS = {
    'online': {'color': '#4CAF50', 'bg': '#E8F5E9', 'text': '在线', 'dot': '🟢'},
    'busy': {'color': '#FFC107', 'bg': '#FFF8E1', 'text': '忙碌', 'dot': '🟡'},
    'invisible': {'color': '#9E9E9E', 'bg': '#F5F5F5', 'text': '离线', 'dot': '⚪'}
}

class ChatWindow(QMainWindow):
    def __init__(self, network, username):
        super().__init__()
        self.network = network
        self.current_user = username
        self.current_status = 'online'  # 默认在线状态
        self.setWindowTitle(f'聊天室 - {get_avatar(self.current_user)} {self.current_user}')
        self.resize(850, 650)
        self.seen_msg_ids = set()
        # 私聊会话管理
        self.private_sessions = {}  # {username: {'widget', 'chat_area', 'input', 'send_btn'}}
        self.active_private_user = None
        # 未读消息计数：{username: count}
        self.unread_counts = {}
        
        self.setup_ui()
        self.connect_signals()

        self.network.send_message({'type': 'get_online_users'})
        self.network.send_message({'type': 'get_group_history'})

    def closeEvent(self, event):
        """关闭窗口时自动设置为离线"""
        # 先发送状态更新为离线
        self.network.send_message({'type': 'change_status', 'status': 'invisible'})
        # 等待一小段时间确保消息发送
        import time
        time.sleep(0.1)
        # 然后发送登出消息
        self.network.send_message({'type': 'logout'})
        event.accept()

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        header = QHBoxLayout()
        user_lbl = QLabel(f'👋 欢迎回来，{get_avatar(self.current_user)} {self.current_user}')
        user_lbl.setStyleSheet('font-size: 18px; color: #4682B4;')
        header.addWidget(user_lbl)
        
        # 状态选择按钮
        self.status_btn = QPushButton('🟢 在线')
        self.status_btn.setStyleSheet(f'''
            QPushButton {{
                background-color: #E8F5E9;
                color: #4CAF50;
                border: 2px solid #4CAF50;
                border-radius: 15px;
                padding: 6px 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #C8E6C9;
            }}
        ''')
        self.status_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.status_btn.clicked.connect(self.show_status_menu)
        header.addWidget(self.status_btn)
        
        refresh_btn = QPushButton('🔄 刷新好友')
        refresh_btn.setMinimumHeight(40)
        refresh_btn.clicked.connect(lambda: self.network.send_message({'type': 'get_online_users'}))
        header.addWidget(refresh_btn, alignment=Qt.AlignmentFlag.AlignRight)

        # 未读消息提示标签
        self.unread_badge = QLabel('')
        self.unread_badge.setStyleSheet('''
            background-color: #FF0000;
            color: white;
            border-radius: 10px;
            padding: 4px 10px;
            font-weight: bold;
            font-size: 12px;
            min-width: 20px;
        ''')
        self.unread_badge.setVisible(False)
        header.addWidget(self.unread_badge)
        main_layout.addLayout(header)

        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        # 群聊标签
        group_tab = QWidget()
        glayout = QVBoxLayout(group_tab)
        glayout.setContentsMargins(0, 10, 0, 0)
        
        self.group_chat_area = QTextEdit()
        self.group_chat_area.setReadOnly(True)
        glayout.addWidget(self.group_chat_area)
        
        ginput_layout = QHBoxLayout()
        self.group_input = QLineEdit()
        self.group_input.setPlaceholderText('说点什么吧... 💬')
        self.group_input.setMinimumHeight(45)
        self.group_input.returnPressed.connect(self.on_group_send)
        
        gsend_btn = QPushButton('发送 🚀')
        gsend_btn.setMinimumHeight(45)
        gsend_btn.clicked.connect(self.on_group_send)
        
        ginput_layout.addWidget(self.group_input)
        ginput_layout.addWidget(gsend_btn)
        glayout.addLayout(ginput_layout)
        self.tabs.addTab(group_tab, '🌐 快乐群聊')

        # 私聊标签 - 改为动态创建每个用户的聊天窗口
        private_tab = QWidget()
        self.private_layout = QHBoxLayout(private_tab)
        self.private_layout.setContentsMargins(0, 10, 0, 0)
        
        # 用户列表
        user_layout = QVBoxLayout()
        user_layout.addWidget(QLabel('我的伙伴们'))
        self.user_list = QListWidget()
        self.user_list.setMaximumWidth(200)
        self.user_list.itemClicked.connect(self.on_user_selected)
        user_layout.addWidget(self.user_list)
        self.private_layout.addLayout(user_layout)
        
        # 聊天区域容器（右侧）
        self.chat_container = QVBoxLayout()
        placeholder_lbl = QLabel('← 点击左边的小伙伴开始私聊')
        placeholder_lbl.setStyleSheet('color: #87CEFA; font-weight: normal;')
        self.chat_container.addWidget(placeholder_lbl)
        self.private_layout.addLayout(self.chat_container)
        
        self.tabs.addTab(private_tab, '💌 悄悄话')

    def show_status_menu(self):
        """显示状态选择菜单"""
        menu = QMenu(self)
        menu.setStyleSheet('''
            QMenu {
                background-color: white;
                border: 1px solid #B0E0E6;
                border-radius: 10px;
                padding: 5px;
            }
            QMenu::item {
                padding: 10px 30px;
                border-radius: 8px;
                margin: 2px;
            }
            QMenu::item:selected {
                background-color: #E6F2FF;
            }
        ''')
        
        # 在线选项
        online_action = menu.addAction('🟢  在线')
        online_action.triggered.connect(lambda: self.change_status('online'))
        
        # 忙碌选项
        busy_action = menu.addAction('🟡  忙碌')
        busy_action.triggered.connect(lambda: self.change_status('busy'))
        
        # 隐身选项
        invisible_action = menu.addAction('⚪  隐身')
        invisible_action.triggered.connect(lambda: self.change_status('invisible'))
        
        menu.exec(self.status_btn.mapToGlobal(self.status_btn.rect().bottomLeft()))

    def change_status(self, new_status):
        """切换用户状态"""
        if self.current_status != new_status:
            self.current_status = new_status
            status_info = STATUS_COLORS[new_status]
            
            # 更新按钮样式
            self.status_btn.setText(f"{status_info['dot']} {status_info['text']}")
            self.status_btn.setStyleSheet(f'''
                QPushButton {{
                    background-color: {status_info['bg']};
                    color: {status_info['color']};
                    border: 2px solid {status_info['color']};
                    border-radius: 15px;
                    padding: 6px 12px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: {status_info['bg']};
                }}
            ''')
            
            # 发送状态更新到服务器
            self.network.send_message({'type': 'change_status', 'status': new_status})

    def connect_signals(self):
        self.network.groupMessage.connect(self.on_group_msg)
        self.network.usersUpdated.connect(self.update_user_list)
        self.network.groupHistory.connect(self.on_group_history)
        self.network.privateMessage.connect(self.on_private_msg)
        self.network.privateHistory.connect(self.on_private_history)

    def append_html_msg(self, text_edit, sender, content, is_sending=False, is_confirmed=False):
        avatar = get_avatar(sender)
        color = "#4169E1" if sender == self.current_user else "#20B2AA"
        if is_sending:
            status = " <i style='color:#999; font-size:12px;'>(发送中...)</i>"
        elif is_confirmed:
            status = " <i style='color:#4CAF50; font-size:12px;'>✓ 已发送</i>"
        else:
            status = ""
        msg_html = "<div style='margin: 8px 0;'>"
        msg_html += "<span style='color:" + color + "; font-weight:bold; font-size:15px;'>" + avatar + " " + sender + status + "</span><br>"
        msg_html += "<span style='background-color:#E6F2FF; color:#333; font-size:14px; padding:4px; border-radius:4px;'>&nbsp;" + content + "&nbsp;</span>"
        msg_html += "</div><br>"
        text_edit.append(msg_html)

    def on_group_send(self):
        content = self.group_input.text().strip()
        if not content: return
        self.group_input.clear()
        msg_id = str(uuid.uuid4())
        self.append_html_msg(self.group_chat_area, self.current_user, content, is_sending=True)
        self.seen_msg_ids.add(msg_id)
        self.network.send_message({'type': 'message', 'content': content, 'client_msg_id': msg_id})

    def on_group_msg(self, msg, msg_id):
        if msg_id in self.seen_msg_ids: return
        self.seen_msg_ids.add(msg_id)
        self.append_html_msg(self.group_chat_area, msg.get('from', ''), msg.get('content', ''))

    def on_group_history(self, history):
        for msg in history:
            self.append_html_msg(self.group_chat_area, msg.get('sender', ''), msg.get('content', ''))

    def on_private_history(self, history):
        """处理私聊历史消息"""
        if not history:
            return
        # 根据历史消息判断是与哪个用户的私聊
        first_msg = history[0]
        # 从消息中提取对方用户名
        if first_msg.get('sender') == self.current_user:
            other_user = first_msg.get('receiver')
        else:
            other_user = first_msg.get('sender')
        
        if not other_user or other_user not in self.private_sessions:
            return
        
        # 在对应的聊天窗口显示历史消息
        for msg in history:
            sender = msg.get('sender', '')
            content = msg.get('content', '')
            self._append_private_message(other_user, sender, content)

    def update_user_list(self, users):
        """
        更新用户列表
        业务逻辑：
        - 不显示当前登录用户自己
        - 其他所有用户显示为离线（白色）
        """
        self.user_list.clear()
        for u in users:
            if isinstance(u, dict):
                name = u.get('username', '')
            else:
                name = u

            # 不显示当前登录用户自己
            if name == self.current_user:
                continue

            # 所有其他用户都显示为离线
            status = 'invisible'

            status_info = STATUS_COLORS.get(status, STATUS_COLORS['invisible'])
            item = QListWidgetItem(f"{get_avatar(name)}  {name}  {status_info['dot']}")
            item.setData(Qt.ItemDataRole.UserRole, {'username': name, 'status': status})
            item.setForeground(QColor(status_info['color']))
            self.user_list.addItem(item)

    def on_user_selected(self, item):
        """点击用户创建/切换私聊会话"""
        user_data = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(user_data, dict):
            username = user_data.get('username', '')
        else:
            username = user_data
        
        # 清除该用户的未读计数
        self.unread_counts[username] = 0
        
        # 如果会话不存在，创建新会话
        if username not in self.private_sessions:
            self._create_private_chat_session(username)
        
        # 切换到该用户的聊天窗口
        self._switch_to_chat_session(username)
    
    def _create_private_chat_session(self, username):
        """为用户创建私聊会话"""
        session_widget = QWidget()
        session_layout = QVBoxLayout(session_widget)
        session_layout.setContentsMargins(5, 5, 5, 5)
        
        # 标题
        title = QLabel(f'💬 与 {get_avatar(username)} {username} 的私聊')
        title.setStyleSheet('font-weight: bold; color: #4682B4; padding: 5px;')
        session_layout.addWidget(title)
        
        # 聊天区域
        chat_area = QTextEdit()
        chat_area.setReadOnly(True)
        session_layout.addWidget(chat_area)
        
        # 输入区域
        input_layout = QHBoxLayout()
        input_field = QLineEdit()
        input_field.setPlaceholderText(f'给 {username} 发悄悄话...')
        input_field.setMinimumHeight(40)
        input_field.returnPressed.connect(lambda: self._send_private_message(username))
        
        send_btn = QPushButton('发送')
        send_btn.setMinimumHeight(40)
        send_btn.clicked.connect(lambda: self._send_private_message(username))
        
        input_layout.addWidget(input_field)
        input_layout.addWidget(send_btn)
        session_layout.addLayout(input_layout)
        
        # 存储会话
        self.private_sessions[username] = {
            'widget': session_widget,
            'chat_area': chat_area,
            'input': input_field,
            'send_btn': send_btn
        }
    
    def _switch_to_chat_session(self, username):
        """切换到指定用户的聊天窗口"""
        if username not in self.private_sessions:
            return
        
        self.active_private_user = username
        
        # 清除聊天容器，添加新会话
        while self.chat_container.count():
            item = self.chat_container.takeAt(0)
            if item.widget():
                item.widget().hide()
        
        self.chat_container.addWidget(self.private_sessions[username]['widget'])
        
        # 请求历史消息
        self.network.send_message({'type': 'get_private_history', 'with_user': username})
    
    def _send_private_message(self, username):
        """发送私聊消息"""
        if username not in self.private_sessions:
            return
        
        content = self.private_sessions[username]['input'].text().strip()
        if not content:
            return
        
        self.private_sessions[username]['input'].clear()
        msg_id = str(uuid.uuid4())
        
        # 显示发送中的消息
        self._append_private_message(username, self.current_user, content, is_sending=True)
        self.seen_msg_ids.add(msg_id)
        self.network.send_message({
            'type': 'private_message',
            'to': username,
            'content': content,
            'client_msg_id': msg_id
        })
        # 3秒后显示已发送
        QTimer.singleShot(3000, lambda: self._mark_message_sent(username))

    def _append_private_message(self, username, sender, content, is_sending=False):
        """在指定用户的私聊窗口中追加消息"""
        if username not in self.private_sessions:
            return
        chat_area = self.private_sessions[username]['chat_area']
        self.append_html_msg(chat_area, sender, content, is_sending=is_sending)

    def _mark_message_sent(self, username):
        """标记消息已发送"""
        if username in self.private_sessions:
            chat_area = self.private_sessions[username]['chat_area']
            chat_area.append("<span style='color:#4CAF50; font-size:12px;'>✓ 已发送</span><br>")

    def on_private_msg(self, msg, msg_id):
        """
        处理私聊消息 - 根据发送者显示在对应用户的私聊窗口
        """
        if msg_id in self.seen_msg_ids: return
        self.seen_msg_ids.add(msg_id)
        
        sender = msg.get('from', '')
        content = msg.get('content', '')
        
        # 初始化该发送者的会话（如果不存在）
        if sender not in self.private_sessions:
            self._create_private_chat_session(sender)
        
        # 无论是否正在与该发送者聊天，都将消息追加到对应的聊天窗口
        self._append_private_message(sender, sender, content)
        
        # 检查是否正在与该发送者聊天
        is_current_chat = (sender == self.active_private_user)
        
        if not is_current_chat:
            # 不在当前聊天，增加该用户的未读计数
            if sender not in self.unread_counts:
                self.unread_counts[sender] = 0
            self.unread_counts[sender] += 1
            self.update_unread_badge()
            # 显示提醒
            self.show_new_message_notification(sender, content)

    def update_unread_badge(self):
        """更新未读消息徽章"""
        total_unread = sum(self.unread_counts.values()) if hasattr(self, 'unread_counts') else 0
        if total_unread > 0:
            self.unread_badge.setText(f'💬 {total_unread}')
            self.unread_badge.setVisible(True)
            # 窗口标题闪烁提醒
            self.flash_window_title()
        else:
            self.unread_badge.setVisible(False)

    def flash_window_title(self):
        """窗口标题闪烁提醒"""
        # 保存原始标题
        if not hasattr(self, 'original_title'):
            self.original_title = self.windowTitle()
        
        # 窗口标题变成红色提示
        self.setWindowTitle(f'🔴 新消息! - {self.original_title}')
        # 2秒后恢复
        QTimer.singleShot(2000, lambda: self.setWindowTitle(self.original_title))

    def show_new_message_notification(self, from_user, content):
        """显示新消息通知（联系人列表中该用户项闪烁）"""
        # 在用户列表中找到该用户并高亮
        for i in range(self.user_list.count()):
            item = self.user_list.item(i)
            user_data = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(user_data, dict) and user_data.get('username') == from_user:
                # 设置红色高亮背景
                item.setBackground(QColor('#FFE4E1'))
                # 3秒后恢复原色
                QTimer.singleShot(3000, lambda: item.setBackground(QColor('transparent')))
                break

    def on_user_selected(self, item):
        """点击用户创建/切换私聊会话"""
        user_data = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(user_data, dict):
            username = user_data.get('username', '')
        else:
            username = user_data
        
        # 清除该用户的未读计数
        self.unread_counts[username] = 0
        
        # 如果会话不存在，创建新会话
        if username not in self.private_sessions:
            self._create_private_chat_session(username)
        
        # 切换到该用户的聊天窗口
        self._switch_to_chat_session(username)
        
        # 切换到私聊标签
        self.tabs.setCurrentIndex(1)