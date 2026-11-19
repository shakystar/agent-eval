"""Public reports exclude source text and private criteria."""
from collections import Counter
from .contracts import require
from .service import context


def flatten(obj, prefix=''):
    result = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            result.update(flatten(v, f'{prefix}.{k}' if prefix else k))
    else:
        result[prefix] = obj
    return result


def rate(n, d):
    return {'numerator': n, 'denominator': d, 'value': n/d if d else None,
            'missing_reason': None if d else 'zero_denominator'}


def report(store, experiment_id, evaluation_id):
    exp, tasks = context(store, experiment_id)
    ev = store.get('evaluation', evaluation_id)
    require(ev['experiment'] == experiment_id, 'evaluation/experiment mismatch')
    for source in store.all('source'):
        if store.get('evidence', source['evidence'])['experiment'] == experiment_id:
            store.read_blob(source['sha256'])
    for judgment in ev['judgments']:
        for field in ('evidence_sha256', 'native_log_sha256', 'error_sha256'):
            if judgment.get(field):
                store.read_blob(judgment[field])
    runs = [r for r in store.all('run') if r['experiment'] == experiment_id]
    base = next(c for c in exp['conditions'] if c['id'] == exp['baseline'])
    base_flat = flatten({k:v for k,v in base.items() if k != 'id'})
    conditions = []
    for cond in exp['conditions']:
        flat = flatten({k:v for k,v in cond.items() if k != 'id'})
        diffs = [k for k in sorted(flat.keys() | base_flat.keys()) if flat.get(k) != base_flat.get(k)]
        confounds = [k for k in diffs if k not in exp['varying_fields']]
        rows = []
        for task in tasks:
            for repeat in range(1, exp['repetitions']+1):
                match = [r for r in runs if (r['condition'],r['task'],r['repeat']) == (cond['id'],task,repeat)]
                row = {'task':task, 'repeat':repeat, 'run':None, 'status':'not_imported',
                       'outcome':'unknown', 'exclusion_reason':'missing_run'}
                if match:
                    r = match[0]
                    js = [j for j in ev['judgments'] if j['run'] == r['id']]
                    required = [j for j in js if j['required']]
                    errors = sum(j['processing'] == 'error' for j in js)
                    required_errors = sum(j['processing']=='error' for j in required)
                    if not required or required_errors or any(j['verdict']=='unknown' for j in required):
                        outcome, why = 'unknown', 'scorer_error' if required_errors else 'insufficient_evidence'
                    elif r['execution_status'] != 'completed':
                        outcome, why = 'unknown', 'execution_'+r['execution_status']
                    else:
                        outcome = 'met' if all(j['verdict']=='met' for j in required) else 'unmet'
                        why = None
                    row.update(run=r['id'], attempt_id=r['attempt_id'], status=r['execution_status'],
                               outcome=outcome, exclusion_reason=why,
                               environment_mismatch=r['environment'] != cond['environment'],
                               native_sample_id=r.get('sample_id'), native_epoch=r.get('epoch'),
                               native_score_states=dict(Counter(s['state'] for s in r['native']['scores'].values())),
                               native_error=r['native']['error'] is not None,
                               native_score_absent=not bool(r['native']['scores']),
                               item_counts=dict(Counter(j['verdict'] for j in js)), scorer_errors=errors,
                               item_met_rate=rate(sum(j['verdict']=='met' for j in js),sum(j['verdict']!='not_applicable' for j in js)),
                               measurements={k:{f:v for f,v in m.items() if f!='missing_reason'} for k,m in r['measurements'].items()},
                               missing_measurement_reasons={k:'not_measured' for k,m in r['measurements'].items() if m['value'] is None})
                rows.append(row)
        counts = Counter(r['outcome'] for r in rows)
        absent = sum(r['run'] is None for r in rows)
        mismatch = any(r.get('environment_mismatch') for r in rows)
        conditions.append({'condition':cond['id'], 'planned':len(rows), 'imported':len(rows)-absent,
            'judgeable':counts['met']+counts['unmet'], 'unknown':counts['unknown'],
            'status_counts':dict(Counter(r['status'] for r in rows)),
            'exclusion_counts':dict(Counter(r['exclusion_reason'] for r in rows if r['exclusion_reason'])),
            'overall_confirmed_success_rate':rate(0,len(rows)),
            'confirmed_success_note':'No human confirmation in M1; rule judgments remain draft.',
            'provisional_success_rate':rate(counts['met'],len(rows)),
            'provisional_judgeable_success_rate':rate(counts['met'],counts['met']+counts['unmet']),
            'missing_run_rate':rate(absent,len(rows)),
            'missing_measurement_rates':{k:rate(sum(r['run'] is None or k in r.get('missing_measurement_reasons',{}) for r in rows),len(rows)) for k in ('time','tokens','cost')},
            'condition_differences':diffs, 'unplanned_differences':confounds,
            'comparable':not confounds and not mismatch,
            'comparison_reasons':(['unplanned_condition_difference'] if confounds else [])+(['actual_environment_differs_from_plan'] if mismatch else []),
            'tasks':{t:{'planned':exp['repetitions'],'outcomes':dict(Counter(r['outcome'] for r in rows if r['task']==t))} for t in tasks},
            'runs':rows})
    native = []
    for e in store.all('evidence'):
        if e['experiment'] != experiment_id or not e['native_results']:
            continue
        result = e['native_results']
        native.append({'evidence':e['id'], 'total_samples':result.get('total_samples'),
                       'completed_samples':result.get('completed_samples'),
                       'metrics':[{'scorer':s.get('name'),'metrics':{k:v.get('value') for k,v in s.get('metrics',{}).items()}} for s in result.get('scores',[])],
                       'denominator_policy':'Inspect native metrics; not planned-run success rate'})
    return {'schema_version':1,'experiment':experiment_id,'evaluation':evaluation_id,
            'criterion_bundle':ev['criterion_bundle'],'parent_evaluation':ev['parent'],
            'confirmation':'draft','conclusion':'withheld_pending_task_validity_and_human_reference',
            'aggregation':'equal weight per planned task/repeat; missing runs stay in denominator',
            'conditions':conditions,'native_aggregates':native,
            'limitations':['Evidence-only M1; no execution, injection or semantic evaluator.',
                           'Task validity and evaluator reliability are not established.',
                           'No automatic human confirmation; raw outputs and private criteria omitted.']}


def markdown(obj):
    lines = ['# Evidence evaluation report','',f"Experiment: {obj['experiment']}; evaluation: {obj['evaluation']}.",'',
             'Draft rule judgments. Performance conclusions withheld.','',
             '| Condition | Planned | Imported | Judgeable | Provisional successes | Comparable |',
             '| --- | ---: | ---: | ---: | ---: | --- |']
    for c in obj['conditions']:
        label = c['condition'].replace('|','/').replace('\n',' ')
        lines.append(f"| {label} | {c['planned']} | {c['imported']} | {c['judgeable']} | {c['provisional_success_rate']['numerator']} | {c['comparable']} |")
    for condition in obj['conditions']:
        lines += ['', '## '+condition['condition'].replace('\n',' '), '',
                  'Condition differences: '+', '.join(condition['condition_differences']),
                  'Comparison restrictions: '+', '.join(condition['comparison_reasons']),
                  'Missing measurements: '+', '.join(k+'='+str(v['numerator'])+'/'+str(v['denominator']) for k,v in condition['missing_measurement_rates'].items()), '',
                  '| Task | Repeat | Execution | Outcome | Exclusion |',
                  '| --- | ---: | --- | --- | --- |']
        for row in condition['runs']:
            task=row['task'].replace('|','/').replace('\n',' ')
            lines.append(f"| {task} | {row['repeat']} | {row['status']} | {row['outcome']} | {row['exclusion_reason'] or ''} |")
    lines += ['','Native metrics use their original Inspect denominator; see report.json for values.','']
    return '\n'.join(lines)
