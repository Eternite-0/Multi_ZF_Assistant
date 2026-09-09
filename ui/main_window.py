import json
import os
import time
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QLineEdit, QPushButton, QTextEdit, QFormLayout,
                             QComboBox, QTabWidget, QTableWidget, QTableWidgetItem,
                             QGridLayout, QFileDialog, QHeaderView,
                             QAbstractItemView, QMessageBox, QDialog, QDialogButtonBox,
                             QInputDialog, QListWidget, QListWidgetItem, QSpinBox,
                             QCheckBox, QDateTimeEdit, QFrame, QSplitter, QCompleter)
from PyQt6.QtCore import Qt, QTimer, QDateTime

# 确保这些导入路径是正确的
from api.zfn_api import Client
from core import config, models
from core.config import load_wishlists, save_wishlists
from ui.dialogs import CaptchaDialog, ExamCalendarDialog
from ui.assets import STYLESHEET, TRANSLATIONS
from utils.workers import ApiWorker, PriorityBatchGrabber, BatchLoginWorker, BatchActionWorker, ManualCourseFetchWorker
from utils.course_matching import (
    course_identity,
    legacy_course_identity,
    manual_course_matches,
    remap_wishlist_courses,
)
import random


class AccountDialog(QDialog):
    """一个简单的对话框用于添加/编辑账户。"""
    def __init__(self, parent=None, account=None):
        super().__init__(parent)
        self.setWindowTitle("添加/编辑账户")
        self.layout = QFormLayout(self)
        # 校外环境经 WebVPN 转发到教务系统；保持末尾斜杠以供 urljoin 拼接接口路径。
        self.url_input = QLineEdit(
            "https://csvpn.lingnan.edu.cn/http/"
            "77726476706e69737468656265737421fae00f902e3e6f5e7f06c7a99c406d36a1/"
        )
        self.sid_input = QLineEdit()
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.login_mode_input = QComboBox()
        self.login_mode_input.addItem("校内直连（教务系统账号）", "campus")
        self.login_mode_input.addItem("校外 WebVPN（统一认证账号）", "webvpn")
        self.webvpn_sid_input = QLineEdit()
        self.webvpn_password_input = QLineEdit()
        self.webvpn_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.layout.addRow("教务系统URL:", self.url_input)
        self.layout.addRow("登录方式:", self.login_mode_input)
        self.sid_label = QLabel("教务账号:")
        self.password_label = QLabel("教务密码:")
        self.layout.addRow(self.sid_label, self.sid_input)
        self.layout.addRow(self.password_label, self.password_input)
        self.webvpn_sid_label = QLabel("WebVPN 账号:")
        self.webvpn_password_label = QLabel("WebVPN 密码:")
        self.layout.addRow(self.webvpn_sid_label, self.webvpn_sid_input)
        self.layout.addRow(self.webvpn_password_label, self.webvpn_password_input)
        self.login_mode_input.currentIndexChanged.connect(self._update_login_mode_labels)
        if account:
            self.url_input.setText(account.url)
            self.sid_input.setText(account.sid)
            self.password_input.setText(account.password)
            mode = "webvpn" if account.use_webvpn else getattr(account, "login_mode", "campus")
            self.login_mode_input.setCurrentIndex(1 if mode == "webvpn" else 0)
            self.webvpn_sid_input.setText(account.webvpn_sid)
            self.webvpn_password_input.setText(account.webvpn_password)
        self._update_login_mode_labels()
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.layout.addWidget(self.buttons)

    def get_credentials(self):
        if not all([self.url_input.text(), self.sid_input.text(), self.password_input.text()]):
            return None
        login_mode = self.login_mode_input.currentData()
        if login_mode == "webvpn" and not all([self.webvpn_sid_input.text(), self.webvpn_password_input.text()]):
            return None
        return models.UserCredentials(
            url=self.url_input.text().strip(),
            sid=self.sid_input.text().strip(),
            password=self.password_input.text(),
            use_webvpn=login_mode == "webvpn",
            webvpn_sid=self.webvpn_sid_input.text().strip() if login_mode == "webvpn" else "",
            webvpn_password=self.webvpn_password_input.text() if login_mode == "webvpn" else "",
            login_mode=login_mode,
        )

    def _update_login_mode_labels(self):
        remote = self.login_mode_input.currentData() == "webvpn"
        self.sid_label.setText("教务账号:")
        self.password_label.setText("教务密码:")
        self.webvpn_sid_label.setVisible(remote)
        self.webvpn_password_label.setVisible(remote)
        self.webvpn_sid_input.setVisible(remote)
        self.webvpn_password_input.setVisible(remote)


class ZFN_GUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.accounts = []
        self.logged_in_clients = {}
        self.priority_grabbers = {}
        self.current_selectable_courses = {}
        self._table_courses = []
        self.current_wishlist_courses = [] # 新增：用于存储当前显示的志愿列表课程对象
        self.current_wishlist_sid = None
        self.fetched_data = {}
        self.last_batch_action = None
        self.batch_action_params = {}
        self.wishlists = {}
        self.manual_wishlist_specs = {}
        self.manual_fetch_results = {}
        self.manual_waiting = False
        self.manual_timer = QTimer()
        self.manual_edit_row = -1

        self.active_workers = []
        
        # 定时抢课相关变量
        self.scheduled_enabled = False
        self.scheduled_time = None
        self.timer_for_current_time = QTimer()
        self.timer_for_scheduled_grab = QTimer()
        self.waiting_for_scheduled_grab = False

        self.init_ui()
        self.load_initial_config()
        self.load_all_wishlists()

    def init_ui(self):
        self.setWindowTitle('LNU正方教务系统助手 (多账户稳定版)')
        self.setGeometry(100, 100, 1300, 850) # 再次加宽以容纳按钮
        self.setStyleSheet(STYLESHEET)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint |
                            Qt.WindowType.WindowMinimizeButtonHint | Qt.WindowType.WindowMaximizeButtonHint)

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self.create_main_tab()
        self.create_grabber_tab()
        self.create_grabber2_tab()
        self.toggle_actions(False)
        self.accounts_table.itemSelectionChanged.connect(self.display_selected_account_details)

    def create_main_tab(self):
        self.main_tab = QWidget()
        main_layout = QVBoxLayout(self.main_tab)
        account_group = QWidget()
        account_group.setObjectName("group-box")
        account_layout = QVBoxLayout(account_group)
        account_layout.addWidget(QLabel("账户管理 (点击下方账户可查看详情)"))
        
        # 首页账户搜索框
        main_search_layout = QHBoxLayout()
        main_search_layout.addWidget(QLabel("🔍 搜索账户:"))
        self.main_account_search_input = QLineEdit()
        self.main_account_search_input.setPlaceholderText("在此检索学号或教务URL...")
        self.main_account_search_input.textChanged.connect(self.filter_main_accounts_table)
        main_search_layout.addWidget(self.main_account_search_input)
        account_layout.addLayout(main_search_layout)

        self.accounts_table = QTableWidget()
        self.accounts_table.setColumnCount(3)
        self.accounts_table.setHorizontalHeaderLabels(["学号", "教务系统URL", "登录状态"])
        self.accounts_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.accounts_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.accounts_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        account_layout.addWidget(self.accounts_table)
        account_control_layout = QHBoxLayout()
        self.add_account_button = QPushButton("➕ 添加账户")
        self.edit_account_button = QPushButton("✏️ 编辑账户")
        self.remove_account_button = QPushButton("➖ 删除账户")
        self.login_all_button = QPushButton("🚀 批量登录")
        self.force_login_all_button = QPushButton("🔄 强制重登全部")
        self.force_login_all_button.setToolTip("忽略当前登录状态，清理旧会话并重新登录所有账户")
        self.add_account_button.clicked.connect(self.add_account)
        self.edit_account_button.clicked.connect(self.edit_account)
        self.remove_account_button.clicked.connect(self.remove_account)
        self.login_all_button.clicked.connect(self.batch_login)
        self.force_login_all_button.clicked.connect(self.force_batch_login)
        account_control_layout.addWidget(self.add_account_button)
        account_control_layout.addWidget(self.edit_account_button)
        account_control_layout.addWidget(self.remove_account_button)
        account_control_layout.addStretch()
        account_control_layout.addWidget(self.login_all_button)
        account_control_layout.addWidget(self.force_login_all_button)
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
        
        # 账户搜索框
        account_search_layout = QHBoxLayout()
        account_search_layout.addWidget(QLabel("🔍:"))
        self.account_search_input = QLineEdit()
        self.account_search_input.setPlaceholderText("快速检索账号...")
        self.account_search_input.textChanged.connect(self.filter_accounts_list)
        account_search_layout.addWidget(self.account_search_input)
        account_selection_layout.addLayout(account_search_layout)

        self.grabber_account_list = QListWidget()
        self.grabber_account_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.grabber_account_list.setToolTip("请先在主页登录账户，这里才会显示可选项\n按住Ctrl可多选，按住Shift可连续选择")
        self.grabber_account_list.itemSelectionChanged.connect(self.load_wishlist_to_ui)
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
        self.manage_cache_button = QPushButton('📂 管理和加载缓存') # 新增：管理缓存按钮
        
        params_layout.addRow("学年:", self.grab_year_display)
        params_layout.addRow("学期:", self.grab_term_input)
        params_layout.addRow("选课板块:", self.grab_block_input)
        params_layout.addRow("目标抢课数:", self.grab_target_count_input)
        params_layout.addRow(self.fetch_courses_button)
        params_layout.addRow(self.manage_cache_button) # 新增：添加管理缓存按钮
        top_container_layout.addWidget(params_group, 2)
        grabber_layout.addWidget(top_group, 0)
        
        middle_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        courses_group = QWidget()
        courses_group.setObjectName("group-box")
        courses_layout = QVBoxLayout(courses_group)
        
        # 搜索栏
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("🔍 搜索:"))
        self.course_search_input = QLineEdit()
        self.course_search_input.setPlaceholderText("搜索课程名称、教师或上课时间...")
        self.course_search_input.textChanged.connect(self.filter_courses_table)
        search_layout.addWidget(self.course_search_input)
        courses_layout.addLayout(search_layout)

        courses_layout.addWidget(QLabel("可选课程列表 (勾选作为志愿)"))
        self.courses_table = QTableWidget()
        self.courses_table.setColumnCount(5)
        self.courses_table.setHorizontalHeaderLabels(['课程ID', '课程名称', '教师', '上课时间', '已选/容量'])
        self.courses_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.courses_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.courses_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.courses_table.setToolTip("按住Ctrl可多选，按住Shift可连续选择")
        self.courses_table.itemSelectionChanged.connect(self.update_wishlist_from_table_selection)
        courses_layout.addWidget(self.courses_table)
        middle_splitter.addWidget(courses_group)

        wishlist_container = QWidget()
        wishlist_container_layout = QHBoxLayout(wishlist_container)
        wishlist_container_layout.setContentsMargins(0, 0, 0, 0)
        wishlist_group = QWidget()
        wishlist_group.setObjectName("group-box")
        wishlist_layout = QVBoxLayout(wishlist_group)
        wishlist_layout.addWidget(QLabel("当前志愿列表 (可拖拽排序)"))
        self.wishlist_display = QListWidget()
        self.wishlist_display.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.wishlist_display.setToolTip("这里显示您已选择的课程志愿，可直接拖拽调整顺序。")
        self.wishlist_display.model().rowsMoved.connect(self.wishlist_order_changed)
        wishlist_layout.addWidget(self.wishlist_display)
        wishlist_container_layout.addWidget(wishlist_group)
        
        wishlist_controls = QVBoxLayout()
        self.wishlist_up_button = QPushButton("🔼 上移")
        self.wishlist_down_button = QPushButton("🔽 下移")
        self.wishlist_up_button.clicked.connect(self.move_wishlist_item_up)
        self.wishlist_down_button.clicked.connect(self.move_wishlist_item_down)
        wishlist_controls.addStretch()
        wishlist_controls.addWidget(self.wishlist_up_button)
        wishlist_controls.addWidget(self.wishlist_down_button)
        wishlist_controls.addStretch()
        wishlist_container_layout.addLayout(wishlist_controls)
        middle_splitter.addWidget(wishlist_container)
        
        middle_splitter.setStretchFactor(0, 3)
        middle_splitter.setStretchFactor(1, 2)
        grabber_layout.addWidget(middle_splitter, 3)

        bottom_layout = QHBoxLayout()
        control_group = QWidget()
        control_group.setObjectName("group-box")
        control_layout = QVBoxLayout(control_group)
        
        # 定时抢课设置区域
        timing_frame = QFrame()
        timing_frame.setFrameStyle(QFrame.Shape.Box)
        timing_layout = QVBoxLayout(timing_frame)
        timing_layout.addWidget(QLabel("⏰ 定时抢课设置"))
        
        # 启用定时抢课开关
        self.scheduled_checkbox = QCheckBox("启用定时抢课")
        self.scheduled_checkbox.setToolTip("启用后，点击开始抢课将等待到设定时间才开始")
        timing_layout.addWidget(self.scheduled_checkbox)
        
        # 时间选择器
        time_layout = QHBoxLayout()
        time_layout.addWidget(QLabel("开始时间:"))
        self.scheduled_datetime = QDateTimeEdit()
        self.scheduled_datetime.setDateTime(QDateTime.currentDateTime().addSecs(3600))  # 默认一小时后
        self.scheduled_datetime.setDisplayFormat("yyyy-MM-dd hh:mm:ss")
        self.scheduled_datetime.setCalendarPopup(True)
        self.scheduled_datetime.setMinimumDateTime(QDateTime.currentDateTime())
        time_layout.addWidget(self.scheduled_datetime)
        timing_layout.addLayout(time_layout)
        
        # 当前时间显示
        current_time_layout = QHBoxLayout()
        current_time_layout.addWidget(QLabel("当前时间:"))
        self.current_time_label = QLabel()
        current_time_layout.addWidget(self.current_time_label)
        timing_layout.addLayout(current_time_layout)
        
        control_layout.addWidget(timing_frame)
        
        # 原有的控制按钮
        self.save_wishlist_button = QPushButton('💾 保存当前志愿')
        self.load_wishlist_button = QPushButton('📂 加载已存志愿')
        self.start_grab_button = QPushButton('🚀 开始志愿抢课')
        self.stop_grab_button = QPushButton('停止所有抢课')
        control_layout.addWidget(self.save_wishlist_button)
        control_layout.addWidget(self.load_wishlist_button)
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
        grabber_layout.addLayout(bottom_layout, 2)
        
        self.fetch_courses_button.clicked.connect(self.fetch_block_courses)
        self.manage_cache_button.clicked.connect(self.show_cache_manager) # 新增：连接管理缓存按钮
        self.start_grab_button.clicked.connect(self.start_priority_grabbing)
        self.stop_grab_button.clicked.connect(self.stop_all_grabbing)
        self.save_wishlist_button.clicked.connect(self.save_wishlist_for_selected)
        self.load_wishlist_button.clicked.connect(self.load_wishlist_to_ui)
        
        # 定时抢课相关连接
        self.scheduled_checkbox.toggled.connect(self.on_scheduled_checkbox_toggled)
        self.timer_for_current_time.timeout.connect(self.update_current_time)
        self.timer_for_scheduled_grab.timeout.connect(self.check_scheduled_time)
        
        # 启动当前时间显示定时器
        self.timer_for_current_time.start(1000)  # 每秒更新一次当前时间
        self.update_current_time()  # 立即更新一次
        
        self.tabs.addTab(self.grabber_tab, "抢课助手")

    def create_grabber2_tab(self):
        """未开放选课时使用：先保存课程名称/教师/星期节次，到点再匹配。"""
        self.grabber2_tab = QWidget()
        layout = QVBoxLayout(self.grabber2_tab)
        title = QLabel("抢课助手2  ·  未开放选课预设")
        title.setStyleSheet("font-size: 18px; font-weight: bold; padding: 6px 0;")
        layout.addWidget(title)
        hint = QLabel("先填写志愿信息并保存，系统会在同一个设定时间一次性拉取课程、匹配教学班并开始持续抢课。")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        top = QHBoxLayout()
        self.grabber2_account_list = QListWidget()
        self.grabber2_account_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.grabber2_account_list.itemSelectionChanged.connect(self.load_manual_specs_to_ui)
        top.addWidget(self.grabber2_account_list, 1)
        form = QFormLayout()
        self.manual_title_input = QComboBox()
        self.manual_title_input.setEditable(True)
        self.manual_title_input.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.manual_title_input.lineEdit().setPlaceholderText("输入课程名称可检索，也可手动修改")
        self.manual_title_input.setCompleter(QCompleter())
        self.manual_title_input.completer().setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.manual_title_input.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        self.manual_course_code_input = QComboBox()
        self.manual_course_code_input.setEditable(True)
        self.manual_course_code_input.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.manual_course_code_input.lineEdit().setPlaceholderText("导入课表后可检索课程代码，例如：77103130")
        self.manual_course_code_input.setCompleter(QCompleter())
        self.manual_course_code_input.completer().setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.manual_course_code_input.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        self.manual_course_code_input.setToolTip(
            "课程代码只用于确认同一门课程；同一课程的不同上课时间仍会继续按星期、节次和周次严格匹配。"
        )
        self.manual_teacher_input = QComboBox()
        self.manual_teacher_input.setEditable(True)
        self.manual_weekday_input = QComboBox()
        for value, label in [("1", "星期一"), ("2", "星期二"), ("3", "星期三"), ("4", "星期四"), ("5", "星期五"), ("6", "星期六"), ("7", "星期日")]:
            self.manual_weekday_input.addItem(label, value)
        self.manual_section_input = QComboBox()
        self.manual_section_input.setEditable(True)
        self.manual_section_input.lineEdit().setPlaceholderText("例如：5-6")
        self.manual_weeks_input = QComboBox()
        self.manual_weeks_input.setEditable(True)
        self.manual_weeks_input.lineEdit().setPlaceholderText("例如：1-16周")
        self.manual_schedule_rows = []
        self._manual_schedule_syncing = False
        self.manual_schedule_status = QLabel("未导入课表")
        self.manual_course_code_input.currentTextChanged.connect(self._on_manual_course_code_changed)
        self.manual_title_input.currentTextChanged.connect(self._on_manual_title_changed)
        self.manual_teacher_input.currentTextChanged.connect(self._on_manual_teacher_changed)
        self.manual_weekday_input.currentIndexChanged.connect(self._on_manual_weekday_changed)
        self.manual_block_input = QComboBox()
        self.manual_block_input.addItems(["专业选修课", "公共选修课", "跨专业课程"])
        self.manual_target_input = QSpinBox(); self.manual_target_input.setMinimum(1); self.manual_target_input.setValue(1)
        self.manual_datetime = QDateTimeEdit(QDateTime.currentDateTime().addSecs(3600))
        self.manual_datetime.setDisplayFormat("yyyy-MM-dd hh:mm:ss"); self.manual_datetime.setCalendarPopup(True)
        self.manual_schedule_checkbox = QCheckBox("启用统一定时（默认立即开始）")
        self.manual_schedule_checkbox.setChecked(False)
        self.manual_schedule_checkbox.toggled.connect(self.manual_schedule_toggled)
        self.manual_schedule_toggled(False)
        import_schedule_button = QPushButton("📥 导入Excel课表")
        import_schedule_button.clicked.connect(self.import_manual_schedule)
        clear_schedule_button = QPushButton("清空课表")
        clear_schedule_button.clicked.connect(self.clear_manual_schedule)
        schedule_buttons = QHBoxLayout()
        schedule_buttons.addWidget(import_schedule_button)
        schedule_buttons.addWidget(clear_schedule_button)
        schedule_buttons.addWidget(self.manual_schedule_status)
        schedule_buttons.addStretch()
        form.addRow("课表数据:", schedule_buttons)
        form.addRow("课程代码:", self.manual_course_code_input)
        form.addRow("课程名称:", self.manual_title_input)
        form.addRow("教师名称:", self.manual_teacher_input)
        form.addRow("星期几:", self.manual_weekday_input)
        form.addRow("第几节:", self.manual_section_input)
        form.addRow("上课周次:", self.manual_weeks_input)
        form.addRow("选课板块:", self.manual_block_input)
        form.addRow("目标抢课门数:", self.manual_target_input)
        form.addRow("抢课模式:", self.manual_schedule_checkbox)
        form.addRow("统一开始时间:", self.manual_datetime)
        self.manual_wait_label = QLabel("状态：尚未启动")
        self.manual_wait_label.setStyleSheet("color: #555; padding: 4px;")
        form.addRow(self.manual_wait_label)
        top.addLayout(form, 3)
        layout.addLayout(top)

        self.manual_table = QTableWidget(); self.manual_table.setColumnCount(6)
        self.manual_table.setHorizontalHeaderLabels(["课程代码", "课程名称", "教师", "星期", "节次", "上课周次"])
        self.manual_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.manual_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.manual_table.setToolTip("选中一行后点击“编辑选中”，修改完成后点击“完成编辑”；双击也可进入编辑。")
        self.manual_table.cellDoubleClicked.connect(lambda row, _column: self.edit_manual_spec_for_row(row))
        self.manual_table.setToolTip("表格从上到下就是抢课优先级；越靠上优先级越高。")
        layout.addWidget(self.manual_table, 3)
        controls = QHBoxLayout()
        add_btn = QPushButton("➕ 添加志愿"); edit_btn = QPushButton("✏️ 编辑选中"); remove_btn = QPushButton("➖ 删除选中")
        self.manual_add_button = add_btn
        save_btn = QPushButton("💾 保存预设"); start_btn = QPushButton("🚀 按统一时间启动")
        self.manual_start_button = start_btn
        self.manual_stop_button = QPushButton("⏹ 停止")
        self.manual_stop_button.setEnabled(False)
        controls.addWidget(add_btn); controls.addWidget(edit_btn); controls.addWidget(remove_btn); controls.addWidget(save_btn)
        controls.addStretch(); controls.addWidget(start_btn); controls.addWidget(self.manual_stop_button)
        layout.addLayout(controls)
        self.manual_log = QTextEdit(); self.manual_log.setReadOnly(True); layout.addWidget(self.manual_log, 2)
        add_btn.clicked.connect(self.add_manual_spec)
        edit_btn.clicked.connect(self.edit_manual_spec)
        remove_btn.clicked.connect(self.remove_manual_spec)
        save_btn.clicked.connect(self.save_manual_specs)
        start_btn.clicked.connect(self.start_manual_grab)
        self.manual_stop_button.clicked.connect(self.stop_manual_grab)
        self.manual_timer.timeout.connect(self.check_manual_time)
        self.tabs.addTab(self.grabber2_tab, "抢课助手2")

    def _refresh_grabber2_accounts(self):
        selected = {i.text() for i in self.grabber2_account_list.selectedItems()}
        self.grabber2_account_list.clear()
        for sid in sorted(self.logged_in_clients):
            self.grabber2_account_list.addItem(QListWidgetItem(sid))
        for i in range(self.grabber2_account_list.count()):
            if self.grabber2_account_list.item(i).text() in selected:
                self.grabber2_account_list.item(i).setSelected(True)

    def import_manual_schedule(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "导入课表 Excel",
            "",
            "Excel 文件 (*.xlsx *.xlsm);;所有文件 (*.*)",
        )
        if not path:
            return
        try:
            from utils.course_schedule import load_schedule_workbook

            rows = load_schedule_workbook(path)
        except Exception as exc:
            return QMessageBox.critical(self, "导入失败", f"读取课表失败：{exc}")
        if not rows:
            return QMessageBox.warning(self, "导入结果", "没有识别到包含“课程代码”和“课程名称”的数据行。")
        self.manual_schedule_rows = rows
        codes = list(dict.fromkeys(row.get("course_code", "") for row in rows if row.get("course_code")))
        titles = list(dict.fromkeys(row.get("title", "") for row in rows if row.get("title")))
        self.manual_course_code_input.blockSignals(True)
        self.manual_course_code_input.clear()
        self.manual_course_code_input.addItems(codes)
        self.manual_course_code_input.setCurrentIndex(-1)
        self.manual_course_code_input.lineEdit().clear()
        self.manual_course_code_input.completer().setModel(self.manual_course_code_input.model())
        self.manual_course_code_input.blockSignals(False)
        self.manual_title_input.blockSignals(True)
        self.manual_title_input.clear()
        self.manual_title_input.addItems(titles)
        self.manual_title_input.setCurrentIndex(-1)
        self.manual_title_input.lineEdit().clear()
        self.manual_title_input.completer().setModel(self.manual_title_input.model())
        self.manual_title_input.blockSignals(False)
        self.manual_schedule_status.setText(f"已导入 {len(rows)} 条教学班 / {len(codes)} 门课程")
        self.manual_log.append(f"已导入课表：{len(rows)} 条教学班，{len(codes)} 门课程。")
        self._set_editable_combo_items(self.manual_teacher_input, [])
        self._set_manual_weekday_choices([str(i) for i in range(1, 8)])
        self._set_editable_combo_items(self.manual_section_input, [])
        self._set_editable_combo_items(self.manual_weeks_input, [])

    def clear_manual_schedule(self):
        self.manual_schedule_rows = []
        self.manual_course_code_input.blockSignals(True)
        self.manual_course_code_input.clear()
        self.manual_course_code_input.blockSignals(False)
        self.manual_title_input.blockSignals(True)
        self.manual_title_input.clear()
        self.manual_title_input.blockSignals(False)
        self.manual_schedule_status.setText("未导入课表")
        self._set_manual_weekday_choices([str(i) for i in range(1, 8)], "1")
        self._on_manual_course_code_changed("")
        self.manual_log.append("已清空导入课表。")

    @staticmethod
    def _set_editable_combo_items(combo, values, selected=""):
        selected = str(selected or "").strip()
        combo.blockSignals(True)
        combo.clear()
        unique = list(dict.fromkeys(str(value or "").strip() for value in values if str(value or "").strip()))
        combo.addItems(unique)
        combo.setCurrentText(selected if selected else (unique[0] if len(unique) == 1 else ""))
        combo.blockSignals(False)

    def _manual_weekday_value(self):
        data = self.manual_weekday_input.currentData()
        return str(data if data is not None else self.manual_weekday_input.currentText()).strip()

    def _set_manual_weekday(self, value):
        text = str(value or "").strip()
        if text.startswith("星期"):
            text = {"星期一": "1", "星期二": "2", "星期三": "3", "星期四": "4", "星期五": "5", "星期六": "6", "星期日": "7"}.get(text, text)
        index = self.manual_weekday_input.findData(text)
        if index >= 0:
            self.manual_weekday_input.setCurrentIndex(index)

    def _set_manual_weekday_choices(self, values, selected=""):
        selected = str(selected or "").strip()
        unique = list(dict.fromkeys(str(value or "").strip() for value in values if str(value or "").strip()))
        self.manual_weekday_input.blockSignals(True)
        self.manual_weekday_input.clear()
        if len(unique) != 1:
            self.manual_weekday_input.addItem("请选择星期", "")
        for value in unique:
            label = {"1": "星期一", "2": "星期二", "3": "星期三", "4": "星期四", "5": "星期五", "6": "星期六", "7": "星期日"}.get(value, value)
            self.manual_weekday_input.addItem(label, value)
        if selected in unique:
            self.manual_weekday_input.setCurrentIndex(unique.index(selected) + (0 if len(unique) == 1 else 1))
        elif len(unique) == 1:
            self.manual_weekday_input.setCurrentIndex(0)
        else:
            self.manual_weekday_input.setCurrentIndex(0)
        self.manual_weekday_input.blockSignals(False)

    def _on_manual_course_code_changed(self, code):
        code = str(code or "").strip()
        rows = [row for row in self.manual_schedule_rows if str(row.get("course_code", "")).strip() == code]
        if not rows:
            return
        titles = list(dict.fromkeys(row.get("title", "") for row in rows if row.get("title")))
        if titles:
            # 课程名称下拉框必须保留导入课表的全部课程，不能因为选中一门课
            # 就把其它课程从候选列表中清掉；这里只同步当前显示文本。
            self.manual_title_input.blockSignals(True)
            self.manual_title_input.setCurrentText(titles[0])
            self.manual_title_input.blockSignals(False)
        self._set_editable_combo_items(self.manual_teacher_input, [row.get("teacher", "") for row in rows])
        self._set_manual_weekday_choices([row.get("weekday", "") for row in rows])
        self._set_editable_combo_items(self.manual_section_input, [row.get("section", "") for row in rows])
        self._set_editable_combo_items(self.manual_weeks_input, [row.get("weeks", "") for row in rows])

    def _on_manual_title_changed(self, title):
        """按课程名称反查课程代码；名称相同的课程保留当前代码，否则选择首个代码。"""
        if self._manual_schedule_syncing:
            return
        title = str(title or "").strip()
        if not title:
            return
        rows = [row for row in self.manual_schedule_rows if str(row.get("title", "")).strip() == title]
        if not rows:
            return
        codes = list(dict.fromkeys(row.get("course_code", "") for row in rows if row.get("course_code")))
        if not codes:
            return
        current_code = self.manual_course_code_input.currentText().strip()
        code = current_code if current_code in codes else codes[0]
        self._manual_schedule_syncing = True
        try:
            self.manual_course_code_input.blockSignals(True)
            self.manual_course_code_input.setCurrentText(code)
            self.manual_course_code_input.blockSignals(False)
        finally:
            self._manual_schedule_syncing = False
        self._on_manual_course_code_changed(code)

    def _on_manual_teacher_changed(self, _value):
        self._refresh_manual_dependent_choices()

    def _on_manual_weekday_changed(self, _index):
        self._refresh_manual_dependent_choices()

    def _refresh_manual_dependent_choices(self):
        code = self.manual_course_code_input.currentText().strip()
        teacher = self.manual_teacher_input.currentText().strip()
        rows = [row for row in self.manual_schedule_rows if str(row.get("course_code", "")).strip() == code]
        if teacher:
            filtered = [row for row in rows if str(row.get("teacher", "")).strip() == teacher]
            if filtered:
                rows = filtered
        weekday = self._manual_weekday_value()
        if weekday:
            filtered = [row for row in rows if str(row.get("weekday", "")).strip() == weekday]
            if filtered:
                rows = filtered
        self._set_editable_combo_items(self.manual_section_input, [row.get("section", "") for row in rows], self.manual_section_input.currentText())
        self._set_editable_combo_items(self.manual_weeks_input, [row.get("weeks", "") for row in rows], self.manual_weeks_input.currentText())

    def add_manual_spec(self):
        values = [self.manual_course_code_input.currentText().strip(), self.manual_title_input.currentText().strip(), self.manual_teacher_input.currentText().strip(), self._manual_weekday_value(), self.manual_section_input.currentText().strip(), self.manual_weeks_input.currentText().strip()]
        if not all(values[1:]):
            return QMessageBox.warning(self, "提示", "请填写课程名称、教师名称、星期、节次和上课周次；课程代码可选。")
        editing = self.manual_edit_row >= 0
        row = self.manual_edit_row if editing else self.manual_table.rowCount()
        if not editing:
            self.manual_table.insertRow(row)
        for col, value in enumerate(values): self.manual_table.setItem(row, col, QTableWidgetItem(value))
        self.manual_edit_row = -1
        self.manual_add_button.setText("➕ 添加志愿")
        self.manual_course_code_input.setCurrentText(""); self.manual_title_input.setCurrentText(""); self.manual_teacher_input.setCurrentText(""); self.manual_section_input.setCurrentText(""); self.manual_weeks_input.setCurrentText("")
        # “完成编辑”不能只改界面，否则账户列表刷新时会被旧预设覆盖。
        # 添加和编辑统一立即同步到当前选中账户，保存按钮仍可手动重复保存。
        if self._sync_manual_specs_to_selected_accounts(allow_empty=True):
            self.manual_log.append("已完成编辑，预设已自动同步保存。" if editing else "已添加志愿，预设已自动同步保存。")

    def edit_manual_spec(self):
        rows = self.manual_table.selectionModel().selectedRows()
        if len(rows) != 1:
            return QMessageBox.information(self, "提示", "请选择一条志愿后再编辑。")
        self.edit_manual_spec_for_row(rows[0].row())

    def edit_manual_spec_for_row(self, row):
        if row < 0 or row >= self.manual_table.rowCount():
            return
        self.manual_edit_row = row
        self.manual_course_code_input.setCurrentText(self.manual_table.item(row, 0).text())
        self.manual_title_input.setCurrentText(self.manual_table.item(row, 1).text())
        self.manual_teacher_input.setCurrentText(self.manual_table.item(row, 2).text())
        self._set_manual_weekday(self.manual_table.item(row, 3).text())
        self.manual_section_input.setCurrentText(self.manual_table.item(row, 4).text())
        self.manual_weeks_input.setCurrentText(self.manual_table.item(row, 5).text())
        self.manual_add_button.setText("✅ 完成编辑")
        self.manual_title_input.setFocus()

    def load_manual_specs_to_ui(self):
        selected = self.grabber2_account_list.selectedItems()
        if not selected:
            return
        saved = self.manual_wishlist_specs.get(selected[0].text(), {})
        specs = saved.get("courses", []) if isinstance(saved, dict) else []
        self.manual_table.setRowCount(0)
        for spec in specs:
            row = self.manual_table.rowCount(); self.manual_table.insertRow(row)
            self.manual_table.setItem(row, 0, QTableWidgetItem(spec.get("course_code", spec.get("course_id", ""))))
            self.manual_table.setItem(row, 1, QTableWidgetItem(spec.get("title", "")))
            self.manual_table.setItem(row, 2, QTableWidgetItem(spec.get("teacher", "")))
            self.manual_table.setItem(row, 3, QTableWidgetItem(spec.get("weekday", "")))
            self.manual_table.setItem(row, 4, QTableWidgetItem(spec.get("section", "")))
            self.manual_table.setItem(row, 5, QTableWidgetItem(spec.get("weeks", "")))
        if isinstance(saved, dict):
            self.manual_target_input.setValue(int(saved.get("target_count", 1)))
            self.manual_schedule_checkbox.setChecked(bool(saved.get("scheduled", False)))
            block = int(saved.get("block", 1)) - 1
            if 0 <= block < self.manual_block_input.count():
                self.manual_block_input.setCurrentIndex(block)

    def remove_manual_spec(self):
        rows = sorted({i.row() for i in self.manual_table.selectionModel().selectedRows()}, reverse=True)
        for row in rows: self.manual_table.removeRow(row)
        if rows and self._sync_manual_specs_to_selected_accounts(allow_empty=True):
            self.manual_log.append(f"已删除 {len(rows)} 条志愿，预设已自动同步保存。")

    def _manual_specs_from_table(self):
        return [{"course_code": self.manual_table.item(r, 0).text().strip(), "title": self.manual_table.item(r, 1).text().strip(), "teacher": self.manual_table.item(r, 2).text().strip(), "weekday": self.manual_table.item(r, 3).text().strip(), "section": self.manual_table.item(r, 4).text().strip(), "weeks": self.manual_table.item(r, 5).text().strip()}
                for r in range(self.manual_table.rowCount())]

    def _sync_manual_specs_to_selected_accounts(self, allow_empty=False):
        """将当前表格草稿同步到选中账号，避免界面刷新后恢复旧数据。"""
        sids = [i.text() for i in self.grabber2_account_list.selectedItems()]
        specs = self._manual_specs_from_table()
        if not sids or (not specs and not allow_empty):
            return False
        for sid in sids:
            previous = self.manual_wishlist_specs.get(sid, {})
            if not isinstance(previous, dict):
                previous = {}
            self.manual_wishlist_specs[sid] = {
                "block": self.manual_block_input.currentIndex() + 1,
                "target_count": self.manual_target_input.value(),
                "scheduled": self.manual_schedule_checkbox.isChecked(),
                "start_time": self.manual_datetime.dateTime().toString("yyyy-MM-dd hh:mm:ss"),
                "courses": [dict(spec) for spec in specs],
            }
        self.wishlists["__manual_specs__"] = self.manual_wishlist_specs
        save_wishlists(self.wishlists)
        return True

    def save_manual_specs(self):
        sids = [i.text() for i in self.grabber2_account_list.selectedItems()]
        specs = self._manual_specs_from_table()
        if not sids or not specs: return QMessageBox.warning(self, "提示", "请选择账户并添加至少一条预设志愿。")
        self._sync_manual_specs_to_selected_accounts()
        self.manual_log.append(f"已保存 {len(specs)} 条预设志愿。")

    def start_manual_grab(self):
        sids = [i.text() for i in self.grabber2_account_list.selectedItems()]
        specs = self._manual_specs_from_table()
        if not sids or not specs: return QMessageBox.warning(self, "提示", "请选择账户并添加预设志愿。")
        self.save_manual_specs()
        self.manual_waiting = True
        self.manual_selected_sids = sids
        self.manual_start_button.setEnabled(False)
        self.manual_stop_button.setEnabled(True)
        self.manual_log.append(f"已进入等待，全部 {len(specs)} 条志愿将在同一时间拉取并匹配。")
        if self.manual_schedule_checkbox.isChecked():
            self.manual_timer.start(1000)
            self.check_manual_time()
        else:
            self.manual_wait_label.setText("状态：立即拉取并匹配课程…")
            self.manual_waiting = False
            self.fetch_manual_courses_now()

    def manual_schedule_toggled(self, enabled):
        self.manual_datetime.setEnabled(enabled)
        if not enabled and self.manual_waiting:
            self.manual_waiting = False
            self.manual_timer.stop()
            self.manual_wait_label.setText("状态：已切换为立即开始")

    def fetch_manual_courses_now(self):
        clients = {sid: self.logged_in_clients[sid] for sid in self.manual_selected_sids if sid in self.logged_in_clients}
        self.manual_fetch_results = {}
        self.manual_log.append("正在拉取最新课程列表并匹配预设志愿…")
        worker = ManualCourseFetchWorker(clients, self.manual_block_input.currentIndex() + 1)
        worker.result_ready.connect(self.handle_manual_courses)
        worker.finished_all.connect(self.start_manual_matched_grab)
        self._add_worker(worker); worker.start(); self.manual_fetch_worker = worker

    def check_manual_time(self):
        if not self.manual_waiting:
            return
        now = QDateTime.currentDateTime()
        target = self.manual_datetime.dateTime()
        if now >= target:
            self.manual_waiting = False; self.manual_timer.stop()
            self.manual_wait_label.setText("状态：已到点，正在拉取并匹配课程…")
            self.fetch_manual_courses_now()
        else:
            seconds = now.secsTo(target)
            self.manual_wait_label.setText(
                f"状态：等待统一开始时间（剩余 {seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}）"
            )

    def handle_manual_courses(self, sid, result):
        """保存并记录课程接口的完整返回，便于判断未开放/会话失效等原因。"""
        self.manual_fetch_results[sid] = result
        if isinstance(result, dict) and result.get("shared_course_list"):
            source_sid = result.get("shared_from", "其它账号")
            self.manual_log.append(f"[{sid}] 使用共享课程列表（来源：{source_sid}），未重复请求课程接口。")
            return
        try:
            raw = json.dumps(result, ensure_ascii=False, default=str)
        except Exception:
            raw = repr(result)
        if len(raw) > 6000:
            raw = raw[:6000] + "...（已截断）"
        self.manual_log.append(f"[{sid}] 课程接口原始返回：{raw}")

    def start_manual_matched_grab(self):
        started_count = 0
        for sid in self.manual_selected_sids:
            result = self.manual_fetch_results.get(sid, {})
            if not isinstance(result, dict):
                self.manual_log.append(f"[{sid}] 接口返回格式异常，未启动抢课：{result!r}")
                continue
            data = result.get("data") if isinstance(result.get("data"), dict) else {}
            courses = data.get("courses", [])
            if result.get("code") != 1000 or not courses:
                self.manual_log.append(
                    f"[{sid}] 暂未获得可匹配课程：code={result.get('code')}，"
                    f"msg={result.get('msg', '无')}，不会误启动抢课任务。"
                )
                continue
            specs = self.manual_wishlist_specs.get(sid, {}).get("courses", [])
            matched = []
            for spec in specs:
                found = next((c for c in courses if manual_course_matches(c, spec)), None)
                if found: matched.append(found)
                else:
                    weekday_name = {"1": "一", "2": "二", "3": "三", "4": "四", "5": "五", "6": "六", "7": "日"}.get(str(spec.get("weekday", "")), spec.get("weekday", ""))
                    lesson = spec.get("time") or f"星期{weekday_name}第{spec.get('section', '')}节"
                    self.manual_log.append(f"[{sid}] 未匹配：{spec.get('course_code', '')} / {spec['title']} / {spec['teacher']} / {lesson} / {spec.get('weeks', '')}")
            self.manual_log.append(f"[{sid}] 课程列表 {len(courses)} 条，成功匹配 {len(matched)}/{len(specs)} 条预设志愿。")
            if matched:
                grabber = PriorityBatchGrabber(
                    self.logged_in_clients[sid],
                    sid,
                    matched,
                    self.manual_wishlist_specs[sid].get("target_count", 1),
                    block=self.manual_wishlist_specs[sid].get(
                        "block", self.manual_block_input.currentIndex() + 1
                    ),
                )
                grabber.status_update.connect(lambda account, msg: self.manual_log.append(f"[{account}] {msg}")); grabber.finished.connect(self.on_grab_finished)
                self._add_worker(grabber); self.priority_grabbers[sid] = grabber; grabber.start()
                started_count += 1
        if started_count:
            self.manual_wait_label.setText("状态：已完成匹配，抢课任务持续运行中")
            self.manual_stop_button.setEnabled(True)
        else:
            self.manual_wait_label.setText("状态：未匹配到课程，等待选课系统开放后重试")
            self.manual_start_button.setEnabled(True)
            self.manual_stop_button.setEnabled(False)

    def stop_manual_grab(self):
        self.manual_waiting = False; self.manual_timer.stop()
        for grabber in self.priority_grabbers.values():
            if grabber.isRunning(): grabber.stop()
        self.manual_start_button.setEnabled(True)
        self.manual_stop_button.setEnabled(False)
        self.manual_wait_label.setText("状态：已停止")
        self.manual_log.append("已停止抢课助手2。")

    def _add_worker(self, worker_instance):
        self.active_workers.append(worker_instance)
        self.active_workers = [w for w in self.active_workers if not w.isFinished()]

    def closeEvent(self, event):
        self.save_all_configs()
        self.stop_all_grabbing()
        
        # 停止所有定时器
        self.timer_for_current_time.stop()
        self.timer_for_scheduled_grab.stop()
        
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
            # 表格状态必须以当前会话字典为准。此前每次刷新表格都无条件
            # 写入“未登录”，导致批量操作实际成功但界面显示过期状态。
            status = "✅ 登录成功" if account.sid in self.logged_in_clients else "未登录"
            self.accounts_table.setItem(row_position, 2, QTableWidgetItem(status))
        
        # 应用过滤
        if hasattr(self, 'main_account_search_input'):
            self.filter_main_accounts_table()

    def sync_account_login_statuses(self):
        """将账户表中的登录状态与当前登录会话字典同步。"""
        logged_in_sids = set(self.logged_in_clients)
        for row in range(self.accounts_table.rowCount()):
            sid_item = self.accounts_table.item(row, 0)
            if sid_item is None:
                continue
            sid = sid_item.text()
            status_item = self.accounts_table.item(row, 2)
            if sid in logged_in_sids:
                status = "✅ 登录成功"
            elif status_item is None or "✅" in status_item.text():
                status = "未登录"
            else:
                # 保留本次批量登录失败/验证码等诊断信息。
                continue
            self.accounts_table.setItem(row, 2, QTableWidgetItem(status))

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

    def edit_account(self):
        selected_rows = self.accounts_table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.information(self, "提示", "请先选择要编辑的账户。")
            return
        old_sid = self.accounts_table.item(selected_rows[0].row(), 0).text()
        index = next((i for i, account in enumerate(self.accounts) if account.sid == old_sid), None)
        if index is None:
            QMessageBox.warning(self, "错误", "未找到该账户配置。")
            return
        dialog = AccountDialog(self, self.accounts[index])
        if dialog.exec():
            credentials = dialog.get_credentials()
            if credentials:
                if credentials.sid != old_sid and any(a.sid == credentials.sid for a in self.accounts):
                    QMessageBox.warning(self, "错误", "该账号已存在！")
                    return
                self.accounts[index] = credentials
                self.logged_in_clients.pop(old_sid, None)
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
        # 使用新的方法来更新开始抢课按钮状态，而不是直接设为False
        self.update_start_grab_button_state()
        self.stop_grab_button.setEnabled(False)

    def force_batch_login(self):
        """清理现有会话后，强制重新登录全部账户。"""
        if not self.accounts:
            QMessageBox.information(self, "提示", "请先添加至少一个账户。")
            return

        if any(worker.isRunning() for worker in self.active_workers):
            QMessageBox.warning(self, "提示", "当前有批量任务正在运行，请等待任务结束后再强制重新登录。")
            return

        if any(worker.isRunning() for worker in self.priority_grabbers.values()):
            QMessageBox.warning(self, "提示", "请先停止正在运行的抢课任务，再强制重新登录。")
            return

        reply = QMessageBox.question(
            self,
            "确认强制重登",
            "这会清理当前所有登录会话，并重新登录全部账户。是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        for client in self.logged_in_clients.values():
            try:
                logout = getattr(client, "logout", None)
                if callable(logout):
                    logout()
                else:
                    session_manager = getattr(client, "session_manager", None)
                    if session_manager is not None:
                        session_manager.logout()
            except Exception:
                # 清理本地会话失败不应阻止后续重新登录。
                pass
        self.logged_in_clients.clear()
        self.sync_account_login_statuses()
        self.batch_login(force=True)

    def batch_login(self, force=False):
        if not self.accounts:
            QMessageBox.information(self, "提示", "请先添加至少一个账户。")
            return

        # 普通批量登录只重试未成功的账号；强制模式则忽略现有会话，
        # 对全部账号重新建立登录连接。
        pending_accounts = list(self.accounts) if force else [
            account for account in self.accounts
            if account.sid not in self.logged_in_clients
        ]
        if not pending_accounts:
            self.main_result_display.append("所有账户均已登录，无需重复登录。")
            self.sync_account_login_statuses()
            self.toggle_actions(True)
            self.update_grabber_account_list()
            return

        self.fetched_data.clear()
        self.last_batch_action = None
        self.toggle_actions(False)
        self.login_all_button.setEnabled(False)
        self.force_login_all_button.setEnabled(False)
        self.login_all_button.setText("登录中...")
        self.main_result_display.setText(
            f"正在启动{'强制' if force else ''}批量登录（待登录 {len(pending_accounts)} 个，"
            f"已登录 {len(self.logged_in_clients)} 个）...\n"
        )
        
        timeout = getattr(config, 'load_settings', lambda: 10)()  
        
        login_worker = BatchLoginWorker(pending_accounts, timeout)
        login_worker.account_status_update.connect(self.handle_account_login_status)
        login_worker.webvpn_captcha_required.connect(self.handle_webvpn_captcha)
        login_worker.finished.connect(self.handle_batch_login_finished)
        self._add_worker(login_worker)
        login_worker.start()

    def handle_webvpn_captcha(self, sid, captcha_pic, reply, ready):
        """在主线程展示 VPN 验证码，并唤醒等待中的登录工作线程。"""
        dialog = CaptchaDialog(captcha_pic, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            reply["captcha"] = dialog.get_captcha().strip()
        ready.set()

    def handle_account_login_status(self, sid, message, client_instance):
        self.main_result_display.append(f"学号 {sid}: {message}")
        for row in range(self.accounts_table.rowCount()):
            if self.accounts_table.item(row, 0).text() == sid:
                self.accounts_table.setItem(row, 2, QTableWidgetItem(message))
                break
        if client_instance:
            self.logged_in_clients[sid] = client_instance
            # 登录成功信号到达时立即更新表格，避免等待批量任务完全结束。
            self.sync_account_login_statuses()

    def handle_batch_login_finished(self):
        # 兼容表格在登录过程中被刷新/重建的情况，最终状态以会话字典为准。
        self.sync_account_login_statuses()
        self.login_all_button.setEnabled(True)
        self.force_login_all_button.setEnabled(True)
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
        
        # 更新后应用当前过滤器
        if hasattr(self, 'account_search_input'):
            self.filter_accounts_list()
        if hasattr(self, 'grabber2_account_list'):
            self._refresh_grabber2_accounts()
    
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
                self.main_result_display.append(f"    > GPA 结果: {gpa_data}")
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
        
        reply = QMessageBox.question(self, "保存缓存", 
                                     "是否要将获取的课程信息保存到本地缓存？\n这样可以方便后续查询。",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        
        self.save_cache_for_this_fetch = reply == QMessageBox.StandardButton.Yes
        
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
        if result.get('code') != 1000:
            self.grab_log_display.append(f"获取课程失败: {result.get('msg', '未知错误')}")
            self.update_start_grab_button_state()
            return
            
        data = result.get('data', {})
        courses = data.get('courses', [])
        if not courses:
            self.grab_log_display.append("该板块下没有可选择的课程。")
            self.update_start_grab_button_state()
            return

        # do_id 每次拉取都可能变化，只用稳定教学班 ID 回填原志愿。
        selected_items = self.grabber_account_list.selectedItems()
        sid = selected_items[0].text() if selected_items else None
        if sid:
            self.current_wishlist_sid = sid
        old_wishlist = (
            list(self.current_wishlist_courses)
            if self.current_wishlist_sid == sid
            else []
        )
        if not old_wishlist and sid:
            saved = self.wishlists.get(sid)
            if isinstance(saved, dict):
                old_wishlist = list(saved.get("courses", []))
            elif isinstance(saved, list):
                old_wishlist = list(saved)
        remapped_wishlist = remap_wishlist_courses(old_wishlist, courses)

        self.courses_table.setRowCount(0)
        self.current_selectable_courses.clear()
        self._table_courses = []
            
        self.grab_log_display.append(f"成功获取 {len(courses)} 门课程，请在下方表格中选择志愿课程。")
        
        if hasattr(self, 'save_cache_for_this_fetch') and self.save_cache_for_this_fetch:
            self.save_courses_cache(courses, data)
        
        for course in courses:
            course_key = course_identity(course)
            if course_key is None: continue
            
            row_pos = self.courses_table.rowCount()
            self.courses_table.insertRow(row_pos)
            self.courses_table.setItem(row_pos, 0, QTableWidgetItem(course.get('course_id')))
            self.courses_table.setItem(row_pos, 1, QTableWidgetItem(course.get('title')))
            self.courses_table.setItem(row_pos, 2, QTableWidgetItem(course.get('teacher')))
            self.courses_table.setItem(row_pos, 3, QTableWidgetItem(course.get('time')))
            self.courses_table.setItem(row_pos, 4, QTableWidgetItem(f"{course.get('selected_number', 'N/A')}/{course.get('capacity', 'N/A')}"))
            
            self.current_selectable_courses[course_key] = course
            self._table_courses.append(course)

        if old_wishlist:
            self.update_wishlist_display(remapped_wishlist)
            replaced_count = sum(
                1 for old, fresh in zip(old_wishlist, remapped_wishlist)
                if old is not fresh
            )
            if sid and isinstance(self.wishlists.get(sid), (dict, list)):
                if isinstance(self.wishlists[sid], dict):
                    self.wishlists[sid]["courses"] = remapped_wishlist
                else:
                    self.wishlists[sid] = remapped_wishlist
                save_wishlists(self.wishlists)
            self._restore_wishlist_selection()
            missing_count = len(old_wishlist) - replaced_count
            if missing_count:
                self.log_to_grabber(
                    f"⚠️ 有 {missing_count} 门已保存志愿未出现在本次课程列表中，"
                    "已保留原志愿，不会自动替换为其他教学班。"
                )
        
        # 结果显示后更新搜索过滤
        self.filter_courses_table()
        self.update_start_grab_button_state()

    def filter_courses_table(self):
        """根据搜索框内容过滤课程列表表格"""
        search_text = self.course_search_input.text().lower().strip()
        
        for row in range(self.courses_table.rowCount()):
            match = False
            # 搜索：课程ID (0), 课程名称 (1), 教师 (2), 上课时间 (3)
            for col in range(4):
                item = self.courses_table.item(row, col)
                if item and search_text in item.text().lower():
                    match = True
                    break
            
            self.courses_table.setRowHidden(row, not match)

    def filter_accounts_list(self):
        """根据搜索框内容过滤账户列表"""
        if not hasattr(self, 'account_search_input'):
            return
        search_text = self.account_search_input.text().lower().strip()
        for i in range(self.grabber_account_list.count()):
            item = self.grabber_account_list.item(i)
            match = search_text in item.text().lower()
            item.setHidden(not match)

    def filter_main_accounts_table(self):
        """首页账户表格过滤器"""
        if not hasattr(self, 'main_account_search_input'):
            return
        search_text = self.main_account_search_input.text().lower().strip()
        for row in range(self.accounts_table.rowCount()):
            match = False
            for col in range(2): # 搜索学号和URL
                item = self.accounts_table.item(row, col)
                if item and search_text in item.text().lower():
                    match = True
                    break
            self.accounts_table.setRowHidden(row, not match)

    def start_priority_grabbing(self):
        """抢课启动入口 - 处理定时逻辑"""
        selected_account_items = self.grabber_account_list.selectedItems()
        if not selected_account_items:
            return QMessageBox.warning(self, "提示", "请选择至少一个要用于抢课的账户。")

        if self.scheduled_enabled:
            is_valid, start_immediately = self.validate_scheduled_time()
            if not is_valid:
                return
            
            if start_immediately:
                self.execute_priority_grabbing()
            else:
                self.start_scheduled_waiting()
        else:
            self.execute_priority_grabbing()
    
    def start_scheduled_waiting(self):
        """开始定时等待"""
        scheduled_time = self.scheduled_datetime.dateTime()
        self.log_to_grabber(f"⏰ 定时抢课已启动，等待到 {scheduled_time.toString('yyyy-MM-dd hh:mm:ss')} 开始")
        
        self.waiting_for_scheduled_grab = True
        self.start_grab_button.setEnabled(False)
        self.stop_grab_button.setEnabled(True)
        
        self.timer_for_scheduled_grab.start(1000)
        
        self.check_scheduled_time()

    def execute_priority_grabbing(self):
        """执行实际的抢课逻辑 - 并发启动所有账户的抢课任务"""
        selected_account_items = self.grabber_account_list.selectedItems()
        if not selected_account_items:
            return QMessageBox.warning(self, "提示", "请选择至少一个要用于抢课的账户。")

        selected_sids = [item.text() for item in selected_account_items]

        self.start_grab_button.setEnabled(False)
        self.stop_grab_button.setEnabled(True)
        self.grab_log_display.append("\n" + "=" * 15 + " 开始多账户并发抢课任务 " + "=" * 15)

        started_count = 0
        
        # 一次性启动所有抢课线程（真正的并发）
        for sid in selected_sids:
            api_client = self.logged_in_clients.get(sid)
            if not api_client:
                self.log_to_grabber(f"❌ 错误：未找到学号 {sid} 的登录实例，跳过。")
                continue

            if sid in self.priority_grabbers and self.priority_grabbers[sid].isRunning():
                self.log_to_grabber(f"学号 [{sid}] 已有抢课任务在运行，跳过。")
                continue

            wishlist_data = self.wishlists.get(sid)
            if not wishlist_data:
                self.log_to_grabber(f"❌ 学号 [{sid}] 没有找到志愿列表，跳过。请先保存志愿。")
                continue

            target_count = 1
            prioritized_courses = []

            if isinstance(wishlist_data, dict):
                target_count = wishlist_data.get("target_count", 1)
                prioritized_courses = wishlist_data.get("courses", [])
            elif isinstance(wishlist_data, list):
                prioritized_courses = wishlist_data

            if not prioritized_courses:
                self.log_to_grabber(f"❌ 学号 [{sid}] 的志愿列表为空，跳过。")
                continue

            self.log_to_grabber(
                f"➡️ 为学号 [{sid}] 分配抢课任务，目标：{target_count}门，志愿数：{len(prioritized_courses)}门")

            grabber = PriorityBatchGrabber(api_client, sid, prioritized_courses, target_count)
            grabber.status_update.connect(self.update_grab_log)
            grabber.finished.connect(self.on_grab_finished)
            self.priority_grabbers[sid] = grabber
            self._add_worker(grabber)

            # 立即启动抢课线程
            grabber.start()
            started_count += 1

        self.log_to_grabber(f"--- 已同时启动 {started_count} 个抢课任务，正在并发运行 ---")

    def stop_all_grabbing(self):
        """停止所有抢课任务和定时等待"""
        if self.waiting_for_scheduled_grab:
            self.stop_scheduled_waiting()
        
        if self.priority_grabbers:
            self.grab_log_display.append("\n--- 正在发送停止所有抢课任务的信号 ---")
            for grabber in self.priority_grabbers.values():
                if grabber.isRunning():
                    grabber.stop()
        
        self.start_grab_button.setEnabled(True)
        self.stop_grab_button.setEnabled(False)

    def update_grab_log(self, sid, message):
        if "JAS-04" in message or "校验不通过" in message:
            enhanced_message = f"{message}\n    💡 提示: 这通常是教务系统的反爬虫机制，程序已自动重试并刷新会话"
            self.grab_log_display.append(f"[{sid}] {enhanced_message}")
        else:
            self.grab_log_display.append(f"[{sid}] {message}")
    
    def on_grab_finished(self, sid):
        all_finished = not any(g.isRunning() for g in self.priority_grabbers.values())
        if all_finished:
            self.start_grab_button.setEnabled(True)
            self.stop_grab_button.setEnabled(False)
            self.grab_log_display.append("--- 所有账户的抢课任务已结束 ---")
            self.priority_grabbers.clear()

    def load_all_wishlists(self):
        self.wishlists = load_wishlists()
        saved_manual = self.wishlists.get("__manual_specs__", {})
        if isinstance(saved_manual, dict):
            self.manual_wishlist_specs = saved_manual
        self.log_to_grabber(f"已加载 {len(self.wishlists)} 个账户的已存志愿。")
        self.update_start_grab_button_state()

    def save_wishlist_for_selected(self):
        selected_account_items = self.grabber_account_list.selectedItems()
        if not selected_account_items:
            return QMessageBox.warning(self, "提示", "请在左侧选择至少一个要保存志愿的账户。")
        
        if not self.current_wishlist_courses:
            return QMessageBox.warning(self, "提示", "当前志愿列表为空，没有可保存的内容。")
        
        target_count = self.grab_target_count_input.value()
        sids_to_save = [item.text() for item in selected_account_items]
        
        for sid in sids_to_save:
            self.wishlists[sid] = {
                "target_count": target_count,
                "courses": self.current_wishlist_courses
            }
        
        save_wishlists(self.wishlists)
        self.log_to_grabber(f"已为账户 {', '.join(sids_to_save)} 保存了 {len(self.current_wishlist_courses)} 门志愿(目标 {target_count} 门)。")
        QMessageBox.information(self, "成功", f"已为账户 {', '.join(sids_to_save)} 成功保存志愿列表！")
        
        self.update_start_grab_button_state()

    def load_wishlist_to_ui(self):
        self.courses_table.clearSelection()
        self.grab_target_count_input.setValue(1)
        self.update_wishlist_display([])

        selected_account_items = self.grabber_account_list.selectedItems()
        if not selected_account_items:
            self.update_start_grab_button_state()
            return
        
        sid_to_load = selected_account_items[0].text()
        self.current_wishlist_sid = sid_to_load
        wishlist_data = self.wishlists.get(sid_to_load)

        if not wishlist_data:
            self.log_to_grabber(f"账户 {sid_to_load} 尚无已保存的志愿。")
            self.update_start_grab_button_state()
            return

        target_count = 1
        wishlist_courses = []
        
        if isinstance(wishlist_data, dict):
            target_count = wishlist_data.get("target_count", 1)
            wishlist_courses = wishlist_data.get("courses", [])
        elif isinstance(wishlist_data, list):
            self.log_to_grabber(f"检测到账户 {sid_to_load} 的志愿为旧格式，将为您加载。建议重新保存一次以更新格式。")
            wishlist_courses = wishlist_data
        else:
            self.log_to_grabber(f"❌ 账户 {sid_to_load} 的志愿格式不正确，无法加载。")
            self.update_start_grab_button_state()
            return

        self.grab_target_count_input.setValue(target_count)
        self.update_wishlist_display(wishlist_courses)

        if not wishlist_courses:
            self.update_start_grab_button_state()
            return
            
        loaded_count = 0
        total_wishlist_count = len(wishlist_courses)

        loaded_count = self._restore_wishlist_selection(wishlist_courses)
        
        self.log_to_grabber(
            f"为账户 {sid_to_load} 加载志愿: "
            f"志愿列表共 {total_wishlist_count} 门, "
            f"目标抢课数: {target_count}。"
        )
        
        self.update_start_grab_button_state()
    
    def update_wishlist_display(self, courses):
        """用给定的课程列表更新右侧的志愿显示列表（已加入时间显示）"""
        self.current_wishlist_courses = list(courses or [])
        self.wishlist_display.clear()
        for i, course in enumerate(self.current_wishlist_courses):
            display_text = f"{i+1}. {course.get('title', 'N/A')} - {course.get('teacher', 'N/A')} - {course.get('time', 'N/A')}"
            item = QListWidgetItem(display_text)
            item.setData(Qt.ItemDataRole.UserRole, course_identity(course))
            self.wishlist_display.addItem(item)

    def _restore_wishlist_selection(self, wishlist_courses=None):
        """按稳定教学班 ID 将志愿勾回课程表，返回成功匹配数量。"""
        wishlist = self.current_wishlist_courses if wishlist_courses is None else wishlist_courses
        wishlist_class_ids = {
            course_identity(course)
            for course in wishlist
            if isinstance(course, dict) and str(course.get("class_id") or "").strip()
        }
        wishlist_legacy_ids = {
            legacy_course_identity(course)
            for course in wishlist
            if not (isinstance(course, dict) and str(course.get("class_id") or "").strip())
        }
        legacy_table_rows = {}
        for row, course in enumerate(self._table_courses):
            legacy_table_rows.setdefault(legacy_course_identity(course), []).append(row)
        self.courses_table.blockSignals(True)
        self.courses_table.clearSelection()
        loaded_count = 0
        for row, course in enumerate(self._table_courses):
            selected = course_identity(course) in wishlist_class_ids
            if not selected:
                legacy_id = legacy_course_identity(course)
                selected = (
                    legacy_id in wishlist_legacy_ids
                    and len(legacy_table_rows.get(legacy_id, [])) == 1
                )
            if selected:
                self.courses_table.selectRow(row)
                loaded_count += 1
        self.courses_table.blockSignals(False)
        return loaded_count

    def _course_for_table_row(self, row):
        if 0 <= row < len(self._table_courses):
            return self._table_courses[row]
        return None

    def update_wishlist_from_table_selection(self):
        """当用户在主课程表中选择变化时，更新志愿列表（已修正）"""
        selected_rows_indices = self.courses_table.selectionModel().selectedRows()
        selected_courses_in_table = [
            course for index in selected_rows_indices
            if (course := self._course_for_table_row(index.row())) is not None
        ]
        selected_ids = {course_identity(course) for course in selected_courses_in_table}
        selected_by_id = {course_identity(course): course for course in selected_courses_in_table}

        # 已有志愿保持原优先级，但替换成表格中最新的课程对象（尤其是新 do_id）。
        new_wishlist = [
            selected_by_id.get(course_identity(course), course)
            for course in self.current_wishlist_courses
            if course_identity(course) in selected_ids
        ]
        existing_ids = {course_identity(course) for course in new_wishlist}
        for course in selected_courses_in_table:
            if course_identity(course) not in existing_ids:
                new_wishlist.append(course)

        self.update_wishlist_display(new_wishlist)

    def move_wishlist_item_up(self):
        current_row = self.wishlist_display.currentRow()
        if current_row > 0:
            item = self.wishlist_display.takeItem(current_row)
            self.wishlist_display.insertItem(current_row - 1, item)
            self.wishlist_display.setCurrentRow(current_row - 1)
            
            course = self.current_wishlist_courses.pop(current_row)
            self.current_wishlist_courses.insert(current_row - 1, course)
            self.update_wishlist_display(self.current_wishlist_courses)

    def move_wishlist_item_down(self):
        current_row = self.wishlist_display.currentRow()
        if current_row < self.wishlist_display.count() - 1 and current_row != -1:
            item = self.wishlist_display.takeItem(current_row)
            self.wishlist_display.insertItem(current_row + 1, item)
            self.wishlist_display.setCurrentRow(current_row + 1)
            
            course = self.current_wishlist_courses.pop(current_row)
            self.current_wishlist_courses.insert(current_row + 1, course)
            self.update_wishlist_display(self.current_wishlist_courses)

    def wishlist_order_changed(self):
        """拖拽结束后，根据显示顺序重建数据源（已修正解析逻辑）"""
        new_ordered_courses = []
        course_pool = {course_identity(course): course for course in self.current_wishlist_courses}
        for i in range(self.wishlist_display.count()):
            item = self.wishlist_display.item(i)
            identity = item.data(Qt.ItemDataRole.UserRole)
            found_course = course_pool.pop(identity, None)
            if found_course is not None:
                new_ordered_courses.append(found_course)
        
        if len(new_ordered_courses) == len(self.current_wishlist_courses):
            self.update_wishlist_display(new_ordered_courses)
        else:
            self.log_to_grabber("警告：拖拽排序后解析志愿列表失败，恢复原顺序。")
            self.update_wishlist_display(self.current_wishlist_courses)

    def log_to_grabber(self, message):
        self.grab_log_display.append(message)
    
    def save_courses_cache(self, courses, metadata=None):
        """保存课程数据到本地缓存"""
        try:
            cache_dir = os.path.join(os.getcwd(), 'cache')
            os.makedirs(cache_dir, exist_ok=True)
            
            year = self.grab_year_display.text()
            term = self.grab_term_input.currentText()
            block = (metadata or {}).get('block_name') or self.grab_block_input.currentText()
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            
            filename = f"courses_{year}_{term}_{block}_{timestamp}.json"
            filepath = os.path.join(cache_dir, filename)
            
            cache_data = {
                'timestamp': timestamp,
                'year': year,
                'term': term,
                'block': block,
                'total_courses': len(courses),
                'metadata': metadata or {},
                'courses': courses
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            
            self.grab_log_display.append(f"✅ 课程缓存已保存: {filename}")
            
            latest_filename = f"courses_{year}_{term}_{block}_latest.json"
            latest_filepath = os.path.join(cache_dir, latest_filename)
            with open(latest_filepath, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            self.grab_log_display.append(f"❌ 保存课程缓存失败: {str(e)}")

    def display_cached_courses(self, courses, cache_data):
        """显示缓存的课程到表格中"""
        selected_items = self.grabber_account_list.selectedItems()
        sid = selected_items[0].text() if selected_items else None
        if sid:
            self.current_wishlist_sid = sid
        old_wishlist = (
            list(self.current_wishlist_courses)
            if self.current_wishlist_sid == sid
            else []
        )
        if not old_wishlist and sid:
            saved = self.wishlists.get(sid)
            if isinstance(saved, dict):
                old_wishlist = list(saved.get("courses", []))
            elif isinstance(saved, list):
                old_wishlist = list(saved)
        remapped_wishlist = remap_wishlist_courses(old_wishlist, courses)

        self.courses_table.setRowCount(0)
        self.current_selectable_courses.clear()
        self._table_courses = []
        
        for course in courses:
            course_key = course_identity(course)
            if course_key is None:
                continue
            
            row_pos = self.courses_table.rowCount()
            self.courses_table.insertRow(row_pos)
            self.courses_table.setItem(row_pos, 0, QTableWidgetItem(course.get('course_id', '')))
            self.courses_table.setItem(row_pos, 1, QTableWidgetItem(course.get('title', '')))
            self.courses_table.setItem(row_pos, 2, QTableWidgetItem(course.get('teacher', '')))
            self.courses_table.setItem(row_pos, 3, QTableWidgetItem(course.get('time', '')))
            self.courses_table.setItem(row_pos, 4, QTableWidgetItem(f"{course.get('selected_number', 'N/A')}/{course.get('capacity', 'N/A')}"))
            
            self.current_selectable_courses[course_key] = course
            self._table_courses.append(course)
        
        # 结果显示后更新搜索过滤
        self.filter_courses_table()
        if old_wishlist:
            self.update_wishlist_display(remapped_wishlist)
            if sid and isinstance(self.wishlists.get(sid), (dict, list)):
                if isinstance(self.wishlists[sid], dict):
                    self.wishlists[sid]["courses"] = remapped_wishlist
                else:
                    self.wishlists[sid] = remapped_wishlist
                save_wishlists(self.wishlists)
        self._restore_wishlist_selection()
        self.update_start_grab_button_state()

    def show_cache_manager(self):
        """显示缓存管理器对话框，并处理加载和删除逻辑"""
        cache_dir = os.path.join(os.getcwd(), 'cache')
        if not os.path.exists(cache_dir) or not os.listdir(cache_dir):
            QMessageBox.information(self, "提示", "还没有任何缓存文件。")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("课程缓存管理器")
        dialog.setModal(True)
        dialog.resize(800, 500)
        
        layout = QVBoxLayout(dialog)
        
        info_label = QLabel("以下是本地保存的课程缓存文件，您可以选择一个进行加载或删除：")
        layout.addWidget(info_label)
        
        cache_table = QTableWidget()
        cache_table.setColumnCount(6)
        cache_table.setHorizontalHeaderLabels(['文件名', '学年', '学期', '板块', '课程数', '大小'])
        cache_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        cache_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        cache_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        cache_files_info = []
        for filename in os.listdir(cache_dir):
            if filename.startswith('courses_') and filename.endswith('.json'):
                filepath = os.path.join(cache_dir, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        cache_data = json.load(f)
                    cache_files_info.append({
                        'filename': filename,
                        'filepath': filepath,
                        'year': cache_data.get('year', '未知'),
                        'term': cache_data.get('term', '未知'),
                        'block': cache_data.get('block', '未知'),
                        'total_courses': cache_data.get('total_courses', 0),
                        'size': os.path.getsize(filepath)
                    })
                except:
                    continue

        cache_table.setRowCount(len(cache_files_info))
        for i, file_info in enumerate(cache_files_info):
            cache_table.setItem(i, 0, QTableWidgetItem(file_info['filename']))
            cache_table.setItem(i, 1, QTableWidgetItem(str(file_info['year'])))
            cache_table.setItem(i, 2, QTableWidgetItem(str(file_info['term'])))
            cache_table.setItem(i, 3, QTableWidgetItem(str(file_info['block'])))
            cache_table.setItem(i, 4, QTableWidgetItem(str(file_info['total_courses'])))
            cache_table.setItem(i, 5, QTableWidgetItem(f"{file_info['size']/1024:.1f} KB"))
        
        layout.addWidget(cache_table)
        
        button_layout = QHBoxLayout()
        load_button = QPushButton("加载选中缓存")
        delete_button = QPushButton("删除选中")
        open_folder_button = QPushButton("打开缓存文件夹")
        close_button = QPushButton("关闭")
        
        def load_selected_cache():
            selected_rows = cache_table.selectionModel().selectedRows()
            if not selected_rows:
                QMessageBox.warning(dialog, "提示", "请选择一个缓存文件。")
                return
            row = selected_rows[0].row()
            file_info = cache_files_info[row]
            
            try:
                with open(file_info['filepath'], 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                courses = cache_data.get('courses', [])
                if courses:
                    self.display_cached_courses(courses, cache_data)
                    self.log_to_grabber(f"✅ 成功加载缓存: {file_info['filename']}")
                    dialog.close()
                else:
                    QMessageBox.warning(dialog, "警告", "缓存文件没有课程数据。")
            except Exception as e:
                QMessageBox.critical(dialog, "错误", f"加载缓存失败: {str(e)}")
        
        def delete_selected_cache():
            selected_rows = cache_table.selectionModel().selectedRows()
            if not selected_rows:
                QMessageBox.warning(dialog, "提示", "请选择要删除的缓存文件。")
                return
            
            reply = QMessageBox.question(dialog, "确认删除", f"确定要删除选中的 {len(selected_rows)} 个缓存文件吗？",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            
            if reply == QMessageBox.StandardButton.Yes:
                for index in sorted(selected_rows, key=lambda i: i.row(), reverse=True):
                    row = index.row()
                    file_info = cache_files_info[row]
                    try:
                        os.remove(file_info['filepath'])
                        cache_table.removeRow(row)
                        self.log_to_grabber(f"✅ 已删除缓存文件: {file_info['filename']}")
                    except Exception as e:
                        QMessageBox.warning(dialog, "警告", f"删除文件 {file_info['filename']} 失败: {str(e)}")
        
        def open_cache_folder():
            if os.path.exists(cache_dir):
                if os.name == 'nt':
                    os.startfile(cache_dir)
                elif os.name == 'posix':
                    import subprocess
                    subprocess.Popen(['xdg-open', cache_dir])
            else:
                QMessageBox.warning(dialog, "提示", "缓存文件夹不存在。")
                
        load_button.clicked.connect(load_selected_cache)
        delete_button.clicked.connect(delete_selected_cache)
        open_folder_button.clicked.connect(open_cache_folder)
        close_button.clicked.connect(dialog.close)
        
        button_layout.addWidget(load_button)
        button_layout.addWidget(delete_button)
        button_layout.addWidget(open_folder_button)
        button_layout.addStretch()
        button_layout.addWidget(close_button)
        
        layout.addLayout(button_layout)
        
        dialog.exec()
        
    def update_start_grab_button_state(self):
        """更新开始志愿抢课按钮的状态 - 只要有志愿表就可以启用"""
        selected_account_items = self.grabber_account_list.selectedItems()
        if not selected_account_items:
            self.start_grab_button.setEnabled(False)
            return
        
        has_wishlist = False
        for item in selected_account_items:
            sid = item.text()
            wishlist_data = self.wishlists.get(sid)
            if wishlist_data:
                if isinstance(wishlist_data, dict):
                    courses = wishlist_data.get("courses", [])
                    if courses:
                        has_wishlist = True
                        break
                elif isinstance(wishlist_data, list) and wishlist_data:
                    has_wishlist = True
                    break
        
        self.start_grab_button.setEnabled(has_wishlist)
    
    def update_current_time(self):
        """更新当前时间显示"""
        current_time = QDateTime.currentDateTime().toString("yyyy-MM-dd hh:mm:ss")
        self.current_time_label.setText(current_time)
    
    def on_scheduled_checkbox_toggled(self, checked):
        """定时抢课开关状态改变"""
        self.scheduled_enabled = checked
        if checked:
            self.log_to_grabber("✅ 已启用定时抢课功能")
        else:
            self.log_to_grabber("❌ 已禁用定时抢课功能")
            if self.waiting_for_scheduled_grab:
                self.stop_scheduled_waiting()
    
    def check_scheduled_time(self):
        """检查是否到达设定的抢课时间"""
        if not self.scheduled_enabled or not self.waiting_for_scheduled_grab:
            return
            
        current_time = QDateTime.currentDateTime()
        scheduled_time = self.scheduled_datetime.dateTime()
        
        if current_time >= scheduled_time:
            self.log_to_grabber("🚀 到达设定时间，开始执行抢课...")
            self.timer_for_scheduled_grab.stop()
            self.waiting_for_scheduled_grab = False
            self.start_grab_button.setText("🚀 开始志愿抢课")
            self.start_grab_button.setEnabled(True)
            self.execute_priority_grabbing()
        else:
            remaining_seconds = current_time.secsTo(scheduled_time)
            hours = remaining_seconds // 3600
            minutes = (remaining_seconds % 3600) // 60
            seconds = remaining_seconds % 60
            
            time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            self.start_grab_button.setText(f"⏰ 等待中 ({time_str})")
    
    def stop_scheduled_waiting(self):
        """停止定时等待"""
        self.timer_for_scheduled_grab.stop()
        self.waiting_for_scheduled_grab = False
        self.start_grab_button.setText("🚀 开始志愿抢课")
        self.start_grab_button.setEnabled(True)
        self.log_to_grabber("⏹️ 已停止定时等待")
    
    def validate_scheduled_time(self):
        """验证设定的时间是否有效"""
        current_time = QDateTime.currentDateTime()
        scheduled_time = self.scheduled_datetime.dateTime()
        
        if scheduled_time <= current_time:
            reply = QMessageBox.question(
                self, 
                "时间设置", 
                f"设定的开始时间 ({scheduled_time.toString('yyyy-MM-dd hh:mm:ss')}) 已过。\n\n"
                f"当前时间: {current_time.toString('yyyy-MM-dd hh:mm:ss')}\n\n"
                "是否立即开始抢课？\n"
                "点击'是'立即开始，点击'否'取消并修改时间。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.log_to_grabber("⚡ 用户选择立即开始抢课")
                return True, True
            else:
                self.log_to_grabber("⏰ 用户选择修改时间，请重新设置")
                return False, False
        
        return True, False
