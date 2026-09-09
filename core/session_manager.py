import base64
import time
import threading
import random
from typing import Optional, Dict, Any
from urllib.parse import urljoin
import requests
from requests import exceptions
from pyquery import PyQuery as pq
import json
from core.webvpn import WEBVPN_SERVICE, LingnanWebVPN, WebVPNError, is_lingnan_webvpn_url


class SessionManager:
    """
    Session管理器 - 维持长连接并自动处理登录状态
    """
    
    def __init__(
        self,
        base_url: str,
        timeout: int = 10,
        max_retries: int = 1,
        backoff_base: float = 0.25,
        backoff_factor: float = 2.0,
        retry_status_codes=None,
        sleep_func=time.sleep,
        random_func=random.uniform,
    ):
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.backoff_factor = backoff_factor
        self.retry_status_codes = set(retry_status_codes or [502, 503, 504])
        self.sleep_func = sleep_func
        self.random_func = random_func
        self.session = requests.Session()
        self.session.keep_alive = True  # 保持连接
        
        # 登录状态管理
        self.is_logged_in = False
        self.login_time = None
        self.credentials = None
        self.cookies = {}
        # WebVPN 仅负责让会话进入校内网络，仍需随后完成教务系统登录。
        self.webvpn_authenticated = False
        self.webvpn_menu_accessible = False
        self.webvpn = (
            LingnanWebVPN(self.session, self.base_url, self.timeout)
            if is_lingnan_webvpn_url(self.base_url)
            else None
        )
        
        # 线程锁，确保线程安全
        self._lock = threading.RLock()
        
        # 设置默认headers
        self._setup_headers()
        
    def _setup_headers(self):
        """设置默认请求头"""
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
        
    def login(self, sid: str, password: str) -> Dict[str, Any]:
        """
        登录并维持Session
        """
        with self._lock:
            try:
                if self.webvpn and not self.webvpn_authenticated:
                    return {
                        "code": 1001,
                        "msg": "请先完成 WebVPN 登录，再提交教务系统账号密码",
                    }

                # 仅保存教务系统凭据，用于该层会话到期后的自动重登录。
                self.credentials = {'sid': sid, 'password': password}
                
                # 执行登录逻辑
                result = self._perform_login(sid, password)
                
                if result.get('code') == 1000:
                    self.is_logged_in = True
                    self.login_time = time.time()
                    self.cookies = result.get('data', {}).get('cookies', {})
                    self.session.cookies.update(self.cookies)
                    
                return result
                
            except Exception as e:
                return {"code": 999, "msg": f"登录异常: {str(e)}"}

    def begin_webvpn_login(self) -> Dict[str, Any]:
        """创建 WebVPN 验证码挑战，图片仅以 base64 形式返回给调用方展示。"""
        if not self.webvpn:
            return {"code": 1006, "msg": "当前地址不需要 WebVPN 登录"}
        try:
            challenge = self.webvpn.begin_login()
            return {
                "code": 1001,
                "msg": "需要完成 WebVPN 验证码登录",
                "data": {
                    "captcha_image": base64.b64encode(challenge.image).decode("ascii"),
                    "captcha_encoding": "base64",
                },
            }
        except (WebVPNError, exceptions.RequestException) as e:
            return {"code": 2333, "msg": f"无法获取 WebVPN 验证码: {e}"}
        except Exception as e:
            return {"code": 999, "msg": f"WebVPN 登录初始化异常: {e}"}

    def complete_webvpn_login(self, sid: str, password: str, captcha: str) -> Dict[str, Any]:
        """提交 WebVPN 验证码；成功后仍须调用 ``login`` 登录教务系统。"""
        if not self.webvpn:
            return {"code": 1006, "msg": "当前地址不需要 WebVPN 登录"}
        with self._lock:
            try:
                result = self.webvpn.complete_login(sid, password, captcha)
                if result.get("code") == 1000:
                    self.webvpn_authenticated = True
                    self.cookies = result.get("data", {}).get("cookies", {})
                    self.session.cookies.update(self.cookies)
                    # 菜单页在 WebVPN 转发下会因缓存/脚本返回不同内容，不能
                    # 可靠地作为认证判断，但浏览器会先访问它来激活教务 SSO。
                    # 因此保留该导航步骤，实际是否可用仍由后续只读接口确认。
                    self.is_logged_in = True
                    self.login_time = time.time()
                    # 复现浏览器回跳后的资源导航链：先进入 VPN 转发的教务根页，
                    # 再进入菜单页。部分部署会在根页响应中写入目标系统 Cookie。
                    self.session.get(
                        self.base_url,
                        headers={"Referer": WEBVPN_SERVICE},
                        timeout=self.timeout,
                    )
                    menu_url = urljoin(
                        self.base_url,
                        f"xtgl/index_initMenu.html?jsdm=xs&_t={int(time.time() * 1000)}&echarts=1",
                    )
                    menu_response = self.session.get(menu_url, timeout=self.timeout)
                    self.session.headers["Referer"] = menu_url
                    self.webvpn_menu_accessible = (
                        menu_response.status_code == 200
                        and "authserver/login" not in menu_response.url.lower()
                        and "login_slogin" not in menu_response.url.lower()
                    )
                    result["msg"] = "WebVPN 登录成功，正在验证教务系统单点登录会话"
                return result
            except exceptions.Timeout:
                return {"code": 1003, "msg": "WebVPN 登录超时"}
            except (WebVPNError, exceptions.RequestException) as e:
                return {"code": 2333, "msg": f"WebVPN 登录失败: {e}"}
            except Exception as e:
                return {"code": 999, "msg": f"WebVPN 登录异常: {e}"}
    
    def _perform_login(self, sid: str, password: str) -> Dict[str, Any]:
        """
        执行实际的登录操作
        """
        login_url = urljoin(self.base_url, "xtgl/login_slogin.html")
        key_url = urljoin(self.base_url, "xtgl/login_getPublicKey.html")
        
        try:
            # 获取登录页面
            self.session.headers['Referer'] = login_url
            req_csrf = self.session.get(login_url, timeout=self.timeout)
            if req_csrf.status_code != 200:
                return {"code": 2333, "msg": "教务系统无法访问"}
                
            # 解析csrf_token
            doc = pq(req_csrf.text)
            csrf_token = doc("#csrftoken").attr("value")
            
            # 获取公钥
            req_pubkey = self.session.get(key_url, timeout=self.timeout)
            pubkey_data = req_pubkey.json()
            
            # 加密密码
            from api.zfn_api import Client
            encrypted_password = Client.encrypt_password(
                password, 
                pubkey_data["modulus"], 
                pubkey_data["exponent"]
            )
            
            # 登录数据
            login_data = {
                "csrftoken": csrf_token,
                "yhm": sid,
                "mm": encrypted_password,
            }
            
            # 执行登录
            req_login = self.session.post(
                login_url,
                data=login_data,
                timeout=self.timeout,
            )
            
            # 检查登录结果
            doc = pq(req_login.text)
            tips = doc("p#tips")
            if str(tips) != "":
                if "用户名或密码" in tips.text():
                    return {"code": 1002, "msg": "用户名或密码不正确"}
                return {"code": 998, "msg": tips.text()}
                
            cookies = self.session.cookies.get_dict()
            return {"code": 1000, "msg": "登录成功", "data": {"cookies": cookies}}
            
        except exceptions.Timeout:
            return {"code": 1003, "msg": "登录超时"}
        except Exception as e:
            return {"code": 999, "msg": f"登录时发生错误: {str(e)}"}
    
    def is_session_valid(self) -> bool:
        """
        检查Session是否有效 - 简化版，减少不必要的网络请求
        """
        if not self.is_logged_in:
            return False
            
        # 如果登录时间在10分钟内，认为Session有效
        if self.login_time and (time.time() - self.login_time) < 600:
            return True
            
        # 超过10分钟后才进行网络检查
        try:
            # 使用一个更轻量的页面来检查Session状态
            test_url = urljoin(self.base_url, "xtgl/index_initMenu.html")
            response = self.session.get(test_url, timeout=3)
            
            # 如果返回登录页面，说明Session已失效
            if "用户登录" in response.text or "login" in response.url.lower():
                return False
                
            return response.status_code == 200
            
        except Exception:
            # 网络异常时假设Session仍然有效，避免频繁重登录
            return True
    
    def ensure_login(self) -> bool:
        """
        确保当前处于登录状态，如果Session失效则自动重新登录
        """
        with self._lock:
            # 如果Session有效，直接返回
            if self.is_session_valid():
                return True
                
            # 如果没有保存的凭证，无法自动重登录
            if not self.credentials:
                self.is_logged_in = False
                return False
                
            # 执行自动重登录
            print(f"检测到Session失效，正在自动重新登录...")
            result = self._perform_login(
                self.credentials['sid'], 
                self.credentials['password']
            )
            
            if result.get('code') == 1000:
                self.is_logged_in = True
                self.login_time = time.time()
                self.cookies = result.get('data', {}).get('cookies', {})
                self.session.cookies.update(self.cookies)
                print("自动重新登录成功")
                return True
            else:
                print(f"自动重新登录失败: {result.get('msg')}")
                self.is_logged_in = False
                return False
    
    def get_session(self) -> requests.Session:
        """
        获取当前的Session对象，确保登录状态
        """
        if not self.ensure_login():
            raise Exception("无法维持登录状态，请检查账号密码")
        return self.session
    
    def _retry_delay(self, attempt: int) -> float:
        delay = self.backoff_base * (self.backoff_factor ** attempt)
        return delay + self.random_func(0, self.backoff_base)

    def request(self, method: str, url: str, **kwargs) -> requests.Response:
        """
        安全的请求方法，自动处理登录状态 - 优化版
        """
        retryable = kwargs.pop('retryable', method.upper() == 'GET')
        max_retries = kwargs.pop('max_retries', self.max_retries)

        # 只在必要时检查登录状态
        if not self.is_logged_in:
            if not self.ensure_login():
                raise Exception("登录状态失效且无法自动重登录")
        
        # 如果URL是相对路径，转换为绝对路径
        if not url.startswith('http'):
            url = urljoin(self.base_url, url)
        
        # 设置默认超时
        if 'timeout' not in kwargs:
            kwargs['timeout'] = self.timeout
            
        attempt = 0
        while True:
            try:
                response = self.session.request(method, url, **kwargs)
                
                # 只在明确的登录失效标志时才重试
                if (response.status_code == 401 or 
                    ("用户登录" in response.text and response.status_code != 404)):
                    
                    # 标记登录状态失效
                    self.is_logged_in = False
                    
                    # 尝试重新登录一次
                    if self.ensure_login():
                        response = self.session.request(method, url, **kwargs)
                    else:
                        raise Exception("Session失效且重新登录失败")

                if (
                    retryable
                    and response.status_code in self.retry_status_codes
                    and attempt < max_retries
                ):
                    self.sleep_func(self._retry_delay(attempt))
                    attempt += 1
                    continue
                        
                return response
                
            except (exceptions.Timeout, exceptions.ConnectionError) as e:
                if retryable and attempt < max_retries:
                    self.sleep_func(self._retry_delay(attempt))
                    attempt += 1
                    continue
                raise Exception(f"请求失败: {str(e)}")
            except Exception as e:
                raise Exception(f"请求失败: {str(e)}")
    
    def get(self, url: str, **kwargs) -> requests.Response:
        """GET请求"""
        return self.request('GET', url, **kwargs)
    
    def post(self, url: str, **kwargs) -> requests.Response:
        """POST请求"""
        return self.request('POST', url, **kwargs)
    
    def logout(self):
        """
        登出并清理Session
        """
        with self._lock:
            self.session.close()
            self.session = requests.Session()
            self._setup_headers()
            self.is_logged_in = False
            self.webvpn_authenticated = False
            self.webvpn_menu_accessible = False
            self.login_time = None
            self.credentials = None
            self.cookies = {}
            self.webvpn = (
                LingnanWebVPN(self.session, self.base_url, self.timeout)
                if is_lingnan_webvpn_url(self.base_url)
                else None
            )
    
    def get_login_status(self) -> Dict[str, Any]:
        """
        获取登录状态信息
        """
        return {
            'is_logged_in': self.is_logged_in,
            'login_time': self.login_time,
            'session_valid': self.is_session_valid() if self.is_logged_in else False,
            'has_credentials': bool(self.credentials),
            'webvpn_authenticated': self.webvpn_authenticated,
            'webvpn_menu_accessible': self.webvpn_menu_accessible,
        }
