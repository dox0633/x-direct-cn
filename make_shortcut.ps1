# 生成桌面快捷方式「X 关注动态直连助手」，带自制图标
$ErrorActionPreference = 'Stop'
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$desktop = [Environment]::GetFolderPath('Desktop')
$lnkPath = Join-Path $desktop 'X 关注动态直连助手.lnk'

# 生成一个小图标（蓝底白 X），用 System.Drawing 存为 ico
Add-Type -AssemblyName System.Drawing
$bmp = New-Object System.Drawing.Bitmap 64,64
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$g.Clear([System.Drawing.Color]::FromArgb(29,111,242))
$brush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::White)
$font = New-Object System.Drawing.Font('Segoe UI', 34, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
$sf = New-Object System.Drawing.StringFormat
$sf.Alignment = [System.Drawing.StringAlignment]::Center
$sf.LineAlignment = [System.Drawing.StringAlignment]::Center
$g.DrawString('X', $font, $brush, (New-Object System.Drawing.RectangleF(0,0,64,64)), $sf)
$g.Dispose()
$iconPath = Join-Path $dir 'panel.ico'
$hIcon = $bmp.GetHicon()
$icon = [System.Drawing.Icon]::FromHandle($hIcon)
$fs = [System.IO.File]::Create($iconPath)
$icon.Save($fs)
$fs.Close()
$icon.Dispose(); $bmp.Dispose()

$wsh = New-Object -ComObject WScript.Shell
$lnk = $wsh.CreateShortcut($lnkPath)
$lnk.TargetPath = Join-Path $dir 'launch.vbs'
$lnk.WorkingDirectory = $dir
$lnk.IconLocation = "$iconPath,0"
$lnk.Description = 'X 关注动态本地控制面板（国内直连 / 免费）'
$lnk.Save()

Write-Host "桌面快捷方式已创建：$lnkPath" -ForegroundColor Green
Write-Host "图标：$iconPath" -ForegroundColor Gray
