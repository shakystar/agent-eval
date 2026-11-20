"""Reference agreement and paired evaluator disagreement, with explicit coverage."""
from collections import Counter
from . import contracts as c
from .report import rate
from .review import get_bundle, validity


def reliability(store, evaluation_id, reference_id=None, peer_id=None):
    ev = store.get('evaluation', evaluation_id)
    if not reference_id and not peer_id:
        return {'schema_version':1, 'evaluation':evaluation_id, 'status':'unverified',
                'reason':'no_human_reference_selected', 'compared':0, 'agreement':rate(0,0),
                'false_positive_rate':rate(0,0), 'false_negative_rate':rate(0,0)}
    c.require(bool(reference_id) != bool(peer_id), 'select one reference set or peer evaluation')
    for judgment in ev['judgments']:
        for field in ('evidence_sha256','native_log_sha256','request_sha256','response_sha256','error_sha256'):
            if judgment.get(field): store.read_blob(judgment[field])
    rows = {(j['run'], j['criterion']): j for j in ev['judgments']}
    exclusions = Counter(); matrix = Counter(); agreements = 0; compared = 0
    if reference_id:
        ref = store.get('reference', reference_id)
        b = get_bundle(store, ref['bundle'])
        human = ref['origin'] == 'human'
        eligible = ref['bundle'] == ev['criterion_bundle']
        cases = ref['cases']
        counterpart = ref['reviewer']
        provenance = ref['origin']
        split = ref['split']
    else:
        c.require(peer_id != evaluation_id, 'select a different peer evaluation')
        peer = store.get('evaluation', peer_id)
        eligible = peer['experiment'] == ev['experiment'] and peer['criterion_bundle'] == ev['criterion_bundle']
        cases = [{'run': j['run'], 'criterion': j['criterion'], 'criterion_version':j['criterion_version'],
                  'output_sha256':j['evidence_sha256'], 'verdict':j['verdict'], 'processing':j['processing']} for j in peer['judgments']]
        counterpart = peer.get('evaluator', {}).get('id', peer['reviewer'])
        provenance = 'evaluator'; split = None
    c.require(eligible, 'comparison version/experiment mismatch')
    covered = set()
    for item in cases:
        key = (item['run'], item['criterion']); covered.add(key)
        j = rows.get(key)
        if not j:
            exclusions['missing_judgment'] += 1; continue
        if j['criterion_version'] != item['criterion_version'] or j['evidence_sha256'] != item['output_sha256']:
            exclusions['version_or_evidence_mismatch'] += 1; continue
        if j['evidence_sha256']:
            store.read_blob(j['evidence_sha256'])
        if j['processing'] != 'completed' or item.get('processing','completed') != 'completed':
            exclusions['evaluation_error'] += 1; continue
        if j['verdict'] == 'unknown' or item['verdict'] == 'unknown':
            exclusions['unknown'] += 1; continue
        compared += 1
        agreements += j['verdict'] == item['verdict']
        if j['verdict'] not in ('met','unmet') or item['verdict'] not in ('met','unmet'):
            exclusions['nonbinary_from_confusion_matrix'] += 1; continue
        matrix[('TP' if j['verdict']=='met' else 'FN') if item['verdict']=='met' else ('FP' if j['verdict']=='met' else 'TN')] += 1
    evaluator = ev.get('evaluator', {}).get('id', ev['reviewer'])
    applicable_tasks = {store.get('run', item['run'])['task'] for item in cases}
    approved = all(validity(store, ref['bundle'], t) == 'approved' for t in b['tasks'] if t['id'] in applicable_tasks) if reference_id else None
    synthetic_judge = ev.get('evaluator', {}).get('kind') == 'synthetic'
    verified = bool(reference_id and human and approved and compared and not synthetic_judge)
    result = {'schema_version':1,'evaluation':evaluation_id,'reference':reference_id,'peer':peer_id,
            'status':'measured_on_human_references' if verified else 'unverified' if reference_id else 'paired_evaluators',
            'reference_origin':provenance,'split':split,'reference_cases':len(cases),'compared':compared,
            'coverage':rate(compared,len(cases)), 'unreferenced_judgments':len(rows.keys()-covered),
            'agreement':rate(agreements,compared),'disagreement':rate(compared-agreements,compared),
            'confusion_matrix':{k:matrix[k] for k in ('TP','TN','FP','FN')},
            'false_positive_rate':rate(matrix['FP'],matrix['FP']+matrix['TN']),
            'false_negative_rate':rate(matrix['FN'],matrix['FN']+matrix['TP']),
            'excluded':dict(exclusions),'task_validity_approved':approved,'independent_identities':evaluator!=counterpart,
            'limits':['Identity provenance is caller-attested, not externally authenticated.',
                      'Rates apply only to the included cases; calibration is not held-out validation.',
                      'Reference agreement does not confirm model judgments or establish general reliability.']}
    if reference_id and not human:
        fields = ('compared', 'coverage', 'agreement', 'disagreement', 'confusion_matrix',
                  'false_positive_rate', 'false_negative_rate', 'excluded')
        result['synthetic_diagnostics'] = {field: result[field] for field in fields}
        result.update(compared=0, coverage=rate(0, len(cases)), agreement=rate(0, 0),
                      disagreement=rate(0, 0), confusion_matrix=dict.fromkeys(('TP', 'TN', 'FP', 'FN'), 0),
                      false_positive_rate=rate(0, 0), false_negative_rate=rate(0, 0),
                      excluded={'synthetic_reference': len(cases)})
    elif peer_id:
        # A peer can establish disagreement; its verdict is not a truth label.
        for field in ('confusion_matrix', 'false_positive_rate', 'false_negative_rate'):
            result.pop(field)
    return result
