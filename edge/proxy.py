"""Edge proxy = lớp "DNS / Global LB" giả lập. [CÓ SẴN — không sửa]

Không cần Route53: "DNS record" ở đây là file text edge/active_region chứa "a" hoặc "b".
Proxy đọc lại file này ở MỖI request -> cutover = ghi 1 byte, không cần restart.
TTL giả lập bằng EDGE_TTL_SECONDS (mặc định 5s) để sinh viên thấy §2 "DNS cache
không tôn trọng TTL -> cộng thêm giây vào RTO".
"""
import os
import pathlib
import time

import httpx
from fastapi import FastAPI, Response, Body
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

ACTIVE_FILE = pathlib.Path(os.environ.get("ACTIVE_REGION_FILE", "edge/active_region"))
TTL = float(os.environ.get("EDGE_TTL_SECONDS", "5"))
TIMEOUT = float(os.environ.get("EDGE_TIMEOUT_SECONDS", "2"))
UPSTREAM = {"a": os.environ.get("REGION_A_URL", "http://127.0.0.1:8001"),
            "b": os.environ.get("REGION_B_URL", "http://127.0.0.1:8002")}

app = FastAPI(title="edge-proxy")
_cache = {"region": None, "at": 0.0}

static_dir = pathlib.Path("static")
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


def resolve() -> str:
    """Giả lập DNS cache: chỉ đọc lại file sau khi TTL hết hạn."""
    now = time.time()
    if _cache["region"] is None or now - _cache["at"] >= TTL:
        _cache["region"] = ACTIVE_FILE.read_text().strip() if ACTIVE_FILE.exists() else "a"
        _cache["at"] = now
    return _cache["region"]


@app.get("/", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
def get_dashboard():
    template_path = pathlib.Path("templates/dashboard.html")
    if template_path.exists():
        return HTMLResponse(content=template_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Disaster Recovery Dashboard</h1>")


@app.get("/api/dashboard/status")
def get_dashboard_status():
    status = {
        "edge": edge_state(),
        "regions": {
            "a": {"alive": False, "ready": False, "vectors": 0, "poolState": "unknown", "weights": False, "reasons": []},
            "b": {"alive": False, "ready": False, "vectors": 0, "poolState": "unknown", "weights": False, "reasons": []}
        }
    }
    with httpx.Client(timeout=1.0) as client:
        for reg_key in ["a", "b"]:
            base_url = UPSTREAM[reg_key]
            try:
                r_health = client.get(f"{base_url}/healthz")
                status["regions"][reg_key]["alive"] = (r_health.status_code == 200)
            except Exception:
                status["regions"][reg_key]["alive"] = False

            try:
                r_ready = client.get(f"{base_url}/readyz")
                status["regions"][reg_key]["ready"] = (r_ready.status_code == 200)
                if r_ready.status_code in (200, 503):
                    body = r_ready.json()
                    status["regions"][reg_key]["reasons"] = body.get("reasons", [])
                    status["regions"][reg_key]["poolState"] = body.get("pool_state", "unknown")
                    status["regions"][reg_key]["vectors"] = body.get("vectors", {}).get("count", 0)
            except Exception:
                status["regions"][reg_key]["ready"] = False

            try:
                r_state = client.get(f"{base_url}/v1/state")
                if r_state.status_code == 200:
                    b_state = r_state.json()
                    status["regions"][reg_key]["weights"] = b_state.get("weights", False)
                    status["regions"][reg_key]["poolState"] = b_state.get("pool_state", status["regions"][reg_key]["poolState"])
                    status["regions"][reg_key]["vectors"] = b_state.get("count", status["regions"][reg_key]["vectors"])
            except Exception:
                pass

    return status


@app.post("/api/dashboard/failover")
def dashboard_failover(payload: dict = Body(...)):
    target = payload.get("region", "a").lower()
    if target not in ("a", "b"):
        return Response(status_code=400, content='{"error": "Invalid region"}')
    ACTIVE_FILE.parent.mkdir(parents=True, exist_ok=True)
    ACTIVE_FILE.write_text(target)
    return {"status": "ok", "target_region": target}


@app.get("/v1/infer")
def infer(q: str = "hoa don thang 7", response: Response = None):
    region = resolve()
    t0 = time.time()
    try:
        with httpx.Client(timeout=TIMEOUT) as c:
            r = c.get(f"{UPSTREAM[region]}/v1/infer", params={"q": q})
        response.status_code = r.status_code
        return {"edge_region": region, "upstream_status": r.status_code,
                "edge_latency_ms": round((time.time() - t0) * 1000, 1), **r.json()}
    except Exception as e:  # region chết: refused (stop) hoac timeout (netblock)
        response.status_code = 503
        return {"edge_region": region, "upstream_status": None,
                "error": type(e).__name__,
                "edge_latency_ms": round((time.time() - t0) * 1000, 1)}


@app.get("/edge/state")
def edge_state():
    return {"active_region": resolve(), "ttl_seconds": TTL,
            "cache_age_s": round(time.time() - _cache["at"], 2)}
