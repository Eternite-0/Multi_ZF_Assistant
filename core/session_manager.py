import time
import threading
from typing import Optional, Dict, Any
from urllib.parse import urljoin
import requests
from requests import exceptions
from pyquery import PyQuery as pq
import json


class SessionManager:
    """
    Session管理器 - 维持长连接并自动处理登录状态
    """
    
    def __init__(self, base_url: str, timeout: int = 10):
        self.base_url = base_url
        self.timeout = timeout
        self.session = requests.Session()
        self.session.keep_alive = True  # 保持连接
        
        # 登录状态管理
        self.is_logged_in = False
        self.login_time = None
        self.credentials = None
        self.cookies = {}
        
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
                # 保存凭证用于自动重登录
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
    
    def request(self, method: str, url: str, **kwargs) -> requests.Response:
        """
        安全的请求方法，自动处理登录状态 - 优化版
        """
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
            
        # 执行请求
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
                    
            return response
            
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
            self.login_time = None
            self.credentials = None
            self.cookies = {}
    
    def get_login_status(self) -> Dict[str, Any]:
        """
        获取登录状态信息
        """
        return {
            'is_logged_in': self.is_logged_in,
            'login_time': self.login_time,
            'session_valid': self.is_session_valid() if self.is_logged_in else False,
            'has_credentials': bool(self.credentials)
        }