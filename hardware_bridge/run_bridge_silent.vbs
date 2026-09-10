' ====================================================================
' Tuần Châu Resort - Hardware Bridge Silent Background Launcher
' Chạy ngầm dịch vụ kết nối đầu đọc thẻ không hiện cửa sổ Command Prompt
' ====================================================================
Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")
strCurDir = FSO.GetParentFolderName(WScript.ScriptFullName)

' 0 = Hide window, False = Return immediately without waiting
WshShell.Run "python """ & strCurDir & "\server.py""", 0, False
