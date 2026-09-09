import unittest

from utils.workers import ManualCourseFetchWorker, PriorityBatchGrabber


class _CourseClient:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def get_block_courses(self, block=1):
        self.calls += 1
        return self.result


class _JasThenRefreshClient:
    def __init__(self):
        self.select_calls = 0
        self.fetch_calls = 0

    def select_course(self, course):
        self.select_calls += 1
        if self.select_calls == 1:
            return {
                "code": 1010,
                "retryable": True,
                "session_refreshed": True,
                "msg": "JAS-04: 校验不通过，请刷新本网页",
            }
        self.last_course = course
        return {"code": 1000, "msg": "选课成功"}

    def get_block_courses(self, block=1):
        self.fetch_calls += 1
        return {
            "code": 1000,
            "data": {
                "courses": [
                    {
                        "course_id": "COURSE_A",
                        "class_id": "CLASS_A",
                        "do_id": "FRESH_DO_ID",
                        "title": "课程A",
                        "time": "星期一第1-2节{1-16周}",
                    }
                ]
            },
        }


class TestSharedCourseFetch(unittest.TestCase):
    def test_worker_fetches_one_shared_list_for_all_accounts(self):
        source = _CourseClient(
            {
                "code": 1000,
                "data": {"courses": [{"course_id": "A", "class_id": "CA", "do_id": "DO"}]},
            }
        )
        other = _CourseClient({"code": 999, "msg": "should not be called"})
        received = []
        worker = ManualCourseFetchWorker({"A001": source, "A002": other}, block=1)
        worker.result_ready.connect(lambda sid, result: received.append((sid, result)))

        worker.run()

        self.assertEqual(1, source.calls)
        self.assertEqual(0, other.calls)
        self.assertEqual(["A001", "A002"], [sid for sid, _ in received])
        self.assertFalse(received[0][1]["shared_course_list"])
        self.assertTrue(received[1][1]["shared_course_list"])
        self.assertEqual("A001", received[1][1]["shared_from"])
        self.assertIsNot(received[0][1]["data"], received[1][1]["data"])

    def test_jas_failure_can_trigger_only_current_account_full_refresh(self):
        client = _JasThenRefreshClient()
        course = {
            "course_id": "COURSE_A",
            "class_id": "CLASS_A",
            "do_id": "OLD_DO_ID",
            "title": "课程A",
            "time": "星期一第1-2节{1-16周}",
        }
        grabber = PriorityBatchGrabber(client, "A001", [course], 1, block=1)
        grabber._sleep_interruptibly = lambda seconds: False

        grabber.run()

        self.assertEqual(2, client.select_calls)
        self.assertEqual(1, client.fetch_calls)
        self.assertEqual("FRESH_DO_ID", client.last_course["do_id"])


if __name__ == "__main__":
    unittest.main()
