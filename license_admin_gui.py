#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
from pathlib import Path
from typing import Optional


def resolve_project_root() -> Path:
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        if exe_dir.name.lower() == "dist_nuitka":
            return exe_dir.parent
        return exe_dir
    return Path(__file__).resolve().parents[1]


PROJECT_ROOT = resolve_project_root()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from scripts.license_admin_service import (
    DEFAULT_BRANCH,
    DEFAULT_LICENSES,
    DEFAULT_PRIVATE_KEY,
    DEFAULT_REPO_URL,
    DEFAULT_SSH_KEY,
    LicenseIssueInput,
    PublishInput,
    issue_license_to_file,
    publish_license_to_gitee,
)


class LicenseTaskWorker(QThread):
    success = pyqtSignal(dict, str)
    failure = pyqtSignal(str)

    def __init__(self, publish_input: Optional[PublishInput], issue_input: LicenseIssueInput):
        super().__init__()
        self.publish_input = publish_input
        self.issue_input = issue_input

    def run(self):
        try:
            if self.publish_input:
                record, output = publish_license_to_gitee(self.publish_input)
                self.success.emit(record, output or "已推送到 Gitee")
            else:
                record = issue_license_to_file(self.issue_input)
                self.success.emit(record, "已写入本地 licenses.json")
        except Exception as exc:
            self.failure.emit(str(exc))


class LicenseAdminWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.worker: Optional[LicenseTaskWorker] = None
        self.setWindowTitle("授权管理器")
        self.resize(880, 620)
        self._build_ui()

    def _build_ui(self):
        root = QWidget()
        root_layout = QVBoxLayout(root)

        title = QLabel("一机一码授权管理器")
        title.setObjectName("title")
        root_layout.addWidget(title)

        form = QFormLayout()
        self.hwid_input = QTextEdit()
        self.hwid_input.setPlaceholderText("粘贴客户发来的机器码 / HWID")
        self.hwid_input.setFixedHeight(86)
        form.addRow("客户机器码:", self.hwid_input)

        self.owner_input = QLineEdit()
        self.owner_input.setPlaceholderText("客户名、QQ、微信或订单号")
        form.addRow("客户备注:", self.owner_input)

        self.note_input = QLineEdit()
        self.note_input.setPlaceholderText("可选，例如购买渠道、说明")
        form.addRow("内部备注:", self.note_input)

        self.expires_input = QLineEdit("permanent")
        form.addRow("到期时间:", self.expires_input)

        self.features_input = QLineEdit("full")
        form.addRow("功能:", self.features_input)

        root_layout.addLayout(form)

        path_grid = QGridLayout()
        self.private_key_input = QLineEdit(str(PROJECT_ROOT / DEFAULT_PRIVATE_KEY))
        self.licenses_input = QLineEdit(str(PROJECT_ROOT / DEFAULT_LICENSES))
        self.repo_input = QLineEdit(DEFAULT_REPO_URL)
        self.branch_input = QLineEdit(DEFAULT_BRANCH)
        self.ssh_key_input = QLineEdit(DEFAULT_SSH_KEY)

        self._add_path_row(path_grid, 0, "私钥:", self.private_key_input, self.choose_private_key)
        self._add_path_row(path_grid, 1, "授权表:", self.licenses_input, self.choose_licenses_file)
        path_grid.addWidget(QLabel("Gitee 仓库:"), 2, 0)
        path_grid.addWidget(self.repo_input, 2, 1, 1, 2)
        path_grid.addWidget(QLabel("分支:"), 3, 0)
        path_grid.addWidget(self.branch_input, 3, 1, 1, 2)
        self._add_path_row(path_grid, 4, "SSH Key:", self.ssh_key_input, self.choose_ssh_key)
        root_layout.addLayout(path_grid)

        self.push_checkbox = QCheckBox("签发后自动推送到 Gitee")
        self.push_checkbox.setChecked(True)
        root_layout.addWidget(self.push_checkbox)

        button_layout = QHBoxLayout()
        self.issue_button = QPushButton("签发授权")
        self.issue_button.clicked.connect(self.issue_license)
        self.push_button = QPushButton("签发并推送")
        self.push_button.clicked.connect(self.issue_and_push)
        clear_button = QPushButton("清空")
        clear_button.clicked.connect(self.clear_inputs)
        button_layout.addWidget(self.issue_button)
        button_layout.addWidget(self.push_button)
        button_layout.addWidget(clear_button)
        button_layout.addStretch()
        root_layout.addLayout(button_layout)

        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        root_layout.addWidget(self.log_display, 1)

        self.setCentralWidget(root)

    def _add_path_row(self, layout, row, label, line_edit, callback):
        layout.addWidget(QLabel(label), row, 0)
        layout.addWidget(line_edit, row, 1)
        button = QPushButton("选择")
        button.clicked.connect(callback)
        layout.addWidget(button, row, 2)

    def choose_private_key(self):
        self._choose_file(self.private_key_input, "选择 license_private.pem")

    def choose_licenses_file(self):
        self._choose_file(self.licenses_input, "选择 licenses.json")

    def choose_ssh_key(self):
        self._choose_file(self.ssh_key_input, "选择 Gitee SSH 私钥")

    def _choose_file(self, target: QLineEdit, title: str):
        path, _ = QFileDialog.getOpenFileName(self, title, str(PROJECT_ROOT))
        if path:
            target.setText(path)

    def build_issue_input(self) -> LicenseIssueInput:
        hwid = self.hwid_input.toPlainText().strip()
        if not hwid:
            raise ValueError("请先粘贴客户机器码。")
        return LicenseIssueInput(
            hwid=hwid,
            owner=self.owner_input.text().strip(),
            note=self.note_input.text().strip(),
            expires_at=self.expires_input.text().strip() or "permanent",
            features=self.features_input.text().strip() or "full",
            private_key_path=self.private_key_input.text().strip(),
            licenses_path=self.licenses_input.text().strip(),
        )

    def build_publish_input(self, issue: LicenseIssueInput) -> PublishInput:
        return PublishInput(
            issue=issue,
            repo_url=self.repo_input.text().strip() or DEFAULT_REPO_URL,
            branch=self.branch_input.text().strip() or DEFAULT_BRANCH,
            ssh_key_path=self.ssh_key_input.text().strip() or DEFAULT_SSH_KEY,
        )

    def issue_license(self):
        self.start_task(force_push=False)

    def issue_and_push(self):
        self.start_task(force_push=True)

    def start_task(self, force_push: bool = False):
        if self.worker and self.worker.isRunning():
            QMessageBox.warning(self, "正在执行", "当前任务还没结束，请稍等。")
            return
        try:
            issue = self.build_issue_input()
            publish = self.build_publish_input(issue) if (force_push or self.push_checkbox.isChecked()) else None
        except Exception as exc:
            QMessageBox.warning(self, "参数不完整", str(exc))
            return

        self.set_buttons_enabled(False)
        self.log("开始签发授权...")
        if publish:
            self.log(f"将推送到: {publish.repo_url} ({publish.branch})")
        self.worker = LicenseTaskWorker(publish, issue)
        self.worker.success.connect(self.on_success)
        self.worker.failure.connect(self.on_failure)
        self.worker.finished.connect(lambda: self.set_buttons_enabled(True))
        self.worker.start()

    def set_buttons_enabled(self, enabled: bool):
        self.issue_button.setEnabled(enabled)
        self.push_button.setEnabled(enabled)

    def on_success(self, record: dict, message: str):
        self.log("成功: " + message)
        self.log(f"机器码 hash: {record.get('hwid_hash')}")
        self.log(f"到期时间: {record.get('expires_at')}")
        QMessageBox.information(self, "完成", "授权已签发。")

    def on_failure(self, message: str):
        self.log("失败: " + message)
        QMessageBox.critical(self, "失败", message)

    def clear_inputs(self):
        self.hwid_input.clear()
        self.owner_input.clear()
        self.note_input.clear()

    def log(self, message: str):
        self.log_display.append(message)


def main() -> int:
    app = QApplication(sys.argv)
    window = LicenseAdminWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
