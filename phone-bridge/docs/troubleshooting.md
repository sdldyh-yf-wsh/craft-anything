# Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Client times out, no result | Agent not running on phone | Check `~/phone-bridge/agent.log` in Termux; restart with `bash ~/phone-bridge/run.sh` |
| `GH_TOKEN` / 401 from API | Bad/expired PAT, or PAT lacks Issues write | Create a fine-grained PAT: repo → Issues read/write only |
| 404 on create issue | Repo wrong, or `phone-cmd` label missing | `python3 client/phone_client.py --check`; create the label |
| Agent runs but never picks up issues | `GH_REPO` mismatch between phone and client | Both must use the exact same `owner/repo` |
| `sshd: command not found` | openssh not installed | `pkg install openssh` in Termux |
| SSH works on Wi-Fi but not outside | No tunnel/mesh, phone has no public IP | Set up EasyTier/frp/chisel (see `../configs/`) |
| Agent dies when Termux closes | Android killed the background process | Battery → Unrestricted for Termux; keep `termux-wake-lock`; add `sshd` to `~/.bashrc` |
| `termux-battery: command not found` | termux-api not installed | `pkg install termux-api`, grant permissions in Android Settings |
| `tap` returns "screen control is disabled" | Flag off | Set `ENABLE_SCREEN_CONTROL=1` and install Shizuku + rish |
| Screenshot file not found | `screencap` needs Shizuku/rish | See `architecture.md` screen-control section |
| Duplicate execution after restart | Processed-file lost | Agent stores `~/.phone-bridge-processed`; keep Termux storage intact |

## Debug commands

```sh
# On the phone:
cat ~/phone-bridge/agent.log
ps aux | grep phone_agent

# From the client:
python3 client/phone_client.py --check
python3 client/phone_client.py "status"
python3 client/phone_client.py --shell "uname -a; whoami; pwd"
```
