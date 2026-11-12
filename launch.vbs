' X 关注动态直连助手启动器 —— 无黑框、无控制台
Option Explicit
Dim sh, fso, here, pyw, cmd
Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)
Set sh = CreateObject("WScript.Shell")

' 优先 DSH 内置 Python，其次系统 Python
pyw = ""
Dim candidates, c
candidates = Array( _
    sh.ExpandEnvironmentStrings("%USERPROFILE%") & "\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\pythonw.exe", _
    "D:\COSMOS\PCD\Python 3.12.8\pythonw.exe", _
    "" )
For Each c In candidates
    If c <> "" And fso.FileExists(c) Then pyw = c : Exit For
Next
If pyw = "" Then pyw = "pythonw.exe"   ' 退回 PATH

cmd = """" & pyw & """ """ & here & "\panel.py"""
sh.CurrentDirectory = here
sh.Run cmd, 0, False   ' 0 = 隐藏窗口
