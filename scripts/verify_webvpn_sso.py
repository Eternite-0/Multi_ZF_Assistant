"""交互式验证 WebVPN 是否已自动建立教务系统 SSO 会话。

该工具不会保存账号、密码、验证码或 Cookie；仅在进程内完成一次只读验证。
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from api.zfn_api import Client


WEBVPN_BASE_URL = (
    "https://csvpn.lingnan.edu.cn/http/"
    "77726476706e69737468656265737421fae00f902e3e6f5e7f06c7a99c406d36a1/"
)


class WebVPNVerifier(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.client: Client | None = None
        self.setWindowTitle("WebVPN 教务单点登录验证")
        self.setMinimumWidth(540)

        form = QFormLayout()
        self.username = QLineEdit()
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.edu_username = QLineEdit()
        self.edu_username.setEnabled(False)
        self.edu_password = QLineEdit()
        self.edu_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.edu_password.setEnabled(False)
        self.captcha = QLineEdit()
        self.captcha.setEnabled(False)
        form.addRow("WebVPN 账号", self.username)
        form.addRow("WebVPN 密码", self.password)
        form.addRow("验证码", self.captcha)
        form.addRow("教务账号（仅无 SSO 时）", self.edu_username)
        form.addRow("教务密码（仅无 SSO 时）", self.edu_password)

        self.captcha_image = QLabel("点击“获取验证码”后在此显示")
        self.captcha_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.captcha_image.setMinimumHeight(70)

        self.request_button = QPushButton("获取验证码")
        self.submit_button = QPushButton("提交并测试 SSO")
        self.submit_button.setEnabled(False)
        self.edu_login_button = QPushButton("登录教务并测试接口")
        self.edu_login_button.setEnabled(False)
        buttons = QHBoxLayout()
        buttons.addWidget(self.request_button)
        buttons.addWidget(self.submit_button)
        buttons.addWidget(self.edu_login_button)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setPlaceholderText("验证结果将显示在这里；不会展示个人资料内容。")

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("流程：WebVPN 验证码登录 → 自动检测教务 SSO → 只读接口状态测试"))
        layout.addLayout(form)
        layout.addWidget(self.captcha_image)
        layout.addLayout(buttons)
        layout.addWidget(self.output)

        self.request_button.clicked.connect(self.request_captcha)
        self.submit_button.clicked.connect(self.complete_and_test)
        self.edu_login_button.clicked.connect(self.login_education_and_test)

    def request_captcha(self) -> None:
        if not self.username.text().strip() or not self.password.text():
            self.output.setPlainText("请先填写 WebVPN 账号和密码。")
            return

        self.client = Client(base_url=WEBVPN_BASE_URL, timeout=15)
        result = self.client.begin_webvpn_login()
        if result.get("code") != 1001:
            self.output.setPlainText(f"获取验证码失败：{result.get('msg', '未知错误')}")
            return

        encoded = result["data"]["captcha_image"]
        pixmap = QPixmap()
        if not pixmap.loadFromData(base64.b64decode(encoded)):
            self.output.setPlainText("验证码图片无法显示，请重新获取。")
            return
        self.captcha_image.setPixmap(pixmap)
        self.captcha.setEnabled(True)
        self.submit_button.setEnabled(True)
        self.output.setPlainText("请输入图片中的验证码，然后点击“提交并测试 SSO”。")

    def complete_and_test(self) -> None:
        if not self.client or not self.captcha.text().strip():
            self.output.setPlainText("请先获取并填写验证码。")
            return

        result = self.client.complete_webvpn_login(
            self.username.text().strip(), self.password.text(), self.captcha.text().strip()
        )
        lines = [f"WebVPN：{result.get('msg', '未知结果')}"]
        if result.get("code") != 1000:
            lines.append("验证停止：请重新获取验证码后再试。")
            self.output.setPlainText("\n".join(lines))
            return

        status = self.client.get_login_status()
        if not status["is_logged_in"]:
            lines.append("结论：该 VPN 会话未自动登录教务系统，请填写教务账号密码后点击“登录教务并测试接口”。")
            self.edu_username.setEnabled(True)
            self.edu_password.setEnabled(True)
            self.edu_login_button.setEnabled(True)
            self.output.setPlainText("\n".join(lines))
            return

        lines.append("结论：已建立教务单点登录会话；开始只读接口验证。")
        self.run_read_only_tests(lines)

    def login_education_and_test(self) -> None:
        if not self.client:
            self.output.setPlainText("请先完成 WebVPN 登录。")
            return
        if not self.edu_username.text().strip() or not self.edu_password.text():
            self.output.setPlainText("请填写教务账号和密码。")
            return
        result = self.client.login(self.edu_username.text().strip(), self.edu_password.text())
        lines = [f"教务系统：{result.get('msg', '未知结果')}"]
        if result.get("code") != 1000:
            self.output.setPlainText("\n".join(lines))
            return
        lines.append("教务登录成功；开始只读接口验证。")
        self.run_read_only_tests(lines)

    def run_read_only_tests(self, lines: list[str]) -> None:
        """运行不会修改教务数据的接口，并仅显示状态而不输出个人资料。"""
        for name, method in (
            ("个人信息", self.client.get_info),
            ("通知", self.client.get_notifications),
            ("GPA", self.client.get_gpa),
        ):
            try:
                api_result = method()
                lines.append(f"{name}：{api_result.get('msg', '无返回说明')}")
            except Exception as exc:
                lines.append(f"{name}：请求异常：{exc}")
        self.output.setPlainText("\n".join(lines))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = WebVPNVerifier()
    window.show()
    sys.exit(app.exec())
