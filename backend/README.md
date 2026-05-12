# Krip Backend

> AI 기반 여행 플래닝 & 동행 매칭 플랫폼 백엔드.

여행 일정 생성, 메뉴 OCR, 실시간 채팅, 동행 매칭을 한 프로세스에서 다루는 **FastAPI 모듈러 모놀리식** 백엔드.

12개 도메인이 각자 `router · service · schema · repository · model · dto` 6계층으로 격리되고 `dependency-injector` 컨테이너로 관리된다.

## 핵심 기능

| 영역 | 내용 |
| --- | --- |
| AI 여행 일정 | LangGraph 다단계 그래프 + Gemini 추론 |
| 메뉴 OCR | LangChain & Gemini 멀티모달 — 외국어 메뉴판을 구조화된 텍스트로 |
| 다국어 번역 | Papago API |
| 실시간 채팅 | WebSocket fan-out — `in_process` / `node_channel` 두 모드로 단일/멀티 노드 동일 코드 |
| 동행 매칭 | 게시글 · 피드 · 좋아요 · 댓글 |
| 푸시 알림 | FCM |
| 인증 | Google OAuth + JWT |

## 스택 요약

Python 3.11 · FastAPI · PostgreSQL 16 · MongoDB 7 · Redis 7 · LangChain / LangGraph 1.0 · Gemini

## 디렉토리 구조

```
backend/
├── app/                  # FastAPI 애플리케이션
│   ├── main.py           # lifespan + FastAPI 팩토리
│   ├── container.py      # dependency-injector DI 컨테이너
│   ├── config/           # Pydantic Settings — .env 로드 + 타입 검증
│   ├── api/v1/           # REST 라우터 마운트 (도메인 라우터 + /health)
│   ├── domain/           # 12개 도메인 모듈 — auth · chat · tour · tripmate · feed · friend · menu_ai · translation · notification · profile · public
│   ├── core/             # 공유 인프라 — ai/ (tour_planner · menu_ocr · papago_translator) · oauth/ · chat/ · redis · fcm · logger · instrumentation
│   ├── database/         # SQLAlchemy 비동기 세션 + 모델, MongoDB(Beanie) 초기화
│   ├── middleware/       # RequestID · 인증 (Bearer / Cookie) · 에러 트래킹 · 보안 헤더
│   ├── schema/           # 도메인 전체 공유 스키마
│   └── util/             # share_token 등 작은 유틸
├── migration/            # Alembic — versions/ 에 마이그레이션 스크립트
├── test/                 # 단위 (unit/) + 통합 (integration/) 테스트
├── scripts/              # Place 데이터 import · 채팅 smoke test
├── secrets/              # Firebase 서비스 키 등 시크릿 키
├── seoul_data/           # Place DB 시드 — 서울 285개 장소 JSON
├── logs/                 # 런타임 로그
├── Dockerfile
├── alembic.ini
├── pyproject.toml / uv.lock
└── .python-version
```
