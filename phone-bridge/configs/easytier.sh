#!/usr/bin/env bash
# EasyTier quick-start (free Tailscale alternative).
# Docs: https://github.com/EasyTier/EasyTier
# Both phone and PC must use the SAME network-name and network-secret.
# Pick a strong secret and keep it out of the repo (env only).
set -euo pipefail

NETWORK_NAME="${ET_NETWORK_NAME:-my-phone-net}"
NETWORK_SECRET="${ET_NETWORK_SECRET:-change-me}"
PHONE_IP="${ET_PHONE_IP:-10.144.144.2}"
PC_IP="${ET_PC_IP:-10.144.144.1}"

case "${1:-}" in
  phone)
    # Android: install the EasyTier APK from GitHub releases, then
    # set network-name/secret + virtual IP in the app. Or run the
    # CLI in Termux if you have the arm64 binary:
    echo "Phone: install EasyTier APK (GitHub releases), set:"
    echo "  network-name:   $NETWORK_NAME"
    echo "  network-secret: $NETWORK_SECRET"
    echo "  virtual IPv4:   $PHONE_IP"
    echo "Then start Termux sshd and ssh from the PC:"
    echo "  ssh -p 8022 \$(whoami on phone)@$PHONE_IP"
    ;;
  pc)
    # Linux/macOS/Windows (WSL): download easytier-core from
    # https://github.com/EasyTier/EasyTier/releases then:
    echo "PC: run (adjust binary path):"
    echo "  easytier-core -i $PC_IP --network-name $NETWORK_NAME --network-secret $NETWORK_SECRET"
    echo "With shared public nodes (no VPS needed), add a peer, e.g.:"
    echo "  easytier-core -i $PC_IP -p udp://public-node:11010 --network-name $NETWORK_NAME --network-secret $NETWORK_SECRET"
    ;;
  *)
    echo "usage: bash easytier.sh [phone|pc]" >&2
    exit 1
    ;;
esac
