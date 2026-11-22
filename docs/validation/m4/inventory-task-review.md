# 재고 대사·보충 결정 v1 타당성 검토지

검토 대상은 단일 품목 원장을 읽어 가용 수량을 대사하고, 명시된 발주 정책을 JSON으로 적용하는 능력입니다. 2026-11-22에 사용자가 세 과제의 타당성을 모두 승인했습니다. [묶음 명세](../../../bundles/inventory-reconciliation/v1/bundle.json) · [공개 정책](../../../bundles/inventory-reconciliation/v1/public/policy.txt)

| 검토 기준 | 판단에 필요한 근거 |
| --- | --- |
| 측정 목적 | 업무에서 단일 품목의 가용량과 즉시 발주 수량을 계산하는 단계가 이 과제와 대응하는지 검토합니다. |
| 입력 충분성 | 세 원장은 모두 기초 수량·입고·출고·파손을 제공합니다. 정책은 부호, 발주점 3개, 목표 7개, 경계값에서의 동작을 명시합니다. 이 정보만으로 각 답이 하나로 정해지는지 확인합니다. |
| 사례 구별력 | A는 보충 수량 계산, B는 발주점에서의 엄격한 부등식, C는 목표 초과 시 발주 보류를 검사합니다. 모든 원장에 같은 결정을 내리는 방식이 어떤 오류를 놓치는지 검토합니다. |
| 채점 적절성 | 세 필드를 각각 검사하며 JSON 키 순서는 자유입니다. 불리언과 수량을 혼동하거나 요청한 정수 표기 대신 소수로 쓰면 해당 필드가 미충족입니다. 업무가 구조화된 시스템 입력을 요구하는지, 이 형식 요건이 평가 목적에 맞는지 검토합니다. [기존 오답·누락 대조군](cli-results.json) |
| 적용 범위 | 공개된 합성 원장 3개에 고정된 정책 하나를 사용합니다. 복수 품목, 예약 재고, 조달 리드타임이나 수요 예측이 필요한 업무에 적용하려면 어떤 자료와 사례가 더 필요한지 기록합니다. |

<details>
<summary>원장에서 산출한 대조값과 사례별 채점 근거</summary>

| 과제 | 기초 + 입고 − 출고 − 파손 | 판단 | 기대값 (`available`, `reorder`, `order_units`) |
| --- | --- | --- | --- |
| [inventory-a 원장](../../../bundles/inventory-reconciliation/v1/public/ledger-a.csv) | 8 + 3 − 8 − 2 = 1 | 1 < 3이므로 7 − 1 = 6개를 발주합니다. | `1, true, 6` |
| [inventory-b 원장](../../../bundles/inventory-reconciliation/v1/public/ledger-b.csv) | 6 + 4 − 5 − 2 = 3 | 발주점과 같으므로 발주 수량은 0개입니다. | `3, false, 0` |
| [inventory-c 원장](../../../bundles/inventory-reconciliation/v1/public/ledger-c.csv) | 9 + 5 − 4 − 1 = 9 | 목표 수량을 초과하므로 발주 수량은 0개입니다. | `9, false, 0` |

묶음의 채점 근거는 [A](../../../bundles/inventory-reconciliation/v1/private/rubric-a.txt), [B](../../../bundles/inventory-reconciliation/v1/private/rubric-b.txt), [C](../../../bundles/inventory-reconciliation/v1/private/rubric-c.txt)에 있습니다.

</details>

### 검토 기록

검토 대상은 `inventory-reconciliation@1`이며 묶음 해시는 `ecc6c617d22502e30609950e9bc03e271dee9206f1753dbeeb04e024b885ce87`입니다. 세 사례 모두 과제 버전 1입니다.

| 과제 | 검토한 정책 적용 사례 | 사용자 판정 |
| --- | --- | --- |
| inventory-a | 가용 1개에서 목표 7개까지 6개 발주 | [승인](task-reviews/inventory-a.json) |
| inventory-b | 가용 3개는 발주점과 같으므로 0개 발주 | [승인](task-reviews/inventory-b.json) |
| inventory-c | 가용 9개는 목표를 초과하므로 0개 발주 | [승인](task-reviews/inventory-c.json) |

사용자 판정 원문은 “응, A·B·C 세 과제의 타당성을 모두 승인한다. 내 판정을 레포에 기록하라.”입니다. 위 계산은 원장과 정책에서 산출한 검토 자료이며, 사용자는 세 과제에 대한 공통 판정을 제출했습니다.

기존 Codex 실행 저장소에 `task-review --human-attested`로 세 건을 등록했습니다. `inventory-live-rules` 보고서를 다시 생성해 세 과제 모두 `approved`임을 확인했습니다. 모델 응답의 사람 확정 건수는 0건이며 보고서 상태는 `draft`입니다. [검토 기록 계약](../../m2-contract.md)
