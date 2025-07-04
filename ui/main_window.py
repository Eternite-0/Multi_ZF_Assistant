import json
import os
import time
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QLineEdit, QPushButton, QTextEdit, QFormLayout,
                             QComboBox, QTabWidget, QTableWidget, QTableWidgetItem,
                             QGridLayout, QFileDialog, QHeaderView,
                             QAbstractItemView, QMessageBox, QDialog, QDialogButtonBox,
                             QInputDialog, QListWidget, QListWidgetItem, QSpinBox)
from PyQt6.QtCore import Qt

# 确保这些导入路径是正确的
from api.zfn_api import Client
from core import config, models
from ui.dialogs import ExamCalendarDialog
from ui.assets import STYLESHEET, TRANSLATIONS
from utils.workers import ApiWorker, PriorityBatchGrabber, BatchLoginWorker, BatchActionWorker


class AccountDialog(QDialog):
    """一个简单的对话框用于添加/编辑账户。"""
    def __init__(self, parent=None, account=None):
        super().__init__(parent)
        self.setWindowTitle("添加/编辑账户")
        self.layout = QFormLayout(self)
        self.url_input = QLineEdit("http://jw.lingnan.edu.cn/")
        self.sid_input = QLineEdit()
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.layout.addRow("教务系统URL:", self.url_input)
        self.layout.addRow("学号:", self.sid_input)
        self.layout.addRow("密码:", self.password_input)
        if account:
            self.url_input.setText(account.url)
            self.sid_input.setText(account.sid)
            self.password_input.setText(account.password)
            self.sid_input.setReadOnly(True)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.layout.addWidget(self.buttons)

    def get_credentials(self):
        if not all([self.url_input.text(), self.sid_input.text(), self.password_input.text()]):
            return None
        return models.UserCredentials(
            url=self.url_input.text().strip(),
            sid=self.sid_input.text().strip(),
            password=self.password_input.text()
        )


class ZFN_GUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.accounts = []
        self.logged_in_clients = {}
        self.priority_grabbers = {}
        self.current_selectable_courses = {}
        self.fetched_data = {}
        self.last_batch_action = None
        self.batch_action_params = {}
        
        # 【修正】: 使用列表管理所有工作线程，防止被意外销毁
        self.active_workers = []

        self.init_ui()
        self.load_initial_config()

    def init_ui(self):
        self.setWindowTitle('LNU正方教务系统助手 (多账户稳定版)')
        self.setGeometry(100, 100, 1100, 800)
        self.setStyleSheet(STYLESHEET)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint |
                            Qt.WindowType.WindowMinimizeButtonHint | Qt.WindowType.WindowMaximizeButtonHint)

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self.create_main_tab()
        self.create_grabber_tab()
        self.toggle_actions(False)
        self.accounts_table.itemSelectionChanged.connect(self.display_selected_account_details)

    def create_main_tab(self):
        self.main_tab = QWidget()
        main_layout = QVBoxLayout(self.main_tab)
        account_group = QWidget()
        account_group.setObjectName("group-box")
        account_layout = QVBoxLayout(account_group)
        account_layout.addWidget(QLabel("账户管理 (点击下方账户可查看详情)"))
        self.accounts_table = QTableWidget()
        self.accounts_table.setColumnCount(3)
        self.accounts_table.setHorizontalHeaderLabels(["学号", "教务系统URL", "登录状态"])
        self.accounts_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.accounts_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.accounts_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        account_layout.addWidget(self.accounts_table)
        account_control_layout = QHBoxLayout()
        self.add_account_button = QPushButton("➕ 添加账户")
        self.remove_account_button = QPushButton("➖ 删除账户")
        self.login_all_button = QPushButton("🚀 批量登录")
        self.add_account_button.clicked.connect(self.add_account)
        self.remove_account_button.clicked.connect(self.remove_account)
        self.login_all_button.clicked.connect(self.batch_login)
        account_control_layout.addWidget(self.add_account_button)
        account_control_layout.addWidget(self.remove_account_button)
        account_control_layout.addStretch()
        account_control_layout.addWidget(self.login_all_button)
        account_layout.addLayout(account_control_layout)
        main_layout.addWidget(account_group)
        actions_and_params_layout = QHBoxLayout()
        actions_group = QWidget()
        actions_group.setObjectName("group-box")
        actions_layout = QGridLayout(actions_group)
        actions_layout.addWidget(QLabel("批量操作"), 0, 0, 1, 2)
        self.info_button = QPushButton('获取个人信息')
        self.grade_button = QPushButton('获取成绩')
        self.schedule_button = QPushButton('获取课表')
        self.exam_schedule_button = QPushButton('获取考试信息')
        self.selected_courses_button = QPushButton('获取已选课程')
        self.academia_button = QPushButton('获取学业生涯')
        self.gpa_button = QPushButton('获取GPA')
        self.grade_pdf_button = QPushButton('导出成绩单PDF')
        self.view_calendar_button = QPushButton('查看考试日历')
        actions_layout.addWidget(self.info_button, 1, 0)
        actions_layout.addWidget(self.grade_button, 1, 1)
        actions_layout.addWidget(self.schedule_button, 2, 0)
        actions_layout.addWidget(self.exam_schedule_button, 2, 1)
        actions_layout.addWidget(self.selected_courses_button, 3, 0)
        actions_layout.addWidget(self.academia_button, 3, 1)
        actions_layout.addWidget(self.gpa_button, 4, 0)
        actions_layout.addWidget(self.grade_pdf_button, 4, 1)
        actions_layout.addWidget(self.view_calendar_button, 5, 0, 1, 2)
        params_group = QWidget()
        params_group.setObjectName("group-box")
        params_layout = QFormLayout(params_group)
        params_layout.addWidget(QLabel("查询参数"))
        self.year_display = QLineEdit(str(time.localtime().tm_year))
        self.term_input = QComboBox()
        self.term_input.addItems(['全年', '第一学期', '第二学期'])
        params_layout.addRow('学年:', self.year_display)
        params_layout.addRow('学期:', self.term_input)
        actions_and_params_layout.addWidget(actions_group, 2)
        actions_and_params_layout.addWidget(params_group, 1)
        main_layout.addLayout(actions_and_params_layout)
        self.info_button.clicked.connect(lambda: self.run_batch_action('get_info'))
        self.grade_button.clicked.connect(self.get_grades_batch)
        self.schedule_button.clicked.connect(self.get_schedule_batch)
        self.exam_schedule_button.clicked.connect(self.get_exam_schedule_batch)
        self.selected_courses_button.clicked.connect(self.get_selected_courses_batch)
        self.academia_button.clicked.connect(lambda: self.run_batch_action('get_academia'))
        self.gpa_button.clicked.connect(lambda: self.run_batch_action('get_gpa'))
        self.grade_pdf_button.clicked.connect(self.get_grade_pdf_batch)
        self.view_calendar_button.clicked.connect(self.show_exam_calendar)
        self.main_result_display = QTextEdit()
        self.main_result_display.setReadOnly(True)
        self.main_result_display.setPlaceholderText("批量操作的日志将显示在此处。\n数据获取后，请点击上方的账户列表查看单个账户的详细结果。")
        main_layout.addWidget(self.main_result_display)
        self.tabs.addTab(self.main_tab, "账户管理 & 批量操作")

    def create_grabber_tab(self):
        self.grabber_tab = QWidget()
        grabber_layout = QVBoxLayout(self.grabber_tab)
        top_group = QWidget()
        top_group.setObjectName("group-box")
        top_container_layout = QHBoxLayout(top_group)
        account_selection_group = QWidget()
        account_selection_layout = QVBoxLayout(account_selection_group)
        account_selection_layout.addWidget(QLabel("选择抢课账户 (可多选):"))
        self.grabber_account_list = QListWidget()
        self.grabber_account_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.grabber_account_list.setToolTip("请先在主页登录账户，这里才会显示可选项\n按住Ctrl可多选，按住Shift可连续选择")
        account_selection_layout.addWidget(self.grabber_account_list)
        top_container_layout.addWidget(account_selection_group, 1)
        params_group = QWidget()
        params_layout = QFormLayout(params_group)
        self.grab_year_display = QLineEdit(str(time.localtime().tm_year))
        self.grab_term_input = QComboBox()
        self.grab_term_input.addItems(['第一学期', '第二学期'])
        self.grab_block_input = QComboBox()
        self.grab_block_input.addItems(['专业选修课', '公共选修课', '跨专业课程'])
        self.grab_target_count_input = QSpinBox()
        self.grab_target_count_input.setMinimum(1)
        self.grab_target_count_input.setValue(1)
        self.grab_target_count_input.setToolTip("设置每个账号需要抢到的课程数量")
        self.fetch_courses_button = QPushButton('获取板块课程')
        params_layout.addRow("学年:", self.grab_year_display)
        params_layout.addRow("学期:", self.grab_term_input)
        params_layout.addRow("选课板块:", self.grab_block_input)
        params_layout.addRow("目标抢课数:", self.grab_target_count_input)
        params_layout.addRow(self.fetch_courses_button)
        top_container_layout.addWidget(params_group, 2)
        grabber_layout.addWidget(top_group)
        courses_group = QWidget()
        courses_group.setObjectName("group-box")
        courses_layout = QVBoxLayout(courses_group)
        courses_layout.addWidget(QLabel("可选课程列表 (选择作为志愿，按显示顺序抢课)"))
        self.courses_table = QTableWidget()
        self.courses_table.setColumnCount(5)
        self.courses_table.setHorizontalHeaderLabels(['课程ID', '课程名称', '教师', '上课时间', '已选/容量'])
        self.courses_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.courses_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.courses_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.courses_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.courses_table.setToolTip("按住Ctrl可多选，按住Shift可连续选择")
        courses_layout.addWidget(self.courses_table)
        grabber_layout.addWidget(courses_group)
        bottom_layout = QHBoxLayout()
        control_group = QWidget()
        control_group.setObjectName("group-box")
        control_layout = QVBoxLayout(control_group)
        self.start_grab_button = QPushButton('🚀 开始志愿抢课')
        self.stop_grab_button = QPushButton('停止所有抢课')
        control_layout.addWidget(self.start_grab_button)
        control_layout.addWidget(self.stop_grab_button)
        log_group = QWidget()
        log_group.setObjectName("group-box")
        log_layout = QVBoxLayout(log_group)
        log_layout.addWidget(QLabel("抢课日志:"))
        self.grab_log_display = QTextEdit()
        self.grab_log_display.setReadOnly(True)
        log_layout.addWidget(self.grab_log_display)
        bottom_layout.addWidget(control_group, 1)
        bottom_layout.addWidget(log_group, 3)
        grabber_layout.addLayout(bottom_layout)
        self.fetch_courses_button.clicked.connect(self.fetch_block_courses)
        self.start_grab_button.clicked.connect(self.start_priority_grabbing)
        self.stop_grab_button.clicked.connect(self.stop_all_grabbing)
        self.tabs.addTab(self.grabber_tab, "抢课助手")

    def _add_worker(self, worker_instance):
        """统一的worker管理方法"""
        self.active_workers.append(worker_instance)
        # 清理已完成的旧 worker，防止列表无限增长
        self.active_workers = [w for w in self.active_workers if not w.isFinished()]

    def closeEvent(self, event):
        self.save_all_configs()
        # 停止所有仍在运行的线程
        self.stop_all_grabbing()
        for worker in self.active_workers:
            if worker.isRunning():
                worker.quit()
                worker.wait(1000)
        event.accept()

    def load_initial_config(self):
        self.accounts = config.load_accounts()
        self.update_accounts_table()

    def save_all_configs(self):
        config.save_accounts(self.accounts)

    def update_accounts_table(self):
        self.accounts_table.setRowCount(0)
        for account in self.accounts:
            row_position = self.accounts_table.rowCount()
            self.accounts_table.insertRow(row_position)
            self.accounts_table.setItem(row_position, 0, QTableWidgetItem(account.sid))
            self.accounts_table.setItem(row_position, 1, QTableWidgetItem(account.url))
            self.accounts_table.setItem(row_position, 2, QTableWidgetItem("未登录"))

    def add_account(self):
        dialog = AccountDialog(self)
        if dialog.exec():
            creds = dialog.get_credentials()
            if creds:
                if any(acc.sid == creds.sid for acc in self.accounts):
                    QMessageBox.warning(self, "错误", "该学号已存在！")
                    return
                self.accounts.append(creds)
                self.update_accounts_table()
                self.save_all_configs()

    def remove_account(self):
        selected_rows = self.accounts_table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, "提示", "请先在列表中选择要删除的账户。")
            return
        row = selected_rows[0].row()
        sid_to_remove = self.accounts_table.item(row, 0).text()
        reply = QMessageBox.question(self, "确认删除", f"确定要删除学号为 {sid_to_remove} 的账户吗？", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.accounts = [acc for acc in self.accounts if acc.sid != sid_to_remove]
            self.update_accounts_table()
            self.save_all_configs()
            if sid_to_remove in self.logged_in_clients: del self.logged_in_clients[sid_to_remove]
            self.update_grabber_account_list()

    def toggle_actions(self, enabled):
        buttons = [self.info_button, self.grade_button, self.schedule_button,
                   self.exam_schedule_button, self.selected_courses_button,
                   self.academia_button, self.gpa_button, self.grade_pdf_button,
                   self.view_calendar_button]
        for button in buttons:
            button.setEnabled(enabled)
        is_any_account_logged_in = bool(self.logged_in_clients)
        self.fetch_courses_button.setEnabled(is_any_account_logged_in)
        self.start_grab_button.setEnabled(False)
        self.stop_grab_button.setEnabled(False)

    def batch_login(self):
        if not self.accounts:
            QMessageBox.information(self, "提示", "请先添加至少一个账户。")
            return
        
        self.logged_in_clients.clear()
        self.fetched_data.clear()
        self.last_batch_action = None
        self.toggle_actions(False)
        self.login_all_button.setEnabled(False)
        self.login_all_button.setText("登录中...")
        self.main_result_display.setText("正在启动批量登录...\n")
        
        timeout = getattr(config, 'load_settings', lambda: 10)() 
        
        login_worker = BatchLoginWorker(self.accounts, timeout)
        login_worker.account_status_update.connect(self.handle_account_login_status)
        login_worker.finished.connect(self.handle_batch_login_finished)
        self._add_worker(login_worker)
        login_worker.start()

    def handle_account_login_status(self, sid, message, client_instance):
        self.main_result_display.append(f"学号 {sid}: {message}")
        for row in range(self.accounts_table.rowCount()):
            if self.accounts_table.item(row, 0).text() == sid:
                self.accounts_table.setItem(row, 2, QTableWidgetItem(message))
                break
        if client_instance:
            self.logged_in_clients[sid] = client_instance

    def handle_batch_login_finished(self):
        self.login_all_button.setEnabled(True)
        self.login_all_button.setText("🚀 批量登录")
        self.main_result_display.append("\n--- 所有账户登录尝试完毕 ---")
        if self.logged_in_clients:
            self.main_result_display.append(f"成功登录 {len(self.logged_in_clients)} 个账户。现在可以执行批量操作了。")
            self.toggle_actions(True)
        else:
            self.main_result_display.append("没有账户成功登录。")
            self.toggle_actions(False)
        self.update_grabber_account_list()

    def update_grabber_account_list(self):
        self.grabber_account_list.clear()
        sorted_sids = sorted(self.logged_in_clients.keys())
        for sid in sorted_sids:
            self.grabber_account_list.addItem(QListWidgetItem(sid))
    
    def run_batch_action(self, action, params=None):
        if not self.logged_in_clients:
            QMessageBox.warning(self, "无登录账户", "请先成功登录至少一个账户！")
            return
        self.last_batch_action = action
        self.fetched_data[action] = {}
        self.batch_action_params = params if params is not None else {}
        self.main_result_display.clear()
        self.main_result_display.setText(f"开始为 {len(self.logged_in_clients)} 个账户批量获取 [{action}] 数据...\n")
        self.toggle_actions(False)
        
        batch_worker = BatchActionWorker(self.logged_in_clients, action, self.batch_action_params)
        batch_worker.progress_update.connect(lambda msg: self.main_result_display.append(msg))
        batch_worker.action_result.connect(self.handle_batch_action_result)
        batch_worker.finished.connect(self.handle_batch_action_finished)
        self._add_worker(batch_worker)
        batch_worker.start()

    def handle_batch_action_result(self, sid, action, result):
        if action not in self.fetched_data: self.fetched_data[action] = {}
        self.fetched_data[action][sid] = result

        if action == 'get_academia_pdf':
            save_dir = self.batch_action_params.get('save_dir')
            if isinstance(result, dict) and result.get('code') == 1000 and isinstance(result.get('data'), bytes):
                pdf_content = result['data']
                if save_dir:
                    try:
                        filename = os.path.join(save_dir, f"{sid}_成绩单_{int(time.time())}.pdf")
                        with open(filename, 'wb') as f:
                            f.write(pdf_content)
                        self.main_result_display.append(f"✅ 学号 [{sid}] 的成绩单PDF已保存到: {filename}")
                    except Exception as e:
                        self.main_result_display.append(f"❌ 学号 [{sid}] 保存PDF失败: {e}")
            else:
                msg = result.get('msg', '未知错误') if isinstance(result, dict) else "未能获取PDF数据"
                self.main_result_display.append(f"❌ 学号 [{sid}] 获取成绩单PDF失败: {msg}")
            return

        if isinstance(result, dict) and result.get('code') == 1000:
            self.main_result_display.append(f"✅ 学号 [{sid}] 获取 [{action}] 数据成功。")
            if action == 'get_gpa':
                gpa_data = result.get('data', '无GPA数据')
                self.main_result_display.append(f"   > GPA 结果: {gpa_data}")
        else:
            msg = result.get('msg', '未知错误') if isinstance(result, dict) else str(result)
            self.main_result_display.append(f"❌ 学号 [{sid}] 获取 [{action}] 数据失败: {msg}")

    def handle_batch_action_finished(self):
        self.main_result_display.append(f"\n--- 批量获取 [{self.last_batch_action}] 操作已全部完成 ---")
        self.main_result_display.append("请点击上方的账户列表，查看具体结果。")
        self.toggle_actions(True)

    def display_selected_account_details(self):
        selected_rows = self.accounts_table.selectionModel().selectedRows()
        if not selected_rows or not self.last_batch_action: return
        sid = self.accounts_table.item(selected_rows[0].row(), 0).text()
        result = self.fetched_data.get(self.last_batch_action, {}).get(sid)
        if result is None:
            self.main_result_display.setText(f"学号 [{sid}] 没有获取到 [{self.last_batch_action}] 的数据。")
            return
        header = f"{'='*20} 学号: {sid} | 操作: {self.last_batch_action} {'='*20}\n"
        self.main_result_display.setText(header + self.format_and_translate_output(result, self.last_batch_action))

    def format_and_translate_output(self, result, action):
        if isinstance(result, bytes):
            return "二进制数据（如PDF）无法在此处预览。\n请查看操作日志中的文件保存路径。"
            
        if not isinstance(result, dict) or 'code' not in result:
            try:
                safe_repr = json.dumps(result, indent=4, ensure_ascii=False)
            except TypeError:
                safe_repr = str(result)
            return f"返回数据格式异常 (非标准字典):\n{safe_repr}"

        if result.get('code') != 1000:
            return f"操作失败，API返回的详细信息如下:\n\n{json.dumps(result, indent=4, ensure_ascii=False)}"

        data = result.get('data')
        if data is None:
            return f"查询成功: {result.get('msg', '')}\n但无具体数据返回。"

        if not isinstance(data, (dict, list)):
            if action == 'get_gpa':
                return f"查询成功: {result.get('msg', '')}\n平均绩点 (GPA): {data}"
            return f"查询成功: {result.get('msg', '')}\n数据: {json.dumps(data, indent=4, ensure_ascii=False)}"

        full_trans = {**TRANSLATIONS.get('common', {}), **TRANSLATIONS.get(action, {})}
        output_lines = [f"查询成功: {result.get('msg', '')}\n"]

        if action == 'get_academia' and isinstance(data, dict) and 'details' in data:
            if 'sid' in data: output_lines.append(f"{full_trans.get('sid', 'sid')}: {data['sid']}")
            if 'statistics' in data and isinstance(data['statistics'], dict):
                output_lines.append("\n" + "=" * 20 + f" {full_trans.get('statistics', '学分统计')} " + "=" * 20)
                for k, v in data['statistics'].items():
                    if isinstance(v, dict):
                        output_lines.append(f"\n[{full_trans.get(k, k)}]:")
                        for sk, sv in v.items(): output_lines.append(f"  - {full_trans.get(sk, sk)}: {sv}")
                    else: output_lines.append(f"{full_trans.get(k, k)}: {v}")
                output_lines.append("=" * 52 + "\n")
            for cat in data.get('details', []):
                output_lines.append(f"\n---[ {cat.get('type', '未知分类')} ]---")
                if 'credits' in cat and isinstance(cat['credits'], dict):
                    credit_info = [f"{full_trans.get(k, k)}: {v}" for k, v in cat['credits'].items() if v is not None]
                    output_lines.append(" | ".join(credit_info))
                output_lines.append("-" * 40)
                if not cat.get('courses'):
                    output_lines.append("  (该分类下无课程信息)")
                    continue
                for course in cat['courses']:
                    course_lines = [f"  {full_trans.get(k, k)}: {v}" for k, v in course.items() if v is not None and str(v).strip() != '']
                    output_lines.append("\n".join(course_lines))
                    output_lines.append("-" * 25)
            return "\n".join(output_lines)

        if isinstance(data, dict) and 'courses' in data and isinstance(data['courses'], list):
            for k, v in data.items():
                if k != 'courses':
                    output_lines.append(f"{full_trans.get(k, k)}: {v}")
            output_lines.append("\n" + "=" * 40 + "\n")
            for i, item in enumerate(data['courses']):
                output_lines.append(f"--- 第 {i + 1} 项 ---")
                for k, v in item.items():
                    if k in ['list_sessions', 'list_weeks']: continue
                    if v is not None and str(v).strip() != '':
                        output_lines.append(f"  {full_trans.get(k, k)}: {v}")
                output_lines.append("-" * 25)
            return "\n".join(output_lines)
        elif isinstance(data, dict):
            for k, v in data.items():
                if v is not None and str(v).strip() != '':
                    output_lines.append(f"{full_trans.get(k, k)}: {v}")
            return "\n".join(output_lines)
        elif isinstance(data, list):
            for i, item in enumerate(data):
                output_lines.append(f"--- 第 {i + 1} 项 ---")
                if isinstance(item, dict):
                    for k, v in item.items():
                        if v is not None and str(v).strip() != '':
                            output_lines.append(f"  {full_trans.get(k, k)}: {v}")
                else:
                    output_lines.append(f"  {item}")
                output_lines.append("-" * 25)
            return "\n".join(output_lines)
        else:
            return json.dumps(result, indent=4, ensure_ascii=False)

    def get_grades_batch(self):
        params = {'year': int(self.year_display.text()), 'term': self.term_input.currentIndex()}
        self.run_batch_action('get_grade', params)
        
    def get_schedule_batch(self):
        term = self.term_input.currentIndex()
        if term == 0: return QMessageBox.warning(self, "提示", "请选择一个具体的学期。")
        params = {'year': int(self.year_display.text()), 'term': term}
        self.run_batch_action('get_schedule', params)

    def get_exam_schedule_batch(self):
        term = self.term_input.currentIndex()
        if term == 0: return QMessageBox.warning(self, "提示", "请选择一个具体的学期。")
        params = {'year': int(self.year_display.text()), 'term': term}
        self.run_batch_action('get_exam_schedule', params)

    def get_selected_courses_batch(self):
        params = {'year': int(self.year_display.text()), 'term': self.term_input.currentIndex()}
        self.run_batch_action('get_selected_courses', params)

    def get_grade_pdf_batch(self):
        folder = QFileDialog.getExistingDirectory(self, "请选择保存PDF的文件夹", os.getcwd())
        if folder:
            self.run_batch_action('get_academia_pdf', {'save_dir': folder})

    def show_exam_calendar(self):
        action = 'get_exam_schedule'
        if action not in self.fetched_data:
            return QMessageBox.warning(self, "提示", "请先批量获取考试信息。")
        exam_data = self.fetched_data.get(action, {})
        sids_with_data = [sid for sid, res in exam_data.items() if isinstance(res, dict) and res.get('data')]
        if not sids_with_data:
            return QMessageBox.information(self, "提示", "未查询到有效的考试信息。")
        sid, ok = QInputDialog.getItem(self, "选择账户", "选择查看考试日历的账户:", sids_with_data, 0, False)
        if ok and sid:
            data = exam_data.get(sid, {}).get('data')
            if data:
                ExamCalendarDialog(data, self).exec()

    def fetch_block_courses(self):
        selected_items = self.grabber_account_list.selectedItems()
        if not selected_items:
            return QMessageBox.warning(self, "提示", "请选择一个用于获取课程列表的账户。")
        
        sid_to_fetch = selected_items[0].text()
        api_client = self.logged_in_clients.get(sid_to_fetch)
        if not api_client:
            return QMessageBox.critical(self, "错误", f"找不到学号 {sid_to_fetch} 的登录实例。")

        params = {'block': self.grab_block_input.currentIndex() + 1}
        self.grab_log_display.setText(f"正在使用学号 {sid_to_fetch} 获取课程列表...")
        self.fetch_courses_button.setEnabled(False)
        
        worker = ApiWorker(api_client, 'get_block_courses', params)
        worker.result_ready.connect(self.display_block_courses)
        worker.finished.connect(lambda: self.fetch_courses_button.setEnabled(True))
        self._add_worker(worker)
        worker.start()

    def display_block_courses(self, result):
        self.courses_table.setRowCount(0)
        self.current_selectable_courses.clear()
        if result.get('code') != 1000:
            self.grab_log_display.append(f"获取课程失败: {result.get('msg', '未知错误')}")
            return self.start_grab_button.setEnabled(False)
        
        data = result.get('data', {})
        courses = data.get('courses', [])
        if not courses:
            self.grab_log_display.append("该板块下没有可选择的课程。")
            return self.start_grab_button.setEnabled(False)
            
        self.grab_log_display.append(f"成功获取 {len(courses)} 门课程，请在下方表格中选择志愿课程。")
        for course in courses:
            # 使用一个唯一的ID作为字典的键，do_id是最佳选择
            course_key = course.get('do_id') or course.get('class_id')
            if not course_key: continue
            
            row_pos = self.courses_table.rowCount()
            self.courses_table.insertRow(row_pos)
            self.courses_table.setItem(row_pos, 0, QTableWidgetItem(course.get('course_id')))
            self.courses_table.setItem(row_pos, 1, QTableWidgetItem(course.get('title')))
            self.courses_table.setItem(row_pos, 2, QTableWidgetItem(course.get('teacher')))
            self.courses_table.setItem(row_pos, 3, QTableWidgetItem(course.get('time')))
            self.courses_table.setItem(row_pos, 4, QTableWidgetItem(f"{course.get('selected_number', 'N/A')}/{course.get('capacity', 'N/A')}"))
            
            self.current_selectable_courses[course_key] = course
        self.start_grab_button.setEnabled(True)

    def start_priority_grabbing(self):
        if not hasattr(self, 'grabber_account_list') or not self.grabber_account_list:
            QMessageBox.critical(self, "程序错误", "抢课账户列表控件未被正确初始化！")
            return
            
        selected_account_items = self.grabber_account_list.selectedItems()
        if not selected_account_items:
            return QMessageBox.warning(self, "提示", "请选择至少一个要用于抢课的账户。")

        selected_sids = [item.text() for item in selected_account_items]
        selected_rows = self.courses_table.selectionModel().selectedRows()
        if not selected_rows:
            return QMessageBox.warning(self, "提示", "请选择至少一门志愿课程。")

        sorted_rows = sorted([index.row() for index in selected_rows])
        
        prioritized_courses = []
        for row in sorted_rows:
            course_id_text = self.courses_table.item(row, 0).text()
            title_text = self.courses_table.item(row, 1).text()
            # 找到匹配的课程数据
            matching_course = next((c for c in self.current_selectable_courses.values() if c.get('course_id') == course_id_text and c.get('title') == title_text), None)
            if matching_course:
                prioritized_courses.append(matching_course)

        if not prioritized_courses:
            return QMessageBox.warning(self, "错误", "无法获取选中课程的数据，请重试。")

        target_count = self.grab_target_count_input.value()
        if len(prioritized_courses) < target_count:
             reply = QMessageBox.question(self, "确认操作", 
                                          f"您选择了 {len(prioritized_courses)} 门备选课程，但目标是抢 {target_count} 门。\n程序将尝试抢所有备选课程。\n是否继续？",
                                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
             if reply == QMessageBox.StandardButton.No: return

        self.start_grab_button.setEnabled(False)
        self.stop_grab_button.setEnabled(True)
        self.grab_log_display.append("\n--- 开始志愿优先抢课任务 ---")
        
        for sid in selected_sids:
            api_client = self.logged_in_clients.get(sid)
            if not api_client:
                self.grab_log_display.append(f"❌ 错误：未找到学号 {sid} 的客户端实例，跳过。")
                continue
            if sid in self.priority_grabbers and self.priority_grabbers[sid].isRunning():
                self.grab_log_display.append(f"学号 [{sid}] 已有抢课任务在运行，跳过。")
                continue
            
            self.grab_log_display.append(f"➡️ 为学号 [{sid}] 分配志愿抢课任务... 目标：{target_count}门")
            
            # 【修正】: 使用新的构造函数，不再传入 year 和 term
            grabber = PriorityBatchGrabber(api_client, sid, prioritized_courses, target_count)
            grabber.status_update.connect(self.update_grab_log)
            grabber.finished.connect(self.on_grab_finished)
            self.priority_grabbers[sid] = grabber
            self._add_worker(grabber) # 也将抢课线程加入统一管理
            grabber.start()

    def stop_all_grabbing(self):
        if not self.priority_grabbers: return
        self.grab_log_display.append("\n--- 正在发送停止所有抢课任务的信号 ---")
        for grabber in self.priority_grabbers.values():
            if grabber.isRunning():
                grabber.stop()
        self.start_grab_button.setEnabled(True)
        self.stop_grab_button.setEnabled(False)

    def update_grab_log(self, sid, message):
        self.grab_log_display.append(f"[{sid}] {message}")
    
    def on_grab_finished(self, sid):
        # 线程结束后，检查是否所有抢课任务都已结束
        all_finished = not any(g.isRunning() for g in self.priority_grabbers.values())
        if all_finished:
            self.start_grab_button.setEnabled(True)
            self.stop_grab_button.setEnabled(False)
            self.grab_log_display.append("--- 所有账户的抢课任务已结束 ---")
            self.priority_grabbers.clear()