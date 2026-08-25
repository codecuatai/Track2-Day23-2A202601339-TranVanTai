PYTHON ?= python

.PHONY: seed up-bare down-bare drill-baseline drill-dr rto test clean

seed:
	$(PYTHON) state/seed_vectors.py --region a --docs 200
	$(PYTHON) state/seed_vectors.py --region b --docs 0 --weights-mb 0
	$(PYTHON) -c "open('edge/active_region', 'w').write('a')"

up-bare:
	bash scripts/up_bare.sh

down-bare:
	bash scripts/down_bare.sh

# Bước 2: baseline không DR — dùng đúng script sinh viên sẽ chạy tay
drill-baseline:
	$(PYTHON) loadgen/traffic.py --duration 40 --rps 2 --out reports/drill-1-nodr.jsonl &
	sleep 8; $(PYTHON) chaos/kill_region.py --region a --mode netblock --mock
	wait

# Bước 4: replay attack sau khi contain xong
# replicate.py phai chay TRUOC va co it nhat 1 chu ky xong, khong thi failover.py
# se chet o buoc 2_restore_snapshot vi chua tung co snapshot nao duoc put.
drill-dr:
	$(PYTHON) state/ingest.py --region a --rate 0.5 --duration 150 &
	$(PYTHON) state/replicate.py --every 30 --duration 150 --backend fs &
	sleep 5
	$(PYTHON) loadgen/traffic.py --duration 100 --rps 2 --out reports/drill-2-withdr.jsonl &
	$(PYTHON) dr/health_checker.py --interval 5 --threshold 3 --duration 100 --out reports/health-events.jsonl &
	sleep 12; $(PYTHON) chaos/kill_region.py --region a --mode netblock --mock

rto:
	$(PYTHON) tools/measure_rto.py --loadgen reports/drill-2-withdr.jsonl --target-rto 300

test:
	$(PYTHON) -m pytest tests/ -v

clean:
	bash scripts/down_bare.sh 2>/dev/null || true
	rm -rf state/region-a state/region-b state/_replica run
	rm -f reports/*.jsonl reports/*.json chaos/chaos-events.jsonl
