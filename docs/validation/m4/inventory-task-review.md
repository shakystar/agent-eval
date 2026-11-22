# 재고 대사·보충 결정 v1 타당성 검토지

검토 대상은 단일 품목 원장을 읽어 가용 수량을 대사하고, 명시된 발주 정책을 JSON으로 적용하는 능력입니다. 세 과제의 상태는 각각 `unreviewed`입니다. 검토자는 사례별로 모델 응답을 보기 전에 원장과 공개 정책만으로 기대값을 기록할 수 있습니다. [묶음 명세](../../../bundles/inventory-reconciliation/v1/bundle.json) · [공개 정책](../../../bundles/inventory-reconciliation/v1/public/policy.txt)

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

| 과제 | 검토자 독립 계산값 | 타당성 판정 | 사유·근거 또는 보완할 점 |
| --- | --- | --- | --- |
| inventory-a | | | |
| inventory-b | | | |
| inventory-c | | | |

입력·정답·채점 기준이 측정 목적에 적합하면 `approved`, 결함이 있으면 `rejected`, 근거가 더 필요하면 `unreviewed`로 기록합니다. 사람 검토를 완료한 경우 해당 과제 ID와 버전 1, 검토자, 근거 출처, 시각, 사유를 포함한 기록을 `task-review --human-attested`로 등록할 수 있습니다. 과제 승인은 별도 실험에서 나온 모델 응답을 확정하지 않습니다. [검토 기록 계약](../../m2-contract.md)
