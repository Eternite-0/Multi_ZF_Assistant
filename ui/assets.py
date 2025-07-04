# ui/assets.py

STYLESHEET = """
QWidget {
    background-color: #f8f9fa; /* 更柔和的背景色 */
    color: #212529;
    font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Helvetica Neue', Arial, sans-serif;
    font-size: 13px;
    font-weight: 400;
}

QMainWindow {
    background-color: #f8f9fa;
    border-radius: 12px;
}

/* 容器样式 */
QWidget[objectName="group-box"] {
    background-color: #ffffff;
    border: 1px solid #dee2e6;
    border-radius: 8px;
    padding: 10px;
}

/* Tab Widget 风格 */
QTabWidget::pane {
    background: transparent;
    border: none;
    padding: 10px;
}

QTabBar::tab {
    background: #e9ecef;
    color: #495057;
    padding: 10px 20px;
    margin: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-weight: 500;
    min-width: 80px;
    border: 1px solid transparent;
    border-bottom: 1px solid #dee2e6;
}

QTabBar::tab:selected {
    background: #ffffff;
    color: #007bff;
    font-weight: 600;
    border-color: #dee2e6;
    border-bottom-color: #ffffff; /* 与pane融合 */
}

QTabBar::tab:hover:!selected {
    background: #f1f3f5;
}

/* 输入框风格 */
QLineEdit, QComboBox, QSpinBox {
    background: #ffffff;
    border: 1px solid #ced4da;
    border-radius: 6px;
    padding: 8px 12px;
    color: #495057;
    selection-background-color: #007bff;
    selection-color: white;
}

QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
    border-color: #80bdff;
    outline: 0;
}

/* 按钮风格 */
QPushButton {
    background-color: #007bff;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 10px 20px;
    font-weight: 600;
    font-size: 13px;
    min-height: 18px;
}

QPushButton:hover {
    background-color: #0069d9;
}

QPushButton:pressed {
    background-color: #0056b3;
}

QPushButton:disabled {
    background: #6c757d;
    color: #ffffff;
}

/* 文本区域和列表/表格 */
QTextEdit, QListWidget, QTableWidget {
    background-color: #ffffff;
    border: 1px solid #dee2e6;
    border-radius: 8px;
    padding: 5px;
    font-family: 'SF Mono', Monaco, 'Cascadia Code', 'Roboto Mono', Consolas, 'Courier New', monospace;
    font-size: 12px;
}

/* 表格样式 */
QTableWidget {
    gridline-color: #e9ecef; /* 网格线颜色 */
}

QTableWidget::item {
    padding: 10px;
    border: none;
    border-bottom: 1px solid #e9ecef; /* 行分隔线 */
}

QTableWidget::item:selected {
    background-color: #cfe2ff; /* 柔和的蓝色选中背景 */
    color: #000;
}

/* 列表样式 */
QListWidget::item {
    padding: 10px;
    border: none;
}

QListWidget::item:selected {
    background-color: #cfe2ff;
    color: #000;
    border-left: 3px solid #007bff; /* 选中时左侧有标记 */
}

QHeaderView::section {
    background-color: #f8f9fa;
    padding: 10px;
    border: none;
    border-bottom: 1px solid #dee2e6;
    font-weight: 600;
    color: #495057;
}

/* 对话框 */
QDialog {
    background: #ffffff;
    border-radius: 16px;
    border: 1px solid #dee2e6;
}

/* 滚动条风格 */
QScrollBar:vertical {
    background: #f1f3f5;
    width: 10px;
    border-radius: 5px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background: #adb5bd;
    border-radius: 5px;
    min-height: 20px;
}

QScrollBar::handle:vertical:hover {
    background: #6c757d;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
"""

# 请将您原文件 main_gui.py 中的 TRANSLATIONS 字典完整复制到这里
TRANSLATIONS = {
    'common': {
        'sid': '学号', 'name': '姓名', 'year': '学年', 'term': '学期', 'count': '总数', 'courses': '课程列表',
        'course_id': '课程号', 'title': '课程名称', 'teacher': '任课教师', 'class_name': '教学班名称',
        'credit': '学分', 'category': '课程类别', 'nature': '课程性质',
    },
    'get_grade': { 'grade': '成绩', 'grade_point': '绩点', 'grade_nature': '成绩性质', 'start_college': '开课院系', 'mark': '标记', },
    'get_schedule': {
        'weekday': '星期', 'time': '上课时间', 'sessions': '上课节数', 'list_sessions': '开课节数列表',
        'weeks': '开课周数', 'list_weeks': '开课周数列表', 'evaluation_mode': '考核方式', 'campus': '上课校区',
        'place': '上课场地', 'hours_composition': '课程学时组成', 'weekly_hours': '每周学时', 'total_hours': '总学时',
    },
    'get_exam_schedule': {
        'time': '考试时间', 'location': '考试地点', 'xq': '考试校区', 'zwh': '考试座号', 'cxbj': '重修标记',
        'exam_name': '考试名称', 'kkxy': '开课学院', 'ksfs': '考试方式', 'sjbh': '试卷编号', 'bz': '备注',
    },
    'get_selected_courses': {
        'class_id': '教学班ID', 'do_id': '执行ID', 'teacher_id': '教师ID', 'kklxdm': '板块课ID',
        'capacity': '教学班容量', 'selected_number': '已选人数', 'category': '课程类型', 'optional': '是否自选',
        'waiting': '等待情况', 'place': '上课地点', 'time': '上课时间',
    },
    'get_info': {
        'college_name': '学院', 'major_name': '专业', 'status': '学籍状态', 'enrollment_date': '入学日期',
        'candidate_number': '考生号', 'graduation_school': '毕业中学', 'domicile': '籍贯', 'postal_code': '邮政编码',
        'politics_status': '政治面貌', 'nationality': '民族', 'education': '培养层次', 'phone_number': '手机号码',
        'parents_number': '家长电话', 'email': '电子邮箱', 'birthday': '出生日期', 'id_number': '证件号码',
    },
    'get_academia': {
        'situation': '修读情况', 'display_term': '修读学期', 'max_grade': '最佳成绩', 'grade_point': '绩点',
        'statistics': '学分统计', 'gpa': '平均绩点', 'planed_courses': '计划内课程', 'unplaned_courses': '计划外课程',
        'total': '总数', 'passed': '已通过', 'failed': '未通过', 'missed': '未修', 'in': '在读',
        'details': '详细分类', 'credits': '学分详情', 'required': '要求学分', 'earned': '获得学分',
    }
}
