#!/usr/bin/env python3
"""
handsfree — voice + notification hands-free loop for the phone.

Two hands-free modes, both run on the phone in Termux:

1. Voice mode: listens with termux-speech-recognition, maps the
   spoken phrase to a phone-bridge command, executes it, and
   speaks the result back with termux-tts. No typing, no touching
   the phone — like dsh-go's voice input, but fully on-device.

2. Notification watcher: polls termux-notification-list and
   forwards important notifications (SMS, calls, apps) to the
   GitHub heartbeat issue, so the sandbox/autopilot can react
   without you touching the phone. Optionally speaks them aloud.

Voice phrases (Chinese + English):
    电量 / battery          -> battery
    状态 / status / ping    -> status
    短信 / sms              -> sms
    截图 / screenshot       -> screenshot
    剪贴板 / clipboard      -> clipboard-get
    位置 / location         -> location
    通知 <标题> <内容>       -> notify:<标题>:<内容>
    执行 <命令> / run <cmd>  -> shell:<命令>
    帮助 / help             -> help

Env:
    GH_REPO, GH_TOKEN, DEVICE_ID   (same as phone_agent.py)
    HANDSFREE_SPEAK        1 to speak results aloud (default 1)
    HANDSFREE_VOICE        1 to enable voice loop (default 1)
    HANDSFREE_NOTIFY       1 to enable notification watcher (default 1)
    HANDSFREE_INTERVAL     seconds between voice attempts (default 2)
    HEARTBEAT_ISSUE        issue number to forward notifications to

Safety: voice commands go through the same dangerous-pattern
guard as phone_agent.py. Screen control still needs
ENABLE_SCREEN_CONTROL=1. SMS auto-reply is NOT done here.

Original work.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import phone_agent  # noqa: E402

API_BASE = "https://api.github.com"


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] handsfree: {msg}", flush=True)


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def env_flag(name: str, default: bool = True) -> bool:
    v = env(name, "1" if default else "0")
    return v in ("1", "true", "yes", "on")


def speak(text: str) -> None:
    """Speak text aloud via termux-tts (no-op if unavailable)."""
    if not env_flag("HANDSFREE_SPEAK"):
        return
    try:
        subprocess.run(["termux-tts-speak", text[:300]],
                       timeout=30, stdin=subprocess.DEVNULL,
                       capture_output=True)
    except (OSError, subprocess.TimeoutExpired):
        pass


def listen_once() -> str:
    """One speech-recognition attempt. Returns recognized text or ''."""
    try:
        proc = subprocess.run(
            ["termux-speech-recognition"],
            capture_output=True, text=True, timeout=30,
            stdin=subprocess.DEVNULL)
        out = (proc.stdout or "").strip()
        if not out:
            return ""
        # termux-speech-recognition outputs JSON like {"text": "..."}
        try:
            obj = json.loads(out)
            if isinstance(obj, dict):
                return str(obj.get("text", "")).strip()
        except json.JSONDecodeError:
            pass
        return out
    except (OSError, subprocess.TimeoutExpired):
        return ""


def parse_voice(text: str) -> str:
    """Map a spoken phrase to a phone-bridge command string ('' if unrecognized)."""
    t = text.strip()
    low = t.lower()
    if not t:
        return ""
    if any(k in t for k in ("电量", "多少电", "还有电")) or "battery" in low:
        return "battery"
    if any(k in t for k in ("状态", "在吗")) or low in ("status", "ping"):
        return "status"
    if "短信" in t or "sms" in low:
        return "sms"
    if ("截图" in t or "截屏" in t
            or ("截" in t and ("图" in t or "屏" in t))
            or "screenshot" in low):
        return "screenshot"
    if any(k in t for k in ("剪贴板", "粘贴板")) or "clipboard" in low:
        return "clipboard-get"
    if any(k in t for k in ("位置", "定位")) or "location" in low:
        return "location"
    if "帮助" in t or low == "help":
        return "help"
    if t.startswith("通知") or low.startswith("notify"):
        rest = t[2:].strip() if t.startswith("通知") else t[6:].strip()
        parts = rest.split(None, 1)
        title = parts[0] if parts else "phone-bridge"
        body = parts[1] if len(parts) > 1 else ""
        return f"notify:{title}:{body}"
    if t.startswith(("执行", "运行")):
        return f"shell:{t[2:].strip()}"
    if low.startswith("run "):
        return f"shell:{t[4:].strip()}"
    if low.startswith("shell:"):
        return t
    # Ignore unrecognized ambient chatter rather than running arbitrary commands.
    return ""


def post_heartbeat(repo: str, token: str, issue: int, body: str) -> None:
    url = f"{API_BASE}/repos/{repo}/issues/{issue}/comments"
    data = json.dumps({"body": body}).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "phone-bridge-handsfree/1.0")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
    except Exception as e:
        log(f"heartbeat post failed: {e}")


def watch_notifications(cfg: phone_agent.Config, seen: set[str]) -> None:
    """Poll notifications once; forward new ones to the heartbeat issue."""
    if not cfg.heartbeat_issue:
        return
    try:
        proc = subprocess.run(
            ["termux-notification-list"],
            capture_output=True, text=True, timeout=15,
            stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return
    try:
        items = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return
    if not isinstance(items, list):
        return
    for item in items:
        if not isinstance(item, dict):
            continue
        key = f"{item.get('packageName', '')}:{item.get('id', '')}:{item.get('title', '')}"
        if key in seen:
            continue
        seen.add(key)
        title = str(item.get("title", ""))
        content = str(item.get("content", ""))
        log(f"notification: {title} {content}")
        speak(f"{title}。{content}" if title else content)
        post_heartbeat(
            cfg.repo, cfg.token, cfg.heartbeat_issue,
            "<!-- phone-bridge-notification -->\n"
            f"device: {cfg.device_id}\n"
            f"package: {item.get('packageName', '')}\n"
            f"title: {title}\ncontent: {content}")


def main() -> int:
    cfg = phone_agent.Config()
    voice_on = env_flag("HANDSFREE_VOICE")
    notify_on = env_flag("HANDSFREE_NOTIFY")
    interval = int(env("HANDSFREE_INTERVAL", "2") or "2")
    log(f"handsfree starting (voice={voice_on} notify={notify_on})")
    seen: set[str] = set()
    while True:
        if notify_on:
            watch_notifications(cfg, seen)
        if voice_on:
            text = listen_once()
            if text:
                log(f"heard: {text!r}")
                cmd = parse_voice(text)
                if cmd:
                    code, output = phone_agent.execute(cmd, 30, cfg)
                    short = output.strip().splitlines()[0] if output.strip() else "done"
                    speak(short[:200])
                    log(f"ran {cmd!r} -> exit {code}")
        time.sleep(max(1, interval))


if __name__ == "__main__":
    sys.exit(main())
