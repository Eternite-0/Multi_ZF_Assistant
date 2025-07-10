import time
import json
from PyQt6.QtCore import QThread, pyqtSignal
from api.zfn_api import Client # 假设Client类的导入路径正确

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
    【最终正确版】志愿优先抢课工作线程.
    此版本假定 zfn_api.py 中的 api_client 实例已持有所有必需的静态payload，
    本线程只负责传递每门课程的动态参数。
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

    def run(self):
        grabbed_count = 0
        attempted_courses_set = set()

        self.status_update.emit(self.sid, f"任务启动，共 {len(self.priority_courses)} 个志愿，目标 {self.target_count} 门。")

        while grabbed_count < self.target_count and not self._is_stopped:
            next_course_to_try = None
            for course in self.priority_courses:
                course_unique_id = course.get('do_id') or course.get('class_id')
                if course_unique_id not in attempted_courses_set:
                    next_course_to_try = course
                    break

            if next_course_to_try is None:
                self.status_update.emit(self.sid, "所有备选志愿均已尝试完毕，任务结束。")
                break

            course_unique_id = next_course_to_try.get('do_id') or next_course_to_try.get('class_id')
            course_name = next_course_to_try.get('title', '未知课程')
            attempted_courses_set.add(course_unique_id)

            self.status_update.emit(self.sid, f"开始尝试抢课 (优先级: {len(attempted_courses_set)}): 《{course_name}》")

            # **【核心修正】** 从课程数据中提取调用 select_course 所需的【全部】关键动态参数
            # 我们相信这些参数将由 zfn_api.py 内部的 select_course 函数使用
            kch_id_to_select = next_course_to_try.get('course_id')
            do_id_to_select = next_course_to_try.get('do_id')
            kklxdm_to_select = next_course_to_try.get('kklxdm')
            xkkz_id_to_select = next_course_to_try.get('xkkz_id')

            # 检查动态参数是否齐全
            if not all([kch_id_to_select, do_id_to_select, kklxdm_to_select, xkkz_id_to_select]):
                self.status_update.emit(self.sid, f"❌ 抢课失败: 《{course_name}》的课程数据不完整，缺少必要的ID，已跳过。")
                continue

            try:
                # 【最终调用方式】直接调用您已封装好的 select_course 函数，
                # 它会自己组合完整的 payload。
                # 这里我们假设您 zfn_api.py 里的函数定义是：
                # def select_course(self, kch_id, do_id, kklxdm, xkkz_id):
                result = self.api_client.select_course(
                    kch_id=kch_id_to_select,
                    do_id=do_id_to_select,
                    kklxdm=kklxdm_to_select,
                    xkkz_id=xkkz_id_to_select
                )

                msg = result.get('msg', json.dumps(result))

                if result.get("code") == 1000:
                    grabbed_count += 1
                    self.status_update.emit(self.sid, f"✅✅✅ 巨大成功！已抢到课程: 《{course_name}》! (当前进度: {grabbed_count}/{self.target_count})")
                    if grabbed_count >= self.target_count:
                        self.status_update.emit(self.sid, f"🎉 目标达成！已抢到 {self.target_count} 门课程，任务完成。")
                        break
                else:
                    self.status_update.emit(self.sid, f"💨 《{course_name}》 抢课失败: {msg}。尝试下一志愿...")

            except Exception as e:
                # 捕获可能的参数不匹配错误或其他异常
                self.status_update.emit(self.sid, f"💥 调用API时出现异常: 《{course_name}》 - {e}，请检查workers.py与zfn_api.py的函数签名是否匹配。")

            if not self._is_stopped:
                # 建议保留一个小的延时
                time.sleep(1.2)

        if self._is_stopped:
            self.status_update.emit(self.sid, "任务已被用户手动停止。")
        else:
            self.status_update.emit(self.sid, "任务自然结束。")

        self.finished.emit(self.sid)

    def stop(self):
        self._is_stopped = True