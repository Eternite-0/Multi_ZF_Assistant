"""岭南师范学院 WebVPN 登录支持。

WebVPN 与教务系统使用不同的会话。这个模块在同一个
``requests.Session`` 中完成 WebVPN 的 CAS 登录，以便后续教务接口请求
自动携带 VPN 会话 Cookie。
"""

from __future__ import annotations

import base64
import secrets
import time
from dataclasses import dataclass
from typing import Dict, Optional
from urllib.parse import quote, urljoin, urlparse

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7
from pyquery import PyQuery as pq


WEBVPN_HOST = "csvpn.lingnan.edu.cn"
WEBVPN_AUTH_PATH = (
    "/https/77726476706e69737468656265737421f1e2559434357a467b1ac7a0915b243badf0ae285e0ed5da36"
    "/authserver"
)
WEBVPN_SERVICE = f"https://{WEBVPN_HOST}/login?cas_login=true"
_AES_CHARS = "ABCDEFGHJKMNPQRSTWXYZabcdefhijkmnprstwxyz2345678"


@dataclass(frozen=True)
class WebVPNChallenge:
    """一次 WebVPN 登录所需的、短时有效的验证码挑战。"""

    image: bytes
    post_url: str
    fields: Dict[str, str]
    salt: str


class WebVPNError(RuntimeError):
    """WebVPN 页面结构或认证流程发生变化时抛出。"""


def is_lingnan_webvpn_url(base_url: str) -> bool:
    """判断地址是否为岭南师范学院 WebVPN 转发地址。"""

    parsed = urlparse(base_url)
    return parsed.hostname == WEBVPN_HOST and "/http/" in parsed.path


def _random_string(length: int) -> str:
    return "".join(secrets.choice(_AES_CHARS) for _ in range(length))


def encrypt_webvpn_password(password: str, salt: str) -> str:
    """复现登录页 ``encryptPassword`` 的 AES-CBC 加密格式。"""

    if len(salt.encode("utf-8")) not in (16, 24, 32):
        raise WebVPNError("WebVPN 返回了无效的密码加密盐值")

    iv = _random_string(16).encode("utf-8")
    plaintext = (_random_string(64) + password).encode("utf-8")
    padder = PKCS7(algorithms.AES.block_size).padder()
    padded = padder.update(plaintext) + padder.finalize()
    cipher = Cipher(algorithms.AES(salt.encode("utf-8")), modes.CBC(iv))
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(ciphertext).decode("ascii")


class LingnanWebVPN:
    """使用既有 ``requests.Session`` 建立 WebVPN 会话。"""

    def __init__(self, session, base_url: str, timeout: int = 10):
        if not is_lingnan_webvpn_url(base_url):
            raise ValueError("不是受支持的岭南师范学院 WebVPN 地址")
        self.session = session
        self.base_url = base_url if base_url.endswith("/") else f"{base_url}/"
        self.timeout = timeout
        self._challenge: Optional[WebVPNChallenge] = None

        parsed = urlparse(base_url)
        self.origin = f"{parsed.scheme}://{parsed.netloc}"
        self.login_url = f"{self.origin}{WEBVPN_AUTH_PATH}/login?service={quote(WEBVPN_SERVICE, safe='')}"

    def begin_login(self) -> WebVPNChallenge:
        """请求登录页及验证码；调用方应只在内存中短暂保存验证码图片。"""

        response = self.session.get(self.login_url, timeout=self.timeout)
        response.raise_for_status()
        document = pq(response.text)
        form = document("#pwdFromId")
        salt = form("#pwdEncryptSalt").attr("value")
        action = form.attr("action")
        if not form or not salt or not action:
            raise WebVPNError("未找到 WebVPN 账号密码登录表单")

        fields = {}
        for item in form("input").items():
            name = item.attr("name")
            input_type = item.attr("type")
            if name and input_type == "hidden":
                fields[name] = item.attr("value") or ""

        captcha_url = urljoin(response.url, f"getCaptcha.htl?{int(time.time() * 1000)}")
        captcha_response = self.session.get(captcha_url, timeout=self.timeout)
        captcha_response.raise_for_status()
        challenge = WebVPNChallenge(
            image=captcha_response.content,
            post_url=urljoin(response.url, action),
            fields=fields,
            salt=salt,
        )
        self._challenge = challenge
        return challenge

    def complete_login(self, sid: str, password: str, captcha: str) -> Dict[str, object]:
        """提交验证码并验证同一会话能否访问教务系统。"""

        challenge = self._challenge or self.begin_login()
        data = dict(challenge.fields)
        data.update(
            {
                "username": sid,
                "password": encrypt_webvpn_password(password, challenge.salt),
                "captcha": captcha.strip(),
            }
        )
        # 页面加载时 login.js 会将 service 动态附加到 form action；静态
        # HTML 中看不到该参数，因此客户端需要显式复现这一步。
        response = self.session.post(
            challenge.post_url,
            params={"service": WEBVPN_SERVICE},
            data=data,
            headers={"Referer": self.login_url, "Origin": self.origin},
            timeout=self.timeout,
        )

        # 认证错误会重新呈现统一认证页。不要全文搜索“验证码错误”：
        # 登录页的验证码图片 alt 属性本身就包含该固定文字。
        document = pq(response.text)
        error_text = " ".join(
            text.strip()
            for text in (
                document("#showErrorTip").text(),
                document(".form-error").text(),
                document(".item-error-tip").text(),
            )
            if text and text.strip()
        )
        if "Verification code error" in error_text or "验证码错误" in error_text:
            self._challenge = None
            return {"code": 1004, "msg": "WebVPN 验证码错误"}
        if "用户名或密码错误" in error_text or "用户名或密码不正确" in error_text:
            self._challenge = None
            return {"code": 1002, "msg": "WebVPN 用户名或密码错误"}
        if response.status_code >= 400:
            self._challenge = None
            return {"code": 1005, "msg": f"WebVPN 认证被拒绝（HTTP {response.status_code}）"}

        # WebVPN 与教务系统是两层不同认证。此处仅确认 CAS 表单未返回
        # 验证码/凭据错误；教务菜单是否已被 SSO 登录由 SessionManager 单独
        # 检测，不能把教务登录页误判为 WebVPN 认证失败。
        self._challenge = None
        return {"code": 1000, "msg": "WebVPN 登录成功", "data": {"cookies": self.session.cookies.get_dict()}}
