import base64
import re
from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QLineEdit,
                             QDialogButtonBox, QTableWidget, QTableWidgetItem,
                             QPushButton, QHeaderView, QAbstractItemView)

class CaptchaDialog(QDialog):
    """验证码输入对话框"""
    def __init__(self, captcha_pic_base64, parent=None):
        super().__init__(parent)
        self.setWindowTitle("请输入验证码")
        self.layout = QVBoxLayout(self)

        self.captcha_label = QLabel(self)
        pixmap = QPixmap()
        pixmap.loadFromData(base64.b64decode(captcha_pic_base64))
        self.captcha_label.setPixmap(pixmap)
        self.layout.addWidget(self.captcha_label)

        self.captcha_input = QLineEdit(self)
        self.layout.addWidget(self.captcha_input)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.layout.addWidget(self.buttons)

    def get_captcha(self):
        """获取用户输入的验证码"""
        return self.captcha_input.text()

class ExamCalendarDialog(QDialog):
    """一个用于显示考试日历的对话框"""
    def __init__(self, exam_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("考试日历安排")
        self.setGeometry(150, 150, 900, 500)

        layout = QVBoxLayout(self)
        self.table = QTableWidget()
        layout.addWidget(self.table)

        self.populate_table(exam_data)

        close_button = QPushButton("关闭")
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button, alignment=Qt.AlignmentFlag.AlignRight)

    def populate_table(self, exam_data):
        """填充考试信息表格"""
        headers = ['考试日期', '时间', '考试名称', '课程名称', '地点', '座位号', '考试方式', '备注']
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

        exams = exam_data.get('courses', [])
        sorted_exams = self.parse_and_sort_exams(exams)

        self.table.setRowCount(len(sorted_exams))

        for row, exam in enumerate(sorted_exams):
            self.table.setItem(row, 0, QTableWidgetItem(exam.get('date_str', '')))
            self.table.setItem(row, 1, QTableWidgetItem(exam.get('time_range', '')))
            self.table.setItem(row, 2, QTableWidgetItem(exam.get('exam_name', '')))
            self.table.setItem(row, 3, QTableWidgetItem(exam.get('title', '')))
            location = f"{exam.get('xq', '')} {exam.get('location', '')}".strip()
            self.table.setItem(row, 4, QTableWidgetItem(location))
            self.table.setItem(row, 5, QTableWidgetItem(str(exam.get('zwh', ''))))
            self.table.setItem(row, 6, QTableWidgetItem(str(exam.get('ksfs', ''))))
            self.table.setItem(row, 7, QTableWidgetItem(str(exam.get('bz', ''))))

        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

    def parse_and_sort_exams(self, exams):
        """解析并排序考试列表"""
        parsed_exams = []
        pattern = re.compile(r'(\d{4}-\d{2}-\d{2})[ (]*(\d{2}:\d{2})-(\d{2}:\d{2})')

        for exam in exams:
            time_str = exam.get('time')
            if not time_str:
                continue

            match = pattern.search(time_str)
            if match:
                date_part, start_time_str, end_time_str = match.groups()
                try:
                    sort_key = datetime.strptime(f"{date_part} {start_time_str}", "%Y-%m-%d %H:%M")
                    exam.update({
                        'sort_key': sort_key,
                        'date_str': date_part,
                        'time_range': f"{start_time_str}-{end_time_str}"
                    })
                    parsed_exams.append(exam)
                except ValueError:
                    exam.update({'sort_key': datetime.max, 'date_str': '解析失败', 'time_range': time_str})
                    parsed_exams.append(exam)
            else:
                exam.update({'sort_key': datetime.max, 'date_str': '格式未知', 'time_range': time_str})
                parsed_exams.append(exam)

        return sorted(parsed_exams, key=lambda x: x['sort_key'])