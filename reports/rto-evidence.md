# RTO/RPO Evidence — Lab 23

Quy tắc duy nhất: mỗi con số ở đây phải trỏ được về **một dòng log thật**
(`đường/dẫn.jsonl:số_dòng`). `pytest tests/test_rto_evidence.py` sẽ mở từng file ra kiểm tra.
Con số không có evidence = trượt, bất kể các phần khác.

## 1. Drill 1 — không có DR (baseline)

| Chỉ số | Giá trị | Cách đo | Evidence |
|---|---|---|---|
| t_outage | `2026-08-25T05:16:01` | chaos kill | `chaos/chaos-events.jsonl:2` |
| Request fail đầu tiên | `+0.0s` | dòng `ok:false` đầu tiên sau t_outage | `reports/drill-1-nodr.jsonl:17` |
| Request thành công sau đó | không có | không có dòng `ok:true` nào sau t_outage | `reports/drill-1-nodr.jsonl:31` |
| RTO | `NO_RECOVERY` | `tools/measure_rto.py` | `reports/drill-1-nodr.jsonl:17` |

## 2. Drill 2 — có DR

| Mốc | +giây từ t_outage | Cách đo | Evidence |
|---|---|---|---|
| t_outage (mốc 0) | 0.0s | `action:kill` | `chaos/chaos-events.jsonl:8` |
| User thấy lỗi đầu tiên | +0.1s | dòng `ok:false` đầu | `reports/drill-2-withdr.jsonl:25` |
| Health check phát hiện | +14.9s | `to:UNHEALTHY, region:a` | `reports/health-events.jsonl:1` |
| Snapshot restore xong | +18.6s | `step:2_restore_snapshot` | `reports/failover-events.jsonl:2` |
| Region phụ ready | +25.2s | `step:4_wait_ready` | `reports/failover-events.jsonl:4` |
| DNS cutover | +25.2s | `step:5_dns_cutover` | `reports/failover-events.jsonl:5` |
| **RTO đo được** | 30.5s | dòng `ok:true` đầu sau lỗi | `reports/drill-2-withdr.jsonl:39` |

| Chỉ số | Đo được | Mục tiêu (slide §1) | Verdict |
|---|---|---|---|
| RTO — Inference API | `30.5s` | 300s (5 phút) | PASS |
| RPO — Vector DB | `6.0s` / `3` doc | 300s (5 phút) | PASS |

## 3. RTO của tôi gồm những gì (bắt buộc — đây là phần chấm điểm hiểu bài)

| Thành phần | Giây | Nó đến từ đâu | Giảm được bằng cách nào |
|---|---|---|---|
| Health-check detect floor | 15.0s | `interval_s × threshold` trong `reports/health-events.jsonl:1` | Giảm `interval_s` (ví dụ từ 5s xuống 2s) hoặc giảm `threshold` (tăng nguy cơ flapping) |
| Snapshot restore | 0.01s | 2_restore → 3_scale trong `reports/failover-events.jsonl:2` | Sử dụng local NVMe SSD tốc độ cao, snapshot vi phân/WAL thay vì full backup |
| GPU pool warm-up | 6.62s | `waited_s` ở `4_wait_ready` trong `reports/failover-events.jsonl:4` | Pre-load model weights vào GPU VRAM, duy trì pool ở trạng thái warm cao hơn |
| DNS/LB TTL cache | 5.3s | t_recovered − t_cutover (`reports/drill-2-withdr.jsonl:39` - `reports/failover-events.jsonl:5`) | Giảm DNS/Proxy TTL (ví dụ từ 5s xuống 1s) hoặc dùng Anycast routing BGP |
