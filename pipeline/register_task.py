# -*- coding: utf-8 -*-
"""注册 Windows 计划任务：交易日（周一至周五）早上 9:00 跑一次日更。

用 subprocess 而不是在 shell 里敲 schtasks，是因为任务路径和工作区路径
都含中文，shell 转义/代码页容易把路径搞坏；
subprocess 走 CreateProcessW，Unicode 不会坏。
任务只建在当前用户下，不需要管理员权限。
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")
SCRIPT = str(ROOT / "pipeline" / "daily_refresh.py")
TASK = "ChainAtlas-DailyRefresh"

TR = f'"{PY}" "{SCRIPT}"'

r = subprocess.run(
    ["schtasks", "/Create", "/F", "/TN", TASK,
     "/SC", "WEEKLY", "/D", "MON,TUE,WED,THU,FRI", "/ST", "09:00",
     "/TR", TR],
    capture_output=True, text=True, encoding="gbk", errors="replace",
)
print("注册退出码:", r.returncode)
print((r.stdout or "").strip())
if r.stderr.strip():
    print("stderr:", r.stderr.strip())

q = subprocess.run(["schtasks", "/Query", "/TN", TASK, "/FO", "LIST"],
                   capture_output=True, text=True, encoding="gbk", errors="replace")
print("\n=== 查询确认 ===")
print((q.stdout or q.stderr).strip())
sys.exit(0 if r.returncode == 0 else 1)
