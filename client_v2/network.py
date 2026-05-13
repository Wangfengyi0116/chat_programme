import socket
import threading
import json
import logging
from PyQt6.QtCore import QObject, pyqtSignal, QTimer

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class NetworkClient(QObject):
    loginResponse = pyqtSignal(bool, str, str)
    registerResponse = pyqtSignal(bool, str)
    groupMessage = pyqtSignal(dict, str)
    privateMessage = pyqtSignal(dict, str)
    systemMessage = pyqtSignal(dict)
    usersUpdated = pyqtSignal(list)
    groupHistory = pyqtSignal(list)
    privateHistory = pyqtSignal(list)
    loginPolicy = pyqtSignal(bool, str)
    unreadCounts = pyqtSignal(dict)
    unreadIncrement = pyqtSignal(str)
    disconnected = pyqtSignal()
    reconnected = pyqtSignal()  # 重连成功信号

    def __init__(self):
        super().__init__()
        self.socket = None
        self.running = False
        self.username = None
        self.host = None
        self.port = None
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        self.reconnect_timer = None
        self.last_seq_id = 0  # 最后一条消息的序列号，用于离线同步

    def connect_server(self, host, port):
        try:
            self.host = host
            self.port = port
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((host, port))
            self.running = True
            self.reconnect_attempts = 0
            threading.Thread(target=self._receive_messages, daemon=True).start()
            logger.info(f"连接服务器成功: {host}:{port}")
            return True
        except Exception as e:
            logger.error(f'连接服务器失败: {e}')
            return False

    def reconnect(self):
        """自动重连机制"""
        if self.reconnect_attempts >= self.max_reconnect_attempts:
            logger.warning("已达到最大重连次数，停止重连")
            self.disconnected.emit()
            return
        
        self.reconnect_attempts += 1
        logger.info(f"尝试重连 ({self.reconnect_attempts}/{self.max_reconnect_attempts})...")
        
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(10)
            self.socket.connect((self.host, self.port))
            self.running = True
            self.reconnect_attempts = 0
            threading.Thread(target=self._receive_messages, daemon=True).start()
            self.reconnected.emit()
            logger.info("重连成功!")
        except Exception as e:
            logger.error(f"重连失败: {e}")
            # 指数退避延迟重连
            delay = min(30, 2 ** self.reconnect_attempts)
            QTimer.singleShot(delay * 1000, self.reconnect)

    def disconnect_server(self):
        self.running = False
        if self.socket:
            try:
                self.send_message({'type': 'logout'})
                self.socket.close()
            except: pass
        self.disconnected.emit()
        self.socket = None

    def send_message(self, msg: dict):
        if self.socket and self.running:
            try:
                self.socket.send((json.dumps(msg, ensure_ascii=False) + '\n').encode('utf-8'))
            except Exception as e:
                logger.error(f'Send error: {e}')

    def _receive_messages(self):
        buffer = ''
        while self.running and self.socket:
            try:
                self.socket.settimeout(1.0)
                try:
                    data = self.socket.recv(4096)
                    if not data:
                        logger.warning("服务器断开连接")
                        break
                    buffer += data.decode('utf-8', errors='ignore')
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        if line.strip():
                            try:
                                msg = json.loads(line)
                                # 更新最后消息序列号
                                if 'id' in msg:
                                    self.last_seq_id = max(self.last_seq_id, msg['id'])
                                self._dispatch_message(msg)
                            except json.JSONDecodeError:
                                logger.error(f"JSON解析错误: {line}")
                except socket.timeout:
                    continue
            except Exception as e:
                logger.error(f"接收消息出错: {e}")
                break
        
        if self.running:
            self.running = False
            # 触发重连
            self.reconnect()

    def _dispatch_message(self, message: dict):
        msg_type = message.get('type')
        if msg_type == 'login_response':
            success = message.get('success', False)
            if success: self.username = message.get('username')
            self.loginResponse.emit(success, message.get('message', ''), message.get('username', ''))
        elif msg_type == 'register_response': self.registerResponse.emit(message.get('success', False), message.get('message', ''))
        elif msg_type == 'group_message': self.groupMessage.emit({'type': 'group', 'from': message.get('from', ''), 'content': message.get('content', ''), 'timestamp': message.get('timestamp', ''), '_server_id': message.get('client_msg_id', '')}, message.get('client_msg_id', ''))
        elif msg_type == 'private_message': self.privateMessage.emit({'type': 'private', 'from': message.get('from', ''), 'to': message.get('to', ''), 'content': message.get('content', ''), 'timestamp': message.get('timestamp', ''), '_server_id': message.get('client_msg_id', '')}, message.get('client_msg_id', ''))
        elif msg_type == 'system_message': self.systemMessage.emit({'type': 'system', 'content': message.get('content', ''), 'timestamp': message.get('timestamp', '')})
        elif msg_type in ('online_users', 'user_list'): self.usersUpdated.emit(message.get('users', []))
        elif msg_type == 'group_history': self.groupHistory.emit(message.get('messages', []))
        elif msg_type == 'private_history': self.privateHistory.emit(message.get('messages', []))
        elif msg_type == 'login_policy': self.loginPolicy.emit(message.get('needs_password', True), message.get('message', ''))
        elif msg_type == 'unread_counts': self.unreadCounts.emit(message.get('counts', {}))
        elif msg_type == 'unread_increment': self.unreadIncrement.emit(message.get('from', ''))
