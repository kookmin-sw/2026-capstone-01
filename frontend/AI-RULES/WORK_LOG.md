# Krip Frontend Work Log

이 문서는 AI Agent가 수행한 프론트엔드 변경 작업과 검증 결과를 팀원이 빠르게 확인할 수 있도록 기록한다. 최신 작업을 위에 추가한다.

## 기록 형식

```markdown
## YYYY-MM-DD — 작업 제목

### 목적

- 작업 요청과 해결하려는 문제

### 변경 내용

- 구현하거나 수정한 핵심 내용

### 주요 경로

- 변경 파일 또는 디렉터리

### 검증

- 실행한 명령과 결과

### 남은 사항

- 경고, 미검증 항목, 후속 작업 또는 `없음`
```

---

## 2026-07-12 — TSX·Android 보안 및 성능 리팩토링

### 목적

- 전체 TSX와 Android Java 소스에서 민감정보 노출, 미사용 코드, 컴파일 위험 및 성능 병목을 점검하고 개선한다.

### 변경 내용

- 모든 Route Page에 `React.lazy`와 `Suspense`를 적용해 페이지 단위 code splitting을 구성했다.
- Firebase Web 설정의 저장소 내 하드코딩 fallback을 제거하고 필수 환경 변수로 전환했다.
- Firebase 메시징 서비스 워커는 등록 URL로 전달받은 공개 Web 설정을 사용하도록 변경했다.
- 미참조 레거시 `RegisterPage`, `FeedPopup`, 백업 파일을 제거했다.
- 사용되지 않는 기본 Android 단위·계측 테스트 클래스를 제거했다.
- 사진 목록의 index key를 안정적인 URL key로 변경했다.
- `.env`와 `.env.local`이 Git에서 제외되는 것을 확인했다.
- `google-services.json`은 Android Firebase 빌드에 필요한 공개 클라이언트 설정이므로 유지했다.

### 주요 경로

- `frontend/src/app/App.tsx`
- `frontend/src/lib/firebase/app.ts`
- `frontend/src/lib/firebase/messaging.ts`
- `frontend/public/firebase/firebase-messaging-sw.js`
- `frontend/src/pages/`
- `frontend/android/app/src/`

### 검증

- `npm run lint`: 오류 0개, 기존 경고 26개
- `npm run build`: 성공
- 초기 메인 JavaScript 청크가 약 948.7KB에서 390.3KB로 감소했다.
- 각 Route Page가 별도 JavaScript 청크로 생성되는 것을 확인했다.
- `sh gradlew :app:compileDebugJavaWithJavac`: 성공
- 추적 대상 TSX, Java 및 서비스 워커에서 하드코딩된 credential 형태의 문자열이 남지 않은 것을 확인했다.
- `git diff --check`: 성공

### 남은 사항

- `VITE_AUTHORIZATION_BEARER`와 `VITE_TOUR_PLACES_AUTHORIZATION_BEARER`는 브라우저 번들에서 공개될 수 있다. 실제 비밀 값이라면 Backend 프록시 또는 사용자별 단기 토큰 계약으로 이전해야 한다.
- React Hook 의존성, Effect 내부 상태 변경, 지도 SDK `any` 타입 관련 lint 경고 26개가 남아 있다.
- Capacitor 의존성 내부에 deprecated API 및 unchecked operation 컴파일 경고가 있다.

---

## 2026-07-12 — 작업 이력 문서 도입

### 목적

- Agent가 사용자에게 보고하는 작업 결과를 저장소 안에서도 지속적으로 확인할 수 있게 한다.

### 변경 내용

- `WORK_LOG.md`와 공통 기록 형식을 추가했다.
- 변경 작업 완료 시 작업 이력을 갱신하도록 `AI_RULES.md`에 규칙과 체크리스트를 추가했다.

### 주요 경로

- `frontend/AI-RULES/AI_RULES.md`
- `frontend/AI-RULES/WORK_LOG.md`

### 검증

- Markdown 문서 구조와 diff 형식을 확인했다.
- 문서만 변경했으므로 애플리케이션 lint와 build는 생략했다.

### 남은 사항

- 없음

---

## 2026-07-12 — Firebase 통합 및 Layered 구조 개편

### 목적

- 분산된 Firebase 관련 파일을 한 영역으로 모으고 서비스 워커 경로를 명시적으로 관리한다.
- 기능별 구조에 혼재된 Route Page와 기능 코드를 Layered 구조로 분리한다.

### 변경 내용

- Firebase 앱, 메시징, 알림 모듈을 `src/lib/firebase`로 통합했다.
- Firebase 메시징 서비스 워커를 `public/firebase`로 이동했다.
- 서비스 워커 등록 경로를 `/firebase/firebase-messaging-sw.js`로 변경했다.
- 소스 구조를 `app`, `pages`, `features`, `shared`, `api`, `lib` 계층으로 재구성했다.
- 공용 데이터와 유틸리티를 `shared` 계층으로 이동했다.
- Layered 의존 방향을 `app → pages → features → shared`로 규정했다.

### 주요 경로

- `frontend/public/firebase/`
- `frontend/src/lib/firebase/`
- `frontend/src/app/`
- `frontend/src/pages/`
- `frontend/src/features/`
- `frontend/src/shared/`

### 검증

- `npm run build`: 성공
- `npm run lint`: 오류 0개, 기존 경고 26개
- 빌드 결과에 `dist/firebase/firebase-messaging-sw.js`가 포함되는 것을 확인했다.
- 하위 계층에서 `pages` 또는 `app`을 역참조하지 않는 것을 확인했다.
- `git diff --check`: 성공

### 남은 사항

- React Hook 의존성, Effect 내부 상태 변경, 지도 SDK `any` 타입 관련 경고 26개가 남아 있다.
- production bundle 크기 경고가 남아 있다.

---

## 2026-07-12 — ESLint 검사 범위 및 소스 오류 정리

### 목적

- `npm run lint`가 Android 및 PWA 생성 산출물을 검사해 대량 실패하는 문제를 해결한다.

### 변경 내용

- `dist`, `android`, `ios`, `dev-dist`, `coverage`를 ESLint 검사 대상에서 제외했다.
- 사용되지 않는 변수, 함수, import와 불필요한 정규식 escape를 정리했다.
- 중복 Firebase 초기화를 제거했다.
- 기존 지도 SDK 타입과 Effect 패턴은 경고로 계속 노출하도록 조정했다.

### 주요 경로

- `frontend/eslint.config.js`
- `frontend/src/lib/firebase/`
- 관련 `frontend/src` TypeScript 및 TSX 파일

### 검증

- `npm run lint`: 오류 0개
- `npm run build`: 성공
- `git diff --check`: 성공

### 남은 사항

- 기존 lint 경고 26개와 production bundle 크기 경고가 남아 있다.

---

## 2026-07-12 — AI Agent 규칙 개편 및 초기 디렉터리 정리

### 목적

- Krip 프로젝트에서 Agent가 매 작업 전에 확인할 상시 명세를 마련한다.
- 페이지와 컴포넌트가 혼재된 프론트엔드 구조를 도메인 기준으로 일차 정리한다.

### 변경 내용

- 서비스 목적, 팀 구성, 작업 프로토콜, React·TypeScript, 접근성, 보안, API 협업 및 검증 규칙을 추가했다.
- 페이지와 관련 컴포넌트를 인증, 계정, 피드, 메뉴, 알림, 일정 등의 도메인으로 분류했다.
- `Manualplanpage.tsx`를 `ManualPlanPage.tsx`로 정규화했다.
- 이후 Layered 구조 개편을 통해 일차 분류 결과를 `app/pages/features/shared` 계층으로 발전시켰다.

### 주요 경로

- `frontend/AI-RULES/AI_RULES.md`
- `frontend/src/`

### 검증

- `npm run build`: 성공
- import 및 Route 경로를 확인했다.
- `git diff --check`: 성공

### 남은 사항

- 현재 최종 디렉터리 구조는 바로 위의 “Firebase 통합 및 Layered 구조 개편” 기록을 기준으로 한다.
