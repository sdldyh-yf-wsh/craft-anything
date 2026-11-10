#!/usr/bin/env python3
"""
phone-bridge client — runs on a computer or in a chat sandbox.

Sends a command to the phone by creating a GitHub Issue
(label: phone-cmd), then polls the Issue comments until the
phone agent posts its result. Only talks to api.github.com,
so it works from sandboxes that can only reach GitHub.

Usage:
    export GH_REPO=owner/repo GH_TOKEN=ghp_xxx DEVICE_ID=pixel-8
    python3 phone_client.py "status"
    python3 phone_client.py --shell "ls -la ~/downloads"
    python3 phone_client.py --wait 90 "battery"
    python3 phone_client.py --check          # verify repo + token
    python3 phone_client.py --ssh            # print direct-SSH instructions

Direct SSH mode (phone <-> your own PC, no GitHub relay) is
documented in ../configs/ssh_config.example — use EasyTier,
frp, chisel or Cloudflare Tunnel to expose Termux sshd (8022).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

API_BASE = "https://api.github.com"
USER_AGENT = "phone-bridge-client/1.0"
RESULT_MARKER = "<!-- phone-bridge-result -->"


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


class GitHub:
    def __init__(self, repo: str, token: str) -> None:
        self.repo = repo
        self.token = token

    def _request(self, method: str, path: str, data: dict | None = None) -> object:
        url = API_BASE + path
        body = json.dumps(data).encode() if data is not None else None
        req = urllib.request.Request(url, data=body, method=method)
        req.add_header("Authorization", f"Bearer {self.token}")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("User-Agent", USER_AGENT)
        if body is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8", "replace")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:500]
            raise SystemExit(f"GitHub API error {e.code}: {detail}")

    def create_issue(self, title: str, body: str) -> int:
        data = self._request("POST", f"/repos/{self.repo}/issues",
                             {"title": title, "body": body, "labels": ["phone-cmd"]})
        number = data.get("number") if isinstance(data, dict) else None
        if not isinstance(number, int):
            raise SystemExit(f"unexpected create-issue response: {data}")
        return number

    def get_comments(self, number: int) -> list[dict]:
        data = self._request("GET", f"/repos/{self.repo}/issues/{number}/comments?per_page=50")
        return data if isinstance(data, list) else []

    def get_repo(self) -> dict:
        data = self._request("GET", f"/repos/{self.repo}")
        return data if isinstance(data, dict) else {}


def parse_result_comment(body: str) -> dict | None:
    if RESULT_MARKER not in body:
        return None
    meta: dict[str, str] = {}
    output = ""
    in_block = False
    for line in body.splitlines():
        if line.strip().startswith("```"):
            in_block = not in_block
            continue
        if in_block:
            output += line + "\n"
        elif ":" in line and not line.startswith("<!--"):
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    meta["output"] = output.rstrip()
    return meta


def send_command(gh: GitHub, cmd: str, device: str, timeout: int,
                 wait: int, poll: int = 3) -> dict:
    payload = {"cmd": cmd, "timeout": timeout}
    if device:
        payload["device"] = device
    body = json.dumps(payload, ensure_ascii=False)
    number = gh.create_issue(f"[phone] {cmd[:60]}", body)
    print(f"sent #{number} to {gh.repo} — waiting for phone...", file=sys.stderr)
    deadline = time.time() + wait
    while time.time() < deadline:
        for comment in gh.get_comments(number):
            result = parse_result_comment(str(comment.get("body", "")))
            if result is not None:
                result["issue"] = number
                return result
        time.sleep(poll)
    raise SystemExit(f"timed out after {wait}s waiting for #{number}. "
                     "Is the phone agent running? (see agent/setup-termux.sh)")


SSH_HELP = """Direct SSH mode (phone <-> your own PC, no GitHub relay):

1. On the phone (Termux):  pkg install openssh && sshd   # port 8022
2. Pick ONE tunnel (all free, see ../configs/):
   - EasyTier (recommended): phone + PC join the same virtual
     network, then  ssh -p 8022 <termux-user>@<virtual-ip>
   - frp / chisel / bore: phone dials out to a VPS, PC ssh's to VPS
   - Cloudflare Tunnel: phone runs cloudflared, PC uses
     cloudflared access ssh
3. Copy your public key:  ssh-copy-id -p 8022 <user>@<host>
   Then add the Host block from ../configs/ssh_config.example
   to ~/.ssh/config and just run:  ssh phone

This mode does NOT work from a locked-down chat sandbox
(it cannot reach your VPS/tunnel). Use GitHub relay mode
(the default of this client) from the sandbox.
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="phone-bridge client")
    ap.add_argument("command", nargs="?", help="command to run on the phone")
    ap.add_argument("--shell", metavar="CMD", help="run a shell command on the phone")
    ap.add_argument("--device", default=env("DEVICE_ID"), help="target device id")
    ap.add_argument("--timeout", type=int, default=30, help="per-command timeout (s)")
    ap.add_argument("--wait", type=int, default=90, help="max wait for result (s)")
    ap.add_argument("--check", action="store_true", help="verify repo + token, then exit")
    ap.add_argument("--ssh", action="store_true", help="print direct-SSH instructions")
    args = ap.parse_args()

    if args.ssh:
        print(SSH_HELP)
        return 0

    repo, token = env("GH_REPO"), env("GH_TOKEN")
    if not repo or "/" not in repo:
        raise SystemExit("GH_REPO must be set to owner/repo")
    if not token:
        raise SystemExit("GH_TOKEN must be set (GitHub PAT with issues write)")
    gh = GitHub(repo, token)

    if args.check:
        info = gh.get_repo()
        print(f"OK: {info.get('full_name')} (private={info.get('private')})")
        print("token can read this repo. Create the 'phone-cmd' label if missing:")
        print("  gh api repos/{}/labels -f name=phone-cmd -f color=0e8a16".format(repo))
        return 0

    cmd = f"shell:{args.shell}" if args.shell else (args.command or "status")
    result = send_command(gh, cmd, args.device, args.timeout, args.wait)
    print(f"--- #{result['issue']} device={result.get('device', '?')} "
          f"exit={result.get('exit', '?')} duration={result.get('duration', '?')} ---")
    print(result.get("output", ""))
    try:
        return int(result.get("exit", "0"))
    except ValueError:
        return 0


if __name__ == "__main__":
    sys.exit(main())
