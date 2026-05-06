# -*- coding: utf-8 -*-
"""
server.py - TCP多用户聊天服务器

功能：
- TCP socket监听，接受多个客户端连接
- 多线程处理每个客户端
- 用户注册、登录、登出管理
- 群聊消息广播
- 私聊消息转发
- 聊天记录保存到数据库

个性化特色可扩展点：
- 文件传输功能
- 消息加密传输
- 心跳检测（检测断线）
- 踢出用户功能
- 用户禁言功能
- 管理员命令支持
"""

import socket
import threading
import json
import logging
from datetime import datetime
from typing import Dict, Optional

from database import get_database

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('server.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# 服务器配置
HOST = '0.0.0.0'  # 监听所有网络接口
PORT = 8888       # 监听端口
BUFFER_SIZE = 4096  # 接收缓冲区大小


class ChatServer:
    """聊天服务器主类"""

    def __init__(self, host: str = HOST, port: int = PORT):
        self.host = host
        self.port = port
        self.server_socket: Optional[socket.socket] = None
        self.clients: Dict[str, tuple] = {}  # {username: (client_socket, address)}
        self.clients_lock = threading.Lock()  # 保护clients字典的锁
        self.running = False

        # 获取数据库实例
        self.db = get_database()

        logger.info(f"服务器配置: {host}:{port}")

    def start(self):
        """启动服务器"""
        try:
            # 创建TCP socket
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)

            self.running = True
            logger.info(f"="*50)
            logger.info(f"聊天服务器启动成功!")
            logger.info(f"监听地址: {self.host}:{self.port}")
            logger.info(f"按 Ctrl+C 停止服务器")
            logger.info(f"="*50)

            self._accept_connections()

        except socket.error as e:
            logger.error(f"服务器启动失败: {e}")
            self.running = False
        except KeyboardInterrupt:
            logger.info("服务器被手动停止")
            self.stop()

    def _accept_connections(self):
        """接受客户端连接"""
        while self.running:
            try:
                client_socket, address = self.server_socket.accept()
                logger.info(f"新连接: {address}")

                # 为每个客户端创建一个处理线程
                client_thread = threading.Thread(
                    target=self._handle_client,
                    args=(client_socket, address),
                    daemon=True
                )
                client_thread.start()

            except Exception as e:
                if self.running:
                    logger.error(f"接受连接时出错: {e}")

    def _handle_client(self, client_socket: socket.socket, address: tuple):
        """
        处理单个客户端连接

        Args:
            client_socket: 客户端socket
            address: 客户端地址
        """
        username = None

        try:
            # 保持连接，循环处理消息
            while self.running:
                # 接收数据
                data = client_socket.recv(BUFFER_SIZE)

                if not data:
                    break

                # 解码并解析JSON消息
                try:
                    message = json.loads(data.decode('utf-8'))
                    msg_type = message.get('type')

                    # 处理不同类型的消息
                    if msg_type == 'register':
                        username = self._handle_register(client_socket, message)
                    elif msg_type == 'login':
                        username = self._handle_login(client_socket, message)
                    elif msg_type == 'message':
                        self._handle_chat_message(message, username)
                    elif msg_type == 'private_message':
                        self._handle_private_message(message, username)
                    elif msg_type == 'get_online_users':
                        self._send_online_users(client_socket)
                    elif msg_type == 'get_group_history':
                        self._send_group_history(client_socket, username)
                    elif msg_type == 'get_private_history':
                        self._send_private_history(client_socket, username, message)
                    elif msg_type == 'logout':
                        self._handle_logout(username, client_socket)
                        break
                    else:
                        logger.warning(f"未知消息类型: {msg_type}")

                except json.JSONDecodeError as e:
                    logger.error(f"JSON解析错误: {e}, 数据: {data}")

        except ConnectionResetError:
            logger.info(f"客户端异常断开: {address}")
        except Exception as e:
            logger.error(f"处理客户端时出错: {e}")
        finally:
            # 清理资源
            if username:
                self._remove_client(username)
            try:
                client_socket.close()
            except:
                pass

    def _handle_register(self, client_socket: socket.socket, message: dict) -> Optional[str]:
        """
        处理用户注册

        Args:
            client_socket: 客户端socket
            message: 注册消息

        Returns:
            注册成功的用户名，否则None
        """
        username = message.get('username', '').strip()
        password = message.get('password', '')

        if not username or not password:
            self._send_response(client_socket, {
                'type': 'register_response',
                'success': False,
                'message': '用户名和密码不能为空'
            })
            return None

        result = self.db.register_user(username, password)

        self._send_response(client_socket, {
            'type': 'register_response',
            'success': result['success'],
            'message': result['message']
        })

        if result['success']:
            logger.info(f"用户注册成功: {username}")
            return username
        return None

    def _handle_login(self, client_socket: socket.socket, message: dict) -> Optional[str]:
        """
        处理用户登录

        Args:
            client_socket: 客户端socket
            message: 登录消息

        Returns:
            登录成功的用户名，否则None
        """
        username = message.get('username', '').strip()
        password = message.get('password', '')

        if not username or not password:
            self._send_response(client_socket, {
                'type': 'login_response',
                'success': False,
                'message': '用户名和密码不能为空'
            })
            return None

        # 验证登录
        result = self.db.verify_login(username, password)

        if result['success']:
            # 检查是否已在线
            if username in self.clients:
                self._send_response(client_socket, {
                    'type': 'login_response',
                    'success': False,
                    'message': '该用户已在线'
                })
                return None

            # 添加到在线用户列表
            self._add_client(username, client_socket)
            print(f"[服务器] 用户 {username} 已添加到在线列表", flush=True)

            # 发送登录成功响应
            print(f"[服务器] 发送登录响应给 {username}", flush=True)
            self._send_response(client_socket, {
                'type': 'login_response',
                'success': True,
                'message': '登录成功',
                'username': username
            })

            # 确保登录响应已发送
            import time
            time.sleep(0.1)
            print(f"[服务器] 登录响应已发送，等待后发送在线用户列表", flush=True)

            # 向新登录的用户发送当前在线用户列表
            print(f"[服务器] 发送在线用户列表给 {username}", flush=True)
            self._send_online_users(client_socket)

            # 广播用户上线通知给所有其他用户
            print(f"[服务器] 广播 {username} 上线通知", flush=True)
            self._broadcast_system_message(f"{username} 上线了", username)

            # 通知所有其他客户端更新在线用户列表
            self._broadcast_online_users(exclude=username)

            print(f"[服务器] 用户 {username} 登录完成", flush=True)
            logger.info(f"用户登录成功: {username}")
            return username
        else:
            self._send_response(client_socket, {
                'type': 'login_response',
                'success': False,
                'message': result['message']
            })
            return None

    def _handle_chat_message(self, message: dict, sender: Optional[str]):
        """
        处理群聊消息

        Args:
            message: 消息内容
            sender: 发送者用户名
        """
        if not sender:
            logger.warning("未登录用户尝试发送群聊消息")
            return

        content = message.get('content', '').strip()
        if not content:
            return

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 保存到数据库
        self.db.save_message(sender, "ALL", content, "group")

        # 广播给所有在线用户
        broadcast_msg = {
            'type': 'group_message',
            'from': sender,
            'to': 'ALL',
            'content': content,
            'timestamp': timestamp
        }

        self._broadcast(json.dumps(broadcast_msg, ensure_ascii=False), exclude=sender)

        logger.info(f"[群聊] {sender}: {content}")

    def _handle_private_message(self, message: dict, sender: Optional[str]):
        """
        处理私聊消息

        Args:
            message: 消息内容
            sender: 发送者用户名
        """
        if not sender:
            logger.warning("未登录用户尝试发送私聊消息")
            return

        to_user = message.get('to', '').strip()
        content = message.get('content', '').strip()

        if not to_user or not content:
            return

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 保存到数据库
        self.db.save_message(sender, to_user, content, "private")

        # 发送消息给目标用户
        private_msg = {
            'type': 'private_message',
            'from': sender,
            'to': to_user,
            'content': content,
            'timestamp': timestamp
        }

        # 发送给接收者
        self._send_to_user(to_user, json.dumps(private_msg, ensure_ascii=False))

        # 发送确认给发送者
        self._send_to_user(sender, json.dumps(private_msg, ensure_ascii=False))

        logger.info(f"[私聊] {sender} -> {to_user}: {content}")

    def _handle_logout(self, username: Optional[str], client_socket: socket.socket):
        """
        处理用户登出

        Args:
            username: 用户名
            client_socket: 客户端socket
        """
        if username:
            self._remove_client(username)
            self._broadcast_system_message(f"{username} 离线了", username)
            # 通知所有客户端更新在线用户列表
            self._broadcast_online_users()
            logger.info(f"用户登出: {username}")

    def _send_response(self, client_socket: socket.socket, response: dict):
        """
        发送响应给客户端

        Args:
            client_socket: 客户端socket
            response: 响应内容
        """
        try:
            client_socket.send(
                (json.dumps(response, ensure_ascii=False) + '\n').encode('utf-8')
            )
        except Exception as e:
            logger.error(f"发送响应失败: {e}")

    def _add_client(self, username: str, client_socket: socket.socket):
        """
        添加客户端到在线列表

        Args:
            username: 用户名
            client_socket: 客户端socket
        """
        with self.clients_lock:
            self.clients[username] = (client_socket, None)
            self.db.set_user_online(username, True)

        logger.info(f"用户加入在线列表: {username}")

    def _remove_client(self, username: str):
        """
        从在线列表移除客户端

        Args:
            username: 用户名
        """
        with self.clients_lock:
            if username in self.clients:
                del self.clients[username]
                self.db.set_user_online(username, False)
                logger.info(f"用户离开在线列表: {username}")

    def _broadcast(self, message: str, exclude: Optional[str] = None):
        """
        广播消息给所有在线用户

        Args:
            message: 消息内容
            exclude: 要排除的用户名
        """
        with self.clients_lock:
            clients_copy = list(self.clients.items())

        for username, (client_socket, _) in clients_copy:
            if username != exclude:
                try:
                    client_socket.send((message + '\n').encode('utf-8'))
                except Exception as e:
                    logger.error(f"广播消息给 {username} 失败: {e}")

    def _send_to_user(self, username: str, message: str) -> bool:
        """
        发送消息给指定用户

        Args:
            username: 目标用户名
            message: 消息内容

        Returns:
            是否发送成功
        """
        with self.clients_lock:
            if username not in self.clients:
                return False
            client_socket, _ = self.clients[username]

        try:
            client_socket.send((message + '\n').encode('utf-8'))
            return True
        except Exception as e:
            logger.error(f"发送消息给 {username} 失败: {e}")
            return False

    def _broadcast_system_message(self, content: str, exclude: Optional[str] = None):
        """
        广播系统消息

        Args:
            content: 系统消息内容
            exclude: 要排除的用户名
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        system_msg = {
            'type': 'system_message',
            'content': content,
            'timestamp': timestamp
        }
        self._broadcast(json.dumps(system_msg, ensure_ascii=False), exclude=exclude)

    def _send_online_users(self, client_socket: socket.socket):
        """
        发送在线用户列表给客户端

        Args:
            client_socket: 客户端socket
        """
        with self.clients_lock:
            online_users = list(self.clients.keys())

        response = {
            'type': 'online_users',
            'users': online_users
        }
        self._send_response(client_socket, response)

    def _broadcast_online_users(self, exclude: Optional[str] = None):
        """
        广播在线用户列表给所有客户端（用于通知更新）

        Args:
            exclude: 要排除的用户名
        """
        with self.clients_lock:
            online_users = list(self.clients.keys())
            clients_copy = list(self.clients.items())

        response = {
            'type': 'online_users',
            'users': online_users
        }
        response_json = json.dumps(response, ensure_ascii=False)

        for username, (client_socket, _) in clients_copy:
            if username != exclude:
                try:
                    client_socket.send((response_json + '\n').encode('utf-8'))
                except Exception as e:
                    logger.error(f"广播在线用户列表给 {username} 失败: {e}")

    def _send_group_history(self, client_socket: socket.socket, username: Optional[str]):
        """
        发送群聊历史消息给客户端

        Args:
            client_socket: 客户端socket
            username: 用户名
        """
        if not username:
            return

        messages = self.db.get_group_messages(50)
        response = {
            'type': 'group_history',
            'messages': messages
        }
        self._send_response(client_socket, response)

    def _send_private_history(self, client_socket: socket.socket,
                               username: Optional[str], message: dict):
        """
        发送私聊历史消息给客户端

        Args:
            client_socket: 客户端socket
            username: 用户名
            message: 请求消息，包含目标用户名
        """
        if not username:
            return

        target_user = message.get('with_user', '')
        if not target_user:
            return

        messages = self.db.get_private_messages(username, target_user, 50)
        response = {
            'type': 'private_history',
            'with_user': target_user,
            'messages': messages
        }
        self._send_response(client_socket, response)

    def stop(self):
        """停止服务器"""
        logger.info("正在停止服务器...")
        self.running = False

        # 关闭所有客户端连接
        with self.clients_lock:
            for username, (client_socket, _) in self.clients.items():
                try:
                    client_socket.close()
                except:
                    pass
            self.clients.clear()

        # 关闭服务器socket
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass

        logger.info("服务器已停止")


def main():
    """主函数"""
    print("\n" + "="*50)
    print("    TCP 多用户聊天服务器")
    print("="*50 + "\n")

    server = ChatServer()
    server.start()


if __name__ == "__main__":
    main()
