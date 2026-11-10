#!/usr/bin/env python3
"""
autopilot — hands-free daemon for the sandbox/PC side.

Watches the phone's heartbeat issue for:
  - online/offline status (heartbeat comments)
  - forwarded notifications (SMS, calls, app alerts)

And executes tasks you leave as comments on the autopilot issue:
  - Any comment starting with "task:" is run on the phone via the
    GitHub relay, and the result is posted back as a reply.
  - Example:  task: battery
              task: shell:ls ~/downloads

So hands-free flow is: you (or another agent) drops a task comment,
autopilot runs it on the phone, posts the result — no manual CLI.

Env:
    GH_REPO, GH_TOKEN, DEVICE_ID   (same as phone_client.py)
    AUTOPILOT_ISSUE     issue number to watch (required)
    AUTOPILOT_INTERVAL  poll seconds (default 5)
    AUTOPILOT_LOG       log file (default: autopilot.log)
    AUTOPILOT_STATE     processed-comment state file (default: .autopilot-seen.json)

Safety: tasks go through the phone agent's dangerous-pattern
guard. SMS auto-reply is intentionally NOT implemented — the
autopilot only reports notifications, it never sends messages
on your behalf without you writing the task yourself.

Original work.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from phone_client import GitHub, parse_result_comment  # noqa: E402

API_BASE = "https://api.github.com"
RESULT_MARKER = "<!-- phone-bridge-autopilot-result -->"


def log(msg: str, logfile: str = "") -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    line = f"[{ts}] autopilot: {msg}"
    print(line, flush=True)
    if logfile:
        try:
            with open(logfile, "a") as f:
                f.write(line + "\n")
        except OSError:
            pass


def is_heartbeat(body: str) -> bool:
    return "<!-- phone-bridge-heartbeat -->" in body


def is_notification(body: str) -> bool:
    return "<!-- phone-bridge-notification -->" in body


def is_autopilot_result(body: str) -> bool:
    return RESULT_MARKER in body


def parse_task(body: str) -> str | None:
    """Return the task command if the comment is a user task, else None."""
    if "<!-- phone-bridge-" in body:
        return None
    for line in body.splitlines():
        line = line.strip()
        if line.lower().startswith("task:"):
            cmd = line[5:].strip()
            return cmd or None
    return None


def extract_replied_ids(comments: list[dict]) -> set[int]:
    """Find comment IDs already answered by a previous autopilot run."""
    replied: set[int] = set()
    for c in comments:
        body = str(c.get("body", "") or "")
        if not is_autopilot_result(body):
            continue
        for line in body.splitlines():
            if line.startswith("reply_to:"):
                raw = line.split(":", 1)[1].strip()
                if raw.isdigit():
                    replied.add(int(raw))
    return replied


def load_seen(path: str) -> set[int]:
    if not path or not os.path.exists(path):
        return set()
    try:
        with open(path) as f:
            data = json.load(f)
        if isinstance(data, list):
            return {int(x) for x in data if isinstance(x, int)}
    except (OSError, ValueError):
        pass
    return set()


def save_seen(path: str, seen: set[int]) -> None:
    if not path:
        return
    try:
        with open(path, "w") as f:
            json.dump(sorted(seen)[-2000:], f)
    except OSError:
        pass


def run_task(gh: GitHub, device: str, cmd: str, wait: int = 90) -> str:
    payload = {"cmd": cmd, "timeout": 30}
    if device:
        payload["device"] = device
    number = gh.create_issue(f"[phone] {cmd[:60]}",
                             json.dumps(payload, ensure_ascii=False))
    deadline = time.time() + wait
    while time.time() < deadline:
        for comment in gh.get_comments(number):
            result = parse_result_comment(str(comment.get("body", "")))
            if result is not None:
                return (f"exit={result.get('exit', '?')}\n"
                        f"{result.get('output', '')}")
        time.sleep(3)
    return f"timed out waiting for #{number}"


def comment_on(repo: str, token: str, issue: int, body: str) -> None:
    url = f"{API_BASE}/repos/{repo}/issues/{issue}/comments"
    data = json.dumps({"body": body}).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "phone-bridge-autopilot/1.0")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as resp:
        resp.read()


def main() -> int:
    repo = os.environ.get("GH_REPO", "").strip()
    token = os.environ.get("GH_TOKEN", "").strip()
    device = os.environ.get("DEVICE_ID", "").strip()
    issue_s = os.environ.get("AUTOPILOT_ISSUE", "").strip()
    interval = int(os.environ.get("AUTOPILOT_INTERVAL", "5") or "5")
    logfile = os.environ.get("AUTOPILOT_LOG", "autopilot.log")
    statefile = os.environ.get("AUTOPILOT_STATE", ".autopilot-seen.json")
    if not repo or not token:
        raise SystemExit("GH_REPO and GH_TOKEN must be set")
    if not issue_s.isdigit():
        raise SystemExit("AUTOPILOT_ISSUE must be set to an issue number")
    issue = int(issue_s)
    gh = GitHub(repo, token)
    seen = load_seen(statefile)
    log(f"watching #{issue} in {repo} every {interval}s", logfile)
    while True:
        try:
            comments = gh.get_comments(issue)
        except SystemExit:
            raise
        except Exception as e:
            log(f"poll failed: {e}", logfile)
            time.sleep(interval)
            continue
        replied = extract_replied_ids(comments)
        changed = False
        for c in comments:
            cid = c.get("id")
            if not isinstance(cid, int) or cid in seen:
                continue
            seen.add(cid)
            changed = True
            body = str(c.get("body", "") or "")
            if is_autopilot_result(body):
                continue
            if is_heartbeat(body):
                info = body.splitlines()[1] if len(body.splitlines()) > 1 else ""
                log(f"phone online: {info}", logfile)
            elif is_notification(body):
                title = ""
                for line in body.splitlines():
                    if line.startswith("title:"):
                        title = line[6:].strip()
                log(f"phone notification: {title}", logfile)
            elif cid not in replied:
                task = parse_task(body)
                if task:
                    log(f"running task #{cid}: {task!r}", logfile)
                    result = run_task(gh, device, task)
                    try:
                        comment_on(
                            repo, token, issue,
                            f"{RESULT_MARKER}\n"
                            f"reply_to: {cid}\n"
                            f"ran: {task}\n"
                            f"```output\n{result[:8000]}\n```",
                        )
                    except Exception as e:
                        log(f"failed to post result: {e}", logfile)
        if changed:
            save_seen(statefile, seen)
        time.sleep(interval)


if __name__ == "__main__":
    sys.exit(main())
