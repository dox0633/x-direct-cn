# 生成桌面快捷方式「X 关注动态直连助手」，使用 panel.ico（由 make_icon.py 生成）
$ErrorActionPreference = 'Stop'
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$desktop = [Environment]::GetFolderPath('Desktop')
$lnkPath = Join-Path $desktop 'X 动态面板.lnk'
$iconPath = Join-Path $dir 'panel.ico'

# 图标缺失时自动重新生成（需要 Pillow）
if (-not (Test-Path $iconPath)) {
    $py = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $py) { $py = 'C:\Users\Administrator\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe' }
    if (-not (Test-Path $py)) { throw "缺少 panel.ico 且找不到 Python 来生成它" }
    & $py (Join-Path $dir 'make_icon.py')
}
if (-not (Test-Path $iconPath)) { throw "图标生成失败：$iconPath" }

$wsh = New-Object -ComObject WScript.Shell
$lnk = $wsh.CreateShortcut($lnkPath)
$lnk.TargetPath = Join-Path $dir 'launch.vbs'
$lnk.WorkingDirectory = $dir
$lnk.IconLocation = "$iconPath,0"
$lnk.Description = 'X 关注动态直连助手 · 本地控制面板（国内直连 / 免费）'
$lnk.Save()

# 通知资源管理器刷新图标缓存
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public class ShortcutIconRefresh {
  [DllImport("shell32.dll")] public static extern void SHChangeNotify(int eventId, uint flags, IntPtr item1, IntPtr item2);
}
'@
[ShortcutIconRefresh]::SHChangeNotify(0x08000000, 0x0000, [IntPtr]::Zero, [IntPtr]::Zero)

Write-Host "桌面快捷方式已创建：$lnkPath" -ForegroundColor Green
Write-Host "图标：$iconPath" -ForegroundColor Gray
Write-Host "如桌面仍显示旧图标，按 F5 刷新桌面，或注销后重新登录。" -ForegroundColor Yellow
