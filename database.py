# -*- coding: utf-8 -*-
"""
database.py - 数据库管理模块

功能：
- SQLite数据库连接管理
- 用户表和消息表的创建
- 用户注册、登录验证、在线状态管理
- 聊天消息的存储和查询

个性化特色可扩展点：
- 增加消息加密存储
- 增加消息搜索功能
- 增加消息撤回功能
- 增加群组功能表
"""

import sqlite3
import threading
from datetime import datetime
from typing import Optional, List, Dict, Any
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class Database:
    """数据库管理类，提供线程安全的数据库操作"""

    def __init__(self, db_path: str = "chat_server.db"):
        """
        初始化数据库连接

        Args:
            db_path: 数据库文件路径
        """
        self.db_path = db_path
        self.lock = threading.Lock()
        self._init_database()

    def _get_connection(self) -> sqlite3.Connection:
        """
        获取数据库连接（每次操作创建新连接）

        Returns:
            sqlite3.Connection对象
        """
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row  # 支持列名访问
        return conn

    def _init_database(self):
        """初始化数据库，创建必要的表"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # 创建用户表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    is_online INTEGER DEFAULT 0,
                    register_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login_time TIMESTAMP
                )
            """)

            # 创建消息表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender TEXT NOT NULL,
                    receiver TEXT NOT NULL,
                    content TEXT NOT NULL,
                    message_type TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_read INTEGER DEFAULT 0
                )
            """)

            # 创建索引提高查询效率
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_receiver ON messages(receiver)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp)
            """)

            conn.commit()
            conn.close()
            logger.info(f"数据库初始化完成: {self.db_path}")

        except sqlite3.Error as e:
            logger.error(f"数据库初始化失败: {e}")
            raise

    def register_user(self, username: str, password: str) -> Dict[str, Any]:
        """
        注册新用户

        Args:
            username: 用户名
            password: 密码

        Returns:
            包含success和message的字典
        """
        with self.lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()

                # 检查用户名是否已存在
                cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
                if cursor.fetchone():
                    conn.close()
                    return {"success": False, "message": "用户名已存在"}

                # 插入新用户
                cursor.execute(
                    "INSERT INTO users (username, password) VALUES (?, ?)",
                    (username, password)
                )
                conn.commit()
                conn.close()

                logger.info(f"新用户注册成功: {username}")
                return {"success": True, "message": "注册成功"}

            except sqlite3.Error as e:
                logger.error(f"用户注册失败: {e}")
                return {"success": False, "message": f"注册失败: {e}"}

    def verify_login(self, username: str, password: str) -> Dict[str, Any]:
        """
        验证用户登录

        Args:
            username: 用户名
            password: 密码

        Returns:
            包含success和message的字典
        """
        with self.lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()

                # 查询用户
                cursor.execute(
                    "SELECT id, username FROM users WHERE username = ? AND password = ?",
                    (username, password)
                )
                user = cursor.fetchone()

                if user:
                    # 更新在线状态和最后登录时间
                    cursor.execute(
                        "UPDATE users SET is_online = 1, last_login_time = ? WHERE username = ?",
                        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), username)
                    )
                    conn.commit()
                    conn.close()

                    logger.info(f"用户登录成功: {username}")
                    return {"success": True, "message": "登录成功", "username": username}

                conn.close()
                logger.warning(f"用户登录失败: {username}")
                return {"success": False, "message": "用户名或密码错误"}

            except sqlite3.Error as e:
                logger.error(f"登录验证失败: {e}")
                return {"success": False, "message": f"验证失败: {e}"}

    def set_user_online(self, username: str, is_online: bool):
        """
        设置用户在线状态

        Args:
            username: 用户名
            is_online: 是否在线
        """
        with self.lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE users SET is_online = ? WHERE username = ?",
                    (1 if is_online else 0, username)
                )
                conn.commit()
                conn.close()

                status = "上线" if is_online else "离线"
                logger.info(f"用户状态更新: {username} - {status}")

            except sqlite3.Error as e:
                logger.error(f"更新用户在线状态失败: {e}")

    def get_online_users(self) -> List[str]:
        """
        获取所有在线用户列表

        Returns:
            在线用户名列表
        """
        with self.lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT username FROM users WHERE is_online = 1")
                users = [row[0] for row in cursor.fetchall()]
                conn.close()
                return users

            except sqlite3.Error as e:
                logger.error(f"获取在线用户失败: {e}")
                return []

    def save_message(self, sender: str, receiver: str, content: str,
                     message_type: str = "group") -> bool:
        """
        保存聊天消息

        Args:
            sender: 发送者用户名
            receiver: 接收者用户名（群聊为"ALL"）
            content: 消息内容
            message_type: 消息类型（"group"群聊，"private"私聊）

        Returns:
            是否保存成功
        """
        with self.lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()
                cursor.execute(
                    """INSERT INTO messages (sender, receiver, content, message_type)
                       VALUES (?, ?, ?, ?)""",
                    (sender, receiver, content, message_type)
                )
                conn.commit()
                conn.close()

                msg_type = "群聊" if message_type == "group" else "私聊"
                logger.debug(f"消息已保存: [{msg_type}] {sender} -> {receiver}")
                return True

            except sqlite3.Error as e:
                logger.error(f"保存消息失败: {e}")
                return False

    def get_group_messages(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        获取群聊历史消息

        Args:
            limit: 返回消息数量上限

        Returns:
            消息列表
        """
        with self.lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT id, sender, receiver, content, message_type, timestamp
                       FROM messages
                       WHERE message_type = 'group'
                       ORDER BY timestamp DESC
                       LIMIT ?""",
                    (limit,)
                )
                messages = [dict(row) for row in cursor.fetchall()]
                conn.close()
                return messages[::-1]  # 按时间正序返回

            except sqlite3.Error as e:
                logger.error(f"获取群聊消息失败: {e}")
                return []

    def get_private_messages(self, user1: str, user2: str,
                             limit: int = 50) -> List[Dict[str, Any]]:
        """
        获取两个用户之间的私聊消息

        Args:
            user1: 用户1
            user2: 用户2
            limit: 返回消息数量上限

        Returns:
            消息列表
        """
        with self.lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT id, sender, receiver, content, message_type, timestamp
                       FROM messages
                       WHERE message_type = 'private'
                       AND ((sender = ? AND receiver = ?) OR (sender = ? AND receiver = ?))
                       ORDER BY timestamp DESC
                       LIMIT ?""",
                    (user1, user2, user2, user1, limit)
                )
                messages = [dict(row) for row in cursor.fetchall()]
                conn.close()
                return messages[::-1]  # 按时间正序返回

            except sqlite3.Error as e:
                logger.error(f"获取私聊消息失败: {e}")
                return []

    def get_user_messages(self, username: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        获取某用户相关的所有消息（私聊）

        Args:
            username: 用户名
            limit: 返回消息数量上限

        Returns:
            消息列表
        """
        with self.lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT id, sender, receiver, content, message_type, timestamp
                       FROM messages
                       WHERE message_type = 'private'
                       AND (sender = ? OR receiver = ?)
                       ORDER BY timestamp DESC
                       LIMIT ?""",
                    (username, username, limit)
                )
                messages = [dict(row) for row in cursor.fetchall()]
                conn.close()
                return messages[::-1]

            except sqlite3.Error as e:
                logger.error(f"获取用户消息失败: {e}")
                return []

    def get_all_users(self) -> List[str]:
        """
        获取所有注册用户列表

        Returns:
            用户名列表
        """
        with self.lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT username FROM users ORDER BY register_time DESC")
                users = [row[0] for row in cursor.fetchall()]
                conn.close()
                return users

            except sqlite3.Error as e:
                logger.error(f"获取所有用户失败: {e}")
                return []

    def close(self):
        """关闭数据库（此处无需关闭，SQLite自动管理）"""
        logger.info("数据库连接已关闭")


# 单例模式供其他模块使用
_db_instance: Optional[Database] = None
_db_lock = threading.Lock()


def get_database(db_path: str = "chat_server.db") -> Database:
    """
    获取数据库单例实例

    Args:
        db_path: 数据库文件路径

    Returns:
        Database实例
    """
    global _db_instance
    if _db_instance is None:
        with _db_lock:
            if _db_instance is None:
                _db_instance = Database(db_path)
    return _db_instance
