#!/usr/bin/env python3
"""
phone-bridge MCP server — hands-free phone control for any MCP client.

Exposes the phone as MCP tools over stdio (JSON-RPC 2.0, one JSON
object per line). Works with Claude Code, craft-anything-cli mcp,
Cursor, and any MCP-compatible agent: the agent calls tools like
phone_status / phone_shell / phone_tap directly, no manual CLI.

Each tool sends a command through the GitHub relay (same protocol
as phone_client.py), so it works from sandboxes that can only
reach api.github.com.

Tools:
    phone_status        battery, storage, uptime, Termux info
    phone_battery       battery level/status
    phone_shell         arbitrary shell command (dangerous patterns refused)
    phone_sms           last 10 SMS
    phone_clipboard_get read clipboard
    phone_clipboard_set write clipboard
    phone_notify        send a notification (title, body)
    phone_location      GPS location
    phone_tap           tap screen (needs Shizuku on phone)
    phone_screenshot    save screenshot on phone, report path

Env: GH_REPO, GH_TOKEN, DEVICE_ID (same as phone_client.py)

Run:
    python3 phone_mcp.py            # stdio server (for MCP clients)
    python3 phone_mcp.py --selftest # print tools/list JSON and exit

Original work. MCP protocol shape follows the public MCP spec;
no code is copied from any MCP implementation.
"""

from __future__ import annotations

import json
import os
import sys

# Reuse the GitHub relay client from phone_client.py (same directory).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from phone_client import GitHub, parse_result_comment  # noqa: E402

PROTOCOL_VERSION = "2024-11-05"

TOOLS = [
    {
        "name": "phone_status",
        "description": "Get phone status: battery, storage, uptime, Termux info.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "phone_battery",
        "description": "Get battery level and charging status.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "phone_shell",
        "description": "Run a shell command on the phone (Termux). Dangerous patterns are refused by the agent.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to run"},
                "timeout": {"type": "integer", "description": "Timeout seconds (default 30)"},
            },
            "required": ["command"],
        },
    },
    {
        "name": "phone_sms",
        "description": "Read the last 10 SMS messages (needs SMS permission on phone).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "phone_clipboard_get",
        "description": "Read the phone clipboard.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "phone_clipboard_set",
        "description": "Write text to the phone clipboard.",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
    {
        "name": "phone_notify",
        "description": "Send a notification to the phone.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["title"],
        },
    },
    {
        "name": "phone_location",
        "description": "Get GPS location (needs location permission).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "phone_tap",
        "description": "Tap the screen at x,y (needs Shizuku + ENABLE_SCREEN_CONTROL=1 on phone).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "x": {"type": "integer"},
                "y": {"type": "integer"},
            },
            "required": ["x", "y"],
        },
    },
    {
        "name": "phone_swipe",
        "description": "Swipe screen from (x1,y1) to (x2,y2) over ms milliseconds (needs Shizuku + ENABLE_SCREEN_CONTROL=1).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "x1": {"type": "integer"},
                "y1": {"type": "integer"},
                "x2": {"type": "integer"},
                "y2": {"type": "integer"},
                "duration_ms": {"type": "integer", "description": "Duration in ms (default 300)"},
            },
            "required": ["x1", "y1", "x2", "y2"],
        },
    },
    {
        "name": "phone_input",
        "description": "Type text into the focused field on the phone screen (needs Shizuku + ENABLE_SCREEN_CONTROL=1).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "phone_screenshot",
        "description": "Save a screenshot on the phone and report its path.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def tool_to_command(name: str, args: dict) -> str:
    if name == "phone_status":
        return "status"
    if name == "phone_battery":
        return "battery"
    if name == "phone_shell":
        return f"shell:{args.get('command', '')}"
    if name == "phone_sms":
        return "sms"
    if name == "phone_clipboard_get":
        return "clipboard-get"
    if name == "phone_clipboard_set":
        return f"clipboard-set:{args.get('text', '')}"
    if name == "phone_notify":
        return f"notify:{args.get('title', 'phone-bridge')}:{args.get('body', '')}"
    if name == "phone_location":
        return "location"
    if name == "phone_tap":
        return f"tap:{args.get('x', 0)}:{args.get('y', 0)}"
    if name == "phone_swipe":
        ms = args.get("duration_ms", 300)
        return f"swipe:{args.get('x1', 0)}:{args.get('y1', 0)}:{args.get('x2', 0)}:{args.get('y2', 0)}:{ms}"
    if name == "phone_input":
        return f"input:{args.get('text', '')}"
    if name == "phone_screenshot":
        return "screenshot"
    raise ValueError(f"unknown tool: {name}")


def call_phone(gh: GitHub, device: str, cmd: str, timeout: int = 30,
               wait: int = 90) -> str:
    """Send one command via GitHub relay, return formatted result text."""
    import time
    payload = {"cmd": cmd, "timeout": timeout}
    if device:
        payload["device"] = device
    number = gh.create_issue(f"[phone] {cmd[:60]}",
                             json.dumps(payload, ensure_ascii=False))
    deadline = time.time() + wait
    while time.time() < deadline:
        for comment in gh.get_comments(number):
            result = parse_result_comment(str(comment.get("body", "")))
            if result is not None:
                return (f"exit={result.get('exit', '?')} "
                        f"duration={result.get('duration', '?')}\n"
                        f"{result.get('output', '')}")
        time.sleep(3)
    return f"timed out after {wait}s waiting for #{number}. Is the phone agent running?"


def handle_request(req: dict, gh: GitHub | None, device: str) -> dict | None:
    method = req.get("method", "")
    req_id = req.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": req_id, "result": {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "phone-bridge", "version": "1.0.0"},
        }}
    if method.startswith("notifications/"):
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = req.get("params", {})
        name = params.get("name", "")
        args = params.get("arguments", {}) or {}
        if gh is None:
            text = "GH_REPO/GH_TOKEN not set; cannot reach phone."
            is_error = True
        else:
            try:
                cmd = tool_to_command(name, args)
                timeout = int(args.get("timeout", 30)) if name == "phone_shell" else 30
                text = call_phone(gh, device, cmd, timeout=timeout)
                is_error = False
            except Exception as e:
                text = f"error: {e}"
                is_error = True
        return {"jsonrpc": "2.0", "id": req_id, "result": {
            "content": [{"type": "text", "text": text}],
            "isError": is_error,
        }}
    return {"jsonrpc": "2.0", "id": req_id, "error": {
        "code": -32601, "message": f"method not found: {method}"}}


def main() -> int:
    if "--selftest" in sys.argv:
        print(json.dumps({"tools": TOOLS}, ensure_ascii=False, indent=2))
        return 0
    repo = os.environ.get("GH_REPO", "").strip()
    token = os.environ.get("GH_TOKEN", "").strip()
    device = os.environ.get("DEVICE_ID", "").strip()
    gh = GitHub(repo, token) if repo and token else None
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle_request(req, gh, device)
        if resp is not None:
            print(json.dumps(resp, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
