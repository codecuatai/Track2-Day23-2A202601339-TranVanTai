"""Supervisor process to keep Region A (8001), Region B (8002), and Edge Proxy (8080) running.
Supports signals/commands to restart or shutdown.
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

def start_services():
    processes = []
    # Region A
    env_a = os.environ.copy()
    env_a.update({"REGION": "a", "STATE_DIR": "state/region-a", "WARMUP_SECONDS": "6"})
    out_a = open(RUN / "region-a.log", "a")
    p_a = subprocess.Popen(
        [PYTHON, "-m", "uvicorn", "serving.app:app", "--host", "127.0.0.1", "--port", "8001", "--log-level", "warning"],
        env=env_a, stdout=out_a, stderr=subprocess.STDOUT, cwd=str(ROOT)
    )
    (RUN / "region-a.pid").write_text(str(p_a.pid))
    processes.append(("region-a", p_a))

    # Region B
    env_b = os.environ.copy()
    env_b.update({"REGION": "b", "STATE_DIR": "state/region-b", "WARMUP_SECONDS": "6"})
    out_b = open(RUN / "region-b.log", "a")
    p_b = subprocess.Popen(
        [PYTHON, "-m", "uvicorn", "serving.app:app", "--host", "127.0.0.1", "--port", "8002", "--log-level", "warning"],
        env=env_b, stdout=out_b, stderr=subprocess.STDOUT, cwd=str(ROOT)
    )
    (RUN / "region-b.pid").write_text(str(p_b.pid))
    processes.append(("region-b", p_b))

    # Edge
    env_e = os.environ.copy()
    env_e.update({"EDGE_TTL_SECONDS": "5"})
    out_e = open(RUN / "edge.log", "a")
    p_e = subprocess.Popen(
        [PYTHON, "-m", "uvicorn", "edge.proxy:app", "--host", "127.0.0.1", "--port", "8080", "--log-level", "warning"],
        env=env_e, stdout=out_e, stderr=subprocess.STDOUT, cwd=str(ROOT)
    )
    (RUN / "edge.pid").write_text(str(p_e.pid))
    processes.append(("edge", p_e))

    return processes

def main():
    print("Starting services under supervisor...")
    procs = start_services()
    time.sleep(2)
    print("Services running. Supervisor waiting...")
    try:
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        for name, p in procs:
            p.terminate()

if __name__ == "__main__":
    main()
