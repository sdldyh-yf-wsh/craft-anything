#!/usr/bin/env bash
# chisel reverse tunnel (free, single binary, HTTP-wrapped so it
# passes strict firewalls). Docs: https://github.com/jpillora/chisel
# Server (VPS):  chisel server --reverse --port 8080 --auth user:pass
# Phone:         chisel client https://vps.example.com:8080 R:2222:localhost:8022
# PC:            ssh -p 2222 <termux-user>@vps.example.com
set -euo pipefail
echo "VPS:  chisel server --reverse --port 8080 --auth user:pass"
echo "Phone (Termux): chisel client https://vps.example.com:8080 R:2222:localhost:8022"
echo "PC:   ssh -p 2222 <termux-user>@vps.example.com"
