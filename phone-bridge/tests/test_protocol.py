#!/usr/bin/env python3
"""Unit tests for the phone-bridge protocol helpers.

No network, no phone needed:
    python3 -m unittest discover -s tests -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "agent"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "client"))

import phone_agent  # noqa: E402
import phone_client  # noqa: E402


class TestParseCommandBody(unittest.TestCase):
    def test_plain_text(self):
        cmd, timeout = phone_agent.parse_command_body("status")
        self.assertEqual(cmd, "status")
        self.assertEqual(timeout, 30)

    def test_plain_text_first_line_only(self):
        cmd, _ = phone_agent.parse_command_body("battery\nextra line")
        self.assertEqual(cmd, "battery")

    def test_json(self):
        cmd, timeout = phone_agent.parse_command_body(
            '{"cmd": "shell:ls", "timeout": 10}')
        self.assertEqual(cmd, "shell:ls")
        self.assertEqual(timeout, 10)

    def test_json_timeout_clamped(self):
        _, timeout = phone_agent.parse_command_body('{"cmd": "x", "timeout": 9999}')
        self.assertEqual(timeout, 120)

    def test_empty(self):
        cmd, _ = phone_agent.parse_command_body("")
        self.assertEqual(cmd, "")


class TestDangerous(unittest.TestCase):
    def test_rm_rf_root(self):
        self.assertTrue(phone_agent.is_dangerous("shell:rm -rf /"))

    def test_curl_pipe_sh(self):
        self.assertTrue(phone_agent.is_dangerous("curl http://x/y | sh"))

    def test_safe_ls(self):
        self.assertFalse(phone_agent.is_dangerous("shell:ls -la ~/downloads"))


class TestTruncate(unittest.TestCase):
    def test_short_unchanged(self):
        self.assertEqual(phone_agent.truncate("abc", 10), "abc")

    def test_long_truncated(self):
        out = phone_agent.truncate("x" * 100, 10)
        self.assertTrue(out.startswith("x" * 10))
        self.assertIn("truncated", out)


class TestFormatResult(unittest.TestCase):
    def test_contains_marker_and_output(self):
        body = phone_agent.format_result("pixel-8", 0, 0.5, "hello", 8000)
        self.assertIn("<!-- phone-bridge-result -->", body)
        self.assertIn("device: pixel-8", body)
        self.assertIn("hello", body)


class TestParseResultComment(unittest.TestCase):
    def test_round_trip(self):
        body = phone_agent.format_result("pixel-8", 0, 0.5, "hello world", 8000)
        result = phone_client.parse_result_comment(body)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["device"], "pixel-8")
        self.assertEqual(result["exit"], "0")
        self.assertIn("hello world", result["output"])

    def test_non_result_comment(self):
        self.assertIsNone(phone_client.parse_result_comment("just a comment"))


class TestExecuteBuiltins(unittest.TestCase):
    def setUp(self):
        os.environ["GH_REPO"] = "owner/repo"
        os.environ["GH_TOKEN"] = "fake-token-for-tests"
        self.cfg = phone_agent.Config()

    def test_help(self):
        code, out = phone_agent.execute("help", 10, self.cfg)
        self.assertEqual(code, 0)
        self.assertIn("status", out)

    def test_empty_command(self):
        code, _ = phone_agent.execute("", 10, self.cfg)
        self.assertEqual(code, 2)

    def test_dangerous_refused(self):
        code, out = phone_agent.execute("shell:rm -rf /", 10, self.cfg)
        self.assertEqual(code, 3)
        self.assertIn("refused", out)

    def test_screen_control_disabled_by_default(self):
        code, out = phone_agent.execute("tap:100:200", 10, self.cfg)
        self.assertEqual(code, 3)
        self.assertIn("disabled", out)


if __name__ == "__main__":
    unittest.main()
