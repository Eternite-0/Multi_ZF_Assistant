import unittest

import build_nuitka


class TestBuildNuitka(unittest.TestCase):
    def test_hardened_command_contains_release_protection_flags(self):
        command = build_nuitka.build_nuitka_command(extra_args=[])
        command_text = " ".join(command)

        self.assertIn("--onefile", command)
        self.assertIn("--deployment", command)
        self.assertIn("--lto=yes", command)
        self.assertIn("--python-flag=no_asserts", command)
        self.assertIn("--python-flag=no_docstrings", command)
        self.assertIn("--windows-console-mode=disable", command)
        self.assertNotIn("--windows-disable-console", command_text)


if __name__ == "__main__":
    unittest.main()
