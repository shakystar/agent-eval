# agent-eval 문서 색인

[프로젝트 개요](../README.md) · [기획 명세](planning-spec.md) · [Inspect AI·Harbor 비교와 채택 근거](research/inspect-harbor.md) · [Linux 실행 환경](../containers/linux/README.md)

[v0.3.3 기획안 · 하위 모델 역할 계약 비교와 코드 품질 개선](milestones/v0.3.3/README.md)

[v0.3.2 기획안 · 독립 리뷰 실행 근거와 계약 재측정](milestones/v0.3.2/README.md)

## 개발 단계와 검증 기록

[이슈 #1 · 병합 후 네 저장소 통합 검증](validation/issue-1-20261122/README.md)에서 고정 커밋, 조건별 결과, 오프라인 재평가와 남은 제약을 확인할 수 있습니다.

M0는 연동 사전 검사이며, M1~M4는 첫 버전의 개발 마일스톤입니다. M5.1은 고정 협업 사례를 사용하는 후속 검증입니다.

| 단계 | 확인할 동작 | 계약과 검증 근거 |
| --- | --- | --- |
| M0 | Inspect 로그·재채점 호환성과 플랫폼별 실행 범위 | [기초 검사](validation/m0.md) · [Linux 통합](validation/m0-linux.md) · [Windows 오류 수정](validation/m0-windows-fixes.md) |
| M1 | 저장 증거 가져오기, 규칙 채점, 기존 판정을 보존하는 재평가 | [사용·데이터 계약](m1-contract.md) · [검증](validation/m1.md) · [보고서 예시](validation/m1/example-report.md) |
| M2 | 의미 평가, 근거 인용, 사람 검토와 승인 철회, 장애 인계 보정 사례 4건 | [사용 계약](m2-contract.md) · [공지문 보정](m2-calibration.md) · [장애 인계 최초 검증](validation/m2.md) · [통합 검증](validation/m2-integration.md) · [보고서 예시](validation/m2/example-report.md) |
| M3 | 실제 Codex에서 단독·협업·자료 주입·인계 장애를 조건별 2회 실행하고, 별도 1회에서 수정과 최종 수락 확인 | [실행·복구 방법](m3-execution.md) · [사전 검사](validation/m3-preflight.md) · [검증 기록](validation/m3.md) · [실행별 결과](validation/m3/linux-results.json) |
| M4 | 공지문·재고 과제의 공통 CLI 회귀, 실제 Codex의 재고 과제 3건 완료와 규칙 9건 충족 | [사전 검증](validation/m4-preflight.md) · [검증·첫 버전 기준 대조](validation/m4.md) · [실제 모델 실행](validation/m4/inventory-codex.md) · [과제 타당성 승인](validation/m4/inventory-task-review.md) |
| M5.1 | 모델 호출 없이 최종 산출물 판정, 필수 정보 인계율, 복구 성공률의 분모·제외 사유 대조 | [사례별 결과·재현 절차](validation/m5.1.md) · [JSON](validation/m5.1/recovery.json) · [Markdown](validation/m5.1/recovery.md) |

## 릴리스 기록과 누락 항목

[패키지 메타데이터](../pyproject.toml)의 버전은 `0.1.0`이며, [재고 과제 묶음](../bundles/inventory-reconciliation/v1/bundle.json)의 `v1`은 과제 데이터의 버전입니다. M1~M4 검증 기록은 개발 단계별 결과를 담고 있습니다.

2026-11-22 기준 원격 Git 태그와 저장소 내 릴리스 노트는 없습니다. M1~M4를 배포 버전에 대응시키는 기록도 없습니다.

| 필요한 문서 | 필요한 이유 | 작성 완료 조건 |
| --- | --- | --- |
| 개별 릴리스 기록 | 배포 시 패키지 버전과 실제 배포 소스를 연결해야 합니다. | 릴리스를 확정하면 태그·커밋 SHA·주요 변경점·검증 근거를 기록합니다. |
| 네 레포 통합 마일스톤 기록 | 재현할 소스 조합과 실험의 완료 조건을 한곳에서 확인할 수 있어야 합니다. [통합 검증 이슈 #1](https://github.com/shakystar/agent-eval/issues/1) | 통합 버전·목표·완료 조건을 합의하면 `docs/milestones/vX.Y.Z/README.md`에 네 레포 SHA와 완료 조건을 기록하고, 검증 후 실행 결과·근거·남은 범위를 연결합니다. |

## 기존 검증에서 확인할 수 없는 항목

M3의 초기 단독 실행 1건과 M4의 재고 A 실행은 실제 영수증이 있으나 해당 턴의 모델명 기록이 없습니다. 재고 3건의 과제 타당성은 승인됐으며, 재고 산출물에 대한 독립적인 사람 판정 일치율은 미측정입니다. [M3 실행 기록](validation/m3.md) · [재고 실행 증거](validation/m4/inventory-codex.md) · [M4 기준 대조](validation/m4.md)

문서 작성과 새 마일스톤 기록에 사용하는 두 자료는 비공개 저장소의 접근 권한이 필요합니다. [공통 문서 정책](https://github.com/shakystar/agent-collaboration-lab/blob/main/docs/documentation-policy.md) · [마일스톤 템플릿](https://github.com/shakystar/agent-collaboration-lab/blob/main/templates/milestone.md)

[통합 마일스톤 v0.1.0](milestones/v0.1.0/README.md)

[통합 마일스톤 v0.1.1 · 개발 산출물 인계와 누락 원인 검증](milestones/v0.1.1/README.md)
