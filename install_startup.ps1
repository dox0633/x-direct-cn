# 把 x-direct-cn 加入 Windows 开机自启（无黑框后台运行）
# 用法：右键 -> 使用 PowerShell 运行；或在 PowerShell 里执行  .\install_startup.ps1
# 卸载：删除下面输出的 .lnk 文件即可

$ErrorActionPreference = 'Stop'
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$script = Join-Path $dir 'x_watch.py'

$pyw = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
if (-not $pyw) {
    $py = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
    if (-not $py) { throw '找不到 Python，请先安装并加入 PATH' }
    $pyw = Join-Path (Split-Path $py) 'pythonw.exe'
    if (-not (Test-Path $pyw)) { throw "找不到 pythonw.exe：$pyw" }
}

$startup = [Environment]::GetFolderPath('Startup')
$lnkPath = Join-Path $startup 'x-direct-cn.lnk'

$ws = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut($lnkPath)
$lnk.TargetPath = $pyw
$lnk.Arguments = '"' + $script + '"'
$lnk.WorkingDirectory = $dir
$lnk.Description = 'X 关注动态实时提醒（国内直连 / 免费）'
$lnk.Save()

Write-Host "已加入开机自启：$lnkPath" -ForegroundColor Green
Write-Host "运行日志：$dir\watch.log" -ForegroundColor Gray
Write-Host "现在也会立即启动一次..." -ForegroundColor Gray
Start-Process -FilePath $pyw -ArgumentList ('"' + $script + '"') -WorkingDirectory $dir -WindowStyle Hidden
Write-Host "完成。卸载时删除该快捷方式即可。" -ForegroundColor Green
