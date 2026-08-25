"""Stops all bare mode services by killing PIDs in run/*.pid.
"""
import os
import pathlib
import signal
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
RUN = ROOT / "run"

def kill_pid(pid: int):
    if sys.platform == "win32":
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
        except Exception:
            pass
    else:
        try:
            os.kill(pid, signal.SIGCONT)
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass

def main():
    if not RUN.exists():
        print("all stopped")
        return
    for pid_file in RUN.glob("*.pid"):
        try:
            text = pid_file.read_text().strip()
            if text:
                pid = int(text)
                kill_pid(pid)
        except Exception:
            pass
        pid_file.unlink(missing_ok=True)
    print("all stopped")

if __name__ == "__main__":
    main()
