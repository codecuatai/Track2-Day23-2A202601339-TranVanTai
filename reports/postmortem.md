# Postmortem — DR Drill Lab 23

Theo đúng template §4 "Sau Failover: Blameless Postmortem". Blameless: tập trung vào việc cải tiến hệ thống và quy trình tự động hoá, không đổ lỗi cá nhân.

## 1. Timeline (mọi dòng đều có evidence path:line thật)

| ISO time | Sự kiện | Evidence |
|---|---|---|
| 2026-08-25T05:36:14 | Outage bắt đầu (Region A bị netblock) | `chaos/chaos-events.jsonl:8` |
| 2026-08-25T05:36:14 | User đầu tiên bị ảnh hưởng (request timeout) | `reports/drill-2-withdr.jsonl:25` |
| 2026-08-25T05:36:29 | Health check alert (Region A UNHEALTHY sau 3 lần fail) | `reports/health-events.jsonl:1` |
| 2026-08-25T05:36:39 | Operator / Runbook hoàn tất cutover sang Region B | `reports/failover-events.jsonl:5` |
| 2026-08-25T05:36:44 | Resolved (request đầu tiên thành công từ Region B) | `reports/drill-2-withdr.jsonl:39` |

## 2. RTO/RPO đo được vs mục tiêu — Gap Analysis

- **RTO (Recovery Time Objective):**
  - Mục tiêu SLA: 300s (5 phút)
  - Đo được thực tế: **`30.5s`**
  - Gap: Đạt sớm hơn mục tiêu **`269.5s`** (Vượt cam kết SLA).
- **RPO (Recovery Point Objective):**
  - Mục tiêu SLA: 300s (5 phút)
  - Đo được thực tế: **`6.0s`** (`3` documents bị mất trong quá trình failover).
  - Gap: Thấp hơn nhiều so với ngưỡng tối đa 300s (**gap: `294.0s`**).
- **Bước tốn nhiều thời gian nhất trong RTO:**
  - **Health-Check Detection Floor (`15.0s`, chiếm ~49.2% tổng RTO)**.
  - *Lý do:* Để chống hiện tượng flapping (chuyển vùng liên tục khi mạng chập chờn), hệ thống bắt buộc phải chờ 3 chu kỳ probe liên tiếp thất bại ($5s \times 3 = 15s$) trước khi kích hoạt quy trình failover.

## 3. Root Cause Analysis (5 Whys)

1. **Tại sao user nhận lỗi 503 khi gọi API?**
   - Do Region A bị cô lập mạng (`netblock`), không phản hồi request inference.
2. **Tại sao hệ thống không phục vụ từ Region B ngay lập tức?**
   - Vì Region B đang ở trạng thái Standby (`pool_state=warm`, data trống) để tiết kiệm chi phí hạ tầng.
3. **Tại sao mất 15 giây hệ thống mới bắt đầu quá trình khôi phục?**
   - Do cấu hình phát hiện sự cố yêu cầu `threshold=3` lần kiểm tra thất bại để tránh báo động giả.
4. **Tại sao mất 3 documents trong quá trình khôi phục?**
   - Do chu kỳ sao lưu replication chạy mỗi 30s; 3 documents được ingest vào Region A ngay trước thời điểm sự cố và chưa kịp sao lưu sang replica.
5. **Tại sao sau khi DNS cutover vẫn mất thêm 5.3s traffic mới ổn định?**
   - Do cơ chế cache TTL của Edge proxy / DNS giữ định tuyến cũ trong tối đa 5 giây.

## 4. Action Items (Phòng ngừa & Tối ưu hoá)

| # | Action Item | Owner | Deadline | Giảm RTO/RPO bao nhiêu giây |
|---|---|---|---|---|
| 1 | Tối ưu hóa chu kỳ Health Check: giảm `interval` xuống 3s, giữ `threshold=3` | SRE Team | 2026-09-01 | Giảm ~6s RTO (detect floor còn 9s) |
| 2 | Chuyển cơ chế sao lưu sang Continuous WAL Archiving / Change Data Capture (CDC) | Data Eng | 2026-09-15 | Giảm RPO xuống < 1s (Docs lost = 0) |
| 3 | Tối ưu hóa GPU pool warm-up bằng cách pre-load model weights vào GPU VRAM | AI Infra | 2026-09-20 | Giảm ~4s RTO ở bước `4_wait_ready` |
| 4 | Bổ sung Circuit Breaker tự động tại Edge Proxy khi upstream trả về lỗi liên tiếp | DevOps | 2026-10-01 | Giảm ~3s DNS cache lag |

## 5. Ba câu hỏi bắt buộc trả lời

1. **`interval × threshold` của bạn là bao nhiêu giây? Nó chiếm bao nhiêu % RTO?**
   - `interval_s = 5.0s`, `threshold = 3` $\rightarrow$ Detection floor là **`15.0s`**.
   - Con số này chiếm **`49.18%`** tổng RTO đo được (15.0s / 30.5s).
2. **Nếu hạ interval xuống 1s, RTO giảm mấy giây — và bạn trả giá gì (§4 flapping)?**
   - Nếu hạ `interval = 1s` (với `threshold = 3`), detection floor giảm từ 15s xuống **3s** $\rightarrow$ **RTO giảm được 12.0s**.
   - **Cái giá phải trả:** Nguy cơ **flapping** rất cao. Nếu mạng chỉ bị nghẽn cục bộ (jitter / packet loss tạm thời trong 3s), hệ thống sẽ kích hoạt failover nhầm, gây gián đoạn toàn bộ người dùng và tốn chi phí đồng bộ dữ liệu 2 chiều.
3. **Nếu outage kéo dài 6 giờ và region chính mất dữ liệu vĩnh viễn, `docs_lost` của bạn có nghĩa gì với khách hàng?**
   - `docs_lost` là số lượng bản ghi (tickets / transactions / vectors) đã được khách hàng gửi lên nhưng chưa kịp replicate sang Region B trước khi Region A sập hoàn toàn.
   - Với khách hàng, điều này đồng nghĩa với việc họ phải nhập lại hoặc hệ thống phải replay lại dữ liệu của các giao dịch bị mất trong khoảng thời gian cửa sổ RPO (6 giây).
