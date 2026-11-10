#!/usr/bin/env python3
"""
phone-bridge agent — runs on an Android phone inside Termux.

Polls a GitHub repository's Issues (label: phone-cmd) for commands,
executes them on the phone, and posts the result back as an Issue
comment. The phone only ever makes *outbound* HTTPS calls to
api.github.com, so no public IP, no port forwarding and no VPN
account are needed. This is what lets a cloud chat sandbox (which
can only reach github.com / api.github.com) control the phone.

Protocol
--------
Client -> agent (create an Issue):
    title:  [phone] <short description>
    body:   plain command text, OR a JSON object:
            {"cmd": "status", "timeout": 30, "device": "pixel-8"}
    labels: phone-cmd

Agent -> client (Issue comment):
    <!-- phone-bridge-result -->
    device: <DEVICE_ID>
    exit: <code>
    duration: <seconds>s
    ```output
    <stdout+stderr, capped>
    ```

Built-in commands (no shell needed):
    status / ping     battery, storage, uptime, Termux info
    battery           termux-battery (or /sys fallback)
    storage           df -h
    sms               termux-sms-list (needs SMS permission)
    clipboard-get     termux-clipboard-get
    clipboard-set:<t> termux-clipboard-set
    location          termux-location
    notify:<t>:<b>    termux-notification
    toast:<msg>       termux-toast
    shell:<cmd>       arbitrary shell command in Termux
    help              list commands

Screen control (needs ENABLE_SCREEN_CONTROL=1 and Shizuku/rish):
    tap:<x>:<y>  swipe:<x1>:<y1>:<x2>:<y2>:<ms>  input:<text>
    screenshot   (saves to ~/phone-bridge-screenshot.png, reports path)

Environment:
    GH_REPO               owner/repo            (required)
    GH_TOKEN              GitHub PAT            (required, never logged)
    DEVICE_ID             label for this phone  (default: "phone")
    POLL_INTERVAL         seconds between polls (default: 5)
    HEARTBEAT_ISSUE       issue number for heartbeats (optional)
    HEARTBEAT_INTERVAL    seconds between heartbeats (default: 300)
    ENABLE_SCREEN_CONTROL 1 to allow tap/swipe/input/screenshot
    ALLOW_DANGEROUS       1 to allow destructive shell patterns
    MAX_OUTPUT            max result chars      (default: 8000)

Original work. Concepts inspired by open-source projects listed in
../docs/github-projects.md; no code is copied from them.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

API_BASE = "https://api.github.com"
USER_AGENT = "phone-bridge-agent/1.0"

# Destructive shell patterns refused unless ALLOW_DANGEROUS=1.
DANGEROUS_PATTERNS = [
    r"rm\s+-rf\s+/",
    r"rm\s+-rf\s+~",
    r"mkfs",
    r"dd\s+if=",
    r":\(\)\s*\{",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bhalt\b",
    r"chmod\s+-R\s+777\s+/",
    r"curl[^|]*\|\s*(ba)?sh",
    r"wget[^|]*\|\s*(ba)?sh",
]


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def env_int(name: str, default: int) -> int:
    try:
        return int(env(name, str(default)))
    except ValueError:
        return default


def env_flag(name: str) -> bool:
    return env(name, "0") in ("1", "true", "yes", "on")


class Config:
    def __init__(self) -> None:
        self.repo = env("GH_REPO")
        self.token = env("GH_TOKEN")
        self.device_id = env("DEVICE_ID", "phone")
        self.poll_interval = env_int("POLL_INTERVAL", 5)
        self.heartbeat_issue = env_int("HEARTBEAT_ISSUE", 0)
        self.heartbeat_interval = env_int("HEARTBEAT_INTERVAL", 300)
        self.screen_control = env_flag("ENABLE_SCREEN_CONTROL")
        self.allow_dangerous = env_flag("ALLOW_DANGEROUS")
        self.max_output = env_int("MAX_OUTPUT", 8000)
        if not self.repo or "/" not in self.repo:
            raise SystemExit("GH_REPO must be set to owner/repo")
        if not self.token:
            raise SystemExit("GH_TOKEN must be set (GitHub PAT with issues write)")
        self.processed_file = os.path.expanduser("~/.phone-bridge-processed")


class GitHub:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    def _request(self, method: str, path: str, data: dict | None = None) -> object:
        url = API_BASE + path
        body = json.dumps(data).encode() if data is not None else None
        req = urllib.request.Request(url, data=body, method=method)
        req.add_header("Authorization", f"Bearer {self.cfg.token}")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("User-Agent", USER_AGENT)
        if body is not None:
            req.add_header("Content-Type", "application/json")
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    raw = resp.read().decode("utf-8", "replace")
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as e:
                last_err = e
                if e.code in (429, 500, 502, 503, 504) and attempt < 2:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                last_err = e
                if attempt < 2:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise
        raise RuntimeError(f"GitHub request failed: {last_err}")

    def list_open_commands(self) -> list[dict]:
        path = f"/repos/{self.cfg.repo}/issues?labels=phone-cmd&state=open&per_page=50"
        data = self._request("GET", path)
        return data if isinstance(data, list) else []

    def comment(self, number: int, body: str) -> None:
        self._request("POST", f"/repos/{self.cfg.repo}/issues/{number}/comments",
                      {"body": body})

    def close(self, number: int) -> None:
        self._request("PATCH", f"/repos/{self.cfg.repo}/issues/{number}",
                      {"state": "closed"})


def parse_command_body(body: str) -> tuple[str, int]:
    """Return (command, timeout_seconds). Accepts plain text or JSON."""
    text = (body or "").strip()
    if text.startswith("{"):
        try:
            obj = json.loads(text)
            cmd = str(obj.get("cmd", "")).strip()
            timeout = int(obj.get("timeout", 30))
            return cmd, max(1, min(timeout, 120))
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
    return text.splitlines()[0].strip() if text else "", 30


def is_dangerous(cmd: str) -> bool:
    return any(re.search(p, cmd) for p in DANGEROUS_PATTERNS)


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated, {len(text)} chars total]"


def run_shell(cmd: str, timeout: int) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=timeout, stdin=subprocess.DEVNULL,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode, out
    except subprocess.TimeoutExpired as e:
        out = ((e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or ""))
        return 124, out + f"\n[timeout after {timeout}s]"
    except OSError as e:
        return 127, f"[failed to run: {e}]"


def which(name: str) -> bool:
    import shutil
    return shutil.which(name) is not None


def builtin_status() -> str:
    lines = [f"device: {os.uname().nodename}", f"machine: {os.uname().machine}"]
    code, out = run_shell("termux-info 2>/dev/null || uname -a", 10)
    lines.append(out.strip())
    code, out = run_shell("df -h ~ 2>/dev/null | head -5", 10)
    lines.append(out.strip())
    code, out = run_shell("uptime 2>/dev/null || cat /proc/uptime", 10)
    lines.append(out.strip())
    return "\n".join(lines)


def builtin_battery() -> str:
    if which("termux-battery"):
        code, out = run_shell("termux-battery", 10)
        return out.strip()
    # Fallback: read sysfs directly (no Termux:API needed).
    for path in ("/sys/class/power_supply/battery/capacity",
                 "/sys/class/power_supply/battery/status"):
        try:
            with open(path) as f:
                return f"{path.split('/')[-1]}: {f.read().strip()}"
        except OSError:
            continue
    return "battery: unknown (install termux-api for termux-battery)"


def screen_prefix() -> str | None:
    """Return the command prefix that can run `input`/`screencap`."""
    if which("rish"):
        return "rish -c"
    if which("input"):
        return ""
    return None


def execute(cmd: str, timeout: int, cfg: Config) -> tuple[int, str]:
    """Execute one command string. Returns (exit_code, output)."""
    if not cmd:
        return 2, "empty command. Send 'help' for the command list."
    low = cmd.lower()

    if low in ("help", "commands"):
        return 0, HELP_TEXT
    if low in ("status", "ping", "hello"):
        return 0, builtin_status()
    if low == "battery":
        return 0, builtin_battery()
    if low == "storage":
        code, out = run_shell("df -h", 10)
        return code, out
    if low == "sms":
        if not which("termux-sms-list"):
            return 127, "termux-sms-list not found. Install termux-api and grant SMS permission."
        code, out = run_shell("termux-sms-list -l 10", 15)
        return code, out
    if low == "clipboard-get":
        if not which("termux-clipboard-get"):
            return 127, "termux-clipboard-get not found. Install termux-api."
        code, out = run_shell("termux-clipboard-get", 10)
        return code, out
    if low.startswith("clipboard-set:"):
        text = cmd.split(":", 1)[1]
        if not which("termux-clipboard-set"):
            return 127, "termux-clipboard-set not found. Install termux-api."
        code, out = run_shell(f"termux-clipboard-set {subprocess.list2cmdline([text])}", 10)
        return code, out or "clipboard set"
    if low == "location":
        if not which("termux-location"):
            return 127, "termux-location not found. Install termux-api."
        code, out = run_shell("termux-location", 15)
        return code, out
    if low.startswith("notify:"):
        parts = cmd.split(":", 2)
        title = parts[1] if len(parts) > 1 else "phone-bridge"
        body = parts[2] if len(parts) > 2 else ""
        if not which("termux-notification"):
            return 127, "termux-notification not found. Install termux-api."
        code, out = run_shell(
            f"termux-notification -t {subprocess.list2cmdline([title])} "
            f"-c {subprocess.list2cmdline([body])}", 10)
        return code, out or "notification sent"
    if low.startswith("toast:"):
        msg = cmd.split(":", 1)[1]
        if not which("termux-toast"):
            return 127, "termux-toast not found. Install termux-api."
        code, out = run_shell(f"termux-toast {subprocess.list2cmdline([msg])}", 10)
        return code, out or "toast shown"
    if low.startswith("shell:"):
        inner = cmd.split(":", 1)[1].strip()
        if not inner:
            return 2, "shell: needs a command after the colon"
        if is_dangerous(inner) and not cfg.allow_dangerous:
            return 3, ("refused: destructive pattern detected. "
                       "Set ALLOW_DANGEROUS=1 on the phone to override.")
        return run_shell(inner, timeout)
    if low.startswith(("tap:", "swipe:", "input:", "screenshot")):
        if not cfg.screen_control:
            return 3, ("screen control is disabled. Set ENABLE_SCREEN_CONTROL=1 "
                       "on the phone and install Shizuku + rish first.")
        prefix = screen_prefix()
        if prefix is None:
            return 127, ("no 'input'/'rish' found. Install Shizuku, start it, "
                         "then install rish (see docs/architecture.md).")
        if low.startswith("tap:"):
            _, x, y = cmd.split(":")
            return run_shell(f"{prefix} input tap {x} {y}", timeout)
        if low.startswith("swipe:"):
            _, x1, y1, x2, y2, ms = cmd.split(":")
            return run_shell(f"{prefix} input swipe {x1} {y1} {x2} {y2} {ms}", timeout)
        if low.startswith("input:"):
            text = cmd.split(":", 1)[1]
            return run_shell(f"{prefix} input text {subprocess.list2cmdline([text])}", timeout)
        # screenshot
        path = os.path.expanduser("~/phone-bridge-screenshot.png")
        code, out = run_shell(f"{prefix} screencap -p {path}", timeout)
        return code, (out or "") + f"\nscreenshot saved to {path}"

    # Unknown: treat a bare command as a shell command only if it looks
    # like one (starts with a known binary). Otherwise show help.
    if re.match(r"^[a-zA-Z0-9_./-]+(\s|$)", cmd):
        if is_dangerous(cmd) and not cfg.allow_dangerous:
            return 3, ("refused: destructive pattern detected. "
                       "Set ALLOW_DANGEROUS=1 on the phone to override.")
        return run_shell(cmd, timeout)
    return 2, f"unknown command: {cmd}\n\n{HELP_TEXT}"


HELP_TEXT = """phone-bridge commands:
  status / ping        battery, storage, uptime, Termux info
  battery              battery level/status
  storage              df -h
  sms                  last 10 SMS (needs termux-api + permission)
  clipboard-get        read clipboard
  clipboard-set:<t>    write clipboard
  location             GPS location (needs permission)
  notify:<title>:<b>   send a notification
  toast:<msg>          show a toast
  shell:<cmd>          run a shell command in Termux
  tap:<x>:<y>          tap screen (Shizuku + ENABLE_SCREEN_CONTROL=1)
  swipe:<x1>:<y1>:<x2>:<y2>:<ms>
  input:<text>         type text
  screenshot           save screenshot to ~/phone-bridge-screenshot.png
  help                 this list
"""


def format_result(device: str, code: int, duration: float, output: str, limit: int) -> str:
    return (
        "<!-- phone-bridge-result -->\n"
        f"device: {device}\n"
        f"exit: {code}\n"
        f"duration: {duration:.2f}s\n"
        "```output\n"
        f"{truncate(output, limit)}\n"
        "```"
    )


def load_processed(cfg: Config) -> set[int]:
    try:
        with open(cfg.processed_file) as f:
            return {int(x) for x in f.read().split() if x.strip().isdigit()}
    except OSError:
        return set()


def mark_processed(cfg: Config, number: int) -> None:
    try:
        with open(cfg.processed_file, "a") as f:
            f.write(f"{number}\n")
    except OSError:
        pass


def heartbeat(gh: GitHub, cfg: Config) -> None:
    if not cfg.heartbeat_issue:
        return
    body = (
        "<!-- phone-bridge-heartbeat -->\n"
        f"device: {cfg.device_id}\n"
        f"time: {datetime.now(timezone.utc).isoformat()}\n"
        f"battery: {builtin_battery().splitlines()[0] if builtin_battery() else 'unknown'}"
    )
    try:
        gh.comment(cfg.heartbeat_issue, body)
        log("heartbeat sent")
    except Exception as e:  # never let heartbeat kill the loop
        log(f"heartbeat failed: {e}")


def main() -> int:
    cfg = Config()
    gh = GitHub(cfg)
    processed = load_processed(cfg)
    log(f"phone-bridge agent starting for device '{cfg.device_id}' repo {cfg.repo}")
    log(f"poll every {cfg.poll_interval}s, screen_control={cfg.screen_control}")
    last_heartbeat = 0.0
    while True:
        try:
            issues = gh.list_open_commands()
        except Exception as e:
            log(f"poll failed: {e}")
            time.sleep(cfg.poll_interval)
            continue
        for issue in issues:
            number = issue.get("number")
            if not isinstance(number, int) or number in processed:
                continue
            title = str(issue.get("title", ""))
            body = str(issue.get("body", "") or "")
            cmd, timeout = parse_command_body(body)
            # Only obey commands addressed to this device (or broadcast).
            device = ""
            if body.strip().startswith("{"):
                try:
                    device = str(json.loads(body).get("device", ""))
                except (json.JSONDecodeError, ValueError):
                    device = ""
            if device and device != cfg.device_id:
                continue
            log(f"#{number} {title} -> {cmd!r}")
            start = time.time()
            code, output = execute(cmd, timeout, cfg)
            duration = time.time() - start
            try:
                gh.comment(number, format_result(cfg.device_id, code, duration, output, cfg.max_output))
                gh.close(number)
            except Exception as e:
                log(f"failed to post result for #{number}: {e}")
            processed.add(number)
            mark_processed(cfg, number)
        now = time.time()
        if cfg.heartbeat_issue and now - last_heartbeat >= cfg.heartbeat_interval:
            heartbeat(gh, cfg)
            last_heartbeat = now
        time.sleep(cfg.poll_interval)


if __name__ == "__main__":
    sys.exit(main())
