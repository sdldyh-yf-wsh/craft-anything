#!/usr/bin/env bash
# One-click Termux setup for phone-bridge.
# Run inside Termux on Android (install Termux from F-Droid or
# https://github.com/termux/termux-app/releases — NOT Play Store).
#
#   curl -fsSL <raw-url>/setup-termux.sh | bash
# or copy this file to the phone and run:  bash setup-termux.sh
#
# Required env (export before running, or edit the defaults below):
#   GH_REPO=owner/repo  GH_TOKEN=ghp_xxx  DEVICE_ID=pixel-8
set -euo pipefail

GH_REPO="${GH_REPO:-owner/repo}"
GH_TOKEN="${GH_TOKEN:-}"
DEVICE_ID="${DEVICE_ID:-phone}"
INSTALL_DIR="$HOME/phone-bridge"

if [ -z "$GH_TOKEN" ] || [ "$GH_TOKEN" = "ghp_xxx" ]; then
  echo "ERROR: set GH_TOKEN first, e.g.:" >&2
  echo "  export GH_REPO=owner/repo GH_TOKEN=ghp_xxx DEVICE_ID=pixel-8" >&2
  exit 1
fi
if [ "$GH_REPO" = "owner/repo" ]; then
  echo "ERROR: set GH_REPO to your real repo (owner/repo)" >&2
  exit 1
fi

echo "==> Updating Termux packages..."
pkg update -y
pkg upgrade -y

echo "==> Installing openssh, termux-api, python..."
pkg install -y openssh termux-api python

echo "==> Setting up SSH server (port 8022)..."
passwd || true
# Start sshd now; add to .bashrc so it restarts when Termux opens.
sshd 2>/dev/null || true
grep -q "sshd" "$HOME/.bashrc" 2>/dev/null || echo "sshd 2>/dev/null || true" >> "$HOME/.bashrc"

echo "==> Keeping the phone awake..."
termux-wake-lock || true
termux-setup-storage || true

echo "==> Installing phone-bridge agent to $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"
# If this script was run from a clone, copy the agent; otherwise
# download it from GitHub (adjust the repo/branch to yours).
if [ -f "$(dirname "$0")/phone_agent.py" ]; then
  cp "$(dirname "$0")/phone_agent.py" "$INSTALL_DIR/phone_agent.py"
else
  curl -fsSL "https://raw.githubusercontent.com/${GH_REPO}/main/phone-bridge/agent/phone_agent.py" \
    -o "$INSTALL_DIR/phone_agent.py"
fi

cat > "$INSTALL_DIR/run.sh" <<EOF
#!/usr/bin/env bash
export GH_REPO="$GH_REPO"
export GH_TOKEN="$GH_TOKEN"
export DEVICE_ID="$DEVICE_ID"
export POLL_INTERVAL="${POLL_INTERVAL:-5}"
export HEARTBEAT_ISSUE="${HEARTBEAT_ISSUE:-0}"
export ENABLE_SCREEN_CONTROL="${ENABLE_SCREEN_CONTROL:-0}"
exec python3 "$INSTALL_DIR/phone_agent.py"
EOF
chmod +x "$INSTALL_DIR/run.sh"

echo "==> Starting agent in the background..."
nohup bash "$INSTALL_DIR/run.sh" > "$INSTALL_DIR/agent.log" 2>&1 &
sleep 2
if kill -0 $! 2>/dev/null; then
  echo "Agent is running (pid $!). Log: $INSTALL_DIR/agent.log"
else
  echo "Agent failed to start. Log:" >&2
  cat "$INSTALL_DIR/agent.log" >&2
  exit 1
fi

echo
echo "Done. Next steps:"
echo "  1. Set battery to Unrestricted for Termux (Settings > Apps > Termux > Battery)."
echo "  2. From your PC/sandbox, test:  python3 client/phone_client.py \"status\""
echo "  3. For direct SSH from your PC, see ../configs/ssh_config.example"
echo "  4. For screen control, install Shizuku + rish, then set"
echo "     ENABLE_SCREEN_CONTROL=1 in $INSTALL_DIR/run.sh and restart the agent."
