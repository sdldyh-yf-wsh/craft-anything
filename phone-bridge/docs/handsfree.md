# Hands-free mode — 完全解放双手

不仅不用插线、不用公网 IP，现在**连命令行都不用敲、手机也不用碰**：
手机端 + 对话/沙箱端各配齐了免手动层，连重启自启都写好了。

---

## 0. 开机免碰屏幕（`Termux:Boot` 自启）

`agent/setup-termux.sh` 会自动生成 `~/.termux/boot/start-phone-bridge.sh`。
只需从 F-Droid 免费安装 **Termux:Boot** 并打开一次、关掉电池优化：

- 手机重启后自动执行：`termux-wake-lock` + `sshd(8022)` + `phone_agent.py`
- 若安装时设了 `ENABLE_HANDSFREE=1`，还会一并拉起 `handsfree.py`

全程零触屏。

---

## 1. 语音免提 + 通知主动上报（手机端 `agent/handsfree.py`）

手机放桌上，直接开口说话即可（基于 `termux-speech-recognition` + `termux-tts-speak`）：

| 你说（中文 / English） | 手机自动执行 |
|---|---|
| “电量多少” / `battery` | 读取电量并语音播报 |
| “手机状态” / “在吗” / `status` | 播报电量、存储、运行状态 |
| “看看短信” / `sms` | 读取最近短信并播报摘要 |
| “剪贴板” / `clipboard` | 读出手机剪贴板内容 |
| “位置” / `location` | 获取 GPS 坐标 |
| “截个图” / `screenshot` | 截屏保存到 `~/phone-bridge-screenshot.png` |
| “通知 提醒 开会了” | 在手机上弹出通知 |
| “执行 ls -la” / `run ls -la` | 执行任意安全 Shell 命令并播报首行结果 |

同时，只要设置了 `HEARTBEAT_ISSUE=<Issue编号>`，`handsfree.py` 会后台轮询
`termux-notification-list`，把新收到的短信、来电、App 通知自动朗读并转发到该 Issue，
沙箱里的 AI 不用你截图传话就能看到手机通知。

启动方式（一键脚本已生成启动器）：

```sh
bash ~/phone-bridge/run-handsfree.sh
```

可选开关环境变量：
- `HANDSFREE_SPEAK=1`（默认开启 TTS 语音播报，静音设为 `0`）
- `HANDSFREE_VOICE=1`（默认开启语音指令监听）
- `HANDSFREE_NOTIFY=1`（默认开启通知监听转发）

---

## 2. MCP 工具直连（对话/沙箱端 `client/phone_mcp.py`）

把手机封装成标准 **MCP (stdio JSON-RPC 2.0)** 服务器。
Claude Code、Cursor、`craft-anything-cli` 或任何支持 MCP 的 Agent 接入后，
你在聊天框里直接说“帮我看下手机电量 / 帮我点一下屏幕 (540,1200) / 看看刚来的短信”，
AI 自动调用工具完成，**零手工敲命令**。

把 [configs/mcp.json.example](../configs/mcp.json.example) 拷到你的 MCP 配置（如 `.mcp.json`）并填入 `GH_REPO` / `GH_TOKEN` 即可。

内置 12 个免手动工具：
- 状态与系统：`phone_status`、`phone_battery`、`phone_shell`
- 信息与传感器：`phone_sms`、`phone_clipboard_get`、`phone_clipboard_set`、`phone_notify`、`phone_location`
- 屏幕操控（配合 Shizuku）：`phone_tap`、`phone_swipe`、`phone_input`、`phone_screenshot`

本地自检：

```sh
python3 phone-bridge/client/phone_mcp.py --selftest
```

---

## 3. 自动驾驶守护进程（沙箱/电脑端 `client/autopilot.py`）

即使客户端不支持 MCP，也可以后台挂一个 `autopilot.py` 盯着单个 GitHub Issue（`AUTOPILOT_ISSUE`）：

1. **自动收信**：手机在线心跳、转发过来的通知自动落盘到 `autopilot.log`
2. **评论即执行**：你（或任意 Agent / GitHub Action / 手机网页）在该 Issue 下评论一行：
   ```text
   task: battery
   ```
   或
   ```text
   task: shell:ls -la ~/downloads
   ```
   `autopilot.py` 自动派发给手机执行，并把结果贴回同一条 Issue（自带 `reply_to` 防重放与 `.autopilot-seen.json` 断点续跑，不会死循环或重复执行）。

启动方式：

```sh
export GH_REPO=你的用户名/phone-bridge
export GH_TOKEN=ghp_xxx
export DEVICE_ID=pixel-8
export AUTOPILOT_ISSUE=1
python3 phone-bridge/client/autopilot.py
```

---

## 安全底线（解放双手 ≠ 裸奔）

- **不自动回短信 / 不自动转账**：`handsfree.py` 与 `autopilot.py` 只汇报通知，绝不替你自动发消息或点付款。
- **同源危险拦截**：语音、MCP、`autopilot` 全部复用 `phone_agent.py` 的危险命令黑名单（拦截 `rm -rf /`、`curl | sh`、`dd`、`mkfs` 等）。
- **屏幕点击默认锁死**：必须在手机 `run.sh` 中显式开启 `ENABLE_SCREEN_CONTROL=1` 才允许 `tap/swipe/input`。
