import json
import os
import tempfile
import unittest

from ui.main_window import ZFN_GUI


class FakeText:
    def __init__(self, value):
        self.value = value

    def text(self):
        return self.value

    def currentText(self):
        return self.value


class FakeLog:
    def __init__(self):
        self.messages = []

    def append(self, message):
        self.messages.append(message)


class TestCoursesCache(unittest.TestCase):
    def test_save_courses_cache_prefers_real_block_name_from_metadata(self):
        fake_window = type("FakeWindow", (), {})()
        fake_window.grab_year_display = FakeText("2026")
        fake_window.grab_term_input = FakeText("第一学期")
        fake_window.grab_block_input = FakeText("专业选修课")
        fake_window.grab_log_display = FakeLog()

        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmpdir:
            os.chdir(tmpdir)
            try:
                ZFN_GUI.save_courses_cache(
                    fake_window,
                    [{"course_id": "COURSE_A"}],
                    {"block_name": "通识选修课"},
                )
            finally:
                os.chdir(old_cwd)

            latest_path = os.path.join(tmpdir, "cache", "courses_2026_第一学期_通识选修课_latest.json")
            self.assertTrue(os.path.exists(latest_path))
            with open(latest_path, encoding="utf-8") as f:
                cache_data = json.load(f)
            self.assertEqual("通识选修课", cache_data["block"])


if __name__ == "__main__":
    unittest.main()
