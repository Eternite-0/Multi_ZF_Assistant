import unittest
from urllib.parse import urlparse

from pyquery import PyQuery as pq

from api.zfn_api import Client


class FakeResponse:
    def __init__(self, payload=None, text="", url="http://jw.example/test"):
        self._payload = payload
        self.text = text
        self.url = url
        self.status_code = 200
        self.encoding = "UTF-8"

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class StrictBlockCourseClient(Client):
    base_url = "http://jw.example/"

    def __init__(self):
        self.part_display_payload = None
        self.class_payloads = []
        self._hidden_values = {
            "firstKklxdm": "10",
            "firstKklxmc": "通识选修课",
            "firstXkkzId": "RIGHT_XKKZ_ID",
            "rwlx": "2",
            "xklc": "1",
            "xkly": "0",
            "bklx_id": "0",
            "sfkkjyxdxnxq": "0",
            "kzkcgs": "0",
            "xqh_id": "DYNAMIC_XQH",
            "jg_id": "DYNAMIC_JG",
            "zyh_id": "DYNAMIC_ZY",
            "zyfx_id": "DYNAMIC_ZYFX",
            "txbsfrl": "0",
            "njdm_id": "2026",
            "bh_id": "2026123456",
            "bjgkczxbbjwcx": "0",
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
            "bbhzxjxb": "0",
            "kkbk": "0",
            "kkbkdj": "0",
            "bklbkcj": "0",
            "sfkgbcx": "0",
            "sfrxtgkcxd": "0",
            "tykczgxdcs": "0",
            "xkxnm": "2026",
            "xkxqm": "3",
            "xkxskcgskg": "1",
            "rlkz": "0",
            "cdrlkz": "0",
            "rlzlkz": "1",
            "jxbzcxskg": "0",
            "xkzgbj": "0",
            "jxbzb": "",
            "xkmcjzxskcs": "10",
        }
        self._overview_courses = [
            self._course_row("COURSE_A", "课程A"),
            self._course_row("COURSE_B", "课程B"),
            self._course_row("COURSE_C", "课程C"),
        ]

    def _hidden_html(self):
        inputs = "".join(
            f'<input type="hidden" name="{name}" value="{value}"/>'
            for name, value in self._hidden_values.items()
        )
        return f"<html><body><form>{inputs}</form></body></html>"

    def _get_course_entry_page_doc(self):
        response = FakeResponse(text=self._hidden_html(), url=self.base_url + "xsxk/index")
        return pq(response.text), response

    def _course_row(self, course_id, title):
        return {
            "kch_id": course_id,
            "kcmc": title,
            "xf": "1.0",
            "cxbj": "0",
            "fxbj": "0",
        }

    def _class_row(self, course_id):
        return {
            "kch_id": course_id,
            "jxb_id": f"{course_id}_JXB",
            "do_jxb_id": f"{course_id}_DO",
            "jsxx": f"{course_id}教师",
            "jxbrl": "80",
            "yxzrs": "1",
            "jxdd": "教室",
            "sksj": "星期一第1-2节",
        }

    def _uses_current_payload(self, payload):
        return (
            payload.get("kklxdm") == self._hidden_values["firstKklxdm"]
            and payload.get("xkkz_id") == self._hidden_values["firstXkkzId"]
            and payload.get("xklc") == self._hidden_values["xklc"]
            and payload.get("xqh_id") == self._hidden_values["xqh_id"]
            and payload.get("jg_id") == self._hidden_values["jg_id"]
            and payload.get("xkxnm") == self._hidden_values["xkxnm"]
            and payload.get("xkxqm") == self._hidden_values["xkxqm"]
        )

    def _safe_request(self, method, url, **kwargs):
        path = urlparse(url).path.lower()
        if method == "GET" and "display" in path:
            return FakeResponse({})

        payload = kwargs.get("data") or {}
        if "partdisplay" in path:
            self.part_display_payload = payload
            page_start = int(payload.get("kspage", "0"))
            page_end = int(payload.get("jspage", "0"))
            if self._uses_current_payload(payload) and page_start == 1 and page_end >= len(self._overview_courses):
                return FakeResponse({"tmpList": self._overview_courses})
            return FakeResponse({"tmpList": self._overview_courses[:1]})

        if "withkch" in path:
            self.class_payloads.append(payload)
            if self._uses_current_payload(payload):
                return FakeResponse([self._class_row(payload["kch_id"])])
            return FakeResponse([])

        raise AssertionError(f"unexpected request: {method} {url}")


class TestBlockCoursesPayload(unittest.TestCase):
    def test_get_block_courses_uses_current_hidden_payload_and_fetches_full_page(self):
        client = StrictBlockCourseClient()

        result = client.get_block_courses(block=1)

        self.assertEqual(1000, result["code"])
        courses = result["data"]["courses"]
        self.assertEqual(["COURSE_A", "COURSE_B", "COURSE_C"], [c["course_id"] for c in courses])
        self.assertEqual("RIGHT_XKKZ_ID", result["data"]["courses"][0]["xkkz_id"])
        self.assertEqual("通识选修课", result["data"]["block_name"])
        self.assertEqual(("1", "10"), (client.part_display_payload["kspage"], client.part_display_payload["jspage"]))
        self.assertTrue(all(payload["xkkz_id"] == "RIGHT_XKKZ_ID" for payload in client.class_payloads))

    def test_get_block_courses_follows_more_button_pagination(self):
        client = PaginatedBlockCourseClient()

        result = client.get_block_courses(block=1)

        self.assertEqual(1000, result["code"])
        self.assertEqual(["COURSE_A", "COURSE_B", "COURSE_C"], [c["course_id"] for c in result["data"]["courses"]])
        self.assertEqual([("1", "2"), ("3", "4")], client.part_display_ranges)


class PaginatedBlockCourseClient(StrictBlockCourseClient):
    def __init__(self):
        super().__init__()
        self._hidden_values["xkmcjzxskcs"] = "2"
        self.part_display_ranges = []

    def _safe_request(self, method, url, **kwargs):
        path = urlparse(url).path.lower()
        if method == "GET" and "display" in path:
            return FakeResponse({})

        payload = kwargs.get("data") or {}
        if "partdisplay" in path:
            page_range = (payload.get("kspage"), payload.get("jspage"))
            self.part_display_ranges.append(page_range)
            if not self._uses_current_payload(payload):
                return FakeResponse({"tmpList": []})
            pages = {
                ("1", "2"): self._overview_courses[:2],
                ("3", "4"): self._overview_courses[2:],
            }
            return FakeResponse({"tmpList": pages.get(page_range, [])})

        if "withkch" in path:
            self.class_payloads.append(payload)
            if self._uses_current_payload(payload):
                return FakeResponse([self._class_row(payload["kch_id"])])
            return FakeResponse([])

        raise AssertionError(f"unexpected request: {method} {url}")


if __name__ == "__main__":
    unittest.main()
