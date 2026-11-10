# GitHub projects this bridge is built from

All of these are free and open source. phone-bridge does not copy
their code (see the repo's original-work rule); it uses them as
building blocks / design references.

| Project | What it does | Used here for |
|---|---|---|
| [termux/termux-app](https://github.com/termux/termux-app) | Android terminal + Linux environment, no root | Phone-side shell + sshd host |
| [termux/termux-api](https://github.com/termux/termux-api) | Phone APIs: SMS, clipboard, battery, location, notifications | `sms`, `battery`, `clipboard-*`, `location`, `notify`, `toast` commands |
| [EasyTier/EasyTier](https://github.com/EasyTier/EasyTier) | Decentralized mesh VPN (Rust), NAT traversal, Android support | Free Tailscale alternative for direct SSH (phone ↔ PC) |
| [juanfont/headscale](https://github.com/juanfont/headscale) | Self-hosted Tailscale control plane | Alternative: keep Tailscale clients, own the control server |
| [netbirdio/netbird](https://github.com/netbirdio/netbird) | WireGuard mesh VPN, self-hostable, free cloud tier | Alternative mesh VPN |
| [zerotier/ZeroTierOne](https://github.com/zerotier/ZeroTierOne) | Mesh networking, free for 25 devices | Alternative mesh VPN |
| [fatedier/frp](https://github.com/fatedier/frp) | Reverse proxy / tunnel (ngrok alternative) | Expose Termux sshd via a VPS |
| [jpillora/chisel](https://github.com/jpillora/chisel) | TCP tunnel over HTTP, single binary | Expose Termux sshd via a VPS, firewall-friendly |
| [ekzhang/bore](https://github.com/ekzhang/bore) | Minimal TCP tunnel (Rust) | Lightweight alternative to frp/chisel |
| [Genymobile/scrcpy](https://github.com/Genymobile/scrcpy) | Mirror + control Android screen from PC via ADB, no root | Screen control from your own PC (USB/Wi-Fi ADB) |
| [RikkaApps/Shizuku](https://github.com/RikkaApps/Shizuku) | Give apps `adb shell` privileges without root | `tap` / `swipe` / `input` / `screenshot` on the phone |
| [m96-chan/DroidRunner](https://github.com/m96-chan/DroidRunner) | Android phone as a GitHub Actions self-hosted runner | Alternative GitHub-relay design (Actions instead of Issues) |
| [ccch1mneyyy/dsh-go](https://github.com/ccch1mneyyy/dsh-go) | DeepSeek Harness Android client, SSH to PC + on-phone control | The UX reference: chat UI that controls phone/PC |
| [actions/runner](https://github.com/actions/runner) | Official GitHub Actions self-hosted runner | If you prefer Actions over Issue polling |

## Why GitHub Issues as the relay?

A locked-down chat sandbox can only reach `github.com` /
`api.github.com`. Both the phone agent and the sandbox client only
need outbound HTTPS to `api.github.com`, so GitHub works as a free
message bus with no VPS, no tunnel account and no open ports.
Trade-off: ~5–15s latency (polling), not interactive SSH.
For interactive SSH from your own PC, use EasyTier/frp/chisel
(see `../configs/`).
