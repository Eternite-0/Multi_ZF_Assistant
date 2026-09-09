from typing import Callable

from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from core.license import LicenseStatus


class LicenseDialog(QDialog):
    def __init__(
        self,
        status: LicenseStatus,
        checker: Callable[[], LicenseStatus],
        parent=None,
    ):
        super().__init__(parent)
        self.status = status
        self.checker = checker

        self.setWindowTitle("软件授权")
        self.setModal(True)
        self.resize(620, 240)

        layout = QVBoxLayout(self)

        title = QLabel("当前设备尚未授权")
        title.setObjectName("license-title")
        layout.addWidget(title)

        self.reason_label = QLabel()
        self.reason_label.setWordWrap(True)
        layout.addWidget(self.reason_label)

        layout.addWidget(QLabel("机器码:"))
        code_layout = QHBoxLayout()
        self.machine_code_input = QLineEdit()
        self.machine_code_input.setReadOnly(True)
        code_layout.addWidget(self.machine_code_input)

        copy_button = QPushButton("复制机器码")
        copy_button.clicked.connect(self.copy_machine_code)
        code_layout.addWidget(copy_button)
        layout.addLayout(code_layout)

        hint = QLabel("把机器码发给管理员，管理员授权后点击“刷新授权”。")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        button_layout = QHBoxLayout()
        refresh_button = QPushButton("刷新授权")
        refresh_button.clicked.connect(self.refresh_license)
        exit_button = QPushButton("退出")
        exit_button.clicked.connect(self.reject)

        button_layout.addStretch()
        button_layout.addWidget(refresh_button)
        button_layout.addWidget(exit_button)
        layout.addLayout(button_layout)

        self.update_status(status)

    def update_status(self, status: LicenseStatus) -> None:
        self.status = status
        self.reason_label.setText(f"授权状态: {status.reason}")
        self.machine_code_input.setText(status.machine_code)

    def copy_machine_code(self) -> None:
        QApplication.clipboard().setText(self.status.machine_code)
        QMessageBox.information(self, "已复制", "机器码已复制到剪贴板。")

    def refresh_license(self) -> None:
        status = self.checker()
        self.update_status(status)
        if status.allowed:
            QMessageBox.information(self, "授权成功", "授权验证通过，即将进入主程序。")
            self.accept()
        else:
            QMessageBox.warning(self, "仍未授权", status.reason)
