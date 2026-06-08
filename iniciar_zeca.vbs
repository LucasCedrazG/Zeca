Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\JARVIS"
WshShell.Run "pythonw.exe detector_palmas.py", 0, False