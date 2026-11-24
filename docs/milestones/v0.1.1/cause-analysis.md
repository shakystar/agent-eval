# v0.1.1 · 인계 결함이 수락까지 남은 경로

비교 대상은 2026-11-23의 팀 후보입니다. 인계 구현과 저장소·CLI·복구 테스트 3개가 같은 커밋에서 추가됐습니다. 당시 통합 검토 기록에는 M3 수락과 M5 승인이 남아 있습니다. M3에서 검토한 것은 산출물 개정 고정, 역요청, 중복 제출 방지, 수정본 수락입니다. [구현과 테스트](https://github.com/shakystar/role-orchestrator/commit/2dfe5329047d7951c969eaf88fd7c5154f369a17) · [수락 기록](../v0.1.0/evidence/validation.json)

| 발견 | 계약 → 구현 → 검토에서 처음 확인한 누락 | 검증 가능한 원인 |
|---|---|---|
| 소비자 산출물 | 역할 계약은 oracle·변경 패치 등 후속 산출물을 요구합니다. 단일 인계 테스트는 소비자에게 보고서를 읽도록 지시하고 성공 영수증으로 종료합니다. | 읽기로 끝나는 작업의 완료 조건을 다음 산출물의 생산자에게도 적용했습니다. 실행 수락과 결과물 수락을 구별할 실행 계약이 없었습니다. [역할별 인계 명세](https://github.com/shakystar/agent-collaboration-lab/blob/0bbd7b1/docs/features/development-handoffs.md) · [기준 테스트](https://github.com/shakystar/role-orchestrator/blob/2dfe532/tests/test_handoff_runner.py#L32-L46) |
| 누락 항목과 보완 상한 | 필드 검사기는 첫 누락에서 반환하고 실행기는 슬롯당 2회를 허용했습니다. 각각의 규칙은 기존 시험을 통과했습니다. | 둘을 합친 사용자 경로에서 정보가 소실됩니다. 생산자가 통보된 모든 사항을 고쳐도 세 번째 누락을 처음 통보받을 때 상한에 도달합니다. [필드 판정](https://github.com/shakystar/role-orchestrator/blob/2dfe532/role_orchestrator/handoffs.py#L401-L414) · [상한 검사](https://github.com/shakystar/role-orchestrator/blob/2dfe532/tests/test_handoffs.py#L379) |
| 확정 실패 영수증 | 인계 실행기의 검사 함수는 성공 영수증만 정상 반환합니다. 상위 복구 함수는 상태 거절과 영수증 판독 불가를 같은 불확실 상태로 바꿉니다. | 무재제출을 지키는 예외 경로에 확정 실패까지 합쳐져 복구 시 실패 사실을 전달하지 못했습니다. [영수증 판독](https://github.com/shakystar/role-orchestrator/blob/2dfe532/role_orchestrator/handoff_runner.py#L180-L193) · [복구](https://github.com/shakystar/role-orchestrator/blob/2dfe532/role_orchestrator/handoff_runner.py#L310-L321) |
| 같은 보완 요청의 재표현 | 명세는 같은 기준 개정·인수 조건의 미결 요청을 재사용합니다. 저장 키에는 관찰 문구까지 직렬화돼 들어갑니다. | 재전달된 같은 바이트의 사례는 통과해도 사람이 같은 관찰을 다르게 적으면 새 요청으로 분류됐습니다. 키에서 관찰 근거와 요구사항의 동일성을 분리할 필요가 있었습니다. 요청 중복만으로 모델이 두 번 실행됐다는 결론을 내릴 수 없습니다. [기준 요청 키](https://github.com/shakystar/role-orchestrator/blob/2dfe532/role_orchestrator/handoffs.py#L370-L399) |

**귀속 범위.** 현재 확보한 기록에는 이 변경의 담당 멤버별 배정 원문, 패치 해시와 연결된 개별 리뷰 원문이 없습니다. 공통 Git 계정만으로 특정 역할의 지시 불이행을 판정할 수 없습니다. 확인한 원인은 역할 간 요구가 실제 검증 조건으로 전달되는 과정의 누락입니다. 당시 각 담당자가 받은 지시와 판단은 미확정입니다.
