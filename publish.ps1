<#
.SYNOPSIS
  准备并发布 x-direct-cn（X 关注动态直连助手）到 GitHub。

.PARAMETER Token
  GitHub Personal Access Token（classic，需 repo 权限）。
  GitHub 自 2021 起停用账号密码推送，只接受 PAT / SSH。
  也可用环境变量 GITHUB_TOKEN 提供，避免出现在命令行历史里。

.PARAMETER CreateRepo
  PAT 有权限时自动创建 public 仓库（若不存在）。

.PARAMETER Name / Email
  本机 git 提交身份。不传则沿用全局配置。

.PARAMETER Commit
  传此开关才真正 commit（默认只预览）。

.PARAMETER Push
  传此开关才 push，必须提供 Token 或已配好 SSH。

.EXAMPLE
  $env:GITHUB_TOKEN = "ghp_xxxxxxxx"
  powershell -ExecutionPolicy Bypass -File .\publish.ps1 -CreateRepo -Commit -Push

.NOTES
  绝不把账号密码写进 URL 或文件。脚本会主动拒绝非 ghp_/github_pat_ 形态的凭据。
#>
param(
    [string]$Token = "",
    [string]$Name = "",
    [string]$Email = "",
    [switch]$CreateRepo,
    [switch]$Commit,
    [switch]$Push
)

$ErrorActionPreference = 'Stop'
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $dir

$Owner   = 'dox0633'
$Repo    = 'x-direct-cn'
$RepoUrl = "https://github.com/$Owner/$Repo.git"
$ApiRepo = "https://api.github.com/repos/$Owner/$Repo"

Write-Host "== X 关注动态直连助手 · GitHub 发布 ==" -ForegroundColor Cyan
Write-Host "仓库: $Owner/$Repo`n"

if (-not $Token) { $Token = $env:GITHUB_TOKEN }
if ($Token -and $Token -notmatch '^(ghp_|github_pat_|gho_|ghu_|ghs_|ghr_)') {
    throw '凭据不是 PAT 形态。GitHub 不接受账号密码推送，请提供 Personal Access Token。'
}

# 1. 语法检查
Write-Host "[1/6] Python 语法检查" -ForegroundColor Yellow
$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { throw '找不到 python，请先安装并加入 PATH' }
& $py -m py_compile panel.py x_watch.py
if ($LASTEXITCODE -ne 0) { throw '语法检查未通过' }
Write-Host "  OK`n" -ForegroundColor Green

# 2. 必需文件
Write-Host "[2/6] 必需文件" -ForegroundColor Yellow
$required = @(
    'panel.py','panel.html','x_watch.py','launch.vbs','make_shortcut.ps1',
    'panel.ico','run.bat','install_startup.ps1','config.example.json',
    '.gitignore','.gitattributes','README.md','LICENSE','CONTRIBUTING.md',
    'PUBLISH.md','publish.ps1',
    'docs/screenshot-light.png','docs/screenshot-dark.png','docs/screenshot-filter.png'
)
$missing = $required | Where-Object { -not (Test-Path (Join-Path $dir $_)) }
if ($missing) { throw "缺少文件: $($missing -join ', ')" }
Write-Host "  $($required.Count) 个文件齐全`n" -ForegroundColor Green

# 3. 泄露检查
Write-Host "[3/6] 泄露检查" -ForegroundColor Yellow
$forbidden = @('config.json','items.json','state.json','translations.json',
               'panel.log','watch.log','media','__pycache__')
foreach ($f in $forbidden) {
    if (Test-Path (Join-Path $dir $f)) {
        $hit = Select-String -Path (Join-Path $dir '.gitignore') -Pattern ([regex]::Escape($f)) -Quiet
        if (-not $hit) { throw ".gitignore 未覆盖: $f" }
    }
}
$src = Get-Content panel.py, x_watch.py, panel.html -Raw -Encoding UTF8
foreach ($pat in @('sk-[A-Za-z0-9]{20,}', 'ghp_[A-Za-z0-9]{20,}',
                   'github_pat_[A-Za-z0-9_]{20,}', 'hook/[A-Za-z0-9]{20,}',
                   'access_token=[A-Za-z0-9]{20,}')) {
    if ($src -match $pat) { throw "源码里疑似硬编码凭据，匹配: $pat" }
}
Write-Host "  OK（无凭据、无运行时数据入库）`n" -ForegroundColor Green

# 4. PAT 校验 / 自动建仓
Write-Host "[4/6] GitHub 凭据" -ForegroundColor Yellow
$authHeaders = @{
    'User-Agent' = 'x-direct-cn-publish'
    'Accept'     = 'application/vnd.github+json'
}
if ($Token) {
    $authHeaders['Authorization'] = "Bearer $Token"
    try {
        $me = Invoke-RestMethod -Uri 'https://api.github.com/user' -Headers $authHeaders -TimeoutSec 15
        Write-Host "  PAT 有效，身份: $($me.login)" -ForegroundColor Green
    } catch {
        $code = if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { 0 }
        throw "PAT 校验失败 (HTTP $code)。检查 token 是否过期、是否勾了 repo 权限。"
    }
    $exists = $false
    try {
        $null = Invoke-RestMethod -Uri $ApiRepo -Headers $authHeaders -TimeoutSec 15
        $exists = $true
    } catch { $exists = $false }
    if (-not $exists -and $CreateRepo) {
        $body = @{
            name        = $Repo
            description = 'X 关注动态直连助手 · Local X timeline dashboard · 国内直连 / 免费 / 免登录'
            private     = $false
            has_issues  = $true
            has_wiki    = $false
        } | ConvertTo-Json
        try {
            $null = Invoke-RestMethod -Uri 'https://api.github.com/user/repos' -Method Post `
                -Headers $authHeaders -Body $body -ContentType 'application/json' -TimeoutSec 20
            Write-Host "  已创建 public 仓库 $Owner/$Repo" -ForegroundColor Green
        } catch { throw "自动建仓失败: $($_.Exception.Message)" }
    } elseif (-not $exists) {
        Write-Host "  仓库尚不存在；加 -CreateRepo 可自动创建，或先在网页建好。" -ForegroundColor Yellow
    } else {
        Write-Host "  仓库已存在" -ForegroundColor Gray
    }
} else {
    Write-Host "  未提供 PAT（预览模式可用）。推送前请设置 `$env:GITHUB_TOKEN 或 -Token。" -ForegroundColor Gray
}
Write-Host ""

# 5. Git 仓库 / 提交
Write-Host "[5/6] Git 仓库" -ForegroundColor Yellow
if (-not (Test-Path (Join-Path $dir '.git'))) { & git init | Out-Null }
if ($Name)  { & git config user.name  $Name }
if ($Email) { & git config user.email $Email }
$hasName  = & git config user.name
$hasEmail = & git config user.email
if (-not $hasName)  { & git config user.name  $Owner }
if (-not $hasEmail) { & git config user.email "$Owner@users.noreply.github.com" }
$remotes = @(& git remote | ForEach-Object { $_.Trim() })
if ($remotes -contains 'origin') { & git remote set-url origin $RepoUrl | Out-Null }
else                            { & git remote add origin $RepoUrl  | Out-Null }
& git add -A
Write-Host "`n  将提交的文件:" -ForegroundColor Gray
& git status --short
Write-Host ""

if (-not $Commit) {
    Write-Host "  预览模式（未加 -Commit），未创建提交。" -ForegroundColor Cyan
    Write-Host "  发布命令:" -ForegroundColor Gray
    Write-Host '  $env:GITHUB_TOKEN="ghp_xxx"' -ForegroundColor White
    Write-Host '  powershell -ExecutionPolicy Bypass -File .\publish.ps1 -CreateRepo -Commit -Push' -ForegroundColor White
    return
}
& git commit -m "feat: X 关注动态直连助手 — 国内直连 / 免登录的本地 X 动态面板"
if ($LASTEXITCODE -ne 0) { throw 'git commit 失败（可能没有变更）' }
Write-Host "  已提交" -ForegroundColor Green

# 6. 推送
Write-Host "[6/6] 推送" -ForegroundColor Yellow
if (-not $Push) {
    Write-Host "  未推送（加 -Push 推送）" -ForegroundColor Cyan
    return
}
if (-not $Token) { throw 'push 需要 -Token 或 $env:GITHUB_TOKEN；GitHub 不接受账号密码。' }
# 若本机配了 ghfast.top 之类的 GitHub URL 重写，推送时临时禁用：
# 避免把 PAT 交给第三方代理转发，也避免代理改写认证头。
$hadRewrite = $false
$rewriteList = @(& git config --global --get-regexp 'insteadof' 2>$null | Out-String)
$rewriteVal = if ($rewriteList -join '' -match 'ghfast\.top') { 'yes' } else { '' }
if ($rewriteVal) {
    $hadRewrite = $true
    & git config --global --unset 'url.https://ghfast.top/https://github.com/.insteadof' | Out-Null
    Write-Host "  已临时禁用 github.com → ghfast.top 重写" -ForegroundColor Gray
}
$pushUrl = "https://$($Owner):$Token@github.com/$Owner/$Repo.git"
$env:GIT_TERMINAL_PROMPT = '0'
$branch = (& git rev-parse --abbrev-ref HEAD).Trim()
# 用带凭据的 URL 直接推，不写进 .git/config；输出做脱敏
try {
    & git push $pushUrl "HEAD:refs/heads/$branch" 2>&1 | ForEach-Object {
        ($_ -replace [regex]::Escape($Token), '***') | Write-Host
    }
    if ($LASTEXITCODE -ne 0) { throw 'git push 失败' }
    # 推完把 origin 固定为干净的公开 URL
    & git remote set-url origin $RepoUrl
    Write-Host "  已推送到 $Owner/$Repo ($branch)" -ForegroundColor Green
} finally {
    # 无论成功失败都清掉凭据痕迹，并恢复本机原有的重写规则
    & git remote set-url origin $RepoUrl 2>$null
    if ($hadRewrite) {
        & git config --global 'url.https://ghfast.top/https://github.com/.insteadof' 'https://github.com/' | Out-Null
    }
}
Write-Host "`n完成: https://github.com/$Owner/$Repo" -ForegroundColor Cyan
