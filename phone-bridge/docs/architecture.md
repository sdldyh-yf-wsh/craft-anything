# Architecture

## Two modes

### Mode 1 — GitHub relay (sandbox ↔ phone) [default]

```
┌─────────────┐   create Issue    ┌──────────────┐
│  Sandbox /  │ ────────────────▶ │   GitHub     │
│  PC client  │                   │   Issues     │
│ phone_client│ ◀──────────────── │  (label:     │
└─────────────┘   comment=result  │   phone-cmd) │
                                    └──────┬───────┘
                                           │ poll (outbound HTTPS only)
                                    ┌──────▼───────┐
                                    │  Android     │
                                    │  Termux      │
                                    │ phone_agent  │
                                    └──────────────┘
```

- Phone never accepts inbound connections; it polls every 5s.
- Works from any network (CGNAT, hotel Wi-Fi) and from sandboxes
  whose only outbound access is `api.github.com`.
- Latency: poll interval + execution time (~5–15s typical).

### Mode 2 — Direct SSH (your PC ↔ phone)

```
┌─────────────┐   ssh :8022   ┌──────────────┐
│  Your PC    │ ────────────▶ │  Android     │
│             │  via EasyTier │  Termux sshd │
└─────────────┘  / frp / chisel└──────────────┘
```

- Interactive shell, `scp`, port forwarding — real SSH.
- Needs one free tunnel/mesh from `../configs/`.
- Does **not** work from a locked-down sandbox (it cannot reach
  your VPS/tunnel). Use Mode 1 there.

## Screen control (dsh-go style "看屏幕、帮你点")

SSH/Issue commands give you a shell, not a screen. For taps:

1. Install **Shizuku** ([RikkaApps/Shizuku](https://github.com/RikkaApps/Shizuku)),
   start it (Wireless debugging on Android 11+).
2. Install **rish** (from Shizuku's docs) so Termux can run
   `rish -c "input tap ..."`.
3. Set `ENABLE_SCREEN_CONTROL=1` in the agent env and restart.
4. Send: `tap:540:1200`, `swipe:100:1000:100:300:300`,
   `input:hello`, `screenshot`.

For full screen mirroring from your own PC, use
[scrcpy](https://github.com/Genymobile/scrcpy) over USB/Wi-Fi ADB —
it is a PC-side tool, not part of the phone agent.

## Security model

- GitHub PAT is the only credential. Use a **fine-grained PAT**
  with `Issues: read/write` on **only** the bridge repo.
- Agent refuses destructive shell patterns unless
  `ALLOW_DANGEROUS=1`.
- Screen control is off by default (`ENABLE_SCREEN_CONTROL=1`).
- Commands are addressed by `DEVICE_ID`; multi-phone setups
  filter by device.
- Never commit tokens, EasyTier secrets or SSH keys to the repo.
  Use env vars / `~/.ssh/config` only.
