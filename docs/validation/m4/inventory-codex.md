# 재고 대사·보충 결정 v1 실제 Codex 검증

2026-11-22에 `inventory-reconciliation-v1-codex`의 `solo` 조건을 세 원장에 각각 1회 실행했습니다. 세 작성 단계가 모두 성공했고 규칙 판정 9개가 모두 충족됐습니다. 원장의 수량으로 다시 계산한 기대값이 모델의 JSON 값 및 자료형과 각각 일치했습니다. [고정 실험 명세](../../../bundles/inventory-reconciliation/v1/experiment.json) · [실행별 증거](inventory-codex-results.json)

| 과제 | 원장에서 계산한 결정 | 실제 응답 원문 | 규칙 충족 |
| --- | --- | --- | ---: |
| `inventory-a` | 재고 1개, 목표 7개까지 6개 발주 | `{"available":1,"reorder":true,"order_units":6}` | 3/3 |
| `inventory-b` | 재고 3개, 발주점과 같아 발주 보류 | `{"available":3,"reorder":false,"order_units":0}` | 3/3 |
| `inventory-c` | 재고 9개, 목표를 초과해 발주 보류 | `{"available":9,"reorder":false,"order_units":0}` | 3/3 |

### 실행·채점 증거

- 기준 커밋은 `6fff0f1`입니다. 고정 M3 Linux 이미지에서 기존 role-orchestrator → runtime-bridge → Codex 경로를 사용했습니다. 실험 명세는 로그인된 런타임의 모델 설정을 상속합니다. B·C의 턴 기록에서 `gpt-6-astra`와 추론 설정 `medium`을 확인했습니다. A도 실제 Codex 영수증과 출력이 있으며 해당 턴의 모델 메타데이터는 보존되지 않았습니다.
- 세 실행에서 실제 전송 입력과 성공 영수증의 입력 원문이 일치했습니다. 입력 JSON은 공개 과제 정의, 원장, 정책으로만 구성됐고 고정 fixture 응답이나 평가 기준은 포함하지 않았습니다. 실행 컨테이너는 증거 저장소를 마운트했으므로 이 확인의 범위는 모델에 전달한 요청입니다.
- 완료 후 네트워크를 차단하고 `inventory-live-rules`로 저장된 산출물을 채점했습니다. 별도의 읽기 전용 대조에서 입력·출력·영수증 해시를 재계산하고 원본 응답과 저장 산출물의 바이트를 확인했습니다. 판정 가능 3/3, 판정 불가 0건, 채점 오류 0건입니다. 원본 저장소는 로컬 Docker 볼륨 `agent-eval-inventory-codex-1795319998711`의 `/state/store`, 실행 보고서는 `/state/report/report.json`에 보존했습니다.

### 사람의 타당성 검토

실행 시점에는 세 과제가 모두 `unreviewed`였습니다. 이후 사용자가 A·B·C의 과제 타당성을 모두 승인했습니다. 사람 검토로 확정한 모델 응답은 0건입니다. [과제별 승인 기록](inventory-task-review.md)
