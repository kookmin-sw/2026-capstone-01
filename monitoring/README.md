# Krip 모니터링 시스템 구조

Krip 백엔드의 옵저버빌리티 스택. **메트릭(Prometheus) + 로그(Loki) + Synthetic 프로브(Blackbox)** 를 Grafana 한 곳에서 관측한다. 

두 개의 도커 네트워크 (`krip-network`, `monitoring-network`) 로 backend / 데이터스토어 / 모니터링 컴포넌트를 분리·연결.

### 스케일 한눈에 보기

| 항목 | 값 |
| --- | --- |
| 모니터링 컴포넌트 | **10** — Prometheus · Grafana · Loki · Promtail · Blackbox + exporter 5종 (node · postgres · mongo · redis × 2) |
| Prometheus 스크레이프 잡 | **11** (self 3 · DB 4 · node · backend · blackbox 2) |
| Grafana 대시보드 | **7** (provisioning 자동 등록) |
| 메트릭 보존 | Prometheus tsdb **15일** |
| 로그 보존 | Loki filesystem **14일** |
| PII 마스킹 | Promtail ingestion 단에서 **4종 강제** (email · JWT · 휴대폰 · 주민번호) |

---

## 1. 디렉토리 레이아웃

```
monitoring/
├── docker-compose.monitoring.yml   # 10개 모니터링 컴포넌트 정의
├── Makefile                        # up / up-prod / reload / health / metrics / logql
├── .env(.example)                  # ENV / NODE_ID / Grafana 비번 / DB 자격증명
├── prometheus/
│   └── prometheus.yml              # scrape 잡 11개 정의
├── blackbox/
│   └── blackbox.yml                # http_2xx (strict) / http_alive (관대) 두 모듈
├── loki/
│   ├── loki-config.yml             # monolithic, filesystem, 14일 retention
│   └── promtail-config.yml         # 현재 로그 + 회전 .gz 양쪽 tail
└── grafana/
    └── provisioning/
        ├── datasources/            # Prometheus / Loki 자동 등록
        └── dashboards/             # 7개 대시보드 JSON 자동 import
```

---

## 2. 데이터 흐름

```
        ┌─────────────────────────────────────────────────────────┐
        │                      Backend                            │
        │                     (FastAPI)                           │
        │                                                         │
        │  :8000  /health, /health/deep, /ready                   │
        │  :9090  /metrics  (prometheus_client.start_http_server) │
        │  logs → backend/logs/app.log (+ .gz 회전)                │
        └────────────────────────┬────────────────────────────────┘
                                 │
         ┌───────────────────────┼───────────────────────┐
         │                       │                       │
         ▼ scrape                ▼ scrape                ▼ tail
┌────────────────────┐   ┌────────────────────┐  ┌────────────────┐
│   Prometheus       │   │ Blackbox exporter  │  │   Promtail     │
│   :9090            │◄──┤ :9115              │  │   :9080        │
│   tsdb 15d         │   │ (Prometheus 가 호출) │  │  PII 마스킹 4개  │
└─────────┬──────────┘   └────────────────────┘  └────────┬───────┘
          │                                               │ push
          │                              ┌────────────────▼────────┐
          │                              │   Loki :3100            │
          │                              │   tsdb filesystem 14일   │ 
          │                              └─────────┬───────────────┘
          │                                        │
          ▼                                        ▼
       ┌──────────────────────────────────────────────────┐
       │             Grafana :3001 (호스트)                 │
       │                   대시보드                         │
       └──────────────────────────────────────────────────┘

  (주변 exporter)
  postgres-exporter:9187   ──┐
  mongodb-exporter:9216      ├── Prometheus scrape
  redis-exporter-hot:9121    │   (krip-network + monitoring-network 양쪽 가입)
  redis-exporter-dedupe:9121 ┘
  node-exporter:9100       ── 운영 Linux 호스트 전용 (linux-host profile)
```

---

## 3. 컴포넌트별 역할

### 3.1 Prometheus (`prom/prometheus:v2.55.1`)

- 시계열 메트릭 수집 + 저장 + (추후) 알림 평가.
- 보존: `--storage.tsdb.retention.time=15d` (≈ 2-3GB 예상).
- `--enable-feature=expand-external-labels` 로 `${ENV}` 를 external_labels 에 치환.
- `--web.enable-lifecycle` 로 `make reload` 시 hot reload 가능.
- 헬스체크: `wget http://localhost:9090/-/healthy`.

**스크레이프 잡 목록** (`prometheus/prometheus.yml`):

| Job | 대상 | 주기 | 비고 |
|---|---|---|---|
| `prometheus-self` | prometheus:9090 | 15s | 자기 자신 |
| `loki-self` | loki:3100 | 15s | LokiIngestionStalled 룰 의존 |
| `promtail-self` | promtail:9080 | 15s | PromtailDropping 룰 의존 |
| `node` | node-exporter:9100 | 15s | 운영 Linux 만 활성 |
| `postgres` | postgres-exporter:9187 | 15s | pg_stat_*, max_connections |
| `redis-hot` | redis-exporter-hot:9121 | 15s | `db="hot"` 라벨 부착 |
| `redis-dedupe` | redis-exporter-dedupe:9121 | 15s | `db="dedupe"` 라벨 부착 |
| `mongo` | mongodb-exporter:9216 | 15s | op_latencies / connections |
| `blackbox-external` | 5개 외부 API | 60s | `http_alive` 모듈, rate limit 회피 |
| `backend` | backend:9090/metrics | 15s | 애플리케이션 메트릭 |
| `blackbox-internal` | /health, /health/deep, /ready | 30s | `http_2xx` strict |

**카디널리티 통제** — Redis exporter 의 server-side latency 시리즈 (~400 시리즈) 는
backend 의 client-side `redis_command_duration_seconds` 와 의미 중복 + 폭증 hotspot
이라 `metric_relabel_configs` 에서 `redis_(commands_latencies_usec|latency_percentiles_usec|latency_spike).*` drop.

### 3.2 Grafana (`grafana/grafana:11.3.1`)

- 호스트 포트: **3001 → 컨테이너 3000**.
- admin 비번은 `.env` 의 `GRAFANA_ADMIN_PASSWORD` 강제 (`:?` 미설정 시 부팅 거부).
- 익명 접속 / 사용자 가입 모두 비활성.
- 데이터소스 / 대시보드 모두 provisioning 으로 자동 등록 — UI 수정은 가능하지만
  `editable: false` 라 변경 사항은 휘발성.

**프로비저닝 대시보드 7종** (`grafana/provisioning/dashboards/`):

| UID | 제목 | 패널 수 | 태그 |
|---|---|---|---|
| `krip-overview` | Krip 시스템 종합 | 7 | overview |
| `krip-api` | API 트래픽 (RED) | 7 | api, red |
| `krip-ai-pipeline` | AI 파이프라인 | 9 | ai |
| `krip-chat-domain` | 채팅 도메인 (Chat) | 18 | chat |
| `krip-infra-stores` | 데이터스토어 (Infra Stores) | 17 | infra, db |
| `krip-workers` | 워커 (Workers) | 10 | workers |
| `krip-system-resources` | 시스템 리소스 (Host) | 8 | system, host |

### 3.3 Blackbox exporter (`prom/blackbox-exporter:v0.25.0`)

두 모듈로 분리:

- **`http_2xx`** — strict. 200 만 success. `/health`, `/health/deep`, `/ready` 용.
  503 이면 fail 처리.
- **`http_alive`** — 관대. 200/201/204/301/302/304/400/401/403/404 모두 alive 인정.
  외부 API 의 root GET 이 4xx 인 케이스가 정상이라 "DNS + TLS + 응답 수신" 만 검증.
  `fail_if_not_ssl: true` 로 HTTPS 강제.

**모니터링 대상 외부 의존성** (5개): NCloud Object Storage, Papago, Gemini, FCM, Google OAuth.

알림 발화 시 blackbox 시리즈가 0 이면 외부 원인 → 5xx 의 "우리 코드 버그 vs 외부 다운"
1차 분리에 사용. MTTD 단축이 목적.

### 3.4 Loki (`grafana/loki:3.3.1`)

- 단일 인스턴스 monolithic. 멀티 테넌트 미도입 (`auth_enabled: false`).
- Storage: filesystem (dev 적합).
- Schema: v13 tsdb (Loki 3.x 권장).
- 보존: 14일 (`retention_period: 336h`), 7일보다 오래된 샘플은 ingestion 거절.
- ingestion: 10MB/s, burst 20MB.

### 3.5 Promtail (`grafana/promtail:3.3.1`)

`backend/logs/app.log` (현재 파일) 와 `app.log.*.gz` (회전 압축본) 을 동시에 tail.

**라벨 정책** — 인덱스 카디널리티 통제 핵심:

- **라벨 (인덱스)**: `app`, `env`, `node_id`, `level` — 저카디널리티만.
- **본문 필드 (LogQL `| json` 검색)**: `logger_name`, `request_id`, `user_id`.
- 고유 ID 라벨화 **절대 금지**.

**파이프라인 스테이지** (YAML anchor `&pipeline` 으로 두 잡이 공유):

1. `json` — loguru `serialize=True` 의 record 트리 파싱.
2. `replace` × 4 — PII 마스킹 (email, JWT, 휴대폰, 주민번호). ingestion 단에서 강제해
   코드 리뷰 누락이 14일 보존되는 사고를 방지.
3. `labels` — `level` 만 인덱스 라벨로 승격.

**회전 추적** — loguru 가 `app.log → app.log.YYYY-MM-DD_HH-MM-SS_NNNNNN.gz` 로
회전+압축. Promtail 3.x 의 `decompression` 은 pipeline 이 아닌 scrape_config 레벨
옵션이라 잡을 두 개로 분리 (현재 / 회전).

### 3.6 호스트 메트릭

- **node-exporter** (`prom/node-exporter:v1.8.2`) — `profiles: [linux-host]`.
  운영 Linux 호스트 전용. macOS Docker Desktop 은 `rslave` propagation 미지원 +
  VM 내부 메트릭만 보여 의미 없음. `make up-prod` 가 `COMPOSE_PROFILES=linux-host` 로 활성화.

> **cAdvisor 미사용**: Azure VM 등 docker storage driver 가 `overlayfs` 인 환경에서
> "failed to identify the read-write layer ID" 에러로 컨테이너 메트릭 전체 누락
> 향후 storage driver 가 `overlay2` 인 환경 / K8s migration 시 재도입 검토.

### 3.7 데이터스토어 exporter

세 exporter 모두 **`krip-network` + `monitoring-network` 양쪽 가입** — 메인 compose
의 PG/Mongo/Redis 도달 + Prometheus scrape 양립을 위해 필수.

- **postgres-exporter** (`v0.16.0`) — `PG_EXPORTER_AUTO_DISCOVER_DATABASES=true`,
  `pg_settings_max_connections` 기본 노출.
- **mongodb-exporter** (`percona/mongodb_exporter:0.43.1`) — `--collect-all`,
  `--compatible-mode`. 운영에서는 `clusterMonitor` read-only role 권장.
- **redis-exporter** × 2 — Redis DB0 (hot) 와 DB1 (dedupe) 분리 인스턴스.

---

## 4. 네트워크 토폴로지

- **`krip-network`** — 메인 `docker-compose.yml` 이 `driver: bridge` 로 선언. backend, PG, Mongo, Redis 가 가입.
- **`monitoring-network`** — `external: true` 로 선언 → 사전에 `docker network create` 필요. 모니터링 컴포넌트가 가입. exporter 3종은 양쪽 가입.

`docker-compose.monitoring.yml` 은 `networks:` 블록을 **재선언하지 않음** — `-f -f`
deep-merge 충돌 방지.

---

## 5. 부팅 / 운영 명령 (`monitoring/Makefile`)

| 명령 | 의미 |
|---|---|
| `make up` | dev 부팅 (node-exporter 제외, macOS 호환) |
| `make up-prod` | 운영 Linux 부팅 (`linux-host` profile 활성) |
| `make up-build` | backend 이미지 재빌드 후 부팅 |
| `make down` | 전체 종료 (볼륨 유지) |
| `make logs` / `make ps` | 로그 tail / 상태 확인 |
| `make reload` | Prometheus config hot reload (`/-/reload` POST) |
| `make health` | `/health`, `/health/deep`, `/ready` 3종 curl 검증 |
| `make metrics` | backend:9090/metrics 의 RED 메트릭 샘플 조회 |
| `make logql` | Loki/Promtail ready + 라벨 목록 확인 |
| `make net-create` | `monitoring-network` 생성 (`up` 이 자동 호출) |

`COMPOSE_FILES = -f ../docker-compose.yml -f docker-compose.monitoring.yml` —
첫 번째 파일이 `../docker-compose.yml` 이라 project_directory 가 프로젝트 루트로
결정되어 양쪽 compose 의 모든 volume path 가 프로젝트 루트 기준으로 해결됨.

---

## 6. 환경변수 (`.env`)

| 키 | 용도 |
|---|---|
| `ENV` | Prometheus `external_labels.env`, Promtail Loki 라벨 |
| `NODE_ID` | Promtail Loki 라벨 (멀티 노드 식별) |
| `GRAFANA_ADMIN_PASSWORD` | Grafana admin 강제 비번 (`:?` — 미설정 시 부팅 거부) |
| `POSTGRES_USER` / `_PASSWORD` / `_NAME` | postgres-exporter DSN |
| `MONGODB_USER` / `_PASSWORD` | mongodb-exporter URI |

backend 환경변수는 `backend/.env` 와 분리 — docker-compose substitution 은 project
root `.env` 만 자동 로드하기 때문에 일부 중복.

---

## 7. 영속 볼륨

| 볼륨 | 용도 |
|---|---|
| `krip-prometheus-data` | tsdb 15일치 |
| `krip-grafana-data` | Grafana 내부 DB (대시보드 UI 수정분, 사용자) |
| `krip-loki-data` | Loki 청크 + 인덱스 14일치 |
| `krip-promtail-positions` | tail 오프셋 (재기동 시 중복 push 방지) |

---

## 8. Backend 측 연동 지점

| 영역 | 위치 |
|---|---|
| 메트릭 정의 | `backend/app/core/metric/` (ai, auth, chat, db, event_loop, fastapi, fcm, mongo, redis_client, worker) |
| 계측 (instrumentation) | `backend/app/core/instrumentation/` (위 영역과 매칭) |
| 메트릭 서버 | `prometheus_client.start_http_server(9090)` — `/metrics` 노출 |
| 헬스 엔드포인트 | `backend/app/api/v1/health.py` — `/health`, `/health/deep`, `/ready` 3종 분리 |
| 로그 출력 | `loguru serialize=True` JSON → `backend/logs/app.log` (회전 + gz 압축) |

`/health/deep` 와 `/ready` 는 RED 메트릭에서 제외 (`metric/fastapi.py:excluded_handlers`)
되어 `DEEP_CANARY_DURATION` + blackbox synthetic 두 시리즈로만 측정.