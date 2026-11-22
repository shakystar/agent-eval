# Evidence evaluation report

Experiment: m51-recovery; evaluation: m51-recovery-initial.

Review status: draft. Conclusion: withheld_pending_task_validity_or_judgment_review.

| Condition | Planned | Imported | Judgeable | Provisional successes | Confirmed success rate | Comparable |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| fault | 3 | 3 | 1 | 1 | no_confirmed_outcomes | True |

## fault

Condition differences:
Comparison restrictions:
Missing measurements: time=0/3, tokens=3/3, cost=3/3

| Task | Repeat | Execution | Artifact verdict | Outcome | Exclusion |
| --- | ---: | --- | --- | --- | --- |
| notice | 1 | completed | met | met |  |
| notice | 2 | failed | unknown | unknown | final_artifact_not_reached, execution_failed |
| notice | 3 | uncertain | unknown | unknown | final_artifact_not_reached, insufficient_evidence |

| Metric | Count / denominator | Unmeasured reason | Other outcomes | Excluded slots |
| --- | ---: | --- | --- | --- |
| Required handoff items | 2/9 |  | item_absent=1, missing_handoff_evidence=6 |  |
| Fault recovery | 1/2 |  | read_failed=1 | stage_not_reached=1 |

Native metrics use their original Inspect denominator; see report.json for values.
