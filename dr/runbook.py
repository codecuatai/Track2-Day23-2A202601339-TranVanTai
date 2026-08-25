"""BƯỚC 3c — SINH VIÊN VIẾT. Tự động hoá runbook §4 "Runbook: Region Chính Down".

7 bước trên slide, mỗi bước 1 dòng log có ts. Log này CHÍNH LÀ timeline của postmortem.
  1 xac_nhan_outage          — probe cả 2 region, đừng tin 1 lần fail (dùng nhiều lần
                              hoặc gọi health_checker.probe nếu đã viết xong 3a)
  2 thong_bao_incident       — ts của dòng này là mốc "operator biết tin", LUÔN LUÔN
                              SAU t_outage trong chaos-events (không thể trùng — operator
                              không thể biết ngay giây outage xảy ra). Ghi cả 2 ts vào
                              log để postmortem tính được "độ trễ thông báo".
  3 scale_gpu_pool           — gọi HÀM `failover.failover(...)` MỘT LẦN DUY NHẤT. Hàm
                              đó tự làm đủ 5 bước con (verify/restore/scale/wait/cutover)
                              và tự ghi log riêng vào reports/failover-events.jsonl.
  4 verify_state_replica     — KHÔNG gọi lại failover — chỉ ĐỌC kết quả (vector count +
                              weights ở region phụ) từ dict mà bước 3 trả về, để log vào
                              runbook-run.jsonl cho postmortem đọc 1 chỗ duy nhất.
  5 dns_cutover              — cũng chỉ đọc lại: kết quả cutover có ok hay không.
  6 verify_golden_signals    — 10 request thật vào region phụ: p95 latency + error rate
  7 post_incident            — elapsed_s + lệnh đo RTO

BÁN TỰ ĐỘNG, KHÔNG FULL-AUTO (§4: "failover đầu tiên nên là bán tự động — alert +
1-click confirm — tránh flapping gây failover 2 chiều liên tục"). Mặc định phải hỏi
người vận hành confirm; --auto chỉ dùng trong CI/khi chấm điểm.

Chạy:  python dr/runbook.py --primary a --target b --backend fs
"""
import argparse
import json
import pathlib
import sys
import time

import httpx

sys.path.insert(0, ".")
from dr import failover as fo  # noqa: E402

LOG = pathlib.Path("reports/runbook-run.jsonl")
URL = {"a": "http://127.0.0.1:8001", "b": "http://127.0.0.1:8002"}


def step(n: int, name: str, **kw) -> dict:
    """Ghi 1 dòng {ts, iso, step, name, ...} vào LOG và in ra stdout."""
    LOG.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "ts": time.time(),
        "iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
        "step": n,
        "name": name,
        **kw,
    }
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    print(f"RUNBOOK [Bước {n}: {name}]", json.dumps(rec))
    return rec


def confirm(auto: bool, msg: str) -> bool:
    """auto=True -> True; ngược lại hỏi y/N."""
    if auto:
        return True
    try:
        ans = input(f"{msg} [y/N]: ").strip().lower()
        return ans in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False


def run(primary: str, target: str, backend: str, auto: bool) -> dict:
    """Thực hiện đầy đủ 7 bước của runbook."""
    t_start = time.time()

    # Bước 1: xac_nhan_outage
    p_ready = False
    try:
        r = httpx.get(f"{URL[primary]}/readyz", timeout=1.5)
        p_ready = (r.status_code == 200)
    except Exception:
        p_ready = False

    t_alive = False
    try:
        r = httpx.get(f"{URL[target]}/healthz", timeout=1.5)
        t_alive = (r.status_code == 200)
    except Exception:
        t_alive = False

    step(1, "xac_nhan_outage", primary=primary, target=target,
         primary_ready=p_ready, target_alive=t_alive)

    if not confirm(auto, f"Xác nhận kích hoạt failover từ {primary} -> {target}?"):
        print("Huỷ failover theo yêu cầu của operator.")
        return {"ok": False, "reason": "aborted_by_operator"}

    # Bước 2: thong_bao_incident
    step(2, "thong_bao_incident", incident_level="P1",
         msg=f"Operator phat hien su co tren region-{primary}, khoi dong dong ho failover sang region-{target}")

    # Bước 3: scale_gpu_pool (gọi failover.failover EXACTLY ONCE)
    fo_res = fo.failover(target=target, backend=backend, wait=60.0)
    step(3, "scale_gpu_pool", target=target, failover_result=fo_res)

    if not fo_res.get("ok"):
        return {"ok": False, "step": 3, "error": "failover_failed", "failover_result": fo_res}

    # Bước 4: verify_state_replica
    step(4, "verify_state_replica",
         rpo_seconds=fo_res.get("rpo_seconds"),
         docs_lost=fo_res.get("docs_lost"),
         embed_model_version=fo_res.get("embed_model_version"))

    # Bước 5: dns_cutover
    step(5, "dns_cutover", active_region=target, ok=fo_res.get("ok"))

    # Bước 6: verify_golden_signals (10 request thật vào edge)
    latencies = []
    errors = 0
    with httpx.Client(timeout=3.0) as client:
        for i in range(10):
            t_req = time.time()
            try:
                r = client.get("http://127.0.0.1:8080/v1/infer", params={"q": f"kiem tra {i}"})
                if r.status_code != 200:
                    errors += 1
            except Exception:
                errors += 1
            latencies.append((time.time() - t_req) * 1000)
            time.sleep(0.1)

    latencies.sort()
    p95 = round(latencies[int(len(latencies) * 0.95)], 1) if latencies else 0
    step(6, "verify_golden_signals", total_requests=10, errors=errors,
         error_rate=round(errors / 10.0, 2), p95_latency_ms=p95)

    # Bước 7: post_incident
    elapsed = round(time.time() - t_start, 2)
    step(7, "post_incident", status="RESOLVED", elapsed_seconds=elapsed,
         command="python tools/measure_rto.py --loadgen reports/drill-2-withdr.jsonl --target-rto 300")

    return {
        "ok": True,
        "primary": primary,
        "target": target,
        "backend": backend,
        "rpo_seconds": fo_res.get("rpo_seconds"),
        "docs_lost": fo_res.get("docs_lost"),
        "elapsed_seconds": elapsed,
        "p95_latency_ms": p95,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--primary", default="a")
    p.add_argument("--target", default="b")
    p.add_argument("--backend", default="fs", choices=["fs", "minio"])
    p.add_argument("--auto", action="store_true")
    a = p.parse_args()
    print(json.dumps(run(a.primary, a.target, a.backend, a.auto), indent=2))
