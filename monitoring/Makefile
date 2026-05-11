# Krip 모니터링 스택 — Makefile
#
# 위치: monitoring/Makefile (자체 self-contained)
# 호출 패턴:
#   make -C monitoring up        # 어디서든 (-C 는 make 의 chdir 플래그)
#   cd monitoring && make up     # 디렉토리 진입 후
#
# Path 처리: -f 첫 번째 파일이 ../docker-compose.yml 이라 docker-compose 의
# project_directory = 프로젝트 루트로 결정. 양쪽 compose 의 모든 volume path 가
# 프로젝트 루트 기준으로 정상 해결됨.

COMPOSE_FILES = -f ../docker-compose.yml -f docker-compose.monitoring.yml
COMPOSE = docker-compose --env-file .env $(COMPOSE_FILES)

.PHONY: help up up-prod up-build down logs ps reload net-create health metrics logql

help:
	@echo "Krip 모니터링 스택 명령 (monitoring/ 에서 직접 또는 'make -C monitoring <cmd>'):"
	@echo "  make up          — dev 부팅 (node-exporter 제외, macOS 호환)"
	@echo "  make up-prod     — 운영 Linux 부팅 (linux-host profile 활성, node-exporter 포함)"
	@echo "  make up-build    — backend 이미지 재빌드 후 부팅 (코드 변경 시)"
	@echo "  make down        — 전체 종료 (볼륨 유지)"
	@echo "  make logs        — 컨테이너 로그 tail (Ctrl+C 종료)"
	@echo "  make ps          — 컨테이너 상태"
	@echo "  make reload      — Prometheus config hot reload (룰 변경 시)"
	@echo "  make health      — backend health endpoint 3종 검증"
	@echo "  make metrics     — backend:9090/metrics 샘플 조회"
	@echo "  make logql       — Loki / Promtail ready 검증 + 최근 라벨 목록"
	@echo "  make net-create  — monitoring-network 생성 (사전 1회, up 이 자동 호출)"

net-create:
	@docker network ls --filter name=monitoring-network --format "{{.Name}}" | grep -q monitoring-network \
		|| docker network create monitoring-network

up: net-create
	$(COMPOSE) up -d

up-prod: net-create
	COMPOSE_PROFILES=linux-host $(COMPOSE) up -d

up-build: net-create
	$(COMPOSE) up -d --build backend

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f --tail=50

ps:
	$(COMPOSE) ps

reload:
	@docker exec krip-prometheus wget -q --post-data="" -O- http://prometheus:9090/-/reload \
		&& echo "Prometheus reloaded"

health:
	@echo "=== /health (liveness) ==="
	@curl -sw "  HTTP %{http_code}\n" http://localhost:8000/health
	@echo "=== /health/deep (4-ping) ==="
	@curl -sw "  HTTP %{http_code}\n" http://localhost:8000/health/deep
	@echo "=== /ready (deep + AI models) ==="
	@curl -sw "  HTTP %{http_code}\n" http://localhost:8000/ready

metrics:
	@docker exec krip-prometheus wget -qO- http://backend:9090/metrics 2>/dev/null \
		| grep -E "^http_requests_total|^http_request_duration_seconds_count|^auth_failures_total" | head -10

logql:
	@echo "=== Loki ready ==="
	@docker exec krip-prometheus wget -qO- http://loki:3100/ready 2>/dev/null && echo "" || echo "FAIL"
	@echo "=== Promtail ready ==="
	@docker exec krip-prometheus wget -qO- http://promtail:9080/ready 2>/dev/null && echo "" || echo "FAIL"
	@echo "=== Loki 라벨 목록 ==="
	@docker exec krip-prometheus wget -qO- 'http://loki:3100/loki/api/v1/labels' 2>/dev/null | python3 -m json.tool
	@echo "=== app=krip-backend 라벨 값 (env / node_id / level) ==="
	@docker exec krip-prometheus wget -qO- 'http://loki:3100/loki/api/v1/label/level/values' 2>/dev/null | python3 -m json.tool
