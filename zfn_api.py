import base64
import binascii
import json
import re
import time
import traceback
import unicodedata
from urllib.parse import urljoin

import requests
import rsa
from pyquery import PyQuery as pq
from requests import exceptions
from core.session_manager import SessionManager

RASPIANIE = [
    ["8:00", "8:40"],
    ["8:45", "9:25"],
    ["9:30", "10:10"],
    ["10:30", "11:10"],
    ["11:15", "11:55"],
    ["14:30", "15:10"],
    ["15:15", "15:55"],
    ["16:05", "16:45"],
    ["16:50", "17:30"],
    ["18:40", "19:20"],
    ["19:25", "20:05"],
    ["20:10", "20:50"],
    ["20:55", "21:35"],
]


# 文件: api/zfn_api.py
class Client:
    raspisanie = []
    ignore_type = []

    def __init__(self, cookies={}, **kwargs):
        # 【修正】: 修正了初始化顺序，避免 AttributeError
        self.base_url = kwargs.get("base_url")
        if not self.base_url:
            raise ValueError("初始化 Client 时必须提供 base_url 参数")

        self.raspisanie = kwargs.get("raspisanie", RASPIANIE)
        self.ignore_type = kwargs.get("ignore_type", [])
        self.detail_category_type = kwargs.get("detail_category_type", [])
        self.timeout = kwargs.get("timeout", 10) # 适当增加超时时间
        Client.raspisanie = self.raspisanie
        Client.ignore_type = self.ignore_type

        self.key_url = urljoin(self.base_url, "xtgl/login_getPublicKey.html")
        self.login_url = urljoin(self.base_url, "xtgl/login_slogin.html")
        self.kaptcha_url = urljoin(self.base_url, "kaptcha")

        # 使用SessionManager替代原来的requests.Session
        self.session_manager = SessionManager(self.base_url, self.timeout)
        
        # 保持向后兼容性
        self.sess = self.session_manager.session
        self.cookies = cookies
        
        # 保持原有的headers设置，确保向后兼容
        self.headers = self.session_manager.session.headers
        
        # 如果提供了cookies，更新到session中
        if cookies:
            self.sess.cookies.update(cookies)

    # --- 辅助函数 ---
    def _safe_request(self, method, url, **kwargs):
        """安全的请求方法，使用SessionManager"""
        return self.session_manager.request(method, url, **kwargs)
    
    def get_login_status(self):
        """获取登录状态"""
        return self.session_manager.get_login_status()
    
    def _get_course_entry_page_doc(self):
        """获取选课入口页面，并返回解析后的PyQuery对象和原始响应"""
        url_entry = urljoin(self.base_url, "xsxk/zzxkyzb_cxZzxkYzbIndex.html?gnmkdm=N253512&layout=default")
        response = self.session_manager.get(url_entry)
        response.raise_for_status()
        response.encoding = 'UTF-8'
        
        doc = pq(response.text)
        if "用户登录" in doc.text():
            raise exceptions.RequestException("会话已失效，服务器返回了登录页面。")
        
        return doc, response

    def login(self, sid, password):
        """登录教务系统 - 使用SessionManager"""
        try:
            # 使用SessionManager进行登录
            result = self.session_manager.login(sid, password)
            
            # 如果登录成功，更新本地cookies
            if result.get('code') == 1000:
                self.cookies = result.get('data', {}).get('cookies', {})
                self.sess = self.session_manager.session
                
            return result
            
        except Exception as e:
            traceback.print_exc()
            return {"code": 999, "msg": f"登录时发生错误: {str(e)}"}

    def begin_webvpn_login(self):
        """获取校外 WebVPN 验证码挑战。仅在 base_url 为 WebVPN 地址时使用。"""
        return self.session_manager.begin_webvpn_login()

    def complete_webvpn_login(self, sid, password, captcha):
        """提交 WebVPN 验证码；成功后请再调用 ``login`` 登录教务系统。"""
        result = self.session_manager.complete_webvpn_login(sid, password, captcha)
        if result.get("code") == 1000:
            self.cookies = result.get("data", {}).get("cookies", {})
            self.sess = self.session_manager.session
        return result

    def login_with_kaptcha(
            self, sid, csrf_token, cookies, password, modulus, exponent, kaptcha, **kwargs
    ):
        """需要验证码的登陆"""
        try:
            encrypt_password = self.encrypt_password(password, modulus, exponent)
            login_data = {
                "csrftoken": csrf_token,
                "yhm": sid,
                "mm": encrypt_password,
                "yzm": kaptcha,
            }
            req_login = self.sess.post(
                self.login_url,
                headers=self.headers,
                cookies=cookies,
                data=login_data,
                timeout=self.timeout,
            )
            if req_login.status_code != 200:
                return {"code": 2333, "msg": "教务系统挂了"}
            # 请求登录
            doc = pq(req_login.text)
            tips = doc("p#tips")
            if str(tips) != "":
                if "验证码" in tips.text():
                    return {"code": 1004, "msg": "验证码输入错误"}
                if "用户名或密码" in tips.text():
                    return {"code": 1002, "msg": "用户名或密码不正确"}
                return {"code": 998, "msg": tips.text()}
            self.cookies = self.sess.cookies.get_dict()
            # 不同学校系统兼容差异
            if not self.cookies.get("route") and cookies.get("route"):
                route_cookies = {
                    "JSESSIONID": self.cookies["JSESSIONID"],
                    "route": cookies["route"],
                }
                self.cookies = route_cookies
            else:
                return {"code": 1000, "msg": "登录成功", "data": {"cookies": self.cookies}}
        except exceptions.Timeout:
            return {"code": 1003, "msg": "登录超时"}
        except (
                exceptions.RequestException,
                json.decoder.JSONDecodeError,
                AttributeError,
        ):
            traceback.print_exc()
            return {"code": 2333, "msg": "请重试，若多次失败可能是系统错误维护或需更新接口"}
        except Exception as e:
            traceback.print_exc()
            return {"code": 999, "msg": "验证码登录时未记录的错误：" + str(e)}

    def get_info(self):
        """获取个人信息"""
        url = urljoin(self.base_url, "xsxxxggl/xsxxwh_cxCkDgxsxx.html?gnmkdm=N100801")
        try:
            req_info = self._safe_request('GET', url)
            if req_info.status_code != 200:
                return {"code": 2333, "msg": "教务系统挂了"}
            doc = pq(req_info.text)
            if doc("h5").text() == "用户登录":
                return {"code": 1006, "msg": "未登录或已过期，请重新登录"}
            try:
                info = req_info.json()
            except json.decoder.JSONDecodeError:
                # WebVPN 转发有时将此接口包装为 HTML 页面；改用同一会话的
                # 页面版个人信息接口解析，不把有效的 SSO 会话误报为系统错误。
                return self._get_info()
            if info is None:
                return self._get_info()
            result = {
                "sid": info.get("xh"),
                "name": info.get("xm"),
                "college_name": info.get("zsjg_id", info.get("jg_id")),
                "major_name": info.get("zszyh_id", info.get("zyh_id")),
                "class_name": info.get("bh_id", info.get("xjztdm")),
                "status": info.get("xjztdm"),
                "enrollment_date": info.get("rxrq"),
                "candidate_number": info.get("ksh"),
                "graduation_school": info.get("byzx"),
                "domicile": info.get("jg"),
                "postal_code": info.get("yzbm"),
                "politics_status": info.get("zzmmm"),
                "nationality": info.get("mzm"),
                "education": info.get("pyccdm"),
                "phone_number": info.get("sjhm"),
                "parents_number": info.get("gddh"),
                "email": info.get("dzyx"),
                "birthday": info.get("csrq"),
                "id_number": info.get("zjhm"),
            }
            return {"code": 1000, "msg": "获取个人信息成功", "data": result}
        except exceptions.Timeout:
            return {"code": 1003, "msg": "获取个人信息超时"}
        except (
                exceptions.RequestException,
                json.decoder.JSONDecodeError,
                AttributeError,
        ):
            traceback.print_exc()
            return {"code": 2333, "msg": "请重试，若多次失败可能是系统错误维护或需更新接口"}
        except Exception as e:
            traceback.print_exc()
            return {"code": 999, "msg": "获取个人信息时未记录的错误：" + str(e)}

    def _get_info(self):
        """获取个人信息"""
        url = urljoin(self.base_url, "xsxxxggl/xsgrxxwh_cxXsgrxx.html?gnmkdm=N100801")
        try:
            req_info = self.sess.get(
                url, headers=self.headers, cookies=self.cookies, timeout=self.timeout
            )
            if req_info.status_code != 200:
                return {"code": 2333, "msg": "教务系统挂了"}
            doc = pq(req_info.text)
            if doc("h5").text() == "用户登录":
                return {"code": 1006, "msg": "未登录或已过期，请重新登录"}
            pending_result = {}
            # 学生基本信息
            for ul_item in doc.find("div.col-sm-6").items():
                content = pq(ul_item).find("div.form-group")
                # key = re.findall(r'^[\u4E00-\u9FA5A-Za-z0-9]+', pq(content).find('label.col-sm-4.control-label').text())[0]
                key = pq(content).find("label.col-sm-4.control-label").text()
                value = pq(content).find("div.col-sm-8 p.form-control-static").text()
                # 到这一步，解析到的数据基本就是一个键值对形式的html数据了，比如"[学号：]:123456"
                pending_result[key] = value
            # 学生学籍信息，其他信息，联系方式
            for ul_item in doc.find("div.col-sm-4").items():
                content = pq(ul_item).find("div.form-group")
                key = pq(content).find("label.col-sm-4.control-label").text()
                value = pq(content).find("div.col-sm-8 p.form-control-static").text()
                # 到这一步，解析到的数据基本就是一个键值对形式的html数据了，比如"[学号：]:123456"
                pending_result[key] = value
            if pending_result.get("学号：") == "":
                return {
                    "code": 1014,
                    "msg": "当前学年学期无学生时盒数据，您可能已经毕业了。\n\n如果是专升本同学，请使用专升本后的新学号登录～",
                }
            result = {
                "sid": pending_result["学号："],
                "name": pending_result["姓名："],
                 "birthday": "无" if pending_result.get("出生日期：") == '' else pending_result["出生日期："],
                 "id_number": "无" if pending_result.get("证件号码：") == '' else pending_result["证件号码："],
                 "candidate_number": "无" if pending_result.get("考生号：") == '' else pending_result["考生号："],
                 "status": "无" if pending_result.get("学籍状态：") == '' else pending_result["学籍状态："],
                 "entry_date": "无" if pending_result.get("入学日期：") == '' else pending_result["入学日期："],
                 "graduation_school": "无" if pending_result.get("毕业中学：") == '' else pending_result["毕业中学："],
                "domicile": "无"
                if pending_result.get("籍贯：") == ""
                else pending_result["籍贯："],
                "phone_number": "无"
                if pending_result.get("手机号码：") == ""
                else pending_result["手机号码："],
                "parents_number": "无",
                "email": "无"
                if pending_result.get("电子邮箱：") == ""
                else pending_result["电子邮箱："],
                "political_status": "无"
                if pending_result.get("政治面貌：") == ""
                else pending_result["政治面貌："],
                "national": "无"
                if pending_result.get("民族：") == ""
                else pending_result["民族："],
                # "education": "无" if pending_result.get("培养层次：") == '' else pending_result["培养层次："],
                # "postal_code": "无" if pending_result.get("邮政编码：") == '' else pending_result["邮政编码："],
                # "grade": int(pending_result["学号："][0:4]),
            }
            if pending_result.get("学院名称：") is not None:
                # 如果在个人信息页面获取到了学院班级
                result.update(
                    {
                        "college_name": "无"
                        if pending_result.get("学院名称：") == ""
                        else pending_result["学院名称："],
                        "major_name": "无"
                        if pending_result.get("专业名称：") == ""
                        else pending_result["专业名称："],
                        "class_name": "无"
                        if pending_result.get("班级名称：") == ""
                        else pending_result["班级名称："],
                    }
                )
            else:
                # 如果个人信息页面获取不到学院班级，则此处需要请求另外一个地址以获取学院、专业、班级等信息
                _url = urljoin(
                    self.base_url,
                    "xszbbgl/xszbbgl_cxXszbbsqIndex.html?doType=details&gnmkdm=N106005",
                )
                _req_info = self.sess.post(
                    _url,
                    headers=self.headers,
                    cookies=self.cookies,
                    timeout=self.timeout,
                    data={"offDetails": "1", "gnmkdm": "N106005", "czdmKey": "00"},
                )
                _doc = pq(_req_info.text)
                if _doc("p.error_title").text() != "无功能权限，":
                    # 通过学生证补办申请入口，来补全部分信息
                    for ul_item in _doc.find("div.col-sm-6").items():
                        content = pq(ul_item).find("div.form-group")
                        key = (
                                pq(content).find("label.col-sm-4.control-label").text()
                                + "："
                        )  # 为了保持格式一致，这里加个冒号
                        value = (
                            pq(content).find("div.col-sm-8 label.control-label").text()
                        )
                        # 到这一步，解析到的数据基本就是一个键值对形式的html数据了，比如"[学号：]:123456"
                        pending_result[key] = value
                    result.update(
                        {
                            "college_name": "无"
                            if pending_result.get("学院：") is None
                            else pending_result["学院："],
                            "major_name": "无"
                            if pending_result.get("专业：") is None
                            else pending_result["专业："],
                            "class_name": "无"
                            if pending_result.get("班级：") is None
                            else pending_result["班级："],
                        }
                    )
            return {"code": 1000, "msg": "获取个人信息成功", "data": result}
        except exceptions.Timeout:
            return {"code": 1003, "msg": "获取个人信息超时"}
        except (
                exceptions.RequestException,
                json.decoder.JSONDecodeError,
                AttributeError,
        ):
            traceback.print_exc()
            return {"code": 2333, "msg": "请重试，若多次失败可能是系统错误维护或需更新接口"}
        except Exception as e:
            traceback.print_exc()
            return {"code": 999, "msg": "获取个人信息时未记录的错误：" + str(e)}

    def get_grade(self, year: int, term: int = 0, use_personal_info: bool = False):
        """
        获取成绩
        use_personal_info: 是否使用获取个人信息接口获取成绩
        """
        url = urljoin(
            self.base_url,
            "cjcx/cjcx_cxDgXscj.html?doType=query&gnmkdm=N305005"
            if use_personal_info
            else "cjcx/cjcx_cxXsgrcj.html?doType=query&gnmkdm=N305005",
        )
        temp_term = term
        term = term ** 2 * 3
        term = "" if term == 0 else term
        data = {
            "xnm": str(year),  # 学年数
            "xqm": str(term),  # 学期数，第一学期为3，第二学期为12, 整个学年为空''
            "_search": "false",
            "nd": int(time.time() * 1000),
            "queryModel.showCount": "100",  # 每页最多条数
            "queryModel.currentPage": "1",
            "queryModel.sortName": "",
            "queryModel.sortOrder": "asc",
            "time": "0",  # 查询次数
        }
        try:
            req_grade = self.sess.post(
                url,
                headers=self.headers,
                data=data,
                cookies=self.cookies,
                timeout=self.timeout,
            )
            if req_grade.status_code != 200:
                return {"code": 2333, "msg": "教务系统挂了"}
            doc = pq(req_grade.text)
            if doc("h5").text() == "用户登录":
                return {"code": 1006, "msg": "未登录或已过期，请重新登录"}
            grade = req_grade.json()
            grade_items = grade.get("items")
            if not grade_items:
                return {"code": 1005, "msg": "获取内容为空"}
            result = {
                "sid": grade_items[0]["xh"],
                "name": grade_items[0]["xm"],
                "year": year,
                "term": temp_term,
                "count": len(grade_items),
                "courses": [
                    {
                        "course_id": i.get("kch_id"),
                        "title": i.get("kcmc"),
                        "teacher": i.get("jsxm"),
                        "class_name": i.get("jxbmc"),
                        "credit": self.align_floats(i.get("xf")),
                        "category": i.get("kclbmc"),
                        "nature": i.get("kcxzmc"),
                        "grade": self.parse_int(i.get("cj")),
                        "grade_point": self.align_floats(i.get("jd")),
                        "grade_nature": i.get("ksxz"),
                        "start_college": i.get("kkbmmc"),
                        "mark": i.get("kcbj"),
                    }
                    for i in grade_items
                ],
            }
            return {"code": 1000, "msg": "获取成绩成功", "data": result}
        except exceptions.Timeout:
            return {"code": 1003, "msg": "获取成绩超时"}
        except (
                exceptions.RequestException,
                json.decoder.JSONDecodeError,
                AttributeError,
        ):
            traceback.print_exc()
            return {"code": 2333, "msg": "请重试，若多次失败可能是系统错误维护或需更新接口"}
        except Exception as e:
            traceback.print_exc()
            return {"code": 999, "msg": "获取成绩时未记录的错误：" + str(e)}

    def get_exam_schedule(self, year: int, term: int = 0):
        """获取考试信息"""
        url = urljoin(
            self.base_url,
            "kwgl/kscx_cxXsksxxIndex.html?doType=query&gnmkdm=N358105",
        )
        temp_term = term
        term = term ** 2 * 3
        term = "" if term == 0 else term
        data = {
            "xnm": str(year),  # 学年数
            "xqm": str(term),  # 学期数，第一学期为3，第二学期为12, 整个学年为空''
            "_search": "false",
            "nd": int(time.time() * 1000),
            "queryModel.showCount": "100",  # 每页最多条数
            "queryModel.currentPage": "1",
            "queryModel.sortName": "",
            "queryModel.sortOrder": "asc",
            "time": "0",  # 查询次数
        }
        try:
            req_grade = self.sess.post(
                url,
                headers=self.headers,
                data=data,
                cookies=self.cookies,
                timeout=self.timeout,
            )
            if req_grade.status_code != 200:
                return {"code": 2333, "msg": "教务系统挂了"}
            doc = pq(req_grade.text)
            if doc("h5").text() == "用户登录":
                return {"code": 1006, "msg": "未登录或已过期，请重新登录"}
            grade = req_grade.json()
            grade_items = grade.get("items")
            if not grade_items:
                return {"code": 1005, "msg": "获取内容为空"}
            result = {
                "sid": grade_items[0]["xh"],
                "name": grade_items[0]["xm"],
                "year": year,
                "term": temp_term,
                "count": len(grade_items),
                "courses": [
                    {
                        "course_id": i.get("kch"),  # 课程代码
                        "title": i.get("kcmc"),  # 课程名称
                        "time": i.get("kssj"),  # 考试时间
                        "location": i.get("cdmc"),  # 考试地点
                        "xq": i.get("cdxqmc"),  # 考试校区
                        "zwh": i.get("zwh"),  # 考试座号
                        "cxbj": i.get("cxbj", ""),  # 重修标记
                        "exam_name": i.get("ksmc"),  # 考试批次名
                        "teacher": i.get("jsxx"),  # 任课教师(含教师id)
                        "class_name": i.get("jxbmc"),  # 教学班名称
                        "kkxy": i.get("kkxy"),  # 开课学院
                        "credit": self.align_floats(i.get("xf")),  # 课程学分数
                        "ksfs": i.get("ksfs"),  # 考试方式, ep: 笔试 & 开卷 & 机考
                        "sjbh": i.get("sjbh"),  # 试卷编号
                        "bz": i.get("bz1", ""),  # 备注, ep: 免监考班级
                    }
                    for i in grade_items
                ],
            }
            return {"code": 1000, "msg": "获取考试信息成功", "data": result}
        except exceptions.Timeout:
            return {"code": 1003, "msg": "获取考试信息超时"}
        except (
                exceptions.RequestException,
                json.decoder.JSONDecodeError,
                AttributeError,
        ):
            traceback.print_exc()
            return {"code": 2333, "msg": "请重试，若多次失败可能是系统错误维护或需更新接口"}
        except Exception as e:
            traceback.print_exc()
            return {"code": 999, "msg": "获取考试信息时未记录的错误：" + str(e)}

    def get_schedule(self, year: int, term: int):
        """获取课程表信息"""
        url = urljoin(self.base_url, "kbcx/xskbcx_cxXsKb.html?gnmkdm=N2151")
        temp_term = term
        term = term ** 2 * 3
        data = {"xnm": str(year), "xqm": str(term)}
        try:
            req_schedule = self.sess.post(
                url,
                headers=self.headers,
                data=data,
                cookies=self.cookies,
                timeout=self.timeout,
            )
            if req_schedule.status_code != 200:
                return {"code": 2333, "msg": "教务系统挂了"}
            doc = pq(req_schedule.text)
            if doc("h5").text() == "用户登录":
                return {"code": 1006, "msg": "未登录或已过期，请重新登录"}
            schedule = req_schedule.json()
            if not schedule.get("kbList"):
                return {"code": 1005, "msg": "获取内容为空"}
            result = {
                "sid": schedule["xsxx"].get("XH"),
                "name": schedule["xsxx"].get("XM"),
                "year": year,
                "term": temp_term,
                "count": len(schedule["kbList"]),
                "courses": [
                    {
                        "course_id": i.get("kch_id"),
                        "title": i.get("kcmc"),
                        "teacher": i.get("xm"),
                        "class_name": i.get("jxbmc"),
                        "credit": self.align_floats(i.get("xf")),
                        "weekday": self.parse_int(i.get("xqj")),
                        "time": self.display_course_time(i.get("jc")),
                        "sessions": i.get("jc"),
                        "list_sessions": self.list_sessions(i.get("jc")),
                        "weeks": i.get("zcd"),
                        "list_weeks": self.list_weeks(i.get("zcd")),
                        "evaluation_mode": i.get("khfsmc"),
                        "campus": i.get("xqmc"),
                        "place": i.get("cdmc"),
                        "hours_composition": i.get("kcxszc"),
                        "weekly_hours": self.parse_int(i.get("zhxs")),
                        "total_hours": self.parse_int(i.get("zxs")),
                    }
                    for i in schedule["kbList"]
                ],
                "extra_courses": [i.get("qtkcgs") for i in schedule.get("sjkList")],
            }
            result = self.split_merge_display(result)
            return {"code": 1000, "msg": "获取课表成功", "data": result}
        except exceptions.Timeout:
            return {"code": 1003, "msg": "获取课表超时"}
        except (
                exceptions.RequestException,
                json.decoder.JSONDecodeError,
                AttributeError,
        ):
            traceback.print_exc()
            return {"code": 2333, "msg": "请重试，若多次失败可能是系统错误维护或需更新接口"}
        except Exception as e:
            traceback.print_exc()
            return {"code": 999, "msg": "获取课表时未记录的错误：" + str(e)}

    def get_academia(self):
        """获取学业生涯情况"""
        url_main = urljoin(
            self.base_url,
            "xsxy/xsxyqk_cxXsxyqkIndex.html?gnmkdm=N105515&layout=default",
        )
        url_info = urljoin(
            self.base_url, "xsxy/xsxyqk_cxJxzxjhxfyqKcxx.html?gnmkdm=N105515"
        )
        try:
            req_main = self.sess.get(
                url_main,
                headers=self.headers,
                cookies=self.cookies,
                timeout=self.timeout,
                stream=True,
            )
            if req_main.status_code != 200:
                return {"code": 2333, "msg": "教务系统挂了"}
            doc_main = pq(req_main.text)
            if doc_main("h5").text() == "用户登录":
                return {"code": 1006, "msg": "未登录或已过期，请重新登录"}
            if str(doc_main("div.alert-danger")) != "":
                return {"code": 998, "msg": doc_main("div.alert-danger").text()}
            sid = doc_main("form#form input#xh_id").attr("value")
            display_statistics = (
                doc_main("div#alertBox").text().replace(" ", "").replace("\n", "")
            )
            sid = doc_main("input#xh_id").attr("value")
            statistics = self.get_academia_statistics(display_statistics)
            type_statistics = self.get_academia_type_statistics(req_main.text)
            details = {}
            for type in type_statistics.keys():
                details[type] = self.sess.post(
                    url_info,
                    headers=self.headers,
                    data={"xfyqjd_id": type_statistics[type]["id"]},
                    cookies=self.cookies,
                    timeout=self.timeout,
                    stream=True,
                ).json()
            result = {
                "sid": sid,
                "statistics": statistics,
                "details": [
                    {
                        "type": type,
                        "credits": type_statistics[type]["credits"],
                        "courses": [
                            {
                                "course_id": i.get("KCH"),
                                "title": i.get("KCMC"),
                                "situation": self.parse_int(i.get("XDZT")),
                                "display_term": self.get_display_term(
                                    sid, i.get("JYXDXNM"), i.get("JYXDXQMC")
                                ),
                                "credit": self.align_floats(i.get("XF")),
                                "category": self.get_course_category(type, i),
                                "nature": i.get("KCXZMC"),
                                "max_grade": self.parse_int(i.get("MAXCJ")),
                                "grade_point": self.align_floats(i.get("JD")),
                            }
                            for i in details[type]
                        ],
                    }
                    for type in type_statistics.keys()
                    if len(details[type]) > 0
                ],
            }
            return {"code": 1000, "msg": "获取学业情况成功", "data": result}
        except exceptions.Timeout:
            return {"code": 1003, "msg": "获取学业情况超时"}
        except (
                exceptions.RequestException,
                json.decoder.JSONDecodeError,
                AttributeError,
        ):
            traceback.print_exc()
            return {"code": 2333, "msg": "请重试，若多次失败可能是系统错误维护或需更新接口"}
        except Exception as e:
            traceback.print_exc()
            return {"code": 999, "msg": "获取学业情况时未记录的错误：" + str(e)}

    def get_academia_pdf(self, student_id: str):
        """
        获取学业生涯（学生成绩总表）pdf
        [终极解决方案 v5.0] 补全关键请求头(Referer), 修正请求参数
        """
        if not student_id:
            return {"code": 999, "msg": "未提供学生ID，无法继续导出PDF。"}

        # 1. 定义所有需要的URL和关键页面URL (用于Referer)
        main_page_url = urljoin(self.base_url, "bysxxcx/xscjzbdy_cxXscjzbdyIndex.html")
        url_view = urljoin(self.base_url, "bysxxcx/xscjzbdy_dyXscjzbView.html")
        url_count_check = urljoin(self.base_url, "bysxxcx/xscjzbdy_cxXsCount.html")
        url_file_type = urljoin(self.base_url, "bysxxcx/xscjzbdy_cxGswjlx.html")
        url_common_check = urljoin(self.base_url, "common/common_cxJwxtxx.html")
        url_final_list = urljoin(self.base_url, "bysxxcx/xscjzbdy_dyList.html")
        url_progress = urljoin(self.base_url, "xtgl/progress_cxProgressStatus.html")

        # 2. [核心修复] 为本次操作序列创建专用的请求头
        pdf_headers = self.headers.copy()
        pdf_headers["Referer"] = main_page_url
        pdf_headers["X-Requested-With"] = "XMLHttpRequest"

        try:
            # 3. 严格按照前端JS的顺序和参数执行AJAX请求链

            # 请求1: 打开打印设置对话框 (模拟会话)
            # 参照JS, 此请求包含 'dyly' 参数
            view_params = {"gnmkdm": "N558020", "dyly": "dy"}
            req_view = self.sess.post(url_view, headers=pdf_headers, params=view_params, cookies=self.cookies,
                                      timeout=self.timeout)
            if req_view.status_code != 200: return {"code": 2333, "msg": "教务系统挂了 (view)"}
            doc_view = pq(req_view.text)
            if doc_view("h5").text() == "用户登录": return {"code": 1006, "msg": "未登录或已过期，请重新登录"}

            # 从打印设置页面动态获取 gsdygx (打印格式ID)
            gsdygx_val = None
            options = doc_view("#gsdygx option")
            for opt in options.items():
                if "中文" in opt.text() or "默认" in opt.text() or "Chinese" in opt.text():
                    gsdygx_val = opt.val()
                    break
            if not gsdygx_val:
                gsdygx_val = options.eq(0).val() if options else None

            if not gsdygx_val:
                return {"code": 999, "msg": "无法从打印设置页面自动获取打印格式ID (gsdygx)，导出失败。"}

            # 4. 构造与前端 dyParamMap() 函数完全一致的参数字典
            parameterMap = {
                "jg_id": "", "njdm_id": "", "zyh_id": "", "bh_id": "", "xh": "",
                "gsdygx": gsdygx_val,
                "bmlbdm": "", "ids": student_id, "sfby_dm": "", "sfzx": "",
                "shzt": "", "xwshzt": "", "dyrq": "", "bdykc": "", "btmc": "",
                "bwnr": "", "dyfsdkc": "", "zdyjgcj": "", "dyzgcj": "", "bkalsftj": "",
                "cxalsftj": "", "bdycxbkcj": "", "bxsbylwtm": "", "xwrdkcxtj": "",
                "bkcxbj": "", "sfdysljcj": "", "sfdylnpjxfjd": "", "sfxsfx": "",
                "sfgz": "", "kcxzjcbj": "", "sfdypjf": "", "sfdypjjd": "",
                "BdykcmcDms": "", "startxq": "", "endxq": "", "sfqshr": "",
                "sfazjhnkctjxs": "", "sfzxszkcj": "", "bdykcxzDms": "",
                "cytjkcxzDms": "", "cytjkclbDms": "", "cytjkcgsDms": "",
                "bjgbdykcxzDms": "", "bjgbdyxxkcxzDms": "", "djksxmDms": "",
                "cjbzmcDms": "", "zdyfsxmDms": "",
                "cjdySzxs": "",
                "wjlx": "pdf"  # Start with a default
            }

            # 5. 继续执行请求链
            # 请求2: 检查是否可打印 (cxXsCount)
            req_count = self.sess.post(url_count_check, headers=pdf_headers, data=parameterMap, cookies=self.cookies,
                                       timeout=self.timeout)
            if "可打印" not in req_count.text:
                return {"code": 998, "msg": f"服务器检查不通过，无法打印: {req_count.text}"}

            # 请求3: 获取文件类型 (cxGswjlx)
            req_wjlx = self.sess.post(url_file_type, headers=pdf_headers, data=parameterMap, cookies=self.cookies,
                                      timeout=self.timeout)
            file_type = re.sub(r'[^a-zA-Z0-9]', '', req_wjlx.text)
            if file_type:
                parameterMap["wjlx"] = file_type

            # 请求4: 通用检查 (common_cxJwxtxx)
            self.sess.post(url_common_check, headers=pdf_headers, data={'xh_id': student_id}, cookies=self.cookies,
                           timeout=self.timeout)

            # 请求5: 最终生成PDF (dyList)
            req_file_path = self.sess.post(url_final_list, headers=pdf_headers, data=parameterMap, cookies=self.cookies,
                                           timeout=self.timeout + 5)

            if "成功" not in req_file_path.text:
                error_doc = pq(req_file_path.text)
                error_msg = error_doc("p.error_title").text() or error_doc("div.text").text() or "未知错误"
                return {"code": 998, "msg": f"生成PDF时出错: {error_msg}"}

            # 模拟进度条请求
            self.sess.post(url_progress, headers=pdf_headers, data={"key": "score_print_processed"},
                           cookies=self.cookies, timeout=self.timeout)

            # 6. 解析并清理路径，然后下载PDF
            pdf_path_raw = req_file_path.text.strip()
            pdf_path = pdf_path_raw.split("#")[0].replace('"', '').replace('\\', '/').strip()

            if not pdf_path or '.null' in pdf_path:
                return {"code": 998, "msg": f"未能从服务器获取到有效的PDF文件路径，得到: {pdf_path_raw}"}

            final_pdf_url = urljoin(self.base_url, pdf_path.lstrip('/'))

            req_pdf = self.sess.get(final_pdf_url, headers=pdf_headers, cookies=self.cookies, timeout=self.timeout + 15)

            # 7. 最终验证返回内容
            if 'application/pdf' not in req_pdf.headers.get('Content-Type', '').lower():
                return {"code": 999,
                        "msg": f"服务器未返回PDF文件，而是返回了HTML页面。请检查学号是否正确或该功能是否对您开放。URL: {final_pdf_url}"}

            if len(req_pdf.content) < 1024:
                return {"code": 999, "msg": f"收到的PDF文件过小({len(req_pdf.content)}字节)，可能是一个错误的空文件。"}

            return {"code": 1000, "msg": "获取学生成绩总表pdf成功", "data": req_pdf.content}

        except exceptions.Timeout:
            return {"code": 1003, "msg": "请求超时，请增加超时时间或检查网络连接。"}
        except Exception as e:
            traceback.print_exc()
            return {"code": 999, "msg": "获取成绩总表pdf时发生未记录的错误：" + str(e)}

    def get_schedule_pdf(self, year: int, term: int, name: str = "导出"):
        """获取课表pdf"""
        url_policy = urljoin(self.base_url, "kbdy/bjkbdy_cxXnxqsfkz.html")
        url_file = urljoin(self.base_url, "kbcx/xskbcx_cxXsShcPdf.html")
        origin_term = term
        term = term ** 2 * 3
        data = {
            "xm": name,
            "xnm": str(year),
            "xqm": str(term),
            "xnmc": f"{year}-{year + 1}",
            "xqmmc": str(origin_term),
            "jgmc": "undefined",
            "xxdm": "",
            "xszd.sj": "true",
            "xszd.cd": "true",
            "xszd.js": "true",
            "xszd.jszc": "false",
            "xszd.jxb": "true",
            "xszd.xkbz": "true",
            "xszd.kcxszc": "true",
            "xszd.zhxs": "true",
            "xszd.zxs": "true",
            "xszd.khfs": "true",
            "xszd.xf": "true",
            "xszd.skfsmc": "false",
            "kzlx": "dy",
        }

        try:
            # 许可接口
            pilicy_params = {"gnmkdm": "N2151"}
            req_policy = self.sess.post(
                url_policy,
                headers=self.headers,
                data=data,
                params=pilicy_params,
                cookies=self.cookies,
                timeout=self.timeout,
            )
            if req_policy.status_code != 200:
                return {"code": 2333, "msg": "教务系统挂了"}
            doc = pq(req_policy.text)
            if doc("h5").text() == "用户登录":
                return {"code": 1006, "msg": "未登录或已过期，请重新登录"}
            # 获取PDF文件URL
            file_params = {"doType": "table"}
            req_file = self.sess.post(
                url_file,
                headers=self.headers,
                data=data,
                params=file_params,
                cookies=self.cookies,
                timeout=self.timeout,
            )
            doc = pq(req_file.text)
            if "错误" in doc("title").text():
                error = doc("p.error_title").text()
                return {"code": 998, "msg": error}
            result = req_file.content  # 二进制内容
            return {"code": 1000, "msg": "获取课程表pdf成功", "data": result}
        except exceptions.Timeout:
            return {"code": 1003, "msg": "获取课程表pdf超时"}
        except (
                exceptions.RequestException,
                json.decoder.JSONDecodeError,
                AttributeError,
        ):
            traceback.print_exc()
            return {"code": 2333, "msg": "请重试，若多次失败可能是系统错误维护或需更新接口"}
        except Exception as e:
            traceback.print_exc()
            return {"code": 999, "msg": "获取课程表pdf时未记录的错误：" + str(e)}

    def get_notifications(self):
        """获取通知消息"""
        url = urljoin(self.base_url, "xtgl/index_cxDbsy.html?doType=query")
        data = {
            "sfyy": "0",  # 是否已阅，未阅未1，已阅为2
            "flag": "1",
            "_search": "false",
            "nd": int(time.time() * 1000),
            "queryModel.showCount": "1000",  # 最多条数
            "queryModel.currentPage": "1",  # 当前页数
            "queryModel.sortName": "cjsj",
            "queryModel.sortOrder": "desc",  # 时间倒序, asc正序
            "time": "0",
        }
        try:
            req_notification = self.sess.post(
                url,
                headers=self.headers,
                data=data,
                cookies=self.cookies,
                timeout=self.timeout,
            )
            if req_notification.status_code != 200:
                return {"code": 2333, "msg": "教务系统挂了"}
            doc = pq(req_notification.text)
            if doc("h5").text() == "用户登录" or "错误" in doc("title").text():
                return {"code": 1006, "msg": "未登录或已过期，请重新登录"}
            notifications = req_notification.json()
            result = [
                {**self.split_notifications(i), "create_time": i.get("cjsj")}
                for i in notifications.get("items")
            ]
            return {"code": 1000, "msg": "获取消息成功", "data": result}
        except exceptions.Timeout:
            return {"code": 1003, "msg": "获取消息超时"}
        except (
                exceptions.RequestException,
                json.decoder.JSONDecodeError,
                AttributeError,
        ):
            traceback.print_exc()
            return {"code": 2333, "msg": "请重试，若多次失败可能是系统错误维护或需更新接口"}
        except Exception as e:
            traceback.print_exc()
            return {"code": 999, "msg": "获取消息时未记录的错误：" + str(e)}

    def get_selected_courses(self, year: int, term: int):
        """获取已选课程信息"""
        try:
            url = urljoin(
                self.base_url,
                "xsxk/zzxkyzb_cxZzxkYzbChoosedDisplay.html?gnmkdm=N253512",
            )
            temp_term = term
            term = term ** 2 * 3
            data = {"xkxnm": str(year), "xkxqm": str(term)}
            req_selected = self.sess.post(
                url,
                data=data,
                headers=self.headers,
                cookies=self.cookies,
                timeout=self.timeout,
            )
            if req_selected.status_code != 200:
                return {"code": 2333, "msg": "教务系统挂了"}
            doc = pq(req_selected.text)
            if doc("h5").text() == "用户登录":
                return {"code": 1006, "msg": "未登录或已过期，请重新登录"}
            selected = req_selected.json()
            result = {
                "year": year,
                "term": temp_term,
                "count": len(selected),
                "courses": [
                    {
                        "course_id": i.get("kch"),
                        "class_id": i.get("jxb_id"),
                        "do_id": i.get("do_jxb_id"),
                        "title": i.get("kcmc"),
                        "teacher_id": (re.findall(r"(.*?\d+)/", i.get("jsxx")))[0],
                        "teacher": (re.findall(r"/(.*?)/", i.get("jsxx")))[0],
                        "credit": float(i.get("xf", 0)),
                        "category": i.get("kklxmc"),
                        "capacity": int(i.get("jxbrs", 0)),
                        "selected_number": int(i.get("yxzrs", 0)),
                        "place": self.get_place(i.get("jxdd")),
                        "time": self.get_course_time(i.get("sksj")),
                        "optional": int(i.get("zixf", 0)),
                        "waiting": i.get("sxbj"),
                    }
                    for i in selected
                ],
            }
            return {"code": 1000, "msg": "获取已选课程成功", "data": result}
        except exceptions.Timeout:
            return {"code": 1003, "msg": "获取已选课程超时"}
        except (
                exceptions.RequestException,
                json.decoder.JSONDecodeError,
                AttributeError,
        ):
            traceback.print_exc()
            return {"code": 2333, "msg": "请重试，若多次失败可能是系统错误维护或需更新接口"}
        except Exception as e:
            traceback.print_exc()
            return {"code": 999, "msg": f"获取已选课程时未记录的错误：{str(e)}"}

    def get_selected_courses2(self, year: int = 0, term: int = 0):
        """获取已选课程信息2"""
        try:
            url = urljoin(
                self.base_url,
                "/xsxxxggl/xsxxwh_cxXsxkxx.html?gnmkdm=N100801",
            )
            if (year == 0 or term == 0):
                year = ""
                term = ""
            else:
                temp_term = term
                term = term ** 2 * 3
            data = {
                "xnm": str(year),
                "xqm": str(term),
                "_search": "false",
                "queryModel.showCount": 5000,
                "queryModel.currentPage": 1,
                "queryModel.sortName": "",
                "queryModel.sortOrder": "asc",
                "time": 1,
            }
            req_selected = self.sess.post(
                url,
                data=data,
                headers=self.headers,
                cookies=self.cookies,
                timeout=self.timeout,
            )
            if req_selected.status_code != 200:
                return {"code": 2333, "msg": "教务系统挂了"}
            doc = pq(req_selected.text)
            if doc("h5").text() == "用户登录":
                return {"code": 1006, "msg": "未登录或已过期，请重新登录"}
            selected = req_selected.json()
            result = {
                "year": year,
                "term": temp_term,
                "count": len(selected["items"]),
                "courses": [
                    {
                        "course_id": i.get("kch"),
                        "class_id": i.get("jxb_id"),
                        "title": i.get("kcmc"),
                        "credit": float(i.get("xf", 0)),
                        "teacher": i.get("jsxm"),
                        "category": i.get("kclbmc"),
                        "place": i.get("jxdd"),
                    }
                    for i in selected["items"]
                ],
            }
            return {"code": 1000, "msg": "获取已选课程2成功", "data": result}
        except exceptions.Timeout:
            return {"code": 1003, "msg": "获取已选课程2超时"}
        except (
                exceptions.RequestException,
                json.decoder.JSONDecodeError,
                AttributeError,
        ):
            traceback.print_exc()
            return {
                "code": 2333,
                "msg": "请重试，若多次失败可能是系统错误维护或需更新接口",
            }
        except Exception as e:
            traceback.print_exc()
            return {"code": 999, "msg": f"获取已选课程2时未记录的错误：{str(e)}"}

    def get_block_courses(self, block: int = 1):
        """
        修复版：获取板块课程及对应的教学班详情
        """
        try:
            # 1. 访问选课主页获取必要隐藏参数（Index 页面）
            doc, entry_response = self._get_course_entry_page_doc()
            if "用户登录" in doc.text():
                return {"code": 1006, "msg": "会话已失效，请重新登录。"}
            
            # 提取页面所有隐藏表单域
            hidden = {item.attr("name"): item.attr("value") for item in doc("input[type='hidden']").items() if item.attr("name")}
            
            # 【关键】2. 访问 Display 页面激活选课 Session
            try:
                url_display = urljoin(self.base_url, "xsxk/zzxkyzb_cxZzxkYzbDisplay.html?gnmkdm=N253512")
                self._safe_request('GET', url_display)
            except Exception as e:
                print(f"访问 Display 页面异常（可忽略）: {e}")
            
            # 保存 hidden 参数供后续选课使用
            self._cached_hidden = hidden

            def hidden_value(*names, default=""):
                for name in names:
                    value = hidden.get(name)
                    if value is not None:
                        return value
                return default

            kklxdm = hidden_value("firstKklxdm", "kklxdm")
            xkkz_id = hidden_value("firstXkkzId", "xkkz_id")
            if not kklxdm or not xkkz_id:
                return {"code": 1005, "msg": "无法从选课页面获取板块动态参数(firstKklxdm/firstXkkzId)。"}

            common_payload = {
                "rwlx": hidden_value("rwlx", default="1"),
                "xklc": hidden_value("xklc", default="1"),
                "xkly": hidden_value("xkly", default="0"),
                "bklx_id": hidden_value("bklx_id", default="0"),
                "sfkkjyxdxnxq": hidden_value("sfkkjyxdxnxq", default="0"),
                "kzkcgs": hidden_value("kzkcgs", default="0"),
                "xqh_id": hidden_value("xqh_id"),
                "jg_id": hidden_value("jg_id_1", "jg_id"),
                "njdm_id_1": hidden_value("njdm_id_1"),
                "zyh_id_1": hidden_value("zyh_id_1"),
                "zyh_id": hidden_value("zyh_id"),
                "zyfx_id": hidden_value("zyfx_id"),
                "njdm_id": hidden_value("njdm_id"),
                "bh_id": hidden_value("bh_id"),
                "bjgkczxbbjwcx": hidden_value("bjgkczxbbjwcx", default="0"),
                "xbm": hidden_value("xbm"),
                "xslbdm": hidden_value("xslbdm"),
                "mzm": hidden_value("mzm"),
                "xz": hidden_value("xz"),
                "ccdm": hidden_value("ccdm"),
                "xsbj": hidden_value("xsbj", default="0"),
                "sfkknj": hidden_value("sfkknj", default="0"),
                "gnjkxdnj": hidden_value("gnjkxdnj", default="0"),
                "sfkkzy": hidden_value("sfkkzy", default="0"),
                "kzybkxy": hidden_value("kzybkxy", default="0"),
                "sfznkx": hidden_value("sfznkx", default="0"),
                "zdkxms": hidden_value("zdkxms", default="0"),
                "sfkxq": hidden_value("sfkxq", default="0"),
                "njdm_id_xs": hidden_value("njdm_id_xs"),
                "zyh_id_xs": hidden_value("zyh_id_xs"),
                "sfkcfx": hidden_value("sfkcfx", default="0"),
                "kkbk": hidden_value("kkbk", default="0"),
                "kkbkdj": hidden_value("kkbkdj", default=""),
                "bklbkcj": hidden_value("bklbkcj", default="0"),
                "sfkgbcx": hidden_value("sfkgbcx", default="0"),
                "sfrxtgkcxd": hidden_value("sfrxtgkcxd", default="0"),
                "tykczgxdcs": hidden_value("tykczgxdcs", default="0"),
                "xkxnm": hidden_value("xkxnm"),
                "xkxqm": hidden_value("xkxqm"),
                "bbhzxjxb": hidden_value("bbhzxjxb", default="0"),
                "bhbcyxkjxb": hidden_value("bhbcyxkjxb", default=""),
                "rlkz": hidden_value("rlkz", default="0"),
                "xkzgbj": hidden_value("xkzgbj", default="0"),
                "zxgbxkkg": hidden_value("zxgbxkkg", default=""),
                "kklxdm": kklxdm,
                "xkkz_id": xkkz_id,
            }

            url_courses_api = urljoin(self.base_url, "xsxk/zzxkyzb_cxZzxkYzbPartDisplay.html?gnmkdm=N253512")

            try:
                page_step = int(hidden_value("xkmcjzxskcs", default="10") or 10)
            except (TypeError, ValueError):
                page_step = 10
            if page_step <= 0:
                page_step = 10

            course_rows = []
            jspage = 0
            for _ in range(500):
                course_list_payload = {
                    **common_payload,
                    "kspage": str(jspage + 1),
                    "jspage": str(jspage + page_step),
                }
                if hidden_value("jxbzbkg", default="0") == "1":
                    course_list_payload["jxbzb"] = hidden_value("jxbzb")
                if hidden_value("jxbzhkg", default="0") == "1":
                    course_list_payload["zh"] = hidden_value("zh")

                res = self._safe_request('POST', url_courses_api, data=course_list_payload)
                course_json = res.json()
                if not isinstance(course_json, dict):
                    return {"code": 1004, "msg": f"获取课程列表失败，服务器返回了非预期的内容: {course_json}"}

                page_rows = course_json.get("tmpList", [])
                if not page_rows:
                    break

                course_rows.extend(page_rows)

                first_row_number = self.parse_int(str(page_rows[0].get("kcrow", "")))
                last_row_number = self.parse_int(str(page_rows[-1].get("kcrow", "")))
                if (
                    len(page_rows) < page_step
                    or isinstance(first_row_number, int)
                    and isinstance(last_row_number, int)
                    and (last_row_number - first_row_number + 1) < page_step
                ):
                    break

                jspage += page_step

            if not course_rows:
                return {"code": 1005, "msg": "未获取到课程列表数据"}

            # 3. 遍历课程获取教学班 (使用第二组抓包参数)
            all_classes = []
            seen_do_ids = set() # 新增：去重，防止列表翻倍
            processed_kch = set() # 新增：效率优化，避免重复请求同一课程
            url_jxb_api = urljoin(self.base_url, "xsxk/zzxkyzbjk_cxJxbWithKchZzxkYzb.html?gnmkdm=N253512")
            
            for course in course_rows:
                kch_id = course.get("kch_id")
                if not kch_id or kch_id in processed_kch:
                    continue
                processed_kch.add(kch_id)

                # 构建获取教学班详情的 Payload
                jxb_payload = {
                    **common_payload,
                    "txbsfrl": hidden_value("txbsfrl", default="0"),
                    "xkxskcgskg": hidden_value("xkxskcgskg", default="0"),
                    "cdrlkz": hidden_value("cdrlkz", default="0"),
                    "rlzlkz": hidden_value("rlzlkz", default="1"),
                    "jxbzcxskg": hidden_value("jxbzcxskg", default="0"),
                    "cxcykclxxskg": hidden_value("cxcykclxxskg", default="0"),
                    "kch_id": kch_id,
                    "cxbj": course.get("cxbj", "0"),
                    "fxbj": course.get("fxbj", "0")
                }
                
                jxb_res = self._safe_request('POST', url_jxb_api, data=jxb_payload)
                jxb_list = jxb_res.json()
                
                if isinstance(jxb_list, list):
                    for jxb in jxb_list:
                        do_id = jxb.get("do_jxb_id")
                        # 如果教学班 ID 已存在，则跳过，防止列表翻倍
                        if do_id in seen_do_ids:
                            continue
                        seen_do_ids.add(do_id)

                        all_classes.append({
                            "course_id": kch_id,
                            "class_id": jxb.get("jxb_id"),
                            "do_id": do_id, # 抢课用的关键 ID
                            "title": course.get("kcmc"),
                            "teacher": jxb.get("jsxx"),
                            "credit": float(course.get("xf", 0)),
                            "capacity": int(jxb.get("jxbrl", 0)),
                            "selected_number": int(jxb.get("yxzrs", 0)),
                            "place": jxb.get("jxdd"),
                            "time": jxb.get("sksj"),
                            "kklxdm": kklxdm,
                            "xkkz_id": xkkz_id,
                            "cxbj": course.get("cxbj", "0"),
                            "fxbj": course.get("fxbj", "0")
                        })

            return {
                "code": 1000, 
                "msg": "获取板块课信息成功", 
                "data": {
                    "year": course_list_payload["xkxnm"],
                    "term": course_list_payload["xkxqm"],
                    "block_name": hidden_value("firstKklxmc", "kklxmc"),
                    "count": len(all_classes),
                    "courses": all_classes
                }
            }

        except Exception as e:
            traceback.print_exc()
            return {"code": 999, "msg": f"获取板块课程异常: {str(e)}"}

    def select_course(self, course_data: dict, _jas_attempt: int = 0):
        """
        【简化版】执行选课/抢课操作
        使用 get_block_courses 时缓存的 hidden 参数，确保 Session 一致性
        :param course_data: get_block_courses 返回的单个课程字典对象
        """
        try:
            # 检查是否有缓存的 hidden 参数
            hidden = getattr(self, '_cached_hidden', {})
            
            # 如果没有缓存的参数，先访问页面获取（解决多账号问题）
            if not hidden:
                try:
                    # 访问 Index 页面获取 hidden 参数
                    doc, entry_response = self._get_course_entry_page_doc()
                    hidden = {item.attr("name"): item.attr("value") for item in doc("input[type='hidden']").items() if item.attr("name")}
                    
                    # 访问 Display 页面激活 Session
                    url_display = urljoin(self.base_url, "xsxk/zzxkyzb_cxZzxkYzbDisplay.html?gnmkdm=N253512")
                    self._safe_request('GET', url_display)
                    
                    # 缓存参数供后续使用
                    self._cached_hidden = hidden
                except Exception as e:
                    print(f"获取 hidden 参数异常: {e}")
            
            # 请求头
            ajax_headers = {
                'Referer': urljoin(self.base_url, "xsxk/zzxkyzb_cxZzxkYzbIndex.html?gnmkdm=N253512"),
                'X-Requested-With': 'XMLHttpRequest',
                'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8'
            }


            def hidden_value(*names, default=""):
                for name in names:
                    value = hidden.get(name)
                    if value is not None:
                        return value
                return default

            kklxdm = course_data.get("kklxdm") or hidden_value("firstKklxdm", "kklxdm")
            xkkz_id = course_data.get("xkkz_id") or hidden_value("firstXkkzId", "xkkz_id")
            if not kklxdm or not xkkz_id:
                return {"code": 1005, "msg": "选课失败: 缺少动态板块参数 kklxdm/xkkz_id"}

            # 构建选课 Payload - 使用当前页面 hidden 参数和课程缓存中的动态参数
            select_payload = {
                "jxb_ids": course_data.get("do_id"),
                "kch_id": course_data.get("course_id"),
                "kcmc": course_data.get("title"),
                "kklxdm": kklxdm,
                "xkkz_id": xkkz_id,
                "qz": "0",
                "cxbj": course_data.get("cxbj", "0"),
                "fxbj": course_data.get("fxbj", "0"),
                "rwlx": hidden_value("rwlx", default="1"),
                "xklc": hidden_value("xklc", default="1"),
                "xkly": hidden_value("xkly", default="0"),
                "bklx_id": hidden_value("bklx_id", default="0"),
                "sfkkjyxdxnxq": hidden_value("sfkkjyxdxnxq", default="0"),
                "kzkcgs": hidden_value("kzkcgs", default="0"),
                "xqh_id": hidden_value("xqh_id"),
                "jg_id": hidden_value("jg_id_1", "jg_id"),
                "zyh_id": hidden_value("zyh_id"),
                "zyfx_id": hidden_value("zyfx_id"),
                "txbsfrl": hidden_value("txbsfrl", default="0"),
                "njdm_id": hidden_value("njdm_id"),
                "bh_id": hidden_value("bh_id"),
                "bjgkczxbbjwcx": hidden_value("bjgkczxbbjwcx", default="0"),
                "xbm": hidden_value("xbm"),
                "xslbdm": hidden_value("xslbdm"),
                "mzm": hidden_value("mzm"),
                "xz": hidden_value("xz"),
                "ccdm": hidden_value("ccdm"),
                "xsbj": hidden_value("xsbj", default="0"),
                "sfkknj": hidden_value("sfkknj", default="0"),
                "gnjkxdnj": hidden_value("gnjkxdnj", default="0"),
                "sfkkzy": hidden_value("sfkkzy", default="0"),
                "kzybkxy": hidden_value("kzybkxy", default="0"),
                "sfznkx": hidden_value("sfznkx", default="0"),
                "zdkxms": hidden_value("zdkxms", default="0"),
                "sfkxq": hidden_value("sfkxq", default="0"),
                "sfkcfx": hidden_value("sfkcfx", default="0"),
                "kkbk": hidden_value("kkbk", default="0"),
                "kkbkdj": hidden_value("kkbkdj", default="0"),
                "bklbkcj": hidden_value("bklbkcj", default="0"),
                "sfkgbcx": hidden_value("sfkgbcx", default="0"),
                "sfrxtgkcxd": hidden_value("sfrxtgkcxd", default="0"),
                "tykczgxdcs": hidden_value("tykczgxdcs", default="0"),
                "xkxnm": hidden_value("xkxnm"),
                "xkxqm": hidden_value("xkxqm"),
                "rlkz": hidden_value("rlkz", default="0"),
                "bbhzxjxb": hidden_value("bbhzxjxb", default="0"),
                "xkxskcgskg": hidden_value("xkxskcgskg", default="0"),
                "cdrlkz": hidden_value("cdrlkz", default="0"),
                "rlzlkz": hidden_value("rlzlkz", default="1"),
                "sxbj": hidden_value("sxbj", default="1"),
                "xxkbj": hidden_value("xxkbj", default="0"),
                "jcxx_id": hidden_value("jcxx_id", default=""),
                "jxbzcxskg": hidden_value("jxbzcxskg", default="0"),
                "xkzgbj": hidden_value("xkzgbj", default="0")
            }

            # 直接发送选课请求
            url_select = urljoin(self.base_url, "xsxk/zzxkyzbjk_xkBcZyZzxkYzb.html?gnmkdm=N253512")
            # 选课 POST 在网络拥堵时也允许有限次重试。服务端接口对同一
            # 课程请求是幂等的：成功后再次请求会返回“已选/重复”提示。
            res = self._safe_request(
                'POST',
                url_select,
                data=select_payload,
                headers=ajax_headers,
                retryable=True,
                max_retries=2,
            )
            if res.status_code in [502, 503, 504]:
                return {"code": 1010, "retryable": True, "msg": f"选课服务器繁忙: HTTP {res.status_code}"}
            try:
                result = res.json()
            except (ValueError, json.decoder.JSONDecodeError):
                return {
                    "code": 1010,
                    "retryable": True,
                    "msg": f"选课服务器返回了非JSON内容，HTTP {res.status_code}",
                }

            # 解析返回结果
            # flag 含义: 1-成功, 0-失败, -1-容量满, 2-冲突, 3-有提示词(也算成功), 6-成功
            flag = str(result.get("flag"))
            msg = result.get("msg", "未知响应")

            # JAS-04 表示本次选课请求使用的页面校验参数已失效。刷新
            # 首页、选课入口和 Display 页面后，必须把新的板块参数带入
            # 当前课程的下一次请求，不能只等待后重发旧 payload。
            jas_error = any(
                token in str(msg)
                for token in ["JAS-04", "校验不通过", "刷新本网页"]
            )
            if jas_error:
                if _jas_attempt < 2:
                    refreshed = self._refresh_session()
                    refreshed_course = dict(course_data)
                    refreshed_hidden = getattr(self, "_cached_hidden", {}) or {}
                    new_kklxdm = refreshed_hidden.get("firstKklxdm") or refreshed_hidden.get("kklxdm")
                    new_xkkz_id = refreshed_hidden.get("firstXkkzId") or refreshed_hidden.get("xkkz_id")
                    if new_kklxdm:
                        refreshed_course["kklxdm"] = new_kklxdm
                    if new_xkkz_id:
                        refreshed_course["xkkz_id"] = new_xkkz_id
                    if refreshed:
                        time.sleep(0.5 + 0.5 * _jas_attempt)
                    return self.select_course(refreshed_course, _jas_attempt + 1)
                return {
                    "code": 1010,
                    "retryable": True,
                    "session_refreshed": True,
                    "msg": f"选课会话校验失败（JAS-04）: {msg}",
                }

            if flag in ["1", "3", "6"]:
                return {"code": 1000, "msg": f"选课成功: {msg}"}
            else:
                return {"code": 1007, "msg": f"选课未成功: {msg} (Flag: {flag})"}

        except Exception as e:
            traceback.print_exc()
            if any(token in str(e) for token in ["请求失败", "Timeout", "timed out", "Connection", "超时"]):
                return {"code": 1010, "retryable": True, "msg": f"选课请求超时/网络繁忙: {str(e)}"}
            return {"code": 999, "msg": f"选课接口调用异常: {str(e)}"}
    
    def _refresh_session(self):
        """刷新会话并重新获取选课页面的动态参数。

        选课接口返回 ``JAS-04`` 时，通常是页面校验参数或选课会话已经
        过期。仅重新访问首页并不能修复后续请求使用的 ``_cached_hidden``，
        因此这里要把最新入口页中的 hidden 字段重新缓存起来。
        """
        try:
            # 访问主页面刷新会话
            main_url = urljoin(self.base_url, "xtgl/index_initMenu.html")
            self._safe_request('GET', main_url)
            
            # 重新访问选课入口页面并更新动态参数
            doc, _ = self._get_course_entry_page_doc()
            hidden = {
                item.attr("name"): item.attr("value")
                for item in doc("input[type='hidden']").items()
                if item.attr("name")
            }
            if hidden:
                self._cached_hidden = hidden

            # 激活选课页面对应的会话上下文
            url_display = urljoin(
                self.base_url,
                "xsxk/zzxkyzb_cxZzxkYzbDisplay.html?gnmkdm=N253512",
            )
            self._safe_request('GET', url_display)
            return True
        except Exception as e:
            print(f"刷新会话时出错: {e}")
            return False

    def cancel_course(self, do_id: str, kch_id: str):
        """【修正版】执行退课操作"""
        try:
            doc, _ = self._get_course_entry_page_doc()
            base_payload = {item.attr("name"): item.attr("value") for item in doc("input[type='hidden']").items() if item.attr("name")}

            cancel_data = {
                "jxb_ids": do_id, "kch_id": kch_id,
                "xkxnm": base_payload.get("xkxnm"), "xkxqm": base_payload.get("xkxqm")
            }
            
            url_cancel = urljoin(self.base_url, "xsxk/zzxkyzb_tuikBcZzxkYzb.html")
            req_cancel = self._safe_request('POST', url_cancel, data=cancel_data)
            
            if req_cancel.text.strip() == '"1"':
                return {"code": 1000, "msg": "退课成功"}
            else:
                try: msg = req_cancel.json()
                except json.JSONDecodeError: msg = req_cancel.text
                return {"code": 1008, "msg": f"退课失败: {msg}"}

        except Exception as e:
            traceback.print_exc()
            return {"code": 999, "msg": f"退课时发生错误: {e}"}

    # ============= utils =================

    def get_gpa(self):
        """获取GPA"""
        url = urljoin(
            self.base_url,
            "xsxy/xsxyqk_cxXsxyqkIndex.html?gnmkdm=N105515&layout=default",
        )
        try:
            req_gpa = self.sess.get(
                url,
                headers=self.headers,
                cookies=self.cookies,
                timeout=self.timeout,
            )
            if req_gpa.status_code != 200:
                return {"code": 2333, "msg": "教务系统挂了"}
            doc = pq(req_gpa.text)
            if doc("h5").text() == "用户登录":
                return {"code": 1006, "msg": "未登录或已过期，请重新登录"}

            # 更稳健的GPA提取方式
            display_statistics = doc("div#alertBox").text().replace(" ", "").replace("\n", "")
            gpa_list = re.findall(r"平均学分绩点\(GPA\):([0-9.]+)", display_statistics)

            if gpa_list and self.is_number(gpa_list[0]):
                gpa = float(gpa_list[0])
                return {"code": 1000, "msg": "获取GPA成功", "data": gpa}
            else:
                # 备用解析方法
                allc_str = [allc.text() for allc in doc("font[size='2px']").items()]
                if len(allc_str) > 2 and self.is_number(allc_str[2]):
                    gpa = float(allc_str[2])
                    return {"code": 1000, "msg": "获取GPA成功 (备用方法)", "data": gpa}
                else:
                    return {"code": 1005, "msg": "无法从页面解析GPA数据"}
        except exceptions.Timeout:
            return {"code": 1003, "msg": "获取GPA超时"}
        except Exception as e:
            traceback.print_exc()
            return {"code": 999, "msg": f"获取GPA时发生未知错误: {e}"}


    def get_course_category(self, type, item):
        """根据课程号获取类别"""
        if type not in self.detail_category_type:
            return item.get("KCLBMC")
        if not item.get("KCH"):
            return None
        url = urljoin(self.base_url, f"jxjhgl/common_cxKcJbxx.html?id={item['KCH']}")
        req_category = self.sess.get(
            url,
            headers=self.headers,
            cookies=self.cookies,
            timeout=self.timeout,
        )
        doc = pq(req_category.text)
        ths = doc("th")
        try:
            data_list = [(th.text).strip() for th in ths]
            return data_list[6]
        except:
            return None

    @classmethod
    def encrypt_password(cls, pwd, n, e):
        """对密码base64编码"""
        message = str(pwd).encode()
        rsa_n = binascii.b2a_hex(binascii.a2b_base64(n))
        rsa_e = binascii.b2a_hex(binascii.a2b_base64(e))
        key = rsa.PublicKey(int(rsa_n, 16), int(rsa_e, 16))
        encropy_pwd = rsa.encrypt(message, key)
        result = binascii.b2a_base64(encropy_pwd)
        return result

    @classmethod
    def parse_int(cls, digits):
        if not digits:
            return None
        if not digits.isdigit():
            return digits
        return int(digits)

    @classmethod
    def align_floats(cls, floats):
        if not floats:
            return None
        if floats == "无":
            return "0.0"
        return format(float(floats), ".1f")

    @classmethod
    def display_course_time(cls, sessions):
        if not sessions:
            return None
        args = re.findall(r"(\d+)", sessions)
        start_time = cls.raspisanie[int(args[0]) + 1][0]
        end_time = cls.raspisanie[int(args[0]) + 1][1]
        return f"{start_time}~{end_time}"

    @classmethod
    def list_sessions(cls, sessions):
        if not sessions:
            return None
        args = re.findall(r"(\d+)", sessions)
        return [n for n in range(int(args[0]), int(args[1]) + 1)]

    @classmethod
    def list_weeks(cls, weeks):
        """返回课程所含周列表"""
        if not weeks:
            return None
        args = re.findall(r"[^,]+", weeks)
        week_list = []
        for item in args:
            if "-" in item:
                weeks_pair = re.findall(r"(\d+)", item)
                if len(weeks_pair) != 2:
                    continue
                if "单" in item:
                    for i in range(int(weeks_pair[0]), int(weeks_pair[1]) + 1):
                        if i % 2 == 1:
                            week_list.append(i)
                elif "双" in item:
                    for i in range(int(weeks_pair[0]), int(weeks_pair[1]) + 1):
                        if i % 2 == 0:
                            week_list.append(i)
                else:
                    for i in range(int(weeks_pair[0]), int(weeks_pair[1]) + 1):
                        week_list.append(i)
            else:
                week_num = re.findall(r"(\d+)", item)
                if len(week_num) == 1:
                    week_list.append(int(week_num[0]))
        return week_list

    @classmethod
    def get_academia_statistics(cls, display_statistics):
        display_statistics = "".join(display_statistics.split())
        gpa_list = re.findall(r"([0-9]{1,}[.][0-9]*)", display_statistics)
        if len(gpa_list) == 0 or not cls.is_number(gpa_list[0]):
            gpa = None
        else:
            gpa = float(gpa_list[0])
        plan_list = re.findall(
            r"计划总课程(\d+)门通过(\d+)门?.*未通过(\d+)门?.*未修(\d+)?.*在读(\d+)门?.*计划外?.*通过(\d+)门?.*未通过(\d+)门",
            display_statistics,
        )
        if len(plan_list) == 0 or len(plan_list[0]) < 7:
            return {"gpa": gpa}
        plan_list = plan_list[0]
        return {
            "gpa": gpa,  # 平均学分绩点GPA
            "planed_courses": {
                "total": int(plan_list[0]),  # 计划内总课程数
                "passed": int(plan_list[1]),  # 计划内已过课程数
                "failed": int(plan_list[2]),  # 计划内未过课程数
                "missed": int(plan_list[3]),  # 计划内未修课程数
                "in": int(plan_list[4]),  # 计划内在读课程数
            },
            "unplaned_courses": {
                "passed": int(plan_list[5]),  # 计划外已过课程数
                "failed": int(plan_list[6]),  # 计划外未过课程数
            },
        }

    @classmethod
    def get_academia_type_statistics(cls, content: str):
        finder = re.findall(
            r"\"(.*)&nbsp.*要求学分.*:([0-9]{1,}[.][0-9]*|0|&nbsp;).*获得学分.*:([0-9]{1,}[.][0-9]*|0|&nbsp;).*未获得学分.*:([0-9]{1,}[.][0-9]*|0|&nbsp;)[\s\S]*?<span id='showKc(.*)'></span>",
            content,
        )
        finder_list = list({}.fromkeys(finder).keys())
        academia_list = [
            list(i)
            for i in finder_list
            if i[0] != ""  # 类型名称不为空
               and len(i[0]) <= 20  # 避免正则到首部过长类型名称
               and "span" not in i[-1]  # 避免正则到尾部过长类型名称
               and i[0] not in cls.ignore_type  # 忽略的类型名称
        ]
        result = {
            i[0]: {
                "id": i[-1],
                "credits": {
                    "required": i[1] if cls.is_number(i[1]) and i[1] != "0" else None,
                    "earned": i[2] if cls.is_number(i[2]) and i[2] != "0" else None,
                    "missed": i[3] if cls.is_number(i[3]) and i[3] != "0" else None,
                },
            }
            for i in academia_list
        }
        return result

    @classmethod
    def get_display_term(cls, sid, year, term):
        """
        计算培养方案具体学期转化成中文
        note: 留级和当兵等情况会不准确
        """
        if (sid and year and term) is None:
            return None
        grade = int(sid[0:2])
        year = int(year[2:4])
        term = int(term)
        dict = {
            grade: "大一上" if term == 1 else "大一下",
            grade + 1: "大二上" if term == 1 else "大二下",
            grade + 2: "大三上" if term == 1 else "大三下",
            grade + 3: "大四上" if term == 1 else "大四下",
        }
        return dict.get(year)

    @classmethod
    def split_merge_display(cls, schedule):
        """
        拆分同周同天同课程不同时段数据合并的问题
        """
        repetIndex = []
        count = 0
        for items in schedule["courses"]:
            for index in range(len(schedule["courses"])):
                if (schedule["courses"]).index(items) == count:  # 如果对比到自己就忽略
                    continue
                elif (
                        items["course_id"]
                        == schedule["courses"][index]["course_id"]  # 同周同天同课程
                        and items["weekday"] == schedule["courses"][index]["weekday"]
                        and items["weeks"] == schedule["courses"][index]["weeks"]
                ):
                    repetIndex.append(index)  # 满足条件记录索引
            count += 1  # 记录当前对比课程的索引
        if len(repetIndex) % 2 != 0:  # 暂时考虑一天两个时段上同一门课，不满足条件不进行修改
            return schedule
        for r in range(0, len(repetIndex), 2):  # 索引数组两两成对，故步进2循环
            fir = repetIndex[r]
            sec = repetIndex[r + 1]
            if len(re.findall(r"(\d+)", schedule["courses"][fir]["sessions"])) == 4:
                schedule["courses"][fir]["sessions"] = (
                        re.findall(r"(\d+)", schedule["courses"][fir]["sessions"])[0]
                        + "-"
                        + re.findall(r"(\d+)", schedule["courses"][fir]["sessions"])[1]
                        + "节"
                )
                schedule["courses"][fir]["list_sessions"] = cls.list_sessions(
                    schedule["courses"][fir]["sessions"]
                )
                schedule["courses"][fir]["time"] = cls.display_course_time(
                    schedule["courses"][fir]["sessions"]
                )

                schedule["courses"][sec]["sessions"] = (
                        re.findall(r"(\d+)", schedule["courses"][sec]["sessions"])[2]
                        + "-"
                        + re.findall(r"(\d+)", schedule["courses"][sec]["sessions"])[3]
                        + "节"
                )
                schedule["courses"][sec]["list_sessions"] = cls.list_sessions(
                    schedule["courses"][sec]["sessions"]
                )
                schedule["courses"][sec]["time"] = cls.display_course_time(
                    schedule["courses"][sec]["sessions"]
                )
        return schedule

    @classmethod
    def split_notifications(cls, item):
        if not item.get("xxnr"):
            return {"type": None, "content": None}
        content_list = re.findall(r"(.*):(.*)", item["xxnr"])
        if len(content_list) == 0:
            return {"type": None, "content": item["xxnr"]}
        return {"type": content_list[0][0], "content": content_list[0][1]}

    @classmethod
    def get_place(cls, place):
        return place.split("<br/>")[0] if "<br/>" in place else place

    @classmethod
    def get_course_time(cls, time):
        return "、".join(time.split("<br/>")) if "<br/>" in time else time

    @classmethod
    def is_number(cls, s):
        if s == "":
            return False
        try:
            float(s)
            return True
        except ValueError:
            pass
        try:
            for i in s:
                unicodedata.numeric(i)
            return True
        except (TypeError, ValueError):
            pass
        return False


if __name__ == "__main__":
    from pprint import pprint
    import json
    import base64
    import sys
    import os

    base_url = "https://xxxx.xxx.edu.cn"  # 教务系统URL
    sid = "123456"  # 学号
    password = "abc654321"  # 密码
    lgn_cookies = (
        {
            # "insert_cookie": "",
            # "route": "",
            "JSESSIONID": ""
        }
        if False
        else None
    )  # cookies登录，调整成True使用cookies登录，反之使用密码登录
    test_year = 2022  # 查询学年
    test_term = 2  # 查询学期（1-上|2-下）

    # 初始化
    lgn = Client(lgn_cookies if lgn_cookies is not None else {}, base_url=base_url)
    # 判断是否需要使用cookies登录
    if lgn_cookies is None:
        # 登录
        pre_login = lgn.login(sid, password)
        # 判断登录结果
        if pre_login["code"] == 1001:
            # 需要验证码
            pre_dict = pre_login["data"]
            with open(os.path.abspath("temp.json"), mode="w", encoding="utf-8") as f:
                f.write(json.dumps(pre_dict))
            with open(os.path.abspath("kaptcha.png"), "wb") as pic:
                pic.write(base64.b64decode(pre_dict["kaptcha_pic"]))
            kaptcha = input("输入验证码：")
            result = lgn.login_with_kaptcha(
                pre_dict["sid"],
                pre_dict["csrf_token"],
                pre_dict["cookies"],
                pre_dict["password"],
                pre_dict["modulus"],
                pre_dict["exponent"],
                kaptcha,
            )
            if result["code"] != 1000:
                pprint(result)
                sys.exit()
            lgn_cookies = lgn.cookies
        elif pre_login["code"] == 1000:
            # 不需要验证码，直接登录
            lgn_cookies = lgn.cookies
        else:
            # 出错
            pprint(pre_login)
            sys.exit()

    # 下面是各个函数调用，想调用哪个，取消注释即可
    """ 获取个人信息 """
    result = lgn.get_info()

    """ 获取成绩单PDF """
    # result = lgn.get_academia_pdf()
    # if result["code"] == 1000:
    #     with open(os.path.abspath("grade.pdf"), "wb") as pdf:
    #         pdf.write(result["data"])
    #         result = "已保存到本地"

    """ 获取学业情况 """
    # result = lgn.get_academia()

    """ 获取GPA """
    # result = lgn.get_gpa()

    """ 获取课程表 """
    # result = lgn.get_schedule(test_year, test_term)

    """ 获取成绩 """
    # result = lgn.get_grade(test_year, test_term)

    # 输出结果
    pprint(result)
