import base64
import hashlib
import json
import os
import platform
import re
import sys
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

import requests
import rsa

try:
    from core import license_public_key
except Exception:  # pragma: no cover - defensive fallback for broken builds
    license_public_key = None


MACHINE_CODE_SALT = "Multi_ZF_Assistant-License-v1"
ENV_LICENSE_URL = "ZFN_LICENSE_URL"
ENV_PUBLIC_KEY = "ZFN_LICENSE_PUBLIC_KEY"
ENV_DEV_SKIP = "ZFN_DEV_SKIP_LICENSE"
SIGNED_FIELDS = ("license_id", "hwid_hash", "expires_at", "features", "issued_at")
MACHINE_CODE_RE = re.compile(r"^[a-f0-9]{64}$")


@dataclass
class LicenseStatus:
    allowed: bool
    reason: str
    machine_code: str
    expires_at: Optional[str] = None
    source: str = "none"
    record: Optional[Dict[str, Any]] = None

    @property
    def hwid_hash(self) -> str:
        return self.machine_code


def should_skip_license_check() -> bool:
    """Allow source-tree development without weakening a frozen exe."""
    return (
        os.environ.get(ENV_DEV_SKIP) == "1"
        and not getattr(sys, "frozen", False)
    )


def normalize_hwid(raw_hwid: str) -> str:
    return "|".join(part.strip() for part in str(raw_hwid).splitlines() if part.strip())


def machine_code_from_raw_hwid(raw_hwid: str) -> str:
    normalized = normalize_hwid(raw_hwid)
    payload = f"{MACHINE_CODE_SALT}|{normalized}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def normalize_hwid_to_machine_code(hwid: str) -> str:
    value = str(hwid).strip().lower()
    if MACHINE_CODE_RE.match(value):
        return value
    return machine_code_from_raw_hwid(hwid)


def _read_windows_machine_guid() -> Optional[str]:
    if os.name != "nt":
        return None
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
            return str(value).strip() or None
    except Exception:
        return None


def get_raw_machine_hwid() -> str:
    mac = uuid.getnode()
    parts = [
        ("host", platform.node() or os.environ.get("COMPUTERNAME")),
        ("machine", platform.machine()),
        ("processor", platform.processor()),
        ("mac", f"{mac:012x}" if mac else None),
        ("machine_guid", _read_windows_machine_guid()),
    ]
    stable_parts = [f"{name}={value}" for name, value in parts if value]
    if not stable_parts:
        stable_parts.append(f"user_home={Path.home()}")
    return "|".join(stable_parts)


def get_machine_code(raw_hwid: Optional[str] = None) -> str:
    return machine_code_from_raw_hwid(raw_hwid or get_raw_machine_hwid())


def get_configured_public_key() -> str:
    if not getattr(sys, "frozen", False):
        env_value = os.environ.get(ENV_PUBLIC_KEY, "").strip()
        if env_value:
            return env_value
    return getattr(license_public_key, "PUBLIC_KEY_PEM", "") or ""


def get_configured_license_url() -> str:
    if not getattr(sys, "frozen", False):
        env_value = os.environ.get(ENV_LICENSE_URL, "").strip()
        if env_value:
            return env_value
    return getattr(license_public_key, "LICENSE_URL", "") or ""


def get_cache_grace_days() -> int:
    return int(getattr(license_public_key, "CACHE_GRACE_DAYS", 3) or 3)


def default_license_cache_path() -> str:
    appdata = os.environ.get("APPDATA")
    if appdata:
        base_dir = Path(appdata) / "Multi_ZF_Assistant"
    else:
        base_dir = Path.home() / ".multi_zf_assistant"
    return str(base_dir / "license_cache.json")


def _coerce_date(value: Any) -> Optional[date]:
    if value in (None, "", "never", "permanent", "永久"):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return datetime.strptime(str(value), "%Y-%m-%d").date()


def _today(value: Optional[date]) -> date:
    return value or date.today()


def canonical_license_payload(record: Dict[str, Any]) -> bytes:
    payload: Dict[str, Any] = {}
    for field in SIGNED_FIELDS:
        if field in record:
            payload[field] = record[field]

    if "expires_at" not in payload and "expire_at" in record:
        payload["expires_at"] = record["expire_at"]
    if "features" not in payload:
        payload["features"] = []

    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sign_license_record(record: Dict[str, Any], private_key_pem: str) -> str:
    private_key = rsa.PrivateKey.load_pkcs1(private_key_pem.encode("utf-8"))
    signature = rsa.sign(canonical_license_payload(record), private_key, "SHA-256")
    return base64.b64encode(signature).decode("ascii")


def verify_license_signature(record: Dict[str, Any], public_key_pem: str) -> bool:
    public_key = rsa.PublicKey.load_pkcs1(public_key_pem.encode("utf-8"))
    signature = base64.b64decode(str(record.get("signature", "")))
    rsa.verify(canonical_license_payload(record), signature, public_key)
    return True


def verify_license_record(
    record: Dict[str, Any],
    public_key_pem: str,
    machine_code: str,
    today: Optional[date] = None,
    source: str = "remote",
) -> LicenseStatus:
    if not public_key_pem.strip():
        return LicenseStatus(False, "未配置授权公钥", machine_code, source=source)

    expected_machine_code = normalize_hwid_to_machine_code(machine_code)
    record_machine_code = str(record.get("hwid_hash", "")).strip().lower()
    if record_machine_code != expected_machine_code:
        return LicenseStatus(False, "当前机器未授权", expected_machine_code, source=source)

    try:
        verify_license_signature(record, public_key_pem)
    except Exception:
        return LicenseStatus(False, "授权签名无效", expected_machine_code, source=source)

    expires_at = record.get("expires_at", record.get("expire_at"))
    try:
        expire_date = _coerce_date(expires_at)
    except ValueError:
        return LicenseStatus(False, "授权到期日期格式错误", expected_machine_code, source=source)

    current_date = _today(today)
    if expire_date and expire_date < current_date:
        return LicenseStatus(
            False,
            f"授权已过期: {expires_at}",
            expected_machine_code,
            expires_at=str(expires_at),
            source=source,
            record=record,
        )

    return LicenseStatus(
        True,
        "授权有效",
        expected_machine_code,
        expires_at=str(expires_at) if expires_at else None,
        source=source,
        record=record,
    )


def iter_license_records(payload: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict):
        records = payload.get("licenses") or payload.get("data") or []
    else:
        records = []

    for record in records:
        if isinstance(record, dict):
            yield record


def find_license_record(payload: Any, machine_code: str) -> Optional[Dict[str, Any]]:
    expected_machine_code = normalize_hwid_to_machine_code(machine_code)
    for record in iter_license_records(payload):
        if str(record.get("hwid_hash", "")).strip().lower() == expected_machine_code:
            return record
    return None


def load_remote_license_collection(
    license_url: str,
    request_get: Optional[Callable[..., Any]] = None,
    timeout: int = 8,
) -> Any:
    if license_url.startswith("file://"):
        path = license_url[7:]
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    if os.path.exists(license_url):
        with open(license_url, "r", encoding="utf-8") as f:
            return json.load(f)

    getter = request_get or requests.get
    response = getter(license_url, timeout=timeout)
    if hasattr(response, "raise_for_status"):
        response.raise_for_status()
    try:
        return response.json()
    except Exception:
        return json.loads(response.text)


def save_license_cache(
    record: Dict[str, Any],
    cache_path: Optional[str] = None,
    checked_at: Optional[date] = None,
) -> None:
    path = Path(cache_path or default_license_cache_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    checked = _today(checked_at).isoformat()
    cache_data = {
        "version": 1,
        "checked_at": checked,
        "license": record,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cache_data, f, ensure_ascii=False, indent=2)


def load_license_cache(cache_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    path = Path(cache_path or default_license_cache_path())
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        return None
    return None


def _cache_is_fresh(
    cache_data: Dict[str, Any],
    today: date,
    grace_days: int,
) -> Tuple[bool, str]:
    checked_at = cache_data.get("checked_at")
    try:
        checked_date = _coerce_date(checked_at)
    except ValueError:
        return False, "授权缓存日期格式错误"
    if not checked_date:
        return False, "授权缓存缺少校验日期"
    age_days = (today - checked_date).days
    if age_days < 0:
        return False, "系统日期早于授权缓存日期"
    if age_days > grace_days:
        return False, "授权缓存已超过离线宽限期"
    return True, "授权缓存可用"


def check_cached_license(
    public_key_pem: str,
    machine_code: str,
    cache_path: Optional[str] = None,
    today: Optional[date] = None,
    grace_days: Optional[int] = None,
) -> LicenseStatus:
    current_date = _today(today)
    cache_data = load_license_cache(cache_path)
    if not cache_data:
        return LicenseStatus(False, "没有可用的授权缓存", machine_code, source="cache")

    fresh, reason = _cache_is_fresh(
        cache_data,
        current_date,
        get_cache_grace_days() if grace_days is None else grace_days,
    )
    if not fresh:
        return LicenseStatus(False, reason, machine_code, source="cache")

    record = cache_data.get("license")
    if not isinstance(record, dict):
        return LicenseStatus(False, "授权缓存内容无效", machine_code, source="cache")

    return verify_license_record(
        record,
        public_key_pem,
        machine_code,
        today=current_date,
        source="cache",
    )


def check_license(
    license_url: Optional[str] = None,
    public_key_pem: Optional[str] = None,
    cache_path: Optional[str] = None,
    request_get: Optional[Callable[..., Any]] = None,
    raw_hwid: Optional[str] = None,
    today: Optional[date] = None,
    timeout: int = 8,
    grace_days: Optional[int] = None,
) -> LicenseStatus:
    machine_code = get_machine_code(raw_hwid)
    current_date = _today(today)
    public_key = public_key_pem if public_key_pem is not None else get_configured_public_key()
    url = license_url if license_url is not None else get_configured_license_url()

    if not public_key.strip():
        return LicenseStatus(False, "未配置授权公钥", machine_code)
    if not str(url).strip():
        return LicenseStatus(False, "未配置授权地址", machine_code)

    try:
        payload = load_remote_license_collection(
            str(url).strip(),
            request_get=request_get,
            timeout=timeout,
        )
        record = find_license_record(payload, machine_code)
        if not record:
            return LicenseStatus(False, "当前机器未授权", machine_code, source="remote")

        status = verify_license_record(
            record,
            public_key,
            machine_code,
            today=current_date,
            source="remote",
        )
        if status.allowed:
            save_license_cache(record, cache_path, checked_at=current_date)
        return status
    except Exception as exc:
        cached_status = check_cached_license(
            public_key,
            machine_code,
            cache_path=cache_path,
            today=current_date,
            grace_days=grace_days,
        )
        if cached_status.allowed:
            return cached_status
        return LicenseStatus(
            False,
            f"无法连接授权服务器，且本地缓存不可用: {exc}",
            machine_code,
            source="remote",
        )
