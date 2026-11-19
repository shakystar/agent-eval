"""Versioned JSON contracts. Unknown fields are rejected, never silently ignored."""
import hashlib
import json
import math
import re
from pathlib import Path


class ContractError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise ContractError(message)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def identity(value):
    return digest(canonical(value).encode())


def load(path):
    return loads(Path(path).read_text(encoding='utf-8'))


def loads(raw):
    def pairs(items):
        result = {}
        for k, v in items:
            require(k not in result, f'duplicate JSON key: {k}')
            result[k] = v
        return result
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ContractError('nonfinite JSON')))


def fields(obj, required, optional=()):
    require(isinstance(obj, dict), 'object required')
    require(set(required) <= obj.keys(), f'missing fields: {set(required) - obj.keys()}')
    require(obj.keys() <= set(required) | set(optional), f'unknown fields: {obj.keys() - set(required) - set(optional)}')


def text(value):
    require(isinstance(value, str) and bool(value.strip()), 'nonempty string required')


def positive(value):
    require(type(value) is int and value > 0, 'positive integer required')


def unique(items, key='id'):
    require(isinstance(items, list), 'list required')
    ids = [item[key] for item in items]
    for i in ids:
        text(i)
    require(len(set(ids)) == len(ids), f'duplicate {key}')


def reference(ref, root):
    fields(ref, ['id', 'path', 'sha256'])
    text(ref['id'])
    text(ref['path'])
    root = Path(root).resolve()
    p = (root / ref['path']).resolve()
    require(p.is_relative_to(root) and p.is_file(), 'reference must be an existing local file within manifest directory')
    data = p.read_bytes()
    require(digest(data) == ref['sha256'], 'reference hash mismatch')
    return data


def bundle(obj, root):
    fields(obj, ['schema_version', 'id', 'version', 'split', 'family', 'tasks'])
    require(obj['schema_version'] == 1, 'unsupported bundle schema')
    for k in ('id', 'version', 'family'):
        text(obj[k])
    require(obj['split'] in ('calibration', 'validation'), 'invalid split')
    unique(obj['tasks'])
    require(bool(obj['tasks']), 'empty task bundle')
    blobs = {}
    for t in obj['tasks']:
        fields(t, ['id', 'version', 'domain', 'source', 'inputs', 'evaluation', 'allowed_actions',
                   'outputs', 'completion', 'criteria', 'reference_path', 'validity'])
        for k in ('version', 'domain', 'source', 'completion'):
            text(t[k])
        for k in ('allowed_actions', 'outputs', 'reference_path'):
            require(isinstance(t[k], list), f'{k} must be a list')
            for entry in t[k]:
                text(entry)
        require(bool(t['outputs']), 'output contract required')
        require(t['validity'] in ('unreviewed', 'approved', 'rejected'), 'invalid validity')
        unique(t['inputs']); unique(t['evaluation'])
        require(not ({r['id'] for r in t['inputs']} & {r['id'] for r in t['evaluation']}), 'input/evaluation ID overlap')
        require(not ({r['sha256'] for r in t['inputs']} & {r['sha256'] for r in t['evaluation']}), 'input/evaluation content overlap')
        for ref in t['inputs'] + t['evaluation']:
            blobs[ref['sha256']] = reference(ref, root)
        unique(t['criteria'])
        require(bool(t['criteria']), 'criteria required')
        for c in t['criteria']:
            fields(c, ['id', 'version', 'required', 'kind', 'rule'])
            text(c['version'])
            require(type(c['required']) is bool, 'required must be boolean')
            require(c['kind'] == 'artifact', 'M1 rules support artifact criteria only; action/state verification requires an adapter')
            rule(c['rule'])
        require(any(c['required'] for c in t['criteria']), 'at least one required criterion')
    return blobs


def rule(obj):
    fields(obj, ['type', 'source'], ['value', 'pointer'])
    require(obj['source'] == 'output', 'M1 only supports saved output rules')
    require(obj['type'] in ('nonempty', 'contains', 'json_equals'), 'unsupported rule')
    if obj['type'] == 'contains':
        fields(obj, ['type', 'source', 'value']); text(obj['value'])
    elif obj['type'] == 'json_equals':
        fields(obj, ['type', 'source', 'pointer', 'value'])
        require(isinstance(obj['pointer'], str) and (not obj['pointer'] or obj['pointer'].startswith('/')), 'JSON pointer required')
        require(not re.search(r'~(?![01])', obj['pointer']), 'invalid JSON pointer escape')
        canonical(obj['value'])
    else:
        fields(obj, ['type', 'source'])


def experiment(obj, registered_bundle):
    fields(obj, ['schema_version', 'id', 'hypothesis', 'bundle', 'baseline', 'conditions',
                 'repetitions', 'budget', 'varying_fields', 'comparison_policy'])
    require(obj['schema_version'] == 1, 'unsupported experiment schema')
    for k in ('id', 'hypothesis'):
        text(obj[k])
    fields(obj['bundle'], ['id', 'version', 'sha256'])
    require(obj['bundle'] == {'id': registered_bundle['id'], 'version': registered_bundle['version'],
                              'sha256': identity(registered_bundle)}, 'bundle version/hash mismatch')
    positive(obj['repetitions'])
    unique(obj['conditions'])
    require(obj['baseline'] in [c['id'] for c in obj['conditions']], 'missing baseline')
    require(obj['comparison_policy'] == 'same-task-criteria-budget', 'unsupported comparison policy')
    require(isinstance(obj['varying_fields'], list) and all(isinstance(x, str) for x in obj['varying_fields']), 'invalid varying fields')
    fields(obj['budget'], ['execution', 'evaluation'])
    for b in obj['budget'].values():
        fields(b, ['limit', 'unit', 'mode', 'missing_reason'])
        require(b['mode'] in ('observational', 'enforced'), 'invalid budget mode')
        text(b['unit'])
        if b['limit'] is None:
            text(b['missing_reason'])
        else:
            require(type(b['limit']) in (int, float) and math.isfinite(b['limit']) and b['limit'] >= 0, 'invalid budget')
    for c in obj['conditions']:
        fields(c, ['id', 'target', 'model', 'roles', 'skills', 'environment'])
        fields(c['target'], ['adapter', 'version', 'execution_owner', 'retry_owner', 'auth_method'])
        for v in c['target'].values():
            text(v)
        fields(c['model'], ['name', 'settings', 'missing_reason'])
        if c['model']['name'] is None:
            text(c['model']['missing_reason'])
        else:
            text(c['model']['name'])
        require(isinstance(c['model']['settings'], dict), 'model settings must be object')
        for k in ('roles', 'skills'):
            unique(c[k])
            for item in c[k]:
                fields(item, ['id', 'version']); text(item['version'])
        environment(c['environment'])


def environment(obj):
    fields(obj, ['initial_state', 'reset', 'isolation', 'shared_state', 'session_policy'])
    for v in obj.values():
        text(v)


def run(obj, exp, tasks):
    fields(obj, ['id', 'task', 'condition', 'repeat', 'attempt_id', 'execution_status', 'environment',
                 'started', 'ended', 'receipt', 'measurements'], ['sample_id', 'epoch'])
    for k in ('id', 'attempt_id'):
        text(obj[k])
    require(obj['task'] in tasks, 'unknown task')
    require(obj['condition'] in [c['id'] for c in exp['conditions']], 'unknown condition')
    positive(obj['repeat']); require(obj['repeat'] <= exp['repetitions'], 'repeat outside plan')
    require(obj['execution_status'] in ('prepared', 'running', 'completed', 'failed', 'cancelled', 'uncertain'), 'invalid execution status')
    environment(obj['environment'])
    for k in ('started', 'ended', 'receipt'):
        require(obj[k] is None or isinstance(obj[k], str), f'invalid {k}')
    fields(obj['measurements'], ['time', 'tokens', 'cost'])
    for m in obj['measurements'].values():
        fields(m, ['value', 'unit', 'scope', 'completeness', 'missing_reason'])
        text(m['unit']); text(m['scope'])
        require(m['completeness'] in ('complete', 'partial', 'missing'), 'invalid measurement completeness')
        if m['value'] is None:
            text(m['missing_reason'])
            require(m['completeness'] == 'missing', 'null measurement must be marked missing')
        else:
            require(m['completeness'] != 'missing', 'measured value cannot be marked missing')
            require(type(m['value']) in (int, float) and math.isfinite(m['value']) and m['value'] >= 0, 'invalid measurement value')
