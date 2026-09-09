import json
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path

import rsa

from core.license import normalize_hwid_to_machine_code, verify_license_record
from scripts.license_admin_service import (
    LicenseIssueInput,
    build_git_ssh_command,
    issue_license_to_file,
)


class TestLicenseAdminService(unittest.TestCase):
    def setUp(self):
        public_key, private_key = rsa.newkeys(1024)
        self.public_key_pem = public_key.save_pkcs1().decode("utf-8")
        self.private_key_pem = private_key.save_pkcs1().decode("utf-8")

    def test_issue_license_to_file_creates_signed_permanent_record(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            private_key_path = os.path.join(tmpdir, "private.pem")
            license_path = os.path.join(tmpdir, "licenses.json")
            Path(private_key_path).write_text(self.private_key_pem, encoding="utf-8")

            record = issue_license_to_file(
                LicenseIssueInput(
                    hwid="customer-hwid",
                    owner="张三",
                    private_key_path=private_key_path,
                    licenses_path=license_path,
                ),
                today=date(2026, 7, 4),
            )

            machine_code = normalize_hwid_to_machine_code("customer-hwid")
            status = verify_license_record(
                record,
                self.public_key_pem,
                machine_code,
                today=date(2026, 7, 4),
            )

            self.assertTrue(status.allowed)
            self.assertEqual("permanent", record["expires_at"])
            self.assertEqual("张三", record["owner"])
            with open(license_path, encoding="utf-8") as f:
                collection = json.load(f)
            self.assertEqual(1, len(collection["licenses"]))

    def test_issue_license_to_file_replaces_same_machine_record(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            private_key_path = os.path.join(tmpdir, "private.pem")
            license_path = os.path.join(tmpdir, "licenses.json")
            Path(private_key_path).write_text(self.private_key_pem, encoding="utf-8")

            first = LicenseIssueInput(
                hwid="same-hwid",
                owner="old-owner",
                private_key_path=private_key_path,
                licenses_path=license_path,
            )
            second = LicenseIssueInput(
                hwid="same-hwid",
                owner="new-owner",
                private_key_path=private_key_path,
                licenses_path=license_path,
            )

            issue_license_to_file(first, today=date(2026, 7, 4))
            issue_license_to_file(second, today=date(2026, 7, 4))

            with open(license_path, encoding="utf-8") as f:
                collection = json.load(f)

            self.assertEqual(1, len(collection["licenses"]))
            self.assertEqual("new-owner", collection["licenses"][0]["owner"])

    def test_issue_license_to_file_rejects_public_key_with_clear_message(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            public_key_path = os.path.join(tmpdir, "license_public.pem")
            license_path = os.path.join(tmpdir, "licenses.json")
            Path(public_key_path).write_text(self.public_key_pem, encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "你选的是公钥"):
                issue_license_to_file(
                    LicenseIssueInput(
                        hwid="customer-hwid",
                        private_key_path=public_key_path,
                        licenses_path=license_path,
                    )
                )

    def test_build_git_ssh_command_pins_key_and_batch_mode(self):
        command = build_git_ssh_command(r"C:\Users\me\.ssh\gitee_key")

        self.assertIn("IdentitiesOnly=yes", command)
        self.assertIn("BatchMode=yes", command)
        self.assertIn(r"C:\Users\me\.ssh\gitee_key", command)


if __name__ == "__main__":
    unittest.main()
