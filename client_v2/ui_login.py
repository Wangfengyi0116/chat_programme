from PyQt6.QtWidgets import QWidget, QVBoxLayout, QFormLayout, QLineEdit, QPushButton, QMessageBox

class LoginWindow(QWidget):
    def __init__(self, network):
        super().__init__()
        self.network = network
        self.current_user = None  # 记录当前登录的用户
        self.current_host = '127.0.0.1'  # 记录服务器地址
        self.current_port = 8889  # 记录端口
        self.setWindowTitle('登录')
        self.resize(300, 200)
        
        layout = QFormLayout(self)
        self.host_input = QLineEdit('127.0.0.1')
        self.port_input = QLineEdit('8889')
        self.user_input = QLineEdit()
        self.pass_input = QLineEdit()
        self.pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        
        layout.addRow('地址:', self.host_input)
        layout.addRow('端口:', self.port_input)
        layout.addRow('用户名:', self.user_input)
        layout.addRow('密码:', self.pass_input)
        
        btn_box = QVBoxLayout()
        self.login_btn = QPushButton('登录')
        self.login_btn.clicked.connect(self.on_login)
        self.reg_btn = QPushButton('注册')
        self.reg_btn.clicked.connect(self.on_register)
        btn_box.addWidget(self.login_btn)
        btn_box.addWidget(self.reg_btn)
        layout.addRow(btn_box)

        self.network.registerResponse.connect(self.on_register_response)
        self.network.loginResponse.connect(self.on_login_response_internal)

    def set_network(self, network):
        """设置新的网络连接"""
        # 断开旧的信号连接
        try:
            self.network.registerResponse.disconnect(self.on_register_response)
            self.network.loginResponse.disconnect(self.on_login_response_internal)
        except: pass
        self.network = network
        self.network.registerResponse.connect(self.on_register_response)
        self.network.loginResponse.connect(self.on_login_response_internal)

    def reset(self):
        """重置登录窗口，清空用户名和密码，保留服务器地址"""
        self.user_input.clear()
        self.pass_input.clear()
        self.current_user = None
        # 显示窗口
        self.show()

    def _ensure_connected(self):
        if not self.network.running:
            self.current_host = self.host_input.text()
            self.current_port = int(self.port_input.text())
            return self.network.connect_server(self.current_host, self.current_port)
        return True

    def on_login(self):
        print(f'Attempting login with {self.user_input.text()}')
        if not self._ensure_connected(): return QMessageBox.critical(self, '错误', '无法连接')
        self.current_user = self.user_input.text().strip()
        self.network.send_message({'type': 'login', 'username': self.current_user, 'password': self.pass_input.text(), 'skip_password': False})

    def on_register(self):
        if not self._ensure_connected(): return QMessageBox.critical(self, '错误', '无法连接')
        self.network.send_message({'type': 'register', 'username': self.user_input.text(), 'password': self.pass_input.text()})

    def on_register_response(self, success, msg):
        if success: QMessageBox.information(self, '成功', '注册成功')
        else: QMessageBox.critical(self, '失败', msg)

    def on_login_response_internal(self, success, msg, username):
        """内部登录响应处理 - 用于更新UI"""
        pass  # 实际处理在main.py的on_login_response中
