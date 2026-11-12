# 贡献指南

欢迎提交 Issue 和 Pull Request。

## 开发环境

- Python 3.8+，**仅标准库**，无第三方依赖
- Windows 为主（桌面通知、快捷方式用 PowerShell / VBScript）
- 面板是纯静态 HTML + 原生 JS，无构建步骤、无 npm、无 CDN

```bat
git clone https://github.com/dox0633/x-direct-cn.git
cd x-direct-cn
copy config.example.json config.json
python panel.py
```

浏览器打开 `http://127.0.0.1:8899`。

## 提交前请确认

- [ ] `python -m py_compile panel.py x_watch.py` 通过
- [ ] 面板在白天 / 黑夜两套配色下都能正常渲染
- [ ] 未把 `config.json`、`items.json`、`state.json`、`translations.json`、
      `media/`、`*.log`、`shot_*.png`、`__pycache__/` 提交进仓库
- [ ] 界面里没有新增任何外链、CDN 或 `<a href="http...">`
- [ ] 正文继续用 `textContent` 渲染（不要把用户内容拼进 `innerHTML`）
- [ ] 新增第三方接口时补上失败降级，不能让单个接口挂掉阻塞监控主循环

## 代码结构

| 文件 | 职责 |
|---|---|
| `panel.py` | HTTP 服务、`/api/data`、监控循环、抓取解析、翻译、图片本地化 |
| `panel.html` | 界面与交互（主题、筛选、手动翻译、开关） |
| `x_watch.py` | 无面板的纯推送版，独立可跑 |
| `launch.vbs` / `make_shortcut.ps1` | Windows 桌面入口 |

## 几个约定

- **`since` 只在成功时推进**。任何抓取失败都不能推进增量游标，否则会漏动态。
- **短超时 + 快速重试**，不要改回长超时。国内到 `api.fxtwitter.com` 是链路丢包，
  不是服务端限流；实测 5s × 5 次 + 4 并发成功率最高。
- **图片一律下载到 `media/` 再呈现**，界面不能引用 `pbs.twimg.com` 等外部地址。
- **翻译只翻最新一条 + 手动按需**。免费接口有配额，不要恢复全量自动补译。
- **不引入登录 / Cookie / auth_token**，保持只读公开数据。

## 提交 Issue 时请附上

- 操作系统与 Python 版本
- `panel.log` 里相关时间段的几行
- 复现步骤与期望行为

## 行为准则

保持友善、就事论事。不要提交任何账号凭据、token、webhook 地址或个人数据。
