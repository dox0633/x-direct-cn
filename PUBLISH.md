# GitHub 发布清单

**仓库**：`dox0633/x-direct-cn` · https://github.com/dox0633/x-direct-cn
**中文名**：X 关注动态直连助手

---

## 一、认证说明（重要）

**GitHub 自 2021 年 8 月起停用账号密码推送。** 实测用账号 + 密码请求
`https://api.github.com/user` 与 `git ls-remote` 均返回：

```
remote: Invalid username or token. Password authentication is not supported for Git operations.
fatal: Authentication failed
```

所以**账号密码无法用于发布**，必须改用以下之一：

| 方式 | 说明 |
|---|---|
| **Personal Access Token（classic）** | Settings → Developer settings → Personal access tokens → Tokens (classic) → Generate new token，勾选 `repo`，有效期按需选 |
| **细粒度 PAT** | 需给目标仓库 Contents 读写权限 |
| **SSH key** | 已配置 `git@github.com` 时可改用 SSH 地址 |

token 只在命令行参数或 `GITHUB_TOKEN` 环境变量里临时使用，**脚本不会把它写进
`.git/config` 或任何项目文件**，推送输出的日志也做了脱敏。

> `publish.ps1` 会主动拒绝非 `ghp_` / `github_pat_` 形态的凭据，避免误用密码。

---

## 二、发布步骤

```powershell
cd x-direct-cn

# ① 预览：语法 / 必需文件 / 泄露扫描 / 待提交清单（不提交、不联网）
powershell -ExecutionPolicy Bypass -File .\publish.ps1

# ② 设置 PAT（推荐用环境变量，不进命令行历史）
$env:GITHUB_TOKEN = "ghp_xxxxxxxxxxxxxxxxxxxx"

# ③ 自动建仓 + 提交 + 推送
powershell -ExecutionPolicy Bypass -File .\publish.ps1 -CreateRepo -Commit -Push
```

也可以直接传参：

```powershell
powershell -ExecutionPolicy Bypass -File .\publish.ps1 `
  -Token ghp_xxxx -Name "dox0633" -Email "dox0633@users.noreply.github.com" `
  -CreateRepo -Commit -Push
```

若已在网页建好空仓库，去掉 `-CreateRepo` 即可。
建仓时**不要**勾选 "Initialize this repository with a README"（本地已有 README，会冲突）。

---

## 三、脚本自动做的检查

1. `python -m py_compile panel.py x_watch.py` 必须过
2. 19 个发布必需文件齐全（含 3 张 `docs/` 截图）
3. `.gitignore` 覆盖全部运行时数据；源码里扫描 `sk-` / `ghp_` / `github_pat_` /
   `hook/` / `access_token=` 等硬编码凭据形态
4. PAT 校验（`GET /user`），确认身份与有效性
5. 仓库不存在时按 `-CreateRepo` 自动创建 public 仓库
6. `git init` → 配置身份 → 绑定 `origin` → `git add -A` → 打印待提交清单
7. 加 `-Commit` 才提交；加 `-Push` 才推送

---

## 四、将提交的清单

```
panel.py                 面板主程序
panel.html               界面（零外链）
x_watch.py               纯推送版
launch.vbs               无黑框启动器
make_shortcut.ps1        桌面快捷方式生成
panel.ico                图标
run.bat                  纯推送版启动
install_startup.ps1      开机自启
config.example.json      配置模板
.gitignore / .gitattributes
README.md                使用说明
LICENSE                  MIT（署名 dox0633）
CONTRIBUTING.md          贡献指南
PUBLISH.md               本文档
publish.ps1              发布脚本
docs/screenshot-light.png
docs/screenshot-dark.png
docs/screenshot-filter.png
```

**不会提交**：`config.json`、`items.json`、`state.json`、`translations.json`、
`media/`、`*.log`、`shot_*.png`、`__pycache__/`、`*.lnk`。

---

## 五、发布后建议

- About 填：`X 关注动态直连助手 · Local X timeline dashboard · 国内直连 / 免费 / 免登录`
- Topics：`twitter` `x` `dashboard` `python` `windows` `translation` `no-api-key` `rss`
- 建 `v1.0.0` Release，附上三张截图
- 检查 README 里的仓库地址、徽章链接是否指向 `dox0633/x-direct-cn`

---

## 六、维护注意

- 第三方免费接口（fxtwitter / weserv / 有道 aidemo / MyMemory）随时可能变化或限流，
  发布时不要承诺 SLA；README 里已写明降级行为。
- 不要在任何公开材料里放真实 webhook、token 或抓取账号。
- 用户存档（`items.json` 等）永远不入库，避免把别人的关注列表与阅读记录传上去。
