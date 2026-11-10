# phone-bridge — 让对话沙箱操控你的 Android 手机

> Android 专属。免费、开源、无需 Root、无需 Tailscale 付费版。
> 目标：像 [dsh-go](https://github.com/ccch1mneyyy/dsh-go) 一样，
> 用聊天对话操控手机——只不过方向反过来：**沙箱当遥控器，手机当被控端**。

## 它解决什么问题

| 你的需求 | 本方案 |
|---|---|
| 手机免费连电脑，不用 Tailscale 付费 | EasyTier / frp / chisel / Cloudflare Tunnel（全部免费自建） |
| 沙箱能直接操作手机 | GitHub Issues 当中继：沙箱和手机都只连 `api.github.com` |
| 能 SSH 登录手机 | Termux `sshd`（端口 8022）+ 隧道，见 `configs/` |
| 像 dsh-go 那样“看屏幕、帮你点” | Shizuku + rish 实现 `tap/swipe/input/screenshot`；scrcpy 做 PC 镜像 |
| 读短信、剪贴板、电量、定位、通知 | Termux:API 一键命令 |

## 架构（一图看懂）

```
模式一（沙箱用，默认）:  沙箱 ──发 Issue──▶ GitHub ──轮询──▶ 手机 Termux Agent
                          沙箱 ◀─评论=结果── GitHub ◀─回帖─── 手机执行命令

模式二（你自己电脑用）:  电脑 ──ssh :8022──▶ EasyTier/frp/chisel ──▶ 手机 Termux sshd
```

详见 [docs/architecture.md](docs/architecture.md)。

## 快速开始（5 步）

### 1. 建一个私有仓库当“命令队列”

在 GitHub 建一个私有 repo（比如 `你的用户名/phone-bridge`），
建一个 label：`phone-cmd`（绿色）。生成一个
**Fine-grained PAT**，只给这个 repo 的 `Issues: read/write` 权限。

### 2. 手机上装 Termux 并跑 Agent

从 [F-Droid](https://f-droid.org/en/packages/com.termux/) 或
[GitHub Releases](https://github.com/termux/termux-app/releases)
装 Termux（**不要用 Play 商店的停更版**），然后：

```sh
export GH_REPO=你的用户名/phone-bridge
export GH_TOKEN=ghp_xxx
export DEVICE_ID=pixel-8
bash setup-termux.sh   # 在 agent/ 目录下运行
```

脚本会装 `openssh + termux-api + python`、启动 sshd（8022）、
开 wake-lock、启动 Agent。记得把 Termux 电池设为“不限制”。

### 3. 从电脑/沙箱发命令

```sh
export GH_REPO=你的用户名/phone-bridge
export GH_TOKEN=ghp_xxx
export DEVICE_ID=pixel-8

python3 client/phone_client.py "status"                    # 电量/存储/运行状态
python3 client/phone_client.py "battery"                   # 电量
python3 client/phone_client.py --shell "ls ~/downloads"    # 任意 shell 命令
python3 client/phone_client.py "sms"                       # 最近短信（需授权）
python3 client/phone_client.py "clipboard-get"             # 剪贴板
python3 client/phone_client.py "notify:标题:内容"          # 发通知
```

### 4.（可选）电脑直连 SSH，不走 GitHub

手机已经跑了 sshd（8022）。选一个免费隧道（见 `configs/`）：

- **EasyTier**（推荐）：手机+电脑装 EasyTier，同 network-name/secret，
  然后 `ssh -p 8022 <whoami>@10.144.144.2`
- **frp / chisel / bore**：手机拨出到 VPS，电脑 `ssh -p 2222 user@vps`
- **Cloudflare Tunnel**：手机跑 `cloudflared`，电脑 `cloudflared access ssh`

SSH 配置模板在 [configs/ssh_config.example](configs/ssh_config.example)。

### 5.（可选）屏幕操控（dsh-go 式“帮你点”）

装 [Shizuku](https://github.com/RikkaApps/Shizuku) + rish，
在 Agent 环境里设 `ENABLE_SCREEN_CONTROL=1` 重启，然后：

```sh
python3 client/phone_client.py "tap:540:1200"
python3 client/phone_client.py "swipe:100:1000:100:300:300"
python3 client/phone_client.py "input:hello"
python3 client/phone_client.py "screenshot"
```

## 目录结构

```
phone-bridge/
├── README.md                  ← 你正在看的
├── agent/
│   ├── phone_agent.py         ← 手机端轮询 Agent（纯标准库）
│   └── setup-termux.sh        ← Termux 一键安装脚本
├── client/
│   ├── phone_client.py        ← 沙箱/电脑端客户端（纯标准库）
│   └── ssh_config.example     ← 直连 SSH 配置模板
├── configs/                   ← EasyTier / frp / chisel 配置
├── docs/
│   ├── architecture.md        ← 架构 + 安全模型
│   ├── github-projects.md     ← 用到的 GitHub 项目清单
│   └── troubleshooting.md     ← 常见问题
└── tests/
    └── test_protocol.py       ← 协议单元测试（无网络）
```

## 测试

```sh
python3 -m unittest discover -s tests -v
```

## 安全提醒

- PAT 只给最小权限（单个私有 repo 的 Issues 读写），**绝不提交到仓库**。
- Agent 默认拒绝 `rm -rf /`、`curl | sh` 等危险命令；
  屏幕操控默认关闭。
- 直连 SSH 只用密钥登录（`ssh-copy-id`），禁用密码登录。
- 敏感操作（付款、密码、验证码）请你自己在手机上确认，
  不要让 Agent 代劳——和 dsh-go 的三档确认一个思路。

## 致谢 / 许可证

本目录为原创代码（MIT OR Apache-2.0，与仓库一致），
设计参考了 [docs/github-projects.md](docs/github-projects.md)
所列的开源项目，未复制其代码。
