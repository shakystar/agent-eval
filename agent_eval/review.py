"""Append-only human review and reference contracts. Assertions are not identity authentication."""
from datetime import datetime
from . import contracts as c

AUDIT = ['reviewer', 'origin', 'source', 'created', 'reason']
VERDICTS = ('met', 'unmet', 'unknown', 'not_applicable')


def audit(obj, human_attested):
    for k in ('reviewer', 'source', 'reason'):
        c.text(obj[k])
    c.require(obj['origin'] in ('human', 'synthetic'), 'invalid review origin')
    c.require(obj['origin'] != 'human' or human_attested, 'human origin requires explicit attestation')
    stamp = datetime.fromisoformat(obj['created'])
    c.require(stamp.tzinfo is not None, 'review timestamp must include timezone')


def get_bundle(store, ref):
    c.fields(ref, ['id', 'version', 'sha256'])
    b = store.get('bundle', ref['id']+'@'+ref['version'])
    c.require(c.identity(b) == ref['sha256'], 'review bundle hash mismatch')
    return b


def append_review(store, kind, key, obj):
    with store.db:
        store.db.execute('BEGIN IMMEDIATE')
        matches = [x for x in store.all(kind) if x.get('subject') == key]
        latest = matches[-1] if matches else None
        if 'id' not in obj:
            # The original short-form command has no revision ID. Bind it to
            # the current head while holding the same lock as the write.
            if latest and all(latest.get(field) == value for field, value in obj.items()):
                return latest
            parent_id = latest['id'] if latest else None
            obj = dict(obj, supersedes=parent_id, id=c.identity([key, parent_id, obj]))
        # Idempotence is allowed; stale or branching edits are not.
        same = next((x for x in matches if x['id'] == obj['id']), None)
        if same:
            c.require(same == {**obj, 'subject': key}, 'review ID conflict')
            return same
        c.require(obj['supersedes'] == (latest['id'] if latest else None), 'review must supersede current head')
        result = {**obj, 'subject': key}
        store.put(kind, obj['id'], result)
    return result


def task_review(store, path, human_attested=False):
    obj = c.load(path)
    c.fields(obj, ['schema_version','id','bundle','task','task_version','status','supersedes']+AUDIT)
    c.require(obj['schema_version'] == 1, 'unsupported task review schema'); c.text(obj['id'])
    audit(obj, human_attested)
    b = get_bundle(store, obj['bundle'])
    t = next((t for t in b['tasks'] if t['id'] == obj['task']), None)
    c.require(t is not None and t['version'] == obj['task_version'], 'review task/version mismatch')
    c.require(obj['status'] in ('unreviewed','approved','rejected'), 'invalid task validity')
    key = c.identity([obj['bundle'], obj['task'], obj['task_version']])
    return append_review(store, 'task_review', key, obj)


def validity(store, bundle_ref, task):
    key = c.identity([bundle_ref, task['id'], task['version']])
    records = [r for r in store.all('task_review') if r.get('subject') == key and r.get('origin') == 'human']
    return records[-1]['status'] if records else 'unreviewed'


def judgment_review(store, path, human_attested=False):
    obj = c.load(path)
    c.fields(obj, ['schema_version','id','evaluation','judgment','verdict','supersedes']+AUDIT)
    c.require(obj['schema_version'] == 1, 'unsupported judgment review schema'); c.text(obj['id'])
    audit(obj, human_attested)
    ev = store.get('evaluation', obj['evaluation'])
    j = next((j for j in ev['judgments'] if j['id'] == obj['judgment']), None)
    c.require(j is not None, 'unknown reviewed judgment')
    c.require(obj['verdict'] in VERDICTS, 'invalid reviewed verdict')
    if obj['verdict'] in ('met','unmet'):
        c.require(bool(j['evidence_sha256']), 'binary review requires evidence')
        store.read_blob(j['evidence_sha256'])
    return append_review(store, 'judgment_review', obj['evaluation']+':'+obj['judgment'], obj)


def effective_judgment(store, evaluation_id, judgment):
    records = [r for r in store.all('judgment_review') if r['subject'] == evaluation_id+':'+judgment['id'] and r['origin'] == 'human']
    if not records:
        return judgment
    r = records[-1]
    return {**judgment, 'verdict': r['verdict'], 'processing': 'completed', 'confirmation': 'confirmed', 'review_id': r['id']}


def reference_set(store, path, human_attested=False):
    obj = c.load(path)
    c.fields(obj, ['schema_version','id','version','bundle','split','cases']+AUDIT)
    c.require(obj['schema_version'] == 1, 'unsupported reference schema')
    c.text(obj['id']); c.text(obj['version']); audit(obj, human_attested)
    b = get_bundle(store, obj['bundle'])
    c.require(obj['split'] == b['split'], 'reference split/bundle mismatch')
    c.unique(obj['cases']); c.require(bool(obj['cases']), 'empty reference set')
    seen = set()
    for item in obj['cases']:
        c.fields(item, ['id','run','criterion','criterion_version','criterion_sha256','output_sha256','verdict','rationale'])
        c.text(item['rationale'])
        r = store.latest('run', item['run'])
        c.require(r is not None, 'unknown reference run')
        exp = store.get('experiment', r['experiment'])
        c.require(exp['bundle'] == obj['bundle'], 'reference belongs to a different task bundle')
        t = next(t for t in b['tasks'] if t['id'] == r['task'])
        criterion = next((x for x in t['criteria'] if x['id'] == item['criterion']), None)
        c.require(criterion is not None and criterion['version'] == item['criterion_version'] and c.identity(criterion) == item['criterion_sha256'], 'reference criterion mismatch')
        c.require(item['verdict'] in VERDICTS, 'invalid reference verdict')
        c.require(item['output_sha256'] == r['output_sha256'], 'reference evidence mismatch')
        if item['verdict'] in ('met','unmet'):
            c.require(bool(item['output_sha256']), 'binary reference requires evidence')
        if item['output_sha256']:
            store.read_blob(item['output_sha256'])
        key = (item['run'], item['criterion'])
        c.require(key not in seen, 'duplicate reference case'); seen.add(key)
    with store.db:
        store.put('reference', obj['id']+'@'+obj['version'], obj)
    return obj
