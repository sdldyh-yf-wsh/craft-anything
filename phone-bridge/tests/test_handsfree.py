#!/usr/bin/env python3
"""Unit tests for hands-free helpers (no network, no phone).

    python3 -m unittest discover -s tests -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "agent"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "client"))

import handsfree  # noqa: E402
import phone_mcp  # noqa: E402
import autopilot  # noqa: E402


class TestParseVoice(unittest.TestCase):
    def test_battery_chinese(self):
        self.assertEqual(handsfree.parse_voice("电量多少"), "battery")

    def test_status_chinese(self):
        self.assertEqual(handsfree.parse_voice("手机状态"), "status")

    def test_sms(self):
        self.assertEqual(handsfree.parse_voice("看看短信"), "sms")

    def test_screenshot(self):
        self.assertEqual(handsfree.parse_voice("截个图"), "screenshot")

    def test_notify(self):
        cmd = handsfree.parse_voice("通知 提醒 开会了")
        self.assertTrue(cmd.startswith("notify:"))

    def test_run_shell(self):
        self.assertEqual(handsfree.parse_voice("执行 ls -la"), "shell:ls -la")

    def test_ignores_ambient_chatter(self):
        self.assertEqual(handsfree.parse_voice("今天天气真不错"), "")

    def test_empty(self):
        self.assertEqual(handsfree.parse_voice(""), "")


class TestToolToCommand(unittest.TestCase):
    def test_status(self):
        self.assertEqual(phone_mcp.tool_to_command("phone_status", {}), "status")

    def test_shell(self):
        cmd = phone_mcp.tool_to_command("phone_shell", {"command": "ls"})
        self.assertEqual(cmd, "shell:ls")

    def test_tap(self):
        cmd = phone_mcp.tool_to_command("phone_tap", {"x": 100, "y": 200})
        self.assertEqual(cmd, "tap:100:200")

    def test_swipe(self):
        cmd = phone_mcp.tool_to_command("phone_swipe", {
            "x1": 10, "y1": 900, "x2": 10, "y2": 200, "duration_ms": 250,
        })
        self.assertEqual(cmd, "swipe:10:900:10:200:250")

    def test_input(self):
        cmd = phone_mcp.tool_to_command("phone_input", {"text": "hello"})
        self.assertEqual(cmd, "input:hello")

    def test_unknown_tool(self):
        with self.assertRaises(ValueError):
            phone_mcp.tool_to_command("nope", {})


class TestMcpHandleRequest(unittest.TestCase):
    def test_initialize(self):
        resp = phone_mcp.handle_request(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize"}, None, "")
        assert resp is not None
        self.assertEqual(resp["id"], 1)
        self.assertIn("protocolVersion", resp["result"])

    def test_tools_list(self):
        resp = phone_mcp.handle_request(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, None, "")
        assert resp is not None
        names = [t["name"] for t in resp["result"]["tools"]]
        self.assertEqual(len(names), 12)
        for expected in ("phone_status", "phone_shell", "phone_tap",
                         "phone_swipe", "phone_input", "phone_screenshot"):
            self.assertIn(expected, names)

    def test_ping(self):
        resp = phone_mcp.handle_request(
            {"jsonrpc": "2.0", "id": 3, "method": "ping"}, None, "")
        assert resp is not None
        self.assertEqual(resp["result"], {})

    def test_tools_call_without_credentials_returns_error(self):
        resp = phone_mcp.handle_request({
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "phone_status", "arguments": {}},
        }, None, "")
        assert resp is not None
        self.assertTrue(resp["result"]["isError"])

    def test_unknown_method(self):
        resp = phone_mcp.handle_request(
            {"jsonrpc": "2.0", "id": 4, "method": "nope"}, None, "")
        assert resp is not None
        self.assertIn("error", resp)


class TestAutopilotParseTask(unittest.TestCase):
    def test_task_line(self):
        self.assertEqual(autopilot.parse_task("task: battery"), "battery")

    def test_task_shell(self):
        self.assertEqual(autopilot.parse_task("task: shell:ls"), "shell:ls")

    def test_not_a_task(self):
        self.assertIsNone(autopilot.parse_task("hello world"))

    def test_ignores_autopilot_own_result_comment(self):
        own = (
            "<!-- phone-bridge-autopilot-result -->\n"
            "reply_to: 42\n"
            "task: battery\n"
            "```output\n85%\n```"
        )
        self.assertIsNone(autopilot.parse_task(own))
        self.assertTrue(autopilot.is_autopilot_result(own))

    def test_extract_replied_ids(self):
        comments = [
            {"id": 42, "body": "task: battery"},
            {"id": 43, "body": "<!-- phone-bridge-autopilot-result -->\nreply_to: 42\n"},
        ]
        self.assertEqual(autopilot.extract_replied_ids(comments), {42})

    def test_heartbeat_detection(self):
        self.assertTrue(autopilot.is_heartbeat("<!-- phone-bridge-heartbeat -->"))
        self.assertFalse(autopilot.is_heartbeat("task: battery"))


if __name__ == "__main__":
    unittest.main()
