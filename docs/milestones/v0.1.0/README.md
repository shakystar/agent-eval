# v0.1.0 · 승인한 수정 작업 한 건의 실행과 복구

**상태** 계획 · 개발 준비 검토 완료

## 목표와 범위

저장된 revise 제안을 명시적으로 승인해 한 번 수정하고, 프로세스 재시작 뒤 같은 결과를 조회한다. [기능 명세와 담당 작업](https://github.com/shakystar/role-orchestrator/blob/abf32919ff0a4e3bd96b2c0d58b8a92d45e805a6/docs/features/approved-revision.md)에 실행·평가 계약을 둔다.

## 대상 조합

아래는 [11월 22일 기준 실행](../../validation/issue-1-20261122/README.md)에 사용한 조합이다. 기능 완료 시 새로 검증한 네 SHA와 이미지 증거를 별도로 기록한다.

| 레포 | 기준 커밋 |
|---|---|
| agent-eval | [6db70ed063b2d993670f56408da0493524a02bfa](https://github.com/shakystar/agent-eval/commit/6db70ed063b2d993670f56408da0493524a02bfa) |
| role-orchestrator | [66657b78210fd16697175abec4b1807e95ed1a28](https://github.com/shakystar/role-orchestrator/commit/66657b78210fd16697175abec4b1807e95ed1a28) |
| role-runtime | [7b2f83702fac83e4004bf7b105a343872e3e53d6](https://github.com/shakystar/role-runtime/commit/7b2f83702fac83e4004bf7b105a343872e3e53d6) |
| codex-adapter | [2b8c204b0cb7e3c63c60a3fa7923e4e9ca4d02bb](https://github.com/shakystar/codex-adapter/commit/2b8c204b0cb7e3c63c60a3fa7923e4e9ca4d02bb) |

## 완료 조건과 결과

| 시나리오 | 완료 조건 | 검증 방식 | 상태 |
|---|---|---|---|
| 승인 후 수정 | 올바른 작성자와 계약, 성공 영수증 및 산출물 일치 | 실제 Go runtime과 합성 응답 | 미실행 |
| 중복·동시 승인 및 중단 | 동일 키의 추가 제출 0회, 불확실 상태 보존 | 중단 위치별 재시작 및 영수증 대조 | 미실행 |
| 과거 실행 회귀 | 기존 제안 조회, M3 기본 비교와 수정 분기 재현 | 기준 실행의 fixture 및 실모델 절차 | 미실행 |

## 개발 준비와 마감 판단

[공통 정책](https://github.com/shakystar/agent-collaboration-lab/blob/c541f5ba978d06bc0e5ce7a1c1df0dff1166149f/docs/development-policy.md)을 적용한다. 명세의 공용 사례로 orchestrator·runtime·eval의 테스트 설계를 시작한다. adapter 변경은 예정하지 않는다. 최초 통합에서 표준 M3 빌더에 adapter 커밋을 지정하고 바이너리의 모듈 정보를 확인한다. [고정 검증](../../validation/m3-adapter-pin.md)

제품 기능 및 통합 인수는 미실행이다. 릴리스 판단은 새 조합의 회귀와 인수 결과를 기록한 뒤 내린다.
