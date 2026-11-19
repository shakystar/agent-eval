# Evidence evaluation report

Experiment: m1-demo; evaluation: second.

Draft rule judgments. Performance conclusions withheld.

| Condition | Planned | Imported | Judgeable | Provisional successes | Comparable |
| --- | ---: | ---: | ---: | ---: | --- |
| baseline | 3 | 3 | 2 | 1 | True |
| changed | 3 | 0 | 0 | 0 | True |

## baseline

Condition differences:
Comparison restrictions:
Missing measurements: time=3/3, tokens=3/3, cost=3/3

| Task | Repeat | Execution | Outcome | Exclusion |
| --- | ---: | --- | --- | --- |
| decision | 1 | completed | met |  |
| decision | 2 | completed | unmet |  |
| decision | 3 | uncertain | unknown | insufficient_evidence |

## changed

Condition differences: model.settings.temperature
Comparison restrictions:
Missing measurements: time=3/3, tokens=3/3, cost=3/3

| Task | Repeat | Execution | Outcome | Exclusion |
| --- | ---: | --- | --- | --- |
| decision | 1 | not_imported | unknown | missing_run |
| decision | 2 | not_imported | unknown | missing_run |
| decision | 3 | not_imported | unknown | missing_run |

Native metrics use their original Inspect denominator; see report.json for values.
