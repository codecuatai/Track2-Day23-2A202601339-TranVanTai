# Runbook 1 trang — Region chính down (Lab 23)

Runbook chuẩn vận hành lúc 3h sáng cho sự cố Region chính (Region A) bị gián đoạn hoạt động.

| # | Bước | Lệnh | Biết là xong khi | Ai làm |
|---|---|---|---|---|
| 1 | Xác nhận outage | `curl http://localhost:8001/readyz` và `curl http://localhost:8002/healthz` | Region A timeout/không 200, Region B `/healthz` trả 200; xác nhận lại 3 lần | SRE On-call |
| 2 | Mở incident + bấm giờ RTO | `python dr/runbook.py --primary a --target b --backend fs` | Hiện prompt `Xác nhận kích hoạt failover...`; operator gõ `y`, rồi có dòng `thong_bao_incident` trong `reports/runbook-run.jsonl` | SRE On-call |
| 3 | Restore state ở region phụ | `Get-Content reports/failover-events.jsonl -Tail 5` | Dòng `2_restore_snapshot` có `rpo_seconds`, `docs_lost`, `embed_model_version`; bước này do cùng một lần chạy runbook thực hiện | Automation / SRE |
| 4 | Scale pool warm→full và chờ ready | `curl http://localhost:8002/readyz` | Dòng `4_wait_ready` có `ready:true`, sau đó endpoint trả HTTP 200; **không ghi tay** `pool_state` | Automation / SRE |
| 5 | DNS/LB cutover | `curl http://localhost:8080/edge/state` | Dòng `5_dns_cutover` chỉ xuất hiện sau bước 4; `active_region: b`; **không ghi tay** `edge/active_region` | Automation / SRE |
| 6 | Verify golden signals | `Get-Content reports/runbook-run.jsonl -Tail 2` | Dòng `verify_golden_signals` có `total_requests:10`, `errors:0`, `error_rate:0.0`, `p95_latency_ms < 500`, `ok:true`; runbook tự chờ hết Edge TTL trước khi kiểm tra | SRE On-call |
| 7 | Đo RTO + đóng incident | `python tools/measure_rto.py --loadgen reports/drill-2-withdr.jsonl --target-rto 300` | Output có `"valid": true`, `"rto_verdict": "PASS"`; dòng `post_incident` là `RESOLVED` (không phải `DEGRADED`) | Incident Commander |

---

### Điều kiện Rollback (Failover ngược về Region A)
1. **Điều kiện kỹ thuật:**
   - Region A đã khôi phục hoàn toàn, endpoint `/healthz` và `/readyz` của Region A trả về HTTP 200 ổn định liên tục ít nhất **15 phút**.
   - Dữ liệu mới phát sinh tại Region B trong thời gian sự cố đã được đồng bộ ngược (replicate) về Region A đầy đủ (`docs_lost = 0`).
2. **Quyền quyết định:**
   - **Chỉ Incident Commander hoặc Tech Lead** có thẩm quyền ra quyết định kích hoạt rollback thủ công sau khi họp kiểm tra golden signals.
   - **Tuyệt đối không bật rollback tự động 100% (full-auto)** nhằm ngăn chặn hiện tượng flapping (đảo chiều liên tục giữa 2 region khi mạng không ổn định).
