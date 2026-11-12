<div align="center">

# X 关注动态直连助手

**关注的人一发新动态，第一时间在本机看到。免费 · 国内直连 · 零 API Key · 零代理 · 无需登录 X 账号**

[![Python](https://img.shields.io/badge/Python-3.8%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows-blue)](#快速开始)

A local desktop dashboard that mirrors public X/Twitter timelines into a clean,
self-contained panel — no account login, no paid API, no proxy required from mainland China.

</div>

---

## 为什么做这个

X 主站、Nitter 公共实例、RSSHub 公共实例在国内直连全部超时；官方 API 要付费、要密钥、
要登录。这个项目用一条实测可直连的公开时间线接口做增量拉取，把正文、译文、头像、
配图全部落到本地，用一个纯本地网页呈现——**你的浏览器从头到尾只连 `127.0.0.1`**。

---

## 效果

| 白天 | 黑夜 |
|---|---|
| 白天主题截图见 [`docs/screenshot-light.png`](docs/screenshot-light.png) | 黑夜主题截图见 [`docs/screenshot-dark.png`](docs/screenshot-dark.png) |

按作者筛选：点左侧任一账号，右侧只显示 TA 的全部历史动态，默认最新在前。

---

## 快速开始（Windows）

**要求**：Python 3.8+，安装时勾选 *Add Python to PATH*。仅用标准库，无需 `pip install`。

```bat
git clone https://github.com/dox0633/x-direct-cn.git
cd x-direct-cn
copy config.example.json config.json
```

然后二选一：

**① 桌面控制面板（推荐）** — 右键 `make_shortcut.ps1` →「使用 PowerShell 运行」，
桌面出现「X 关注动态直连助手」图标，双击打开。

> 若提示执行策略限制：
> `powershell -ExecutionPolicy Bypass -File .\make_shortcut.ps1`

**② 直接启动**

```bat
python panel.py
```

浏览器自动打开 `http://127.0.0.1:8899`。关掉浏览器窗口只是关页面，服务仍在后台；
要彻底停止点面板右上角「退出」。

---

## 功能

| 功能 | 说明 |
|---|---|
| **动态存档** | 关注账号的正文按时间倒序排列，全部存本地 `items.json`，随时回看 |
| **正确头像** | 头像与配图经 `images.weserv.nl` 代理下载到 `media/`，断网也能显示 |
| **英译汉** | 只做英→中，不做中译英。开关开启后**只自动翻译最新一条**；历史动态点卡片右上角「译」按需翻译。译过的卡片显示中文为主、原文附在下方，点「看原文 / 看中文」可来回切换显示 |
| **两套配色** | ☀ 白天 / 🌙 黑夜，选择持久化，刷新不闪白 |
| **按作者查看** | 点左侧账号头像或名字筛选；支持 `?user=OfficialLoganK` 直达 |
| **弹窗提醒** | 新动态的 Windows 桌面气泡，可一键关闭（关闭后只在面板里看） |
| **启停监控** | 顶部「暂停 / 开启」，不影响已存档内容 |
| **配图开关** | 一键隐藏推文配图，头像始终显示 |
| **加 / 删关注** | 左侧输入框填 X 账号回车即加，立即抓历史；`×` 移除 |
| **推送渠道** | 可选飞书 / 钉钉 / Server酱 / Bark / 企业微信 webhook（纯推送版 `x_watch.py`） |

界面里**没有任何可点击的外链**，正文用 `textContent` 渲染，来源标识只是纯文本。

---

## 英译汉的设计取舍

免费翻译接口都有每日/IP 配额，一次性翻几百条必然触发限流（429 / 411）。
所以这里不做"全量自动补译"：

- **开启英译汉** → 只自动翻最新一条，几乎瞬时完成
- **历史动态** → 想看哪条就点哪条的「译」，一次只翻一条
- **译文缓存** → 同一句永不重复请求，存 `translations.json`
- **原文/中文切换** → 译过的卡片默认「中文为主 + 原文在下」，点右上角「看原文」只显示英文原文，
  再点「看中文」切回。切换是纯前端视图行为，不重新请求翻译接口
- **单方向** → 固定英→中，不提供中译英
- **双通道** → 有道 `aidemo` 批量为主，MyMemory 兜底；失败静默重试，绝不阻塞监控

翻译通道：`aidemo.youdao.com`（国内直连、免费、无 Key）与
`api.mymemory.translated.net`。两者都不可用时卡片显示原文，不影响其他功能。

---

## 推送实时性 / 延迟 / 是否需要登录

**不需要登录 X 账号。** 全程只读公开时间线，没有用户名密码、没有 Cookie、
没有 auth_token，也不往 X 发任何请求。程序只连：

| 域名 | 用途 |
|---|---|
| `api.fxtwitter.com` | 公开时间线 / 用户资料 |
| `images.weserv.nl` | 代理下载 `pbs.twimg.com` 的头像配图 |
| `aidemo.youdao.com`、`api.mymemory.translated.net` | 免费翻译 |
| 你自己填的 webhook | 可选推送 |

**不是秒级推送，是固定周期轮询**（X 官方 Streaming 需要开发者密钥）。延迟构成：

| 环节 | 耗时 |
|---|---|
| 轮询周期（默认 30s，可配到 20s） | 0~30s |
| 一轮抓取（4 并发 + 5s 短超时 × 5 次重试） | 常态 12~30s，链路抖动最长 60s |
| 页面刷新（3s） | 0~3s |

典型 **30 秒内**，链路抖动时 **1~2 分钟**。状态栏显示「Ns 前抓取」。
循环已做固定周期对齐（扣除本轮耗时），不会把「抓取耗时 + 间隔」叠加。

**不漏推**：`since` 只在成功拿到时间线时推进；某个账号本轮失败，下轮用旧 `since`
重新拉，中间累积的新推一次性补齐——只会晚，不会丢。`seen` 集合二次去重，不会重复提醒。

---

## 实测数据（2026-11，中国大陆网络）

| 配置 | 结果 |
|---|---|
| `x.com` / Nitter 公共实例 / RSSHub 公共实例 / syndication / r.jina.ai | 全部超时 |
| `api.fxtwitter.com/2/profile/{h}/statuses?since=<秒>` | 200 时间线 JSON / 204 无新推 |
| 11 账号串行、20s 超时 ×2 | 一轮 5 分钟以上，不可用 |
| 11 并发、12s 超时 | 链路丢包，仅 2~3/11 成功 |
| **4 并发 + 5s 短超时 + 5 次快速重试** | **11/11 全成功，一轮约 33 秒** |

根因不是限流而是链路丢包：成功的请求 1.8~4s 就返回，失败的请求连 TCP 都建不起来，
所以策略是「短超时 + 快速重试」，而不是「长超时干等」。

`created_timestamp` 是秒级 Unix 时间戳，上游 `results` **并非严格按时间倒序**，
程序用 `max()` 推进 `since`，前端再按 `ts` 倒序渲染。

---

## 配置说明

`config.json`（从 `config.example.json` 复制）字段：

| 字段 | 默认 | 说明 |
|---|---|---|
| `watch` | 11 个 AI 发言人 | 关注的 X 账号列表 |
| `interval` | `30` | 轮询秒数，下限 20 |
| `workers` | `4` | 并发数，实测 4 最稳 |
| `retries` | `5` | 单账号短超时重试次数 |
| `replies` | `false` | 是否包含回复 |
| `retweets` | `true` | 是否包含转推 |
| `show_images` | `true` | 显示推文配图 |
| `translate` | `false` | 英译汉开关 |
| `theme` | `"light"` | `light` / `dark` |
| `popup_notify` | `true` | 桌面弹窗提醒 |
| `notify` | 空 | 可选 webhook 推送渠道 |

---

## 文件结构

```
x-direct-cn/
├── panel.py               # 控制面板主程序（本地 HTTP 服务 + 监控 + 翻译）
├── panel.html             # 面板界面（零外链、零 CDN）
├── x_watch.py             # 纯推送版（可选，无面板）
├── launch.vbs             # 无黑框启动器
├── make_shortcut.ps1      # 生成桌面快捷方式与图标
├── panel.ico              # 桌面图标
├── run.bat                # 纯推送版启动
├── install_startup.ps1    # 开机自启
├── config.example.json    # 配置模板（复制为 config.json）
├── .gitignore
├── LICENSE
├── CONTRIBUTING.md
└── docs/                  # 发布截图
```

运行时生成、不进仓库：`config.json`、`items.json`、`state.json`、
`translations.json`、`media/`、`*.log`。

---

## 纯推送版（可选）

不看面板、只想收通知时用：

```bat
python x_watch.py              :: 常驻监控
python x_watch.py --once       :: 只跑一轮
python x_watch.py --test       :: 发测试推送
python x_watch.py --add sama   :: 追加关注
python x_watch.py --list       :: 列出关注
python x_watch.py --reset      :: 重建基线
```

不填任何 webhook 也能用，自动走 Windows 桌面气泡。想推到手机/微信，
在 `config.json` 的 `notify` 里填一个：

| 字段 | 渠道 |
|---|---|
| `feishu_webhook` | 飞书群机器人 |
| `wecom_webhook` | 企业微信群机器人 |
| `dingtalk_webhook` / `dingtalk_secret` | 钉钉群机器人 |
| `serverchan_key` | Server酱（微信服务号） |
| `bark_url` | Bark（iPhone） |

---

## 免责说明

本项目只读取公开可访问的时间线数据，用于个人信息聚合与阅读，不绕过任何登录、
鉴权或访问控制，不存储任何账号凭据。第三方公开接口（fxtwitter / weserv / 有道 /
MyMemory）的可用性、配额与条款由各自服务方决定，可能随时变化；程序对此做了降级与
缓存处理，接口不可用时只影响对应功能，不影响本地已存档内容。

---

## License

[MIT](LICENSE) · 欢迎 PR，见 [CONTRIBUTING.md](CONTRIBUTING.md)
