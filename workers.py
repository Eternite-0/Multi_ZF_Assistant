import time
import json
import random
import threading
from PyQt6.QtCore import QThread, pyqtSignal
from api.zfn_api import Client # 假设Client类的导入路径正确
from core.webvpn import is_lingnan_webvpn_url

class ApiWorker(QThread):
    """通用的API请求工作线程"""
    result_ready = pyqtSignal(object)

    def __init__(self, api_client, action, params=None):
        super().__init__()
        self.api_client = api_client
        self.action = action
        self.params = params if params is not None else {}

    def run(self):
        """执行API请求"""
        try:
            method = getattr(self.api_client, self.action)
            result = method(**self.params)
            self.result_ready.emit(result)
        except Exception as e:
            self.result_ready.emit({"code": 999, "msg": f"执行操作时出现异常: {e}"})


class BatchLoginWorker(QThread):
    """批量登录工作线程"""
    account_status_update = pyqtSignal(str, str, object)
    webvpn_captcha_required = pyqtSignal(str, str, object, object)
    finished = pyqtSignal()

    def __init__(self, credentials_list, timeout):
        super().__init__()
        self.credentials_list = credentials_list
        self.timeout = timeout
        self.threads = []

    def run(self):
        for creds in self.credentials_list:
            thread = self._create_login_thread(creds)
            self.threads.append(thread)
            thread.start()
        for thread in self.threads:
            thread.wait()
        self.finished.emit()

    def _create_login_thread(self, creds):
        """为单个账户创建登录线程"""
        class LoginSubThread(QThread):
            def __init__(self, parent_worker, credentials):
                super().__init__()
                self.parent = parent_worker
                self.creds = credentials

            def run(self):
                sid = self.creds.sid
                try:
                    self.parent.account_status_update.emit(sid, "正在登录...", None)
                    api_client = Client(base_url=self.creds.url, timeout=self.parent.timeout)
                    login_mode = (
                        "webvpn"
                        if (
                            getattr(self.creds, "use_webvpn", False)
                            or is_lingnan_webvpn_url(self.creds.url)
                        )
                        else getattr(self.creds, "login_mode", "campus")
                    )
                    if login_mode == "webvpn":
                        challenge = api_client.begin_webvpn_login()
                        if challenge.get("code") != 1001:
                            self.parent.account_status_update.emit(sid, f"❌ WebVPN 初始化失败: {challenge.get('msg', '未知错误')}", None)
                            return
                        reply = {}
                        ready = threading.Event()
                        self.parent.webvpn_captcha_required.emit(
                            sid, challenge["data"]["captcha_image"], reply, ready
                        )
                        if not ready.wait(120) or not reply.get("captcha"):
                            self.parent.account_status_update.emit(sid, "❌ WebVPN 验证码已取消或超时", None)
                            return
                        vpn_result = api_client.complete_webvpn_login(
                            self.creds.webvpn_sid or sid,
                            self.creds.webvpn_password or self.creds.password,
                            reply["captcha"],
                        )
                        if vpn_result.get("code") != 1000:
                            self.parent.account_status_update.emit(sid, f"❌ WebVPN 登录失败: {vpn_result.get('msg', '未知错误')}", None)
                            return
                        verification = api_client.get_info()
                        if verification.get("code") == 1000:
                            self.parent.account_status_update.emit(sid, "✅ WebVPN 单点登录成功", api_client)
                        else:
                            self.parent.account_status_update.emit(sid, "WebVPN 登录成功，正在登录教务系统...", None)
                            result = api_client.login(sid, self.creds.password)
                            if result.get('code') == 1000:
                                self.parent.account_status_update.emit(sid, "✅ 登录成功", api_client)
                            else:
                                self.parent.account_status_update.emit(
                                    sid, f"❌ 教务系统登录失败: {result.get('msg', '未知错误')}", None
                                )
                        return
                    result = api_client.login(sid, self.creds.password)
                    if result.get('code') == 1000:
                        self.parent.account_status_update.emit(sid, "✅ 登录成功", api_client)
                    elif result.get('code') == 1001:
                        self.parent.account_status_update.emit(sid, "⚠️ 需要验证码，请在单点登录后重试", None)
                    else:
                        msg = result.get('msg', '未知错误')
                        self.parent.account_status_update.emit(sid, f"❌ 登录失败: {msg}", None)
                except Exception as e:
                    self.parent.account_status_update.emit(sid, f"❌ 登录异常: {e}", None)
        return LoginSubThread(self, creds)


class BatchActionWorker(QThread):
    """批量执行API操作的工作线程"""
    action_result = pyqtSignal(str, str, object)
    progress_update = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, logged_in_clients, action, params=None):
        super().__init__()
        self.clients = logged_in_clients
        self.action = action
        self.params = params if params is not None else {}
        self.threads = []

    def run(self):
        total = len(self.clients)
        count = 0
        for sid, client in self.clients.items():
            count += 1
            self.progress_update.emit(f"({count}/{total}) 正在为学号 {sid} 执行操作: {self.action}...")
            thread = self._create_action_thread(sid, client)
            self.threads.append(thread)
            thread.start()
        for thread in self.threads:
            thread.wait()
        self.finished.emit()
    
    def _create_action_thread(self, sid, client):
        """为单个客户端创建动作线程"""
        class ActionSubThread(QThread):
            def __init__(self, parent_worker, sid, client_instance):
                super().__init__()
                self.parent = parent_worker
                self.sid = sid
                self.client = client_instance

            def run(self):
                try:
                    method = getattr(self.client, self.parent.action)
                    params = {'student_id': self.sid} if self.parent.action == 'get_academia_pdf' else self.parent.params
                    result = method(**params)
                    self.parent.action_result.emit(self.sid, self.parent.action, result)
                except Exception as e:
                    result = {"code": 999, "msg": f"执行操作时出现异常: {e}"}
                    self.parent.action_result.emit(self.sid, self.parent.action, result)
        return ActionSubThread(self, sid, client)


class PriorityBatchGrabber(QThread):
    """
    志愿优先抢课工作线程。

    抢课窗口内课程名额可能随时释放，因此所有志愿跑完后不能直接结束，
    而是会按优先级持续轮询，直到达到目标或用户点击停止。遇到 JAS-04
    时会刷新教务/选课会话和动态 hidden 参数，然后重试当前志愿。
    """
    status_update = pyqtSignal(str, str)
    finished = pyqtSignal(str)

    def __init__(self, api_client, sid, priority_courses, target_count):
        super().__init__()
        self.api_client = api_client
        self.sid = sid
        self.priority_courses = priority_courses
        self.target_count = target_count
        self._is_stopped = False
        self._stop_event = threading.Event()

    @staticmethod
    def _course_id(course, index):
        """返回稳定的课程标识，避免缺少 ID 时把所有课程视为同一门。"""
        return course.get("do_id") or course.get("class_id") or course.get("course_id") or f"index:{index}"

    def _sleep_interruptibly(self, seconds):
        """可被 stop() 提前唤醒的等待，避免停止任务时还要等完整延时。"""
        return self._stop_event.wait(max(0.0, seconds))

    def _refresh_course_session(self, course):
        """刷新 JAS-04 会话，并用最新页面参数重试当前课程。"""
        refresh = getattr(self.api_client, "_refresh_session", None)
        if not callable(refresh):
            return course, False

        try:
            refreshed = refresh()
        except Exception as exc:
            self.status_update.emit(self.sid, f"⚠️ 刷新选课会话失败: {exc}")
            return course, False

        # 新页面中的板块参数可能已经变化，不能继续使用旧志愿缓存里的值。
        hidden = getattr(self.api_client, "_cached_hidden", {}) or {}
        if not hidden:
            return course, bool(refreshed)

        refreshed_course = dict(course)
        kklxdm = hidden.get("firstKklxdm") or hidden.get("kklxdm")
        xkkz_id = hidden.get("firstXkkzId") or hidden.get("xkkz_id")
        if kklxdm:
            refreshed_course["kklxdm"] = kklxdm
        if xkkz_id:
            refreshed_course["xkkz_id"] = xkkz_id
        return refreshed_course, bool(refreshed)

    def run(self):
        grabbed_count = 0
        invalid_courses = set()
        grabbed_course_ids = set()
        round_number = 0

        self.status_update.emit(
            self.sid,
            f"任务启动，共 {len(self.priority_courses)} 个志愿，目标 {self.target_count} 门；"
            "将持续轮询，直到达成目标或手动停止。",
        )
        self._sleep_interruptibly(random.uniform(0, 0.8))

        while grabbed_count < self.target_count and not self._is_stopped:
            round_number += 1
            self.status_update.emit(self.sid, f"🔄 开始第 {round_number} 轮志愿轮询。")
            made_request = False

            for index, original_course in enumerate(self.priority_courses):
                if self._is_stopped or grabbed_count >= self.target_count:
                    break

                course_unique_id = self._course_id(original_course, index)
                if course_unique_id in invalid_courses or course_unique_id in grabbed_course_ids:
                    continue

                course = original_course
                course_name = course.get("title", "未知课程")
                required_fields = ["course_id", "do_id", "kklxdm", "xkkz_id"]
                missing_fields = [field for field in required_fields if not course.get(field)]
                if missing_fields:
                    invalid_courses.add(course_unique_id)
                    self.status_update.emit(
                        self.sid,
                        f"❌ 《{course_name}》课程数据不完整，缺少字段: "
                        f"{', '.join(missing_fields)}，不再重复尝试。",
                    )
                    continue

                self.status_update.emit(
                    self.sid,
                    f"开始尝试抢课 (优先级: {index + 1}): 《{course_name}》",
                )
                msg = ""
                jas_retry_count = 0
                max_attempts = 3

                for attempt in range(1, max_attempts + 1):
                    if self._is_stopped:
                        break
                    made_request = True
                    try:
                        result = self.api_client.select_course(course)
                        if not isinstance(result, dict):
                            result = {"code": 999, "msg": str(result)}
                    except Exception as exc:
                        result = {"code": 1010, "retryable": True, "msg": str(exc)}

                    msg = str(result.get("msg", json.dumps(result, ensure_ascii=False)))
                    if result.get("code") == 1000:
                        grabbed_count += 1
                        grabbed_course_ids.add(course_unique_id)
                        self.status_update.emit(
                            self.sid,
                            f"✅✅✅ 抢到课程: 《{course_name}》! "
                            f"(当前进度: {grabbed_count}/{self.target_count})",
                        )
                        break

                    is_jas = any(token in msg for token in ["JAS-04", "校验不通过", "刷新本网页"])
                    if is_jas and jas_retry_count < 2 and attempt < max_attempts:
                        jas_retry_count += 1
                        self.status_update.emit(
                            self.sid,
                            f"⚠️ 《{course_name}》遇到会话校验问题，正在刷新选课会话 "
                            f"({jas_retry_count}/2) 后重试当前志愿...",
                        )
                        course, refreshed = self._refresh_course_session(course)
                        if not refreshed:
                            self.status_update.emit(self.sid, "⚠️ 会话刷新未完成，稍后继续轮询。")
                        if self._sleep_interruptibly(1.0):
                            break
                        continue

                    retryable = bool(result.get("retryable")) or any(
                        token in msg
                        for token in [
                            "请求超时",
                            "网络繁忙",
                            "请求失败",
                            "Timeout",
                            "timed out",
                            "Connection",
                            "HTTP 502",
                            "HTTP 503",
                            "HTTP 504",
                        ]
                    )
                    if retryable and attempt < max_attempts:
                        delay = min(0.8 * (2 ** (attempt - 1)), 4.0) + random.uniform(0, 0.5)
                        self.status_update.emit(
                            self.sid,
                            f"⏳ 《{course_name}》网络繁忙/超时，第 {attempt}/{max_attempts} 次失败，"
                            f"{delay:.1f}s 后重试当前志愿...",
                        )
                        if self._sleep_interruptibly(delay):
                            break
                        continue

                    if "容量满" in msg or "人数已满" in msg:
                        self.status_update.emit(self.sid, f"📵 《{course_name}》暂时已满，本轮结束后继续轮询。")
                    elif "时间冲突" in msg:
                        self.status_update.emit(self.sid, f"⏰ 《{course_name}》存在时间冲突，本轮结束后继续轮询。")
                    elif is_jas:
                        self.status_update.emit(self.sid, f"⚠️ 《{course_name}》会话校验仍失败，本轮结束后继续轮询。")
                    else:
                        self.status_update.emit(self.sid, f"💨 《{course_name}》本次未成功: {msg}，后续轮次继续尝试。")
                    break

                if grabbed_count >= self.target_count:
                    break
                if not self._is_stopped:
                    self._sleep_interruptibly(random.uniform(0.8, 1.5))

            if grabbed_count >= self.target_count or self._is_stopped:
                break

            if not made_request:
                self.status_update.emit(self.sid, "没有可用的课程数据，任务结束。")
                break

            # 一轮结束后稍作退避，降低高峰期触发限流的概率，再从第一志愿开始。
            delay = random.uniform(2.0, 4.0)
            self.status_update.emit(self.sid, f"本轮志愿已尝试完毕，{delay:.1f}s 后开始下一轮轮询。")
            self._sleep_interruptibly(delay)

        if self._is_stopped:
            self.status_update.emit(self.sid, "任务已被用户手动停止。")
        else:
            if grabbed_count >= self.target_count:
                self.status_update.emit(self.sid, f"🎉 目标达成！已抢到 {self.target_count} 门课程，任务完成。")
            else:
                self.status_update.emit(self.sid, "任务结束。")

        self.finished.emit(self.sid)

    def stop(self):
        self._is_stopped = True
        self._stop_event.set()
