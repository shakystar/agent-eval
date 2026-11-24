# v0.1.1 모듈화 검토 기록

2026-11-23 기준 정적 구조 검토입니다. 아래 위치는 표에 고정한 커밋 기준입니다. 전체 Git 트리에서 실행 소스, 테스트, 실험, 설정과 증거를 식별하고 책임·저장 상태·검증 주체가 달라지는 경계를 조사했습니다. 이 문서는 구현 전 기준선입니다.

| 저장소와 고정 트리 | 추적 파일 | 실행 소스¹ |
|---|---:|---:|
| [role-orchestrator](https://github.com/shakystar/role-orchestrator/tree/6935f81) | 95 | 44 |
| [role-runtime](https://github.com/shakystar/role-runtime/tree/722c9f6) | 134 | 75 |
| [codex-adapter](https://github.com/shakystar/codex-adapter/tree/17b36ab) | 26 | 16 |
| [agent-eval](https://github.com/shakystar/agent-eval/tree/cff6688) | 158 | 49 |
| [agent-collaboration-lab](https://github.com/shakystar/agent-collaboration-lab/tree/0bbd7b1) | 12 | 2 |

¹ Go, Python, MJS, shell 합계이며 테스트·실험·과거 검증 스크립트를 포함합니다. 이미지 정의, 워크플로 설정, 역할 데이터, 명세와 저장 증거는 이 열에서 제외했습니다. 같은 저장소의 두 번째 체크아웃은 한 번만 집계했습니다. 목록 순서는 실행 우선순위를 뜻하지 않습니다.

## 오케스트레이터

| 위치 | 확인한 경계와 변경 대상 | 종결 검사 |
|---|---|---|
| `handoffs.py` | 산출물·개정 읽기, 필드 검사, 보완 조건·충돌·횟수 판정, SQLite 상태 전이가 한 클래스에 있습니다. 필드·정책 판정을 분리하고 비교와 실행권 획득은 같은 트랜잭션에서 수행합니다. 같은 선행 개정을 슬롯마다 다시 검사하므로 조회 트랜잭션 안에서 검증 결과를 재사용합니다. | 두 소비자의 상충 요구, 묶음 누락 통보, 오래된 개정, 손상된 바이트, 동시 실행권, 재시작을 검사합니다. 공통 선행 입력 1개에 결과 슬롯 1·4·8개를 붙인 기존 상태 조회는 SELECT 7·22·42회였습니다. |
| `handoff_runner.py` | 문서 해석, DB 생성, 읽기 전용 내부 클래스, 제출·복구, 영수증 검증이 공존합니다. CLI, 상태 저장소 열기, 작업 실행을 분리합니다. 보완 재조회는 모든 jobs의 JSON을 탐색합니다. 기존 요청 키와 별칭을 보존해 직접 조회합니다. | 조회 중 쓰기 0건, 같은 요청·별칭의 추가 제출 0건, 제출 전·후 중단, 결과가 필수인 소비자의 빈 결과 차단을 검증합니다. |
| `assignment.py`, `runtime.py`, `attempts.py`, `contracts.py` | Markdown 명부 해석, 배정 계획, 실행 영수증 판정을 분리합니다. 배정에도 기존 AttemptReader를 사용합니다. 실행 ID 읽기와 생성을 분리합니다. 배정기·인계기·런타임의 Python 모델/강도 정의와 세 JSON 판독기의 공통 입력 규칙을 모읍니다. 최상위 타입·크기 제한·해시용 인코딩은 호출 계약에 둡니다. | 명부 개정 고정, 미지원 설정, 빈 상태에서 조회, 중복 JSON 키·수치 범위, verdict 저장 전 중단 후 무재제출 복구와 종전 바이트 호환을 검사합니다. |
| `approval.py` | 승인 의도·락·SQLite 저장과 RPC 제출·영수증 해석이 결합돼 있습니다. 영속 의도 소유자와 관측 결과 판정을 구별합니다. 승인 직전 적격성 검사는 유지합니다. | 동일 키 동시 승인, 충돌 해시, 실패 영수증, 전송 여부 불명, 조회만 수행하는 경로를 검사합니다. |
| `workflow/runner.py` | poll 한 번에 수신함·커서, 그래프 조립, 증거 검증, 체크포인트, ACK, 결과 조회가 들어갑니다. 완료 후 반복 poll도 acked 행을 processed로 되돌려 재통지할 수 있습니다. 대기 행 전체 재검사와 그래프 재조립 비용도 분리해 측정합니다. | 정상 완료 뒤 추가 ACK 0회, 체크포인트 후 ACK 전 중단 시 재전달, 중복 생산자 알림, 노드 재생 시 증거 재검사를 확인합니다. |
| `metrics/store.py` | 원시 이벤트 저장과 전체 지표 재계산이 페이지 처리에 결합돼 있습니다. 정상 이벤트 100개 상태에서 빈 페이지와 기존 이벤트 1개 페이지 모두 기존 100건을 다시 해석했습니다. 변경 유무를 먼저 판정하고 투영을 분리합니다. | 빈·중복 입력의 재해석 횟수, 역순·충돌·늦은 이벤트 결과의 기존 전체 재계산과 동치를 검사합니다. |
| `runtime.py`, `observability.py` | 원격 관측 endpoint·인증 설정 조립이 양쪽에 있습니다. 공통 설정에서 언어별 exporter를 구성하고, 로컬 메타데이터 기록은 span별 파일 열기 비용을 배치 단위로 줄일 수 있습니다. | 원격 수집 미설정·중단, 파일 상한과 민감 정보 제외, 종료 시 flush를 검사합니다. |
| `evaluation/__main__.py`, `scripts/evaluate_handoff.py` | 인수 실행기는 unittest의 skip을 실패보다 먼저 판정합니다. 실패와 skip이 섞인 실행을 구분해야 합니다. 인계 평가 스크립트는 스냅샷 검증·평가 입력 구성·외부 CLI 실행·결과 저장을 분리할 경계가 있습니다. | 실패+skip 혼합, 잘못된 스냅샷, 실제 CLI 오류와 결과 귀속을 검사합니다. |
| `tests/test_handoff_runner.py`, `tests/test_handoff_recovery.py` | 복구 테스트가 다른 TestCase의 메서드를 가져와 setUp을 직접 호출합니다. 프로세스·상태 디렉터리 준비만 공용 fixture로 옮기고 각 테스트의 기대값은 직접 작성합니다. | 두 테스트 모듈을 각각 단독 실행하고 동일한 실제 bridge 검사가 선택되는지 확인합니다. |

## 런타임

| 위치 | 확인한 경계와 변경 대상 | 종결 검사 |
|---|---|---|
| `internal/control/server.go`, `approved_revision.go` | 소켓 소유권, 엄격한 JSON, RPC 라우팅, 영수증 조회, 승인 작업 생성·제출이 한 서버 파일에 있습니다. 승인 작업은 기존 승인 모듈에 모으고 전송 계층에는 RPC 해석을 둡니다. | 소켓 잠금·재시작, 미지원 메서드, 필드 거부, 승인 전 적격성·영수증 결속을 검사합니다. |
| `cmd/runtime-bridge/contract.go` | 요청 역직렬화와 프로토콜 검증, 실행 ID 영속 결속, 관측 래퍼, 요청 처리를 분리할 수 있습니다. | 기존 wire 벡터·레거시 데이터·다른 입력으로 attempt ID 재사용·재시작을 검사합니다. |
| `internal/workflowmodel/executor.go`, `internal/researchflow/flow.go` | 두 Step이 각각 입력 의존성 검증, 모델 호출, 결과 발행과 상태 전이를 담당합니다. 각 workflow 내부에서 입력 읽기·결과 검증을 분리하고 영속 전이 순서를 보존합니다. | 결함 산출물, 전달 실패, 재시작과 후속 역할이 참조한 개정을 확인합니다. |
| `internal/control`, `internal/workflowmodel`의 산출물 읽기 | 루트 아래 제한 읽기·크기·해시 검사가 여러 경로에 있습니다. 파일 읽기만 재사용하고 허용 ID, 16 KiB와 1 MiB 등 호출별 제한 및 오류 의미를 유지합니다. | 경계 크기, 예상과 다른 ID·해시, 누락 파일을 각 공개 경로로 확인합니다. |
| `internal/engine/lifecycle.go` | 영속 이벤트 도출·예약·투영과 페이지 조회가 결합돼 있습니다. LifecyclePage가 저장소 락 안에서 파일을 반복 조사합니다. 원장과 투영을 구분하고 페이지별 파일 읽기 수를 측정합니다. | 중단 지점별 원장 복원, cursor 재생·중복 없는 순서, 대량 페이지에서 읽기 수를 비교합니다. |
| `internal/engine/cooperation_pool.go`, `cooperation_store.go` | 빈 워커가 있으면 스케줄러가 작업 파일을 조사합니다. 대기·종료 작업만 많은 경우 반복 조회 비용이 커집니다. 준비된 작업 조회를 저장소 책임으로 두되 인덱스 도입은 측정 결과로 결정합니다. | 대기 작업 수와 poll당 파일 열기 횟수, lease 만료, 재기동 후 실행 가능한 작업 누락 여부를 검사합니다. |
| `cmd/runtime-bridge/telemetry.go`, `internal/workflowmodel/trace.go` | OTLP 전송 설정·인증·시간 제한·재시도·로컬 출력을 중복 구현합니다. 전송 설정과 수명주기만 공유하고 span 필드와 run ID 의미는 각 호출자가 유지합니다. | 원격 수집 실패 시 로컬 증거 보존, 전송 재시도, 종료 시 flush를 확인합니다. |
| `cmd/codex-{collaborate,evidence-pipeline,research-pipeline,pilot,target-review}` | 실험 준비·실행·결과 판정이 명령별 run에 모여 있습니다. collaborate/research의 main 본문, 세 명령의 decodeStrict, evidence/research의 readHandoff·readLimited는 본문 일치를 확인했습니다. 공통 CLI 준비와 유틸리티만 추출하고 과제별 오라클은 유지합니다. | 기존 flag·출력·종료 상태와 각 과제의 정상·결함 판정이 일치해야 합니다. |
| `internal/codexadapter/*_test.go` | 가짜 프로토콜 피어와 제품 어댑터 단언을 분리합니다. 로컬 mapping 테스트의 읽기·쓰기와 도구 프로필 함수는 외부 adapter 본문을 복제합니다. 계약 호환 fixture와 실제 의존성 검증의 범위를 표시합니다. | 실제 고정 adapter의 공개 동작을 검사하고, 과거 형식 fixture를 읽는 호환 검사는 독립적으로 유지합니다. |

## 어댑터와 협업 계약 저장소

| 위치 | 확인한 경계와 변경 대상 | 종결 검사 |
|---|---|---|
| codex-adapter `adapter.go` | 프로세스 시작·재시도, 영속 thread 매핑, 턴 제어, 알림·활동·사용량 해석이 한 파일에 있습니다. Execute에서 알림 해석을 떼고 매핑을 읽는 InspectSession과 같은 구현을 사용합니다. 실행 전후 매핑 쓰기와 실패 단계의 순서는 보존합니다. | 턴 시작 전·후 실패, 성공 사용량 집계, 무관한 알림, 세션 복원, 사용량 동시 조회를 검사합니다. |
| codex-adapter `rpc/client.go`와 runtime `internal/pirpc/client.go` | 제한 진단 버퍼의 Write와 Alive 본문은 동일합니다. 전자는 Codex, 후자는 pi 전송 계약을 가집니다. 이 작은 중복만으로 저장소 사이 공용 RPC 패키지를 도입할 이득은 확인되지 않았습니다. | 한쪽의 프로토콜 변경은 해당 클라이언트 테스트로 검증합니다. 공통 전송 규격을 실제로 채택할 때 다시 엽니다. |
| lab `tools/validate_patch.py` | 입력 스냅샷·Git archive 검증, subprocess와 로그 제한, Docker 실행·정리, 증거 확정이 하나의 CLI에 있습니다. 스냅샷 준비·실행·증거 기록은 독립적으로 시험하고 cleanup 결과까지 기록하는 책임은 실행기가 유지합니다. | stale base, 패치 실패, 테스트 실패, 취소, 시간 초과, 정리 확인 실패 각각에서 최종 상태·증거가 일치해야 합니다. |
| lab `docs/team/roster.md`, `docs/features/development-handoffs.md`와 orchestrator 배정기 | 실행 정책이 Markdown 표의 구문과 Python 해석기에 걸쳐 있습니다. 버전이 고정된 역할 계약에서 배정과 검증이 같은 필드·모델 정의를 사용하게 합니다. 과거 14개 역할과 진단용 28개 후보는 실행 계약과 목적이 다릅니다. | 과거 배정 재조회, 동일 명부에서 동일 계획 생성, 필수 결과 없는 역할과 결과 생산 역할의 차이를 검증합니다. |

## 평가 저장소

| 위치 | 확인한 경계와 변경 대상 | 종결 검사 |
|---|---|---|
| `agent_eval/service.py`, `execution.py` | 증거 매니페스트 검사·원자 저장·채점 준비, 실행 정책·외부 실행·결과 변환을 각각 분리합니다. service와 report의 원본 증거 조회 및 해시 검증은 같은 판독 경로를 재사용합니다. | 중복 가져오기, 절반만 기록된 결과, 원본 해시 불일치, 외부 실행 실패를 검사합니다. |
| `semantic.py` | 버전별 모델 응답·인용 해석, 채점 작업 저장·재개, 기존 결과 재판독이 한 파일에 있습니다. 결과 해석을 분리하고 grade가 저장·재개의 단일 소유자로 남습니다. | 이전 응답 재해석, 잘못된 인용, 채점 중단 뒤 중복 실행 방지를 확인합니다. |
| `report.py`, `store.py`, `review.py`, `reviews.py` | 보고서 조회·집계·표시를 분리합니다. 슬롯별 전체 runs, 실행별 전체 judgments, 판단별 리뷰 원장 조회와 current_runs의 행별 조회가 겹칩니다. ReferenceIndex 생성 시 검토 1건에도 이력을 광범위하게 읽습니다. 요청 단위 선별·인덱싱 후 일관된 스냅샷에서 집계합니다. | 동일 입력의 행·분모·제외 사유, 최신 및 과거 스냅샷, 리뷰 철회 전후 결과를 비교하고 데이터량별 조회 횟수를 기록합니다. |
| `cli.py`, `contracts.py`, `reliability.py`, `reviews.py` | CLI에서 명령 등록과 export_requests 업무를 구분합니다. 공통 JSON 원시 검증과 bundle·experiment·run 스키마를 분리할 수 있습니다. 신뢰도 계산의 rate는 원소유 모듈 contracts에서 가져옵니다. 일반 검토와 semantic 검토는 데이터 계약별로 유지합니다. | 기존 CLI 인자·출력, 스키마별 과거 입력 허용 범위와 통계 분모가 같아야 합니다. |
| `containers/linux/integration_driver.py`, `tests/validate_m4.py`, `tests/validate_m51.py` | 통합 드라이버의 프로세스 준비·상태 대기·검사·결과 기록을 나눕니다. 마일스톤 테스트 사이의 상수·하위 프로세스 호출은 테스트 지원 모듈로 옮기고 각 검증의 독립 기대값은 남깁니다. | 표준 컨테이너 진입점, 프로세스 실패·정리, 두 검증의 단독 실행을 확인합니다. |

## 유지 판정과 재검토 조건

아래는 현재 목적과 호출 경계에서 추가 구조 변경 근거를 발견하지 않은 부위입니다. 위 표에서 특정한 함수·테스트는 해당 변경 항목을 따릅니다.

| 부위 | 유지 근거 | 다시 열 조건 |
|---|---|---|
| orchestrator의 attempts, wire 계약, workflow/client·handoff·review, 연구용 graph | 조회 전용 API, 소켓 전송, 증거 내보내기, 검토 기록, 고정 연구 그래프의 입력·출력이 구별됩니다. | 영수증·wire·메시지·검토 원장 형식 또는 재생 의미 변경 |
| runtime의 engine 잠금·타입·실패 모델, lifecycle ledger, backend별 adapter·RPC, workflow contract, pi 확장 | OS·프로토콜·실행 의미가 다르고 독립 진입점이 있습니다. 일반 워커 풀과 lease 기반 협업 풀의 전이도 구별됩니다. | 플랫폼 지원, 지속 형식, lease·cursor·실패 계약 또는 의존 adapter 변경 |
| codex-adapter의 account, failure, inspection, types, rpc 오류·OS 프로세스 처리, CLI | 계정 조회·실패 모델·읽기 전용 세션 조회·프로세스 제어는 이미 개별 경계입니다. | 외부 호출 계약, 매핑 형식, OS 종료 동작 변경 |
| eval의 collaboration, graders, inspect_adapter, execution_journal, Go 호출 adapter | 협업 지표, 채점 공급자, Inspect 연동, 실행 영수증, 모델 프로세스의 책임이 구별됩니다. | 채점 기준·증거 형식·재시도·실행 공급자 변경 |
| lab의 contexts/role.py, 과거 카탈로그, 서식·정책 | 조회 전용 진단과 과거 기록 판독은 별도 목적입니다. | 조회 CLI 또는 과거 정의의 해석 변경 |
| 나머지 테스트·예제·실험, 과거 검증 driver·보고서, 고정 데이터·컨테이너 정의·CI 설정 | 특정 실행 조합이나 독립 반례를 보존합니다. 고정 보고서를 최신 제품 코드와 합치면 과거 실행 재현성이 바뀝니다. | 해당 fixture·명령·이미지·의존 버전 변경, 실패 재현, 제품 진입점으로 승격 |

**재검토 단위는 저장소 전체가 아니라 변경된 계약과 그 호출자입니다.** 구현 완료 시 해당 행에 구현 SHA, 공개 진입점, 통과한 정상·실패·재시작 검사, 영향을 받는 소비자를 남깁니다. 이후 같은 SHA·계약·의존 조합의 내부 구조 검토는 생략합니다. 파일 내용이 같아도 직접 의존성이 바뀌거나 회귀가 발견되면 연결된 행을 다시 엽니다. 새 파일은 소유 모듈 또는 신규 경계 하나에 먼저 연결합니다.

## 확인 범위

Git 트리, 함수 정의·본문, 호출·저장 경로와 기존 검증 자료를 대조했습니다. Python은 함수 본문 AST 비교, Go는 텍스트 본문 비교로 중복 후보를 추가 확인했습니다. 의미상 중복은 구현과 호출 계약을 별도로 읽었습니다. 조회 횟수와 JSON 재해석 건수는 합성 입력 관측값입니다. 처리시간·메모리 개선율은 미측정입니다. 제품 테스트 재실행, 리팩토링 구현 및 기능 완료 판정은 이 조사에서 수행하지 않았습니다.

### v0.1.1 후보에 반영한 범위

`role-orchestrator@2ac1621`에서 명부 해석, 역할 계약, 필드·보완 정책을 분리했습니다. 시도 영수증 판독, 엄격한 JSON 해석, 모델 경로 규칙을 공유하고, 읽기 전용 저장소 열기와 요청 키에 의한 재조회를 구현했습니다. 종결 근거는 [마일스톤 검사 결과](README.md)에 연결합니다. 성능 측정 제안과 다른 저장소의 구조 개선 항목은 후속 작업으로 남습니다.

## 실행 소스 파일 색인

고정 트리의 실행 소스 186개를 디렉터리별로 기록합니다. 같은 디렉터리 안에서도 위 표에 명시된 함수와 유지 대상은 개별 판정을 따릅니다. 설정·검증 데이터·이미지 정의까지 포함한 전체 파일 목록은 첫 표의 고정 트리에서 확인할 수 있습니다.

### role-orchestrator

| 디렉터리 | 파일 |
|---|---|
| `evaluation/completeness` | `check_g04.py` |
| `experiments` | `workflow_probe.py` |
| `role_orchestrator` | `__init__.py`, `__main__.py`, `approval.py`, `assignment.py`, `attempts.py`, `contracts.py`, `graph.py`, `handoff_runner.py`, `handoffs.py`, `observability.py`, `runtime.py` |
| `role_orchestrator/evaluation` | `__init__.py`, `__main__.py` |
| `role_orchestrator/metrics` | `__init__.py`, `__main__.py`, `store.py` |
| `role_orchestrator/workflow` | `__init__.py`, `__main__.py`, `client.py`, `handoff.py`, `review.py`, `runner.py` |
| `scripts` | `check_m1_handoff.py`, `check_model_workflow.py`, `evaluate_handoff.py`, `init_langfuse.py`, `probe_langfuse.py`, `validate_contract_trace.py` |
| `tests` | `test_approval_contract.py`, `test_assignment.py`, `test_bridge.py`, `test_contracts.py`, `test_graph.py`, `test_handoff_export.py`, `test_handoff_recovery.py`, `test_handoff_runner.py`, `test_handoffs.py`, `test_live_workflow.py`, `test_metrics.py`, `test_observability.py`, `test_workflow_failure_status.py`, `test_workflow_probe.py` |

### role-runtime

| 디렉터리 | 파일 |
|---|---|
| `adapters/pi` | `role-extension.mjs` |
| `cmd/codex-collaborate` | `main.go` |
| `cmd/codex-evidence-pipeline` | `main.go`, `main_test.go` |
| `cmd/codex-pilot` | `main.go` |
| `cmd/codex-research-pipeline` | `main.go`, `main_test.go` |
| `cmd/codex-target-review` | `main.go`, `main_test.go` |
| `cmd/role-runtime` | `main.go` |
| `cmd/runtime-bridge` | `contract.go`, `contract_test.go`, `inspection.go`, `main.go`, `main_test.go`, `telemetry.go` |
| `cmd/runtime-workflow` | `main.go` |
| `experiments/eino` | `spike_test.go` |
| `experiments/pi` | `cooperation-provider.mjs`, `fake-provider.mjs`, `pool-provider.mjs`, `spike.test.mjs` |
| `experiments/workflowprobe` | `main.go` |
| `internal/codexadapter` | `adapter.go`, `adapter_test.go`, `failure_test.go`, `mapping_test.go` |
| `internal/codexcooperation` | `cooperation.go`, `cooperation_test.go` |
| `internal/control` | `approved_revision.go`, `server.go`, `server_test.go` |
| `internal/engine` | `control_access.go`, `cooperation.go`, `cooperation_pool.go`, `cooperation_store.go`, `cooperation_test.go`, `definitions_test.go`, `failure.go`, `failure_test.go`, `lifecycle.go`, `lifecycle_test.go`, `lock_other.go`, `lock_unix.go`, `pool.go`, `pool_test.go`, `store.go`, `types.go` |
| `internal/lifecycle` | `ledger.go`, `ledger_test.go` |
| `internal/piadapter` | `adapter.go`, `cooperation.go` |
| `internal/pirpc` | `client.go`, `client_test.go`, `process_other.go`, `process_unix.go` |
| `internal/pispike` | `cooperation.go`, `cooperation_integration_test.go`, `demo.go`, `demo_integration_test.go` |
| `internal/researchflow` | `flow.go`, `flow_test.go` |
| `internal/workflowmodel` | `approval_cli_test.go`, `approval_evidence_test.go`, `approval_restart_test.go`, `contract.go`, `contract_test.go`, `executor.go`, `executor_test.go`, `trace.go`, `trace_test.go` |
| `scripts` | `benchmark.py`, `check.sh`, `go.sh`, `test_benchmark.py` |

### codex-adapter

| 디렉터리 | 파일 |
|---|---|
| `.` | `account.go`, `adapter.go`, `adapter_test.go`, `cli_test.go`, `effort_test.go`, `failure.go`, `failure_test.go`, `inspection.go`, `types.go` |
| `cmd/codex-adapter` | `main.go` |
| `rpc` | `client.go`, `client_test.go`, `errors.go`, `errors_test.go`, `process_other.go`, `process_unix.go` |

### agent-eval

| 디렉터리 | 파일 |
|---|---|
| `adapters/codex` | `main.go`, `main_test.go` |
| `agent_eval` | `__init__.py`, `__main__.py`, `cli.py`, `collaboration.py`, `contracts.py`, `execution.py`, `execution_journal.py`, `graders.py`, `inspect_adapter.py`, `reliability.py`, `report.py`, `review.py`, `reviews.py`, `semantic.py`, `service.py`, `store.py` |
| `containers/linux` | `build_m3.py`, `integration_driver.py`, `m3-entrypoint.py`, `prepare_context.py`, `run_suite.py`, `score_artifacts.py`, `test_build_m3.py` |
| `docs/validation/issue-1-20261122` | `build_four_commits.py`, `driver.py`, `verify_four_commits.py`, `verify_review_paths.py` |
| `examples/m1` | `create_example.py` |
| `examples/m2` | `create_example.py`, `create_handoff.py` |
| `examples/m3` | `create_example.py` |
| `experiments/m0` | `native_eval_probe.py`, `probe.py`, `test_windows_log_paths.py` |
| `experiments/m4` | `preflight.py` |
| `tests` | `test_m1.py`, `test_m2.py`, `test_m2_handoff.py`, `test_m2_live_criterion.py`, `test_m2_recovery.py`, `test_m3.py`, `test_review_integration.py`, `validate_m1.py`, `validate_m2.py`, `validate_m4.py`, `validate_m51.py`, `verify_approval_evidence.py` |

### agent-collaboration-lab

| 디렉터리 | 파일 |
|---|---|
| `contexts` | `role.py` |
| `tools` | `validate_patch.py` |
