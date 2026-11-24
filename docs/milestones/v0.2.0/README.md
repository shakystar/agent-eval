# v0.2.0 · 개발 과제에서 독립 리뷰팀 호출

**상태** 계획 · 기능 명세 작성 완료 · 통합 인수 미실행

## 목표와 범위

상위 오케스트레이터에 업무와 팀을 배정하면 독립 리뷰팀이 필요한 전문 인력만 호출하고, 원래 과제에 수락·보완·보류 결과를 반환한다. 첫 적용은 기존 Python 개발 과제와 7인 리뷰팀이다. [v0.1.1 개발 과제의 인수 기록](../v0.1.1/README.md) · [v0.2.0 기능 명세와 R1~R6](https://github.com/shakystar/role-orchestrator/blob/df690b9eebaa235700dc0ec22b65ea333974f300/docs/features/review-team-intake.md)

## 대상 조합

아래는 개발 출발점이다. 통합 인수 시에는 실제 실행한 네 구성요소의 전체 SHA, 명부 SHA와 이미지 ID를 다시 기록한다.

| 구성요소 | 출발 커밋 | 역할 |
|---|---|---|
| agent-collaboration-lab | [72fe33e](https://github.com/shakystar/agent-collaboration-lab/commit/72fe33e40fdf505019b41b52679e851ebfbd16df) | 신규 전문가 6명과 기존 최종 인수자 1명의 명부·배정 계약 |
| role-orchestrator | [3ae84e6](https://github.com/shakystar/role-orchestrator/commit/3ae84e60866ad2f0bc2ce7e0d8eece463f2c58cc) | 독립 호출 가능한 팀 배정기와 review-v1 프로필 |
| role-runtime | [722c9f6](https://github.com/shakystar/role-runtime/commit/722c9f620a707a8dc42c43a44f3666a3ba4fc87e) | 고유 실행자 확인 및 영수증 조회 |
| codex-adapter | [17b36ab](https://github.com/shakystar/codex-adapter/commit/17b36ab24d29f45799af705cca2e35c35af1a609) | 명부의 모델·추론 설정 전달 |
| agent-eval | [87b34ac](https://github.com/shakystar/agent-eval/commit/87b34ac5009d3e2baa6c9641f51a4f2438c0862b) | v0.1.1 동결 실험과 회귀 기준 |

## 완료 조건과 결과

| 시나리오 | 관측할 완료 조건 | 검증 방식 | 상태 |
|---|---|---|---|
| 기존 배정기 단독 호출 | 최초 기준을 전문가가 반려하고 보완본을 010과 005가 수락. 오프라인 재조회에서 같은 영수증 반환 | 합성 업무·실모델 | 후보에서 확인. [기존 영수증](https://github.com/shakystar/role-orchestrator/blob/3ae84e60866ad2f0bc2ce7e0d8eece463f2c58cc/docs/validation/independent-review.json) |
| R1·R2 선택 배정 | 부모 과제에서 기준·일반 패치·상태 변경 패치의 실행자와 순서가 계약과 일치 | 실제 브리지·fixture | 미실행 |
| R3·R4 거절과 보완 | 모호하거나 이해충돌이 있는 요청은 제출 0회. 반려 후 원래 작성자에게 사유 전달. 수정본은 새 개정으로 추적 | 반례·fixture | 미실행 |
| R5·R6 복구와 호환 | 재시작·동시 호출에서 중복 제출 0회. 이전 개발 경로의 영수증·조회 결과 보존 | 프로세스 재시작·오프라인 대조 | 미실행 |
| 통합 실모델 인수 | 빈 상태의 상위 진입점 한 번으로 팀에 위임. 수동 하위 CLI 호출 0회. 부모의 최종 결과와 네이티브 영수증 일치 | 동결 후보·실모델·오프라인 재조회 | 미실행 |

## 필요한 문서

인수 전 평가 담당자는 이 디렉터리의 `evidence/`에 부모 과제·개정, 입력과 패치 해시, 예정·실제 구성원, 역할별 시도 ID, 영수증, 요청별 신규 제출 수, 최종 판정과 재현 명령을 기록한다. 후보 변경이나 실패 후 재실행은 각각 사용한 SHA에 연결한다.

## 마감 판단

R1~R6과 통합 실모델 인수를 통과한 조합을 독립 검토자가 판정한다. 아직 완료·병합·릴리스 판정은 없다.

## 개발 준비

Python 담당자는 상위 위임과 부모 상태 복구를 구현한다. 리뷰팀 배정기는 기존 계약을 재사용한다. 검증 담당자는 같은 입력의 기대 경로와 결함 주입 사례를 독립적으로 작성한다. 명부·런타임·어댑터는 고정 버전으로 시작하고 실제 계약 차이가 확인될 때 해당 소유자에게 보완을 요청한다. [공통 개발 정책](https://github.com/shakystar/agent-collaboration-lab/blob/72fe33e40fdf505019b41b52679e851ebfbd16df/docs/development-policy.md)
