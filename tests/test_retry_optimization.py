import unittest
from unittest.mock import patch
from urllib.parse import urlparse

from pyquery import PyQuery as pq
from requests import exceptions

from api.zfn_api import Client
from core.session_manager import SessionManager
from utils import workers
from utils.course_matching import course_identity, manual_course_matches, remap_wishlist_courses


class FakeResponse:
    def __init__(self, payload=None, text="", status_code=200, url="http://jw.example/test"):
        self._payload = payload
        self.text = text
        self.status_code = status_code
        self.url = url
        self.encoding = "UTF-8"

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class FlakySession:
    def __init__(self):
        self.headers = {}
        self.cookies = {}
        self.calls = 0

    def request(self, method, url, **kwargs):
        self.calls += 1
        if self.calls == 1:
            raise exceptions.Timeout("server busy")
        return FakeResponse({"ok": True}, text='{"ok": true}', url=url)


class SelectPayloadClient(Client):
    base_url = "http://jw.example/"

    def __init__(self):
        self.captured_payload = None
        self._cached_hidden = {
            "firstKklxdm": "10",
            "firstXkkzId": "CURRENT_XKKZ",
            "rwlx": "2",
            "xklc": "1",
            "xkly": "0",
            "bklx_id": "0",
            "sfkkjyxdxnxq": "0",
            "kzkcgs": "0",
            "xqh_id": "DYNAMIC_XQH",
            "jg_id_1": "DYNAMIC_JG",
            "zyh_id": "DYNAMIC_ZY",
            "zyfx_id": "DYNAMIC_ZYFX",
            "njdm_id": "2026",
            "bh_id": "2026123456",
            "xbm": "2",
            "xslbdm": "1",
            "mzm": "01",
            "xz": "4",
            "ccdm": "3",
            "xsbj": "0",
            "sfkknj": "0",
            "gnjkxdnj": "0",
            "sfkkzy": "0",
            "kzybkxy": "0",
            "sfznkx": "0",
            "zdkxms": "0",
            "sfkxq": "0",
            "sfkcfx": "0",
            "kkbk": "0",
            "kkbkdj": "0",
            "bklbkcj": "0",
            "sfkgbcx": "0",
            "sfrxtgkcxd": "0",
            "tykczgxdcs": "0",
            "xkxnm": "2026",
            "xkxqm": "3",
            "rlkz": "0",
            "bbhzxjxb": "0",
            "xkxskcgskg": "1",
            "cdrlkz": "0",
            "rlzlkz": "1",
            "jxbzcxskg": "0",
            "xkzgbj": "0",
        }

    def _get_course_entry_page_doc(self):
        inputs = "".join(
            f'<input type="hidden" name="{name}" value="{value}"/>'
            for name, value in self._cached_hidden.items()
        )
        response = FakeResponse(text=f"<html><body>{inputs}</body></html>", url=self.base_url + "xsxk/index")
        return pq(response.text), response

    def _safe_request(self, method, url, **kwargs):
        path = urlparse(url).path.lower()
        if method == "GET" and "display" in path:
            return FakeResponse({})
        if "xkbcz" in path:
            self.captured_payload = kwargs.get("data") or {}
            return FakeResponse({"flag": "1", "msg": "ok"})
        raise AssertionError(f"unexpected request: {method} {url}")


class RetryThenSuccessClient:
    def __init__(self):
        self.calls = 0

    def select_course(self, course):
        self.calls += 1
        if self.calls == 1:
            return {"code": 1010, "retryable": True, "msg": "请求超时"}
        return {"code": 1000, "msg": "选课成功"}


class JasRefreshThenSuccessClient:
    def __init__(self):
        self.calls = 0
        self.refreshes = 0
        self._cached_hidden = {
            "firstKklxdm": "OLD_KKLX",
            "firstXkkzId": "OLD_XKKZ",
        }

    def _refresh_session(self):
        self.refreshes += 1
        self._cached_hidden = {
            "firstKklxdm": "NEW_KKLX",
            "firstXkkzId": "NEW_XKKZ",
        }
        return True

    def select_course(self, course):
        self.calls += 1
        if self.calls == 1:
            return {"code": 1007, "msg": "JAS-04: 校验不通过，请刷新本网页"}
        self.last_course = course
        return {"code": 1000, "msg": "选课成功"}


class HiddenRefreshClient(SelectPayloadClient):
    def __init__(self):
        super().__init__()
        self._cached_hidden["firstXkkzId"] = "NEW_HIDDEN"


class OperationIdRefreshClient(SelectPayloadClient):
    def __init__(self):
        super().__init__()
        self.operation_refresh_calls = 0
        self._cached_hidden["firstXkkzId"] = "CURRENT_XKKZ"

    def _refresh_course_operation_id(self, course_data):
        self.operation_refresh_calls += 1
        refreshed = dict(course_data)
        refreshed["do_id"] = "FRESH_DO_ID"
        return refreshed

    def _refresh_session(self):
        return True

    def _safe_request(self, method, url, **kwargs):
        if "xkbcz" in url.lower():
            self.captured_payload = kwargs.get("data") or {}
            if self.captured_payload.get("jxb_ids") == "OLD_DO_ID":
                return FakeResponse({"flag": "0", "msg": "JAS-04: 校验不通过，请刷新本网页"})
            return FakeResponse({"flag": "1", "msg": "ok"})
        return super()._safe_request(method, url, **kwargs)


class FullThenSuccessClient:
    def __init__(self):
        self.calls = 0

    def select_course(self, course):
        self.calls += 1
        if self.calls == 1:
            return {"code": 1007, "msg": "人数已满"}
        return {"code": 1000, "msg": "选课成功"}


class TestRetryOptimization(unittest.TestCase):
    def test_course_identity_ignores_session_operation_token(self):
        old = {
            "course_id": "COURSE_A", "class_id": "CLASS_A", "do_id": "OLD_TOKEN",
            "title": "课程A", "teacher": "老师", "time": "星期一第1-2节",
        }
        fresh = dict(old, do_id="FRESH_TOKEN", selected_number=12)

        self.assertEqual(course_identity(old), course_identity(fresh))
        self.assertEqual(course_identity(old), workers.PriorityBatchGrabber._course_id(old, 0))

    def test_remap_wishlist_preserves_selected_section_and_priority(self):
        first_saved = {
            "course_id": "COURSE_A", "class_id": "CLASS_A", "do_id": "OLD_A",
            "title": "飞镖俱乐部", "teacher": "张老师", "time": "星期一第5-6节",
        }
        second_saved = {
            "course_id": "COURSE_A", "class_id": "CLASS_B", "do_id": "OLD_B",
            "title": "飞镖俱乐部", "teacher": "张老师", "time": "星期一第7-8节",
        }
        fresh_a = dict(first_saved, do_id="FRESH_A", selected_number=1)
        # Same title/teacher but a different teaching class must not be selected.
        fresh_b = dict(second_saved, do_id="FRESH_B", selected_number=2)

        remapped = remap_wishlist_courses([second_saved, first_saved], [fresh_a, fresh_b])

        self.assertEqual(["CLASS_B", "CLASS_A"], [c["class_id"] for c in remapped])
        self.assertEqual(["FRESH_B", "FRESH_A"], [c["do_id"] for c in remapped])

    def test_remap_wishlist_migrates_legacy_row_without_class_id(self):
        saved = {
            "course_id": "COURSE_A", "do_id": "OLD_TOKEN",
            "title": "课程A", "teacher": "老师", "time": "星期一第1-2节",
        }
        fresh = dict(saved, class_id="CLASS_A", do_id="FRESH_TOKEN")

        remapped = remap_wishlist_courses([saved], [fresh])

        self.assertEqual("CLASS_A", remapped[0]["class_id"])
        self.assertEqual("FRESH_TOKEN", remapped[0]["do_id"])

    def test_remap_wishlist_does_not_guess_between_duplicate_legacy_sections(self):
        saved = {
            "course_id": "COURSE_A", "do_id": "OLD_TOKEN",
            "title": "课程A", "teacher": "老师", "time": "星期一第1-2节",
        }
        fresh_a = dict(saved, class_id="CLASS_A", do_id="FRESH_A")
        fresh_b = dict(saved, class_id="CLASS_B", do_id="FRESH_B")

        remapped = remap_wishlist_courses([saved], [fresh_a, fresh_b])

        self.assertIs(remapped[0], saved)

    def test_manual_course_match_accepts_teacher_title_and_week_suffix(self):
        course = {
            "course_id": "TYQ3",
            "title": "飞镖俱乐部",
            "teacher": "09044/朱林凯/讲师",
            "time": "星期一第5-6节{1-12周}",
        }
        spec = {"course_code": "TYQ3", "title": "飞镖俱乐部", "teacher": "朱林凯", "weekday": "1", "section": "5-6", "weeks": "1-12周"}
        self.assertTrue(manual_course_matches(course, spec))

    def test_manual_course_code_is_course_level_but_time_keeps_sections_distinct(self):
        """相同课程代码可能有多个教学班，不能因此忽略上课时间。"""
        selected = {
            "course_code": "TYQ3",
            "title": "飞镖俱乐部",
            "teacher": "朱林凯",
            "weekday": "四",
            "section": "5-6",
            "weeks": "1-16周",
        }
        same_course_same_slot = {
            "course_id": "TYQ3",
            "title": "飞镖俱乐部",
            "teacher": "09044/朱林凯/讲师",
            "time": "星期四第5-6节{1-16周}",
        }
        same_course_other_slot = {
            **same_course_same_slot,
            "time": "星期四第7-8节{1-16周}",
        }

        self.assertTrue(manual_course_matches(same_course_same_slot, selected))
        self.assertFalse(manual_course_matches(same_course_other_slot, selected))

    def test_manual_course_code_mismatch_is_rejected(self):
        course = {
            "course_id": "TYQ3",
            "title": "飞镖俱乐部",
            "teacher": "朱林凯",
            "time": "星期四第5-6节{1-16周}",
        }
        spec = {
            "course_code": "TJJ3",
            "title": "飞镖俱乐部",
            "teacher": "朱林凯",
            "weekday": "四",
            "section": "5-6",
            "weeks": "1-16周",
        }
        self.assertFalse(manual_course_matches(course, spec))

    def test_manual_course_code_prefers_visible_code_over_internal_course_id(self):
        """页面课程代码和接口内部 course_id 不同时，仍应匹配用户输入的课程代码。"""
        course = {
            "course_id": "B2116D828D0E10F5E0530BC6A8C00660",
            "course_code": "77103130",
            "title": "飞镖3",
            "teacher": "09044/朱林凯/讲师",
            "time": "星期四第5-6节{1-16周}",
        }
        spec = {
            "course_code": "77103130",
            "title": "飞镖3",
            "teacher": "朱林凯",
            "weekday": "四",
            "section": "5-6",
            "weeks": "1-16周",
        }
        self.assertTrue(manual_course_matches(course, spec))

    def test_session_manager_retries_timeout_once_before_succeeding(self):
        sleeps = []
        manager = SessionManager(
            "http://jw.example/",
            timeout=3,
            max_retries=1,
            backoff_base=0.1,
            sleep_func=sleeps.append,
            random_func=lambda low, high: 0,
        )
        manager.is_logged_in = True
        manager.session = FlakySession()

        response = manager.request("GET", "http://jw.example/ping", retryable=True)

        self.assertEqual(200, response.status_code)
        self.assertEqual(2, manager.session.calls)
        self.assertEqual([0.1], sleeps)

    def test_select_course_uses_dynamic_course_and_hidden_payload(self):
        client = SelectPayloadClient()
        course = {
            "course_id": "COURSE_A",
            "do_id": "DO_A",
            "title": "课程A",
            "kklxdm": "10",
            "xkkz_id": "CURRENT_XKKZ",
            "cxbj": "0",
            "fxbj": "0",
        }

        result = client.select_course(course)

        self.assertEqual(1000, result["code"])
        self.assertEqual("CURRENT_XKKZ", client.captured_payload["xkkz_id"])
        self.assertEqual("1", client.captured_payload["xklc"])
        self.assertEqual("DYNAMIC_XQH", client.captured_payload["xqh_id"])
        self.assertEqual("2026", client.captured_payload["xkxnm"])
        self.assertEqual("3", client.captured_payload["xkxqm"])

    def test_priority_grabber_retries_retryable_timeout_for_same_course(self):
        api_client = RetryThenSuccessClient()
        course = {
            "course_id": "COURSE_A",
            "do_id": "DO_A",
            "title": "课程A",
            "kklxdm": "10",
            "xkkz_id": "CURRENT_XKKZ",
        }
        grabber = workers.PriorityBatchGrabber(api_client, "20240001", [course], 1)

        with patch.object(workers.time, "sleep", lambda seconds: None):
            grabber.run()

        self.assertEqual(2, api_client.calls)

    def test_priority_grabber_refreshes_session_on_jas04(self):
        api_client = JasRefreshThenSuccessClient()
        course = {
            "course_id": "COURSE_A",
            "do_id": "DO_A",
            "title": "课程A",
            "kklxdm": "OLD_KKLX",
            "xkkz_id": "OLD_XKKZ",
        }
        grabber = workers.PriorityBatchGrabber(api_client, "20240001", [course], 1)
        grabber._sleep_interruptibly = lambda seconds: False

        grabber.run()

        self.assertEqual(2, api_client.calls)
        self.assertEqual(1, api_client.refreshes)
        self.assertEqual("NEW_KKLX", api_client.last_course["kklxdm"])
        self.assertEqual("NEW_XKKZ", api_client.last_course["xkkz_id"])

    def test_priority_grabber_continues_polling_after_first_round(self):
        api_client = FullThenSuccessClient()
        course = {
            "course_id": "COURSE_A",
            "do_id": "DO_A",
            "title": "课程A",
            "kklxdm": "KKLX",
            "xkkz_id": "XKKZ",
        }
        grabber = workers.PriorityBatchGrabber(api_client, "20240001", [course], 1)
        grabber._sleep_interruptibly = lambda seconds: False

        grabber.run()

        self.assertEqual(2, api_client.calls)

    def test_select_course_prefers_current_hidden_over_cached_course_value(self):
        client = HiddenRefreshClient()
        course = {
            "course_id": "COURSE_A", "do_id": "DO_A", "title": "课程A",
            "kklxdm": "10", "xkkz_id": "OLD_COURSE_CACHE",
        }
        client.select_course(course)
        self.assertEqual("NEW_HIDDEN", client.captured_payload["xkkz_id"])

    def test_select_course_refreshes_only_operation_id_after_jas04(self):
        client = OperationIdRefreshClient()
        course = {
            "course_id": "COURSE_A", "class_id": "CLASS_A", "do_id": "OLD_DO_ID",
            "title": "课程A", "kklxdm": "10", "xkkz_id": "CURRENT_XKKZ",
        }

        result = client.select_course(course)

        self.assertEqual(1000, result["code"])
        self.assertEqual(1, client.operation_refresh_calls)
        self.assertEqual("FRESH_DO_ID", client.captured_payload["jxb_ids"])


if __name__ == "__main__":
    unittest.main()
