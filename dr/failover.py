"""BƯỚC 3b — SINH VIÊN VIẾT. Cutover sang region phụ.

5 bước, THỨ TỰ QUAN TRỌNG (§2 Kiến Trúc Tham Chiếu: DNS/LB, compute, state là 3 lớp riêng):
  1_verify_target    — /v1/state của region phụ: weights? vector count? pool_state?
  2_restore_snapshot — gọi state/snapshot.py get + state/snapshot.py rpo()
                       Log BẮT BUỘC: rpo_seconds, docs_lost, embed_model_version.
                       (§3: "backup index nhưng quên backup embedding model version
                        -> index không tương thích khi restore")
  3_scale_pool       — ghi "full" vào state/region-<t>/pool_state (warm -> full)
  4_wait_ready       — POLL /readyz tới khi 200. Region phụ có WARMUP_SECONDS —
                       đây là GPU pool warm-up của §4, nó nằm trong RTO của bạn.
  5_dns_cutover      — ghi region đích vào edge/active_region

BẪY: nếu bạn đổi edge/active_region TRƯỚC bước 4, user sẽ nhận 503 từ CẢ HAI region
và RTO của bạn dài hơn, không ngắn hơn. Nếu bước 4 timeout -> ABORT, KHÔNG cutover.

Mỗi bước ghi 1 dòng vào reports/failover-events.jsonl với ts + step.
Không có dòng 5_dns_cutover = tools/measure_rto.py không tìm được t_cutover = mất điểm.

Chạy:  python dr/failover.py --target b --backend fs
"""
import argparse
import json
import pathlib
import sys
import time

import httpx

sys.path.insert(0, ".")
from state import snapshot  # noqa: E402

URL = {"a": "http://127.0.0.1:8001", "b": "http://127.0.0.1:8002"}
LOG = pathlib.Path("reports/failover-events.jsonl")


def emit(**kw) -> dict:
    """Append 1 dòng JSONL có ts + iso vào LOG, và print ra stdout."""
    LOG.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "ts": time.time(),
        "iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
        **kw,
    }
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    print("FAILOVER", json.dumps(rec))
    return rec


def state_of(region: str) -> dict:
    """Lấy thông tin state của 1 region qua HTTP hoặc fallback file."""
    try:
        r = httpx.get(f"{URL[region]}/v1/state", timeout=2.0)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    d = pathlib.Path(f"state/region-{region}")
    pool_file = d / "pool_state"
    pool_state = pool_file.read_text().strip() if pool_file.exists() else "unknown"
    weights = (d / "weights" / "model.bin").exists()
    return {"region": region, "pool_state": pool_state, "weights": weights}


def failover(target: str, backend: str, wait: float = 60.0) -> dict:
    """Thực hiện 5 bước failover đúng thứ tự."""
    primary = "a" if target == "b" else "b"

    # Bước 1: 1_verify_target
    target_state = state_of(target)
    emit(step="1_verify_target", target=target, backend=backend, target_state=target_state)

    # Bước 2: 2_restore_snapshot
    snap_meta = snapshot.get(target, backend)
    prim_db = pathlib.Path(f"state/region-{primary}/vectors.sqlite")
    rest_db = pathlib.Path(f"state/region-{target}/vectors.sqlite")
    rpo_info = snapshot.rpo(prim_db, rest_db)
    rpo_s = rpo_info.get("rpo_seconds")
    docs_lost = rpo_info.get("docs_lost")
    embed_ver = snap_meta.get("embed_model_version")
    emit(
        step="2_restore_snapshot",
        target=target,
        rpo_seconds=rpo_s,
        docs_lost=docs_lost,
        embed_model_version=embed_ver,
        snapshot_at=snap_meta.get("snapshot_at"),
    )

    # Bước 3: 3_scale_pool
    pool_file = pathlib.Path(f"state/region-{target}/pool_state")
    pool_file.parent.mkdir(parents=True, exist_ok=True)
    pool_file.write_text("full")
    emit(step="3_scale_pool", target=target, pool_state="full")

    # Bước 4: 4_wait_ready
    t0 = time.time()
    ready = False
    deadline = t0 + wait
    while time.time() < deadline:
        try:
            r = httpx.get(f"{URL[target]}/readyz", timeout=1.5)
            if r.status_code == 200:
                ready = True
                break
        except Exception:
            pass
        time.sleep(0.2)

    waited_s = round(time.time() - t0, 2)
    if not ready:
        emit(step="4_wait_ready", target=target, waited_s=waited_s, ready=False, error="timeout")
        # ABORT: không cutover nếu target chưa ready!
        return {
            "ok": False,
            "step": "4_wait_ready",
            "error": "target_not_ready",
            "waited_s": waited_s,
            "target": target,
        }

    emit(step="4_wait_ready", target=target, waited_s=waited_s, ready=True)

    # Bước 5: 5_dns_cutover
    edge_active = pathlib.Path("edge/active_region")
    edge_active.parent.mkdir(parents=True, exist_ok=True)
    edge_active.write_text(target)
    emit(step="5_dns_cutover", active_region=target, ok=True)

    return {
        "ok": True,
        "target": target,
        "backend": backend,
        "rpo_seconds": rpo_s,
        "docs_lost": docs_lost,
        "embed_model_version": embed_ver,
        "waited_s": waited_s,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--target", default="b", choices=["a", "b"])
    p.add_argument("--backend", default="fs", choices=["fs", "minio"])
    p.add_argument("--wait", type=float, default=60)
    a = p.parse_args()
    print(json.dumps(failover(a.target, a.backend, a.wait), indent=2))
