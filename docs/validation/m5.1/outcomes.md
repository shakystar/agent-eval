# Evidence evaluation report

Experiment: m51-outcomes; evaluation: m51-outcomes-initial.

Review status: draft. Conclusion: withheld_pending_task_validity_or_judgment_review.

| Condition | Planned | Imported | Judgeable | Provisional successes | Confirmed success rate | Comparable |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| accepted | 1 | 1 | 1 | 0 | no_confirmed_outcomes | True |
| corrected | 1 | 1 | 1 | 1 | no_confirmed_outcomes | True |
| output-only | 1 | 1 | 1 | 1 | no_confirmed_outcomes | True |

## accepted

Condition differences:
Comparison restrictions:
Missing measurements: time=0/1, tokens=1/1, cost=1/1

| Task | Repeat | Execution | Artifact verdict | Outcome | Exclusion |
| --- | ---: | --- | --- | --- | --- |
| notice | 1 | completed | unmet | unmet |  |

| Metric | Count / denominator | Unmeasured reason | Other outcomes | Excluded slots |
| --- | ---: | --- | --- | --- |
| Required handoff items | 2/3 |  | item_absent=1 |  |
| Fault recovery | 0/0 | zero_denominator |  | no_fault_planned=1 |

## corrected

Condition differences: workflow.fixture.review.reason, workflow.fixture.review.verdict
Comparison restrictions:
Missing measurements: time=0/1, tokens=1/1, cost=1/1

| Task | Repeat | Execution | Artifact verdict | Outcome | Exclusion |
| --- | ---: | --- | --- | --- | --- |
| notice | 1 | completed | met | met |  |

| Metric | Count / denominator | Unmeasured reason | Other outcomes | Excluded slots |
| --- | ---: | --- | --- | --- |
| Required handoff items | 2/3 |  | item_absent=1 |  |
| Fault recovery | 0/0 | zero_denominator |  | no_fault_planned=1 |

## output-only

Condition differences: workflow.fixture.review.reason, workflow.fixture.review.verdict, workflow.fixture.revise, workflow.fixture.write, workflow.injections
Comparison restrictions:
Missing measurements: time=1/1, tokens=1/1, cost=1/1

| Task | Repeat | Execution | Artifact verdict | Outcome | Exclusion |
| --- | ---: | --- | --- | --- | --- |
| notice | 1 | completed | met | met |  |

| Metric | Count / denominator | Unmeasured reason | Other outcomes | Excluded slots |
| --- | ---: | --- | --- | --- |
| Required handoff items | 0/3 | missing_handoff_evidence | missing_handoff_evidence=3 |  |
| Fault recovery | 0/0 | zero_denominator |  | missing_injection_evidence=1 |

Native metrics use their original Inspect denominator; see report.json for values.
