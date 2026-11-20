"""Explicit local operations; registration/import/regrading cannot execute an agent."""
import json
from pathlib import Path
from . import contracts as c


def register_bundle(store, path):
    obj = c.load(path)
    blobs = c.bundle(obj, Path(path).parent)
    with store.db:
        for data in blobs.values():
            store.blob(data)
        store.put('bundle', f"{obj['id']}@{obj['version']}", obj)
        for task in obj['tasks']:
            store.put('task_contract', c.canonical([obj['id'], task['id'], task['version']]), task)
            for criterion in task['criteria']:
                store.put('criterion_contract', c.canonical([obj['id'], task['id'], criterion['id'], criterion['version']]), criterion)
    return {'id': obj['id'], 'version': obj['version'], 'sha256': c.identity(obj)}


def register_experiment(store, path):
    obj = c.load(path)
    b = obj.get('bundle', {})
    bundle = store.get('bundle', f"{b.get('id')}@{b.get('version')}")
    c.experiment(obj, bundle)
    with store.db:
        store.put('experiment', obj['id'], obj)
    return obj['id']


def context(store, experiment_id):
    exp = store.get('experiment', experiment_id)
    b = exp['bundle']
    bundle = store.get('bundle', f"{b['id']}@{b['version']}")
    return exp, {t['id']: t for t in bundle['tasks']}


def execution_input(store, experiment_id, task_id):
    _, tasks = context(store, experiment_id)
    c.require(task_id in tasks, 'unknown task')
    t = tasks[task_id]
    # Whitelist only. Evaluation files, completion/rules/targets never enter this projection.
    return {'task': t['id'], 'version': t['version'], 'allowed_actions': t['allowed_actions'],
            'outputs': t['outputs'], 'inputs': [
                {'id': r['id'], 'sha256': r['sha256'], 'text': store.read_blob(r['sha256']).decode('utf-8')}
                for r in t['inputs']]}


def import_evidence(store, manifest_path, *, execution_receipt=None):
    manifest = c.load(manifest_path)
    c.fields(manifest, ['schema_version', 'id', 'experiment', 'format', 'source', 'runs'])
    c.require(manifest['schema_version'] == 1, 'unsupported evidence schema')
    c.text(manifest['id'])
    exp, tasks = context(store, manifest['experiment'])
    c.unique(manifest['runs'])
    c.require(bool(manifest['runs']), 'empty evidence import')
    root = Path(manifest_path).parent
    raw = c.reference(manifest['source'], root)
    source_hash = c.digest(raw)
    native = None
    output_blobs = {}
    if manifest['format'] == 'inspect':
        from . import inspect_adapter
        native = inspect_adapter.read(raw)
        semantic = c.identity(native['semantic'])
        native_key = native['eval_id']
        backend = inspect_adapter.backend()
    elif manifest['format'] == 'saved-output-v1':
        source = c.loads(raw.decode('utf-8'))
        c.fields(source, ['schema_version', 'id', 'records'])
        c.require(source['schema_version'] == 1, 'unsupported saved output schema')
        c.text(source['id']); c.unique(source['records'])
        semantic = c.identity(source)
        native_key = source['id']
        backend = {'name': 'saved-output', 'version': '1'}
    else:
        raise c.ContractError('unsupported evidence format')
    entries = []
    used = set()
    for r in manifest['runs']:
        c.run(r, exp, tasks)
        if native:
            c.require('sample_id' in r and 'epoch' in r, 'sample_id and epoch required')
            c.positive(r['epoch'])
            c.require(type(r['sample_id']) in (int, str), 'invalid sample ID')
            key = (type(r['sample_id']).__name__, r['sample_id'], r['epoch'])
            matches = [s for s in native['samples'] if (type(s['id']).__name__, s['id'], s['epoch']) == key]
            c.require(len(matches) == 1, 'sample/epoch reference not found')
            s = matches[0]
            output = s['output']
            native_state = {'scores': s['scores'], 'error': s['error'], 'log_status': native['status']}
        else:
            c.require('sample_id' not in r and 'epoch' not in r, 'saved-output has no native sample selector')
            key = r['id']
            matches = [s for s in source['records'] if s['id'] == key]
            c.require(len(matches) == 1, 'saved-output run reference not found')
            s = matches[0]
            c.fields(s, ['id', 'output', 'missing_reason'])
            if s['output'] is None:
                c.text(s['missing_reason']); output = None
            else:
                data = c.reference(s['output'], root)
                output = data.decode('utf-8')
            native_state = {'scores': {}, 'error': None, 'log_status': None}
        c.require(key not in used, 'native sample mapped more than once')
        used.add(key)
        sha = None
        if output is not None:
            data = output.encode('utf-8'); sha = c.digest(data); output_blobs[sha] = data
        entries.append({**r, 'experiment': exp['id'], 'evidence': manifest['id'], 'native_id': native_key,
                        'output_sha256': sha, 'native': native_state,
                        'missing_reason': ('native output absent' if native else s['missing_reason']) if sha is None else None})
    expected = len(native['samples']) if native else len(source['records'])
    c.require(len(used) == expected, 'every native sample/record requires explicit mapping')
    record = {'id': manifest['id'], 'experiment': exp['id'], 'format': manifest['format'],
              'native_id': native_key, 'semantic_sha256': semantic, 'backend': backend,
              'run_ids': [r['id'] for r in entries], 'native_results': native['results'] if native else None}
    with store.db:
        store.db.execute('BEGIN IMMEDIATE')
        # Native ID and semantic content are independent of file compression/serialization.
        store.put('native_identity', manifest['format'] + ':' + native_key, {'sha256': semantic, 'evidence': manifest['id']})
        created = store.put('evidence', manifest['id'], record)
        store.blob(raw)
        store.put('source', manifest['id'] + ':' + source_hash,
                  {'evidence': manifest['id'], 'sha256': source_hash})
        for data in output_blobs.values():
            store.blob(data)
        for r in entries:
            store.slot(exp['id'], r)
            if execution_receipt is not None:
                c.require(r['receipt'] == execution_receipt and store.find('execution_binding', r['id']),
                          'execution evidence binding mismatch')
                store.observe('run', r['id'], r)
            else:
                if store.find('execution_binding', r['id']) and not store.find('run', r['id']):
                    raise c.ContractError('slot reserved for execution')
                if not store.observed('run', r['id'], r):
                    store.put('run', r['id'], r)
    return {'id': manifest['id'], 'duplicate': not created, 'runs': len(entries)}


def require_free_evaluation_id(store, evaluation_id):
    c.require(all(store.find(kind, evaluation_id) is None
                  for kind in ('evaluation', 'semantic', 'grading_job')), 'evaluation ID already exists or is reserved')


def evaluate(store, experiment_id, evaluation_id, reviewer, reason, parent=None, bundle_ref=None, judge=None):
    c.text(evaluation_id); c.text(reviewer); c.text(reason)
    exp, tasks = context(store, experiment_id)
    if bundle_ref:
        b = store.get('bundle', bundle_ref)
        tasks = {t['id']: t for t in b['tasks']}
        baseline = context(store, experiment_id)[1]
        c.require(tasks.keys() == baseline.keys(), 'regrade task set changed')
        for key in tasks:
            # Only criterion changes are permitted for a stored-evidence regrade.
            c.require({k:v for k,v in tasks[key].items() if k not in ('criteria', 'version')} ==
                      {k:v for k,v in baseline[key].items() if k not in ('criteria', 'version')},
                      'regrade changed task inputs or completion contract')
            old = {c['id']: c for c in baseline[key]['criteria']}
            for criterion in tasks[key]['criteria']:
                previous = old.get(criterion['id'])
                c.require(not previous or criterion == previous or criterion['version'] != previous['version'],
                          'changed criterion requires a new version')
        criterion_bundle = {'id': b['id'], 'version': b['version'], 'sha256': c.identity(b)}
    else:
        criterion_bundle = exp['bundle']
    if any(cn['rule']['type'] == 'semantic' for t in tasks.values() for cn in t['criteria']):
        from .semantic import SavedJudge
        c.require(type(judge) is SavedJudge,
                  'saved semantic evaluation requires recorded responses; use semantic-grade for live grading')
    if parent:
        c.require(store.get('evaluation', parent)['experiment'] == experiment_id, 'parent experiment mismatch')
    require_free_evaluation_id(store, evaluation_id)
    # Verify preserved originals before using derived evidence.
    for src in store.all('source'):
        if store.get('evidence', src['evidence'])['experiment'] == experiment_id:
            store.read_blob(src['sha256'])
    from . import inspect_adapter
    backend = inspect_adapter.backend()
    judgments = []
    run_snapshots = {}
    for r in store.current_runs():
        if r['experiment'] != experiment_id:
            continue
        run_snapshots[r['id']] = store.blob(c.canonical(r).encode())
        sha = r['output_sha256']
        output = store.read_blob(sha).decode('utf-8') if sha else None
        for criterion in tasks[r['task']]['criteria']:
            judgment = {'id': c.identity([evaluation_id, r['id'], criterion['id']]), 'run': r['id'],
                        'criterion': criterion['id'], 'criterion_version': criterion['version'],
                        'required': criterion['required'], 'evidence_sha256': sha,
                        'confirmation': 'draft', 'verdict': 'unknown', 'processing': 'completed',
                        'reason_code': None, 'native_log_sha256': None, 'backend': backend}
            if output is None:
                judgment['reason_code'] = 'missing_output'
            else:
                try:
                    if criterion['rule']['type'] == 'semantic':
                        from .semantic import evaluate as semantic_evaluate
                        result, data = semantic_evaluate(store, r, tasks[r['task']], criterion, judge)
                    else:
                        result, data = inspect_adapter.evaluate(output, criterion, r['native_id'],
                                                               r.get('sample_id', r['id']), r.get('epoch', 1))
                    judgment.update(result)
                    if data is not None:
                        store.blob(data)
                except Exception as exc:
                    # Error text may contain hidden criteria; retain details only in private blob.
                    error_hash = store.blob(str(exc).encode('utf-8'))
                    judgment.update(processing='error', reason_code='scorer_error', error_sha256=error_hash)
            judgments.append(judgment)
    obj = {'id': evaluation_id, 'experiment': experiment_id, 'parent': parent, 'reviewer': reviewer,
           'reason': reason, 'criterion_bundle': criterion_bundle, 'backend': backend,
           'confirmation': 'draft', 'judgments': judgments, 'run_snapshots': run_snapshots,
           'evaluator': judge.identity if judge else {'id': 'inspect-rules', 'kind': 'rule', 'version': '1'}}
    with store.db:
        store.db.execute('BEGIN IMMEDIATE')
        require_free_evaluation_id(store, evaluation_id)
        store.put('evaluation', evaluation_id, obj)
    return obj
