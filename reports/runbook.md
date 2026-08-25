# Runbook 1 trang — Region chính down (Lab 23)

Runbook chuẩn vận hành lúc 3h sáng cho sự cố Region chính (Region A) bị gián đoạn hoạt động.

| # | Bước | Lệnh | Biết là xong khi | Ai làm |
|---|---|---|---|---|
| 1 | Xác nhận outage | `python chaos/kill_region.py status` | `a.ready=false` (hoặc timeout) 3 lần liên tiếp; `b.alive=true` | SRE On-call |
| 2 | Mở incident + bấm giờ RTO | `python dr/runbook.py --primary a --target b --backend fs` | Timestamp mở incident được ghi vào `reports/runbook-run.jsonl` | SRE On-call |
| 3 | Restore state ở region phụ | `python state/snapshot.py get --region b --backend fs` | `state/region-b/vectors.sqlite` và model weights được restore thành công | Automation / SRE |
| 4 | Scale pool warm→full | `python -c "open('state/region-b/pool_state','w').write('full')"` | `curl http://localhost:8002/readyz` trả HTTP 200 (warm-up xong) | Automation / SRE |
| 5 | DNS/LB cutover | `python -c "open('edge/active_region','w').write('b')"` | `curl http://localhost:8080/edge/state` trả về `active_region: b` | Automation / SRE |
| 6 | Verify golden signals | `curl http://localhost:8080/v1/infer` | 10 request liên tiếp trả về HTTP 200, Error rate = 0%, p95 latency < 500ms | SRE On-call |
| 7 | Đo RTO + postmortem | `python tools/measure_rto.py --loadgen reports/drill-2-withdr.jsonl --target-rto 300` | Output trả về `"valid": true`, `"rto_verdict": "PASS"`, RTO <= 300s | Incident Commander |

---

### Điều kiện Rollback (Failover ngược về Region A)
1. **Điều kiện kỹ thuật:**
   - Region A đã khôi phục hoàn toàn, endpoint `/healthz` và `/readyz` của Region A trả về HTTP 200 ổn định liên tục ít nhất **15 phút**.
   - Dữ liệu mới phát sinh tại Region B trong thời gian sự cố đã được đồng bộ ngược (replicate) về Region A đầy đủ (`docs_lost = 0`).
2. **Quyền quyết định:**
   - **Chỉ Incident Commander hoặc Tech Lead** có thẩm quyền ra quyết định kích hoạt rollback thủ công sau khi họp kiểm tra golden signals.
   - **Tuyệt đối không bật rollback tự động 100% (full-auto)** nhằm ngăn chặn hiện tượng flapping (đảo chiều liên tục giữa 2 region khi mạng không ổn định).
