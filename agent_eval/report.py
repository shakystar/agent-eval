"""Public reports exclude source text and private criteria."""
from collections import Counter
from .contracts import loads, rate, require
from .service import context
from . import collaboration


def flatten(obj, prefix=''):
    result = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            result.update(flatten(v, f'{prefix}.{k}' if prefix else k))
    else:
        result[prefix] = obj
    return result


def artifact_grade(required):
    if any(j['processing'] == 'error' for j in required):
        return 'unknown', 'scorer_error'
    if not required or any(j['verdict'] == 'unknown' for j in required):
        return 'unknown', 'insufficient_evidence'
    return ('met' if all(j['verdict'] == 'met' for j in required) else 'unmet'), None


def execution_summary(store, run, required_handoff=()):
    execution = store.find('execution_result', run['id'])
    if execution is None:
        return None
    execution = loads(store.read_blob(run['receipt']))
    require(store.observed('execution_result', run['id'], execution) and
            execution['id'] == run['id'] and execution['runtime_run'] == run['attempt_id'],
            'execution receipt mismatch')
    stages = []
    for stage in execution['stages']:
        for field in ('input_sha256', 'before_sha256', 'wire_sha256', 'receipt_sha256', 'output_sha256'):
            if stage.get(field):
                store.read_blob(stage[field])
        stages.append({key: stage[key] for key in ('stage', 'attempt_id', 'status', 'failure') if key in stage})
    summary = dict(backend=execution['backend'], scenario=execution['scenario'], stages=stages,
                   review=execution['review'], injections=execution['injections'])
    if required_handoff and execution['scenario'] == 'collaboration':
        document = collaboration.received_document(store, execution)
        summary['handoff'] = collaboration.handoff_observation(required_handoff, execution['scenario'], document)
    return summary


def report(store, experiment_id, evaluation_id):
    exp, tasks = context(store, experiment_id)
    ev = store.get('evaluation', evaluation_id)
    require(ev['experiment'] == experiment_id, 'evaluation/experiment mismatch')
    for source in store.all('source'):
        if store.get('evidence', source['evidence'])['experiment'] == experiment_id:
            store.read_blob(source['sha256'])
    for judgment in ev['judgments']:
        for field in ('evidence_sha256', 'native_log_sha256', 'error_sha256', 'request_sha256', 'response_sha256', 'rationale_sha256'):
            if judgment.get(field):
                store.read_blob(judgment[field])
    from .review import get_bundle, validity, effective_judgment
    grading_tasks = {t['id']:t for t in get_bundle(store, ev['criterion_bundle'])['tasks']}
    task_validity = {key:validity(store, ev['criterion_bundle'], t) for key,t in grading_tasks.items()}
    runs = [r for r in store.all('run') if r['experiment'] == experiment_id]
    if 'run_snapshots' in ev:
        runs = [loads(store.read_blob(sha)) for sha in ev['run_snapshots'].values()]
    base = next(c for c in exp['conditions'] if c['id'] == exp['baseline'])
    base_flat = flatten({k:v for k,v in base.items() if k != 'id'})
    conditions = []
    for cond in exp['conditions']:
        plan = cond.get('workflow')
        flat = flatten({k:v for k,v in cond.items() if k != 'id'})
        diffs = [k for k in sorted(flat.keys() | base_flat.keys()) if flat.get(k) != base_flat.get(k)]
        confounds = [k for k in diffs if k not in exp['varying_fields']]
        rows = []
        for task in tasks:
            for repeat in range(1, exp['repetitions']+1):
                match = [r for r in runs if (r['condition'],r['task'],r['repeat']) == (cond['id'],task,repeat)]
                row = {'task':task, 'repeat':repeat, 'run':None, 'status':'not_imported',
                       'outcome':'unknown', 'exclusion_reason':'missing_run',
                       'artifact_verdict':'unknown', 'artifact_reason':'missing_run',
                       'confirmed_outcome':'unknown', 'task_validity':task_validity[task]}
                workflow = None
                requirements = grading_tasks[task].get('required_handoff', [])
                if match:
                    r = match[0]
                    js = [j for j in ev['judgments'] if j['run'] == r['id']]
                    required = [j for j in js if j['required'] and j['verdict'] != 'not_applicable']
                    reviewed = [effective_judgment(store, evaluation_id, j) for j in js if j['required']]
                    active_reviews = [j for j in reviewed if j['verdict'] != 'not_applicable']
                    confirmed = bool(active_reviews) and all(j['confirmation']=='confirmed' and j['verdict']!='unknown' for j in reviewed)
                    confirmed_outcome = ('met' if all(j['verdict']=='met' for j in active_reviews) else 'unmet') if confirmed and r['execution_status']=='completed' else 'unknown'
                    errors = sum(j['processing'] == 'error' for j in js)
                    artifact, artifact_reason = artifact_grade(required)
                    outcome, why = artifact, artifact_reason
                    if r['execution_status'] != 'completed':
                        # A writer draft can survive an interrupted collaboration.
                        artifact, artifact_reason = 'unknown', 'final_artifact_not_reached'
                        outcome, why = 'unknown', why or 'execution_'+r['execution_status']
                    row.update(artifact_verdict=artifact, artifact_reason=artifact_reason,
                               run=r['id'], attempt_id=r['attempt_id'], status=r['execution_status'],
                               outcome=outcome, exclusion_reason=why,
                               confirmed_outcome=confirmed_outcome,
                               environment_mismatch=r['environment'] != cond['environment'],
                               native_sample_id=r.get('sample_id'), native_epoch=r.get('epoch'),
                               native_score_states=dict(Counter(s['state'] for s in r['native']['scores'].values())),
                               native_error=r['native']['error'] is not None,
                               native_score_absent=not bool(r['native']['scores']),
                               item_counts=dict(Counter(j['verdict'] for j in js)), scorer_errors=errors,
                               item_met_rate=rate(sum(j['verdict']=='met' for j in js),sum(j['verdict']!='not_applicable' for j in js)),
                               measurements={k:{f:v for f,v in m.items() if f!='missing_reason'} for k,m in r['measurements'].items()},
                               missing_measurement_reasons={k:'not_measured' for k,m in r['measurements'].items() if m['value'] is None})
                    workflow = execution_summary(store, r, requirements)
                    if workflow is not None:
                        row['workflow'] = workflow
                        if 'handoff' in workflow:
                            row['handoff'] = workflow.pop('handoff')
                if plan:
                    if 'handoff' not in row:
                        row['handoff'] = collaboration.handoff_observation(requirements, plan.get('scenario'), None)
                    row['fault_recovery'] = collaboration.recovery_observation(plan, workflow)
                rows.append(row)
        counts = Counter(r['outcome'] for r in rows)
        absent = sum(r['run'] is None for r in rows)
        mismatch = any(r.get('environment_mismatch') for r in rows)
        confirmed = [r for r in rows if r['confirmed_outcome'] != 'unknown']
        eligible = [r for r in confirmed if r['task_validity'] == 'approved']
        confirmed_rate = rate(sum(r['confirmed_outcome'] == 'met' for r in eligible), len(rows))
        if not eligible:
            reason = 'no_approved_reviewed_outcomes' if confirmed else 'no_confirmed_outcomes'
            confirmed_rate.update(value=None, missing_reason=reason)
        conditions.append({'condition':cond['id'], 'planned':len(rows), 'imported':len(rows)-absent,
            'judgeable':counts['met']+counts['unmet'], 'unknown':counts['unknown'],
            'status_counts':dict(Counter(r['status'] for r in rows)),
            'exclusion_counts':dict(Counter(r['exclusion_reason'] for r in rows if r['exclusion_reason'])),
            'overall_confirmed_success_rate':confirmed_rate,
            'confirmed_judgeable':len(confirmed),
            'confirmed_success_note':'Only explicit human reviews on approved task versions count as confirmed successes.',
            'provisional_success_rate':rate(counts['met'],len(rows)),
            'provisional_judgeable_success_rate':rate(counts['met'],counts['met']+counts['unmet']),
            'missing_run_rate':rate(absent,len(rows)),
            'missing_measurement_rates':{k:rate(sum(r['run'] is None or k in r.get('missing_measurement_reasons',{}) for r in rows),len(rows)) for k in ('time','tokens','cost')},
            'condition_differences':diffs, 'unplanned_differences':confounds,
            'comparable':not confounds and not mismatch,
            'comparison_reasons':(['unplanned_condition_difference'] if confounds else [])+(['actual_environment_differs_from_plan'] if mismatch else []),
            'tasks':{t:{'planned':exp['repetitions'],'outcomes':dict(Counter(r['outcome'] for r in rows if r['task']==t))} for t in tasks},
            'runs':rows})
        if plan:
            conditions[-1].update(collaboration.condition_metrics(rows))
    native = []
    for e in store.all('evidence'):
        if e['experiment'] != experiment_id or not e['native_results']:
            continue
        result = e['native_results']
        native.append({'evidence':e['id'], 'total_samples':result.get('total_samples'),
                       'completed_samples':result.get('completed_samples'),
                       'metrics':[{'scorer':s.get('name'),'metrics':{k:v.get('value') for k,v in s.get('metrics',{}).items()}} for s in result.get('scores',[])],
                       'denominator_policy':'Inspect native metrics; not planned-run success rate'})
    reviewed_count = sum(item['confirmed_judgeable'] for item in conditions)
    all_reviewed = reviewed_count == sum(item['planned'] for item in conditions)
    approved = all(value == 'approved' for value in task_validity.values())
    return {'schema_version':1,'experiment':experiment_id,'evaluation':evaluation_id,
            'criterion_bundle':ev['criterion_bundle'],'parent_evaluation':ev['parent'],
            'confirmation':'confirmed' if all_reviewed else 'partial' if reviewed_count else 'draft',
            'conclusion':'human_reviewed_results_on_approved_tasks' if all_reviewed and approved else 'withheld_pending_task_validity_or_judgment_review',
            'task_validity':task_validity,
            'review_ledger_ids':[x['id'] for x in store.all('judgment_review') if x['evaluation']==evaluation_id],
            'aggregation':'equal weight per planned task/repeat; missing runs stay in denominator',
            'conditions':conditions,'native_aggregates':native,
            'limitations':['Task approvals and human reviews apply to the selected task and criterion versions.',
                           'Evaluator reliability is measured in the reference report.',
                           'No automatic human confirmation; raw outputs and private criteria omitted.']}


def markdown(obj):
    lines = ['# Evidence evaluation report','',f"Experiment: {obj['experiment']}; evaluation: {obj['evaluation']}.",'',
             'Review status: '+obj['confirmation']+'. Conclusion: '+obj['conclusion']+'.','',
             '| Condition | Planned | Imported | Judgeable | Provisional successes | Confirmed success rate | Comparable |',
             '| --- | ---: | ---: | ---: | ---: | ---: | --- |']
    for c in obj['conditions']:
        label = c['condition'].replace('|','/').replace('\n',' ')
        confirmed = c['overall_confirmed_success_rate']
        displayed = (f"{confirmed['numerator']}/{confirmed['denominator']}" if confirmed['value'] is not None
                     else confirmed['missing_reason'])
        lines.append(f"| {label} | {c['planned']} | {c['imported']} | {c['judgeable']} | {c['provisional_success_rate']['numerator']} | {displayed} | {c['comparable']} |")
    for condition in obj['conditions']:
        lines += ['', '## '+condition['condition'].replace('\n',' '), '',
                  'Condition differences: '+', '.join(condition['condition_differences']),
                  'Comparison restrictions: '+', '.join(condition['comparison_reasons']),
                  'Missing measurements: '+', '.join(k+'='+str(v['numerator'])+'/'+str(v['denominator']) for k,v in condition['missing_measurement_rates'].items()), '',
                  '| Task | Repeat | Execution | Artifact verdict | Outcome | Exclusion |',
                  '| --- | ---: | --- | --- | --- | --- |']
        for row in condition['runs']:
            task=row['task'].replace('|','/').replace('\n',' ')
            reasons = ', '.join(dict.fromkeys(filter(None, [row.get('artifact_reason'), row['exclusion_reason']])))
            artifact = row.get('artifact_verdict', 'unreported')
            lines.append(f"| {task} | {row['repeat']} | {row['status']} | {artifact} | {row['outcome']} | {reasons} |")
        if 'required_handoff_rate' in condition:
            lines += ['', '| Metric | Count / denominator | Unmeasured reason | Other outcomes | Excluded slots |',
                      '| --- | ---: | --- | --- | --- |']
            for key, label in [('required_handoff_rate', 'Required handoff items'), ('recovery_success_rate', 'Fault recovery')]:
                metric = condition[key]
                excluded = metric['excluded_slots']
                reasons = ', '.join(f'{k}={v}' for k, v in sorted(metric['reason_counts'].items()) if k not in excluded)
                omitted = ', '.join(f'{k}={v}' for k, v in sorted(excluded.items()))
                lines.append(f"| {label} | {metric['numerator']}/{metric['denominator']} | {metric['missing_reason'] or ''} | {reasons} | {omitted} |")
    lines += ['','Native metrics use their original Inspect denominator; see report.json for values.','']
    return '\n'.join(line.rstrip() for line in lines)
