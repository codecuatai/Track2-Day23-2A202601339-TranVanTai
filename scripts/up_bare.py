"""Launcher for bare mode (Windows and POSIX compatible).
Starts Region A (8001), Region B (8002), and Edge Proxy (8080).
Writes PIDs to run/region-a.pid, run/region-b.pid, run/edge.pid.
"""
import os
import pathlib
import subprocess
import sys
import time
import httpx

ROOT = pathlib.Path(__file__).resolve().parent.parent
RUN = ROOT / "run"
RUN.mkdir(exist_ok=True)
(ROOT / "reports").mkdir(exist_ok=True)

PYTHON = sys.executable

def start_process(cmd, env_vars, log_file, pid_file):
    env = os.environ.copy()
    env.update(env_vars)
    out = open(log_file, "a", buffering=1)
    
    kwargs = {
        "env": env,
        "stdout": out,
        "stderr": subprocess.STDOUT,
        "cwd": str(ROOT),
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP
            | subprocess.DETACHED_PROCESS
        )
    else:
        kwargs["start_new_session"] = True

    proc = subprocess.Popen(cmd, **kwargs)
    pid_file.write_text(str(proc.pid))
    return proc

def main():
    print("Starting bare mode services...")
    # Region A
    start_process(
        [PYTHON, "-m", "uvicorn", "serving.app:app", "--host", "127.0.0.1", "--port", "8001", "--log-level", "warning"],
        {"REGION": "a", "STATE_DIR": "state/region-a", "WARMUP_SECONDS": "6"},
        RUN / "region-a.log",
        RUN / "region-a.pid",
    )
    # Region B
    start_process(
        [PYTHON, "-m", "uvicorn", "serving.app:app", "--host", "127.0.0.1", "--port", "8002", "--log-level", "warning"],
        {"REGION": "b", "STATE_DIR": "state/region-b", "WARMUP_SECONDS": "6"},
        RUN / "region-b.log",
        RUN / "region-b.pid",
    )
    # Edge
    start_process(
        [PYTHON, "-m", "uvicorn", "edge.proxy:app", "--host", "127.0.0.1", "--port", "8080", "--log-level", "warning"],
        {"EDGE_TTL_SECONDS": "5"},
        RUN / "edge.log",
        RUN / "edge.pid",
    )

    print("Waiting for services to be UP (max 10s)...")
    services = [
        ("region-a", 8001, "http://127.0.0.1:8001/healthz"),
        ("region-b", 8002, "http://127.0.0.1:8002/healthz"),
        ("edge", 8080, "http://127.0.0.1:8080/edge/state"),
    ]
    all_up = True
    for name, port, url in services:
        up = False
        for _ in range(10):
            try:
                r = httpx.get(url, timeout=1.0)
                if r.status_code == 200:
                    up = True
                    break
            except Exception:
                pass
            time.sleep(1)
        if up:
            print(f"  {name} (port {port}): UP")
        else:
            print(f"  {name} (port {port}): NOT RESPONDING -- check run/{name}.log")
            all_up = False

    if not all_up:
        print("SOME SERVICES FAILED TO START")
        sys.exit(1)

    try:
        r = httpx.get("http://127.0.0.1:8080/edge/state")
        print(f"Edge state: {r.json()}")
    except Exception as e:
        print(f"Error querying edge state: {e}")

if __name__ == "__main__":
    main()
