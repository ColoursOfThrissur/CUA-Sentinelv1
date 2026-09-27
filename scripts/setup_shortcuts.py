import os
import sys

def setup_shortcuts():
    try:
        import win32com.client
    except ImportError:
        print("pywin32 not installed, skipping shortcut update.")
        return

    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    cmd_exe = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "cmd.exe")
    icon_path = os.path.join(root_dir, "sentinel.ico")

    shell = win32com.client.Dispatch("WScript.Shell")

    shortcuts = [
        {
            "filename": "CUA Sentinel.lnk",
            "target": cmd_exe,
            "args": f'/c ""{os.path.join(root_dir, "launch.bat")}""',
            "desc": "Launch CUA-Sentinel AI Platform",
        },
        {
            "filename": "Restart CUA Sentinel.lnk",
            "target": cmd_exe,
            "args": f'/c ""{os.path.join(root_dir, "restart.bat")}""',
            "desc": "Restart CUA-Sentinel Services",
        },
        {
            "filename": "Stop CUA Sentinel.lnk",
            "target": cmd_exe,
            "args": f'/c ""{os.path.join(root_dir, "stop.bat")}""',
            "desc": "Stop CUA-Sentinel Services",
        },
    ]

    for item in shortcuts:
        lnk_path = os.path.join(desktop, item["filename"])
        shortcut = shell.CreateShortcut(lnk_path)
        shortcut.TargetPath = item["target"]
        shortcut.Arguments = item["args"]
        shortcut.WorkingDirectory = root_dir
        shortcut.Description = item["desc"]
        if os.path.exists(icon_path):
            shortcut.IconLocation = f"{icon_path},0"
        shortcut.WindowStyle = 1
        shortcut.Save()
        print(f"[OK] Refreshed shortcut: {item['filename']} -> {item['args']}")

if __name__ == "__main__":
    setup_shortcuts()
