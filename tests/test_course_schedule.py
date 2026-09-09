import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from utils.course_schedule import load_schedule_workbook


class TestCourseSchedule(unittest.TestCase):
    def test_load_schedule_workbook_parses_teaching_class_rows(self):
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = "课表"
        worksheet.append(["教学班", "课程代码", "课程", "教师", "上课时间", "起始结束周"])
        worksheet.append([
            "(2026-2027-1)-77103130-02",
            "77103130",
            "飞镖3",
            "朱林凯",
            "星期四第5-6节{1-16周}",
            "1-16周",
        ])
        worksheet.append([
            "(2026-2027-1)-77103130-01",
            "77103130",
            "飞镖3",
            "朱林凯",
            "星期四第7-8节{1-16周}",
            "1-16周",
        ])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "schedule.xlsx"
            workbook.save(path)
            rows = load_schedule_workbook(path)

        self.assertEqual(2, len(rows))
        self.assertEqual({"77103130"}, {row["course_code"] for row in rows})
        self.assertEqual({"5-6", "7-8"}, {row["section"] for row in rows})
        self.assertEqual({"4"}, {row["weekday"] for row in rows})
        self.assertEqual({"1-16"}, {row["weeks"] for row in rows})


if __name__ == "__main__":
    unittest.main()
