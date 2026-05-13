import sys
from PyQt6.QtWidgets import QApplication, QMessageBox

from network import NetworkClient
from ui_login import LoginWindow
from ui_chat import ChatWindow

class ClientApp:
    def __init__(self):
        self.network = NetworkClient()
        self.login_window = LoginWindow(self.network)
        self.chat_window = None
        self.network.loginResponse.connect(self.on_login_response)
        self.network.disconnected.connect(self.on_disconnected)

    def start(self): self.login_window.show()

    def on_login_response(self, success, msg, username):
        print(f'Login response: success={success}, msg={msg}, username={username}')
        if success:
            # 登录成功后保留当前网络连接，创建聊天窗口
            # 重要：不要创建新的 NetworkClient，原连接已经与服务器建立了会话
            self.chat_window = ChatWindow(self.network, username)
            self.chat_window.show()
            # 重置登录窗口以供下次使用
            self.login_window.reset()
            # 创建新的网络连接用于下次登录（用户下次登录时使用）
            self.network = NetworkClient()
            self.login_window.set_network(self.network)
            self.network.loginResponse.connect(self.on_login_response)
            self.network.disconnected.connect(self.on_disconnected)
        else: QMessageBox.critical(self.login_window, '错误', msg)

    def on_disconnected(self):
        if self.chat_window: QMessageBox.warning(self.chat_window, '断开连接', '与服务器连接已断开')

blue_qss = """
QWidget { background-color: #F0F8FF; font-family: Segoe UI, sans-serif; color: #444; font-size: 14px; }
QPushButton { background-color: #87CEFA; border: none; border-radius: 16px; padding: 8px 16px; font-weight: bold; color: white; }
QPushButton:hover { background-color: #4682B4; }
QPushButton:pressed { background-color: #0000CD; }
QLineEdit { border: 2px solid #B0E0E6; border-radius: 12px; padding: 6px 12px; background-color: white; }
QLineEdit:focus { border: 2px solid #4682B4; }
QTextEdit, QListWidget { border: 2px solid #ADD8E6; border-radius: 12px; background-color: white; padding: 8px; }
QListWidget::item { padding: 8px; border-radius: 8px; margin-bottom: 2px; }
QListWidget::item:selected { background-color: #87CEFA; color: white; }
QTabBar::tab { background: #E6F2FF; border-top-left-radius: 15px; border-top-right-radius: 15px; padding: 8px 25px; font-weight: bold; }
QTabBar::tab:selected { background: #87CEFA; color: white; }
QLabel { font-weight: bold; color: #4682B4; }
"""

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyleSheet(blue_qss)
    client = ClientApp()
    client.start()
    sys.exit(app.exec())
