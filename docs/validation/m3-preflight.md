# M3 착수 전 검증

2026-11-20, macOS x86_64 호스트와 Docker Linux/amd64. agent-eval `e6459fb` 기준으로 실제 Go runtime, LangGraph, SQLite, Inspect를 연결하고 공개 실행 계약을 대조했다. 모델 추론 호출은 0회다.

## 실행 결과

| 검사 | 고정 Linux 환경 | 현재 원격 main 후보 |
| --- | --- | --- |
| role-runtime / role-orchestrator | `2be08fc` / `5d2b518` | `bba4f3a` / `50bf7a9` |
| Go 및 워크플로 검사 | vet, engine/control/lifecycle race 통과. 워크플로 수락 19/19 | 실행 바이너리 빌드, handoff export 2/2, vet 통과. 첫 race 실행의 control 패키지 실패. control만 10회 재검사 통과. 독립 실행한 수락 검사 19/19 |
| 작성→검토 fixture | 완료 2건, receipt generation 1·1 | 동일 |
| Inspect 및 재시작 | 2개 샘플의 영수증 식별자 보존, 변조 거부. 재채점·재시작의 추가 시도 각각 0회 | 동일 |

고정 환경은 로컬 M0 이미지 `sha256:cf6506e89da19c1a72455d0f8ada3703538802e18fdb52ab0dde4c23fb77f984`이다. 후보는 같은 이미지의 일회성 컨테이너 안에서 두 Git 커밋을 체크아웃한 뒤 runtime-workflow와 runtime-bridge를 다시 빌드했다. 첫 후보 검사에서 `TestLocalControlBoundaries`가 동시 연결 한도에서 busy 응답을 기대하는 중 `server_test.go:97: broken pipe`로 실패했다. 재검사에서는 재현되지 않았다. 버전 변경과의 인과관계는 미확정이다. 고정 소스는 유지한다.

## Codex 계정 경로

공식 codex-adapter `af74d4a`의 doctor를 사용했다. 호스트에서 Codex 0.170.0과 기존 ChatGPT 인증으로 `routingAvailable=true`를 확인했다. Linux에서는 동일 버전의 공식 npm 패키지를 SHA-512로 검증하고 네이티브 바이너리를 실행했다. 기존 auth/config 파일은 읽기 전용으로 연결했고 컨테이너 UID 1000의 읽기 권한을 확인했다.

Linux doctor는 두 번 모두 `workspace_routing_timeout`을 반환했다. 두 번 모두 계정 조회 단계였고 모델 요청을 제출하지 않았다. 동일 이미지에서 인증 없는 공개 chatgpt.com 및 auth.openai.com HTTPS 요청은 인증서 검증 성공·HTTP 200이었다. 계정 라우팅 실패의 근본 원인은 미확정이다. 이 doctor는 독립 CLI의 진단이다. 현재 runtime이 Go 모듈로 사용하는 codex-adapter 버전은 `3ab5b920bf6c`이다.

같은 환경에서 호스트와 Docker의 doctor를 다시 실행했다. 호스트는 `routingAvailable=true`, Docker는 `-32603 (workspace_routing_timeout)`을 반환했다. 최초 검사부터 Docker에서 관측된 시간 초과는 총 3회이며 모델 호출은 0회다.

## M3 실행 계약의 남은 부분

- **C-05 실행 동일성.** 기존 경로는 runtime 소유의 역할별 세션과 advisory 프로필을 쓴다. 이번 fixture에서는 실행·산출물 식별자 보존을 확인했다. Linux 계정 라우팅 복구 후 실제 실행에서 모델·세션·도구·영수증을 대조해야 한다. M2 채점 모델 설정은 실행 모델 설정과 독립적이다.
- **C-06 협업과 주입.** 현재 live workflow는 producer 입력을 고정 Brief로 설정하고 consumer는 고정 producer의 영수증과 문서 해시를 확인한다. 공개 인터페이스에 임의 과제 전달, 이 경로의 단독 실행과 조건부 수정, 단계별 자료 주입 및 지정된 도구 호출 실패 주입 계약이 없다. fixture 실패 모드는 Codex 백엔드에서 거부된다.
- **실행 전 검사.** 버전 있는 과제 입력·단계·역할·필수 기능·실행 예산을 실제 제출 전에 대조하도록 구현한다. 실행 영수증에 연결할 입력 해시와 적용 횟수, 실패·불확실 상태, 재시작 후 중복 방지를 먼저 fixture로 검증한다. M2의 강제 예산 거부는 채점 호출에만 적용된다.

원시 실행 로그와 JSON은 로컬 `artifacts/m3-preflight.aqS5GB/`에 있다. 실제 모델 C-05·C-06의 통과 여부는 M3 구현 후 검증한다. [완료 기준](../planning-spec.md) · [비교 검사 정의](../research/inspect-harbor.md)
