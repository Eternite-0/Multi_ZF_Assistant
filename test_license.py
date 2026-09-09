import json
import os
import tempfile
import unittest
from datetime import date
from unittest.mock import patch

import rsa

from core import license as license_core
from scripts import license_admin


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.text = json.dumps(payload, ensure_ascii=False)
        self.status_code = 200

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class TestLicenseAuthorization(unittest.TestCase):
    def setUp(self):
        public_key, private_key = rsa.newkeys(1024)
        self.public_key_pem = public_key.save_pkcs1().decode("utf-8")
        self.private_key_pem = private_key.save_pkcs1().decode("utf-8")
        self.raw_hwid = "HOST=TEST-PC|GUID=ABC-123|MAC=001122334455"
        self.machine_code = license_core.machine_code_from_raw_hwid(self.raw_hwid)

    def _record(self, expires_at="2027-07-04", machine_code=None):
        return license_admin.create_license_record(
            hwid=machine_code or self.machine_code,
            private_key_pem=self.private_key_pem,
            expires_at=expires_at,
            features=["full"],
            license_id="test-license",
            issued_at="2026-07-04",
        )

    def test_machine_code_is_stable_hash(self):
        first = license_core.machine_code_from_raw_hwid(self.raw_hwid)
        second = license_core.machine_code_from_raw_hwid(self.raw_hwid)

        self.assertEqual(first, second)
        self.assertEqual(64, len(first))
        self.assertNotIn("TEST-PC", first)

    def test_signed_license_allows_matching_machine(self):
        status = license_core.verify_license_record(
            self._record(),
            self.public_key_pem,
            self.machine_code,
            today=date(2026, 7, 4),
        )

        self.assertTrue(status.allowed)
        self.assertEqual("2027-07-04", status.expires_at)

    def test_tampered_license_is_rejected(self):
        record = self._record()
        record["expires_at"] = "2099-01-01"

        status = license_core.verify_license_record(
            record,
            self.public_key_pem,
            self.machine_code,
            today=date(2026, 7, 4),
        )

        self.assertFalse(status.allowed)
        self.assertIn("签名", status.reason)

    def test_expired_license_is_rejected(self):
        status = license_core.verify_license_record(
            self._record(expires_at="2026-07-03"),
            self.public_key_pem,
            self.machine_code,
            today=date(2026, 7, 4),
        )

        self.assertFalse(status.allowed)
        self.assertIn("过期", status.reason)

    def test_check_license_uses_remote_and_saves_cache(self):
        record = self._record()

        def request_get(url, timeout):
            self.assertEqual("https://gitee.example/licenses.json", url)
            self.assertEqual(8, timeout)
            return FakeResponse({"version": 1, "licenses": [record]})

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = os.path.join(tmpdir, "license_cache.json")
            status = license_core.check_license(
                license_url="https://gitee.example/licenses.json",
                public_key_pem=self.public_key_pem,
                cache_path=cache_path,
                request_get=request_get,
                raw_hwid=self.raw_hwid,
                today=date(2026, 7, 4),
            )

            self.assertTrue(status.allowed)
            self.assertEqual("remote", status.source)
            self.assertTrue(os.path.exists(cache_path))

    def test_check_license_falls_back_to_valid_cache_when_remote_fails(self):
        record = self._record()

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = os.path.join(tmpdir, "license_cache.json")
            license_core.save_license_cache(
                record,
                cache_path,
                checked_at=date(2026, 7, 4),
            )

            def request_get(url, timeout):
                raise TimeoutError("network down")

            status = license_core.check_license(
                license_url="https://gitee.example/licenses.json",
                public_key_pem=self.public_key_pem,
                cache_path=cache_path,
                request_get=request_get,
                raw_hwid=self.raw_hwid,
                today=date(2026, 7, 5),
            )

            self.assertTrue(status.allowed)
            self.assertEqual("cache", status.source)

    def test_frozen_build_ignores_environment_license_overrides(self):
        old_frozen = getattr(license_core.sys, "frozen", None)
        old_public_key = license_core.license_public_key.PUBLIC_KEY_PEM
        old_license_url = license_core.license_public_key.LICENSE_URL
        try:
            license_core.sys.frozen = True
            license_core.license_public_key.PUBLIC_KEY_PEM = "embedded-public-key"
            license_core.license_public_key.LICENSE_URL = "https://embedded.example/licenses.json"
            with patch.dict(
                os.environ,
                {
                    license_core.ENV_PUBLIC_KEY: "attacker-public-key",
                    license_core.ENV_LICENSE_URL: "https://attacker.example/licenses.json",
                },
            ):
                self.assertEqual(
                    "embedded-public-key",
                    license_core.get_configured_public_key(),
                )
                self.assertEqual(
                    "https://embedded.example/licenses.json",
                    license_core.get_configured_license_url(),
                )
        finally:
            if old_frozen is None:
                delattr(license_core.sys, "frozen")
            else:
                license_core.sys.frozen = old_frozen
            license_core.license_public_key.PUBLIC_KEY_PEM = old_public_key
            license_core.license_public_key.LICENSE_URL = old_license_url


if __name__ == "__main__":
    unittest.main()
