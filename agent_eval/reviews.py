"""Human reference history and reliability reports for stored evaluations."""
from collections import Counter

from . import contracts as c
from . import review as ledger
from .report import rate


def reference_key(ev, row):
    return c.identity([ev['experiment'], ev['bundle'], ev['task'], ev['rubric_sha256'],
                       row['run'], row.get('evidence_sha256')])


class ReferenceIndex:
    def __init__(self, store):
        self.latest = {}
        self.human = {}
        self.legacy = {}
        evaluations = {ev['id']: ev for ev in store.all('semantic')}
        for ref in store.all('semantic_review'):
            ev = evaluations[ref['evaluation']]
            row = next(j for j in ev['judgments'] if j['run'] == ref['run'])
            self.legacy.setdefault(reference_key(ev, row), []).append(ref)
        for ref in store.all('reference_revision'):
            self.latest[ref['key']] = ref
            if ref['review'].get('origin') == 'human':
                self.human[ref['key']] = ref['review']

    def current(self, ev, row, *, prefer_human=True):
        key = reference_key(ev, row)
        if prefer_human and key in self.human:
            return self.human[key]
        if key in self.latest:
            return self.latest[key]['review']
        records = self.legacy.get(key, [])
        for ref in records:
            if ref['evaluation'] == ev['id']:
                return ref
        if len({ref['verdict'] for ref in records}) == 1:
            return records[-1]
        return None


def provenance(obj, human_attested):
    origin = obj.get('origin', 'human' if human_attested else 'unattested')
    c.require(origin in ('synthetic', 'human', 'unattested'), 'invalid review origin')
    c.require(origin != 'human' or human_attested, 'human origin requires explicit attestation')
    return origin


def review(store, path, human_attested=False):
    obj = c.load(path)
    c.fields(obj, ['evaluation', 'run', 'reviewer', 'reason', 'verdict'], ['origin'])
    for value in obj.values():
        c.text(value)
    obj['origin'] = provenance(obj, human_attested)
    c.require(obj['verdict'] in ('met', 'unmet', 'unknown', 'not_applicable'), 'invalid reference verdict')
    ev = store.get('semantic', obj['evaluation'])
    row = next((j for j in ev['judgments'] if j['run'] == obj['run']), None)
    c.require(row is not None, 'unknown evaluated run')
    key = reference_key(ev, row)
    with store.db:
        store.db.execute('BEGIN IMMEDIATE')
        index = ReferenceIndex(store)
        previous = index.latest.get(key)
        current = index.current(ev, row, prefer_human=False)
        if current != obj:
            revision = 1 if previous is None else previous['revision'] + 1
            store.put('reference_revision', c.identity([key, revision]),
                      dict(key=key, revision=revision, review=obj, previous=current))
    return dict(evaluation=obj['evaluation'], run=obj['run'], origin=obj['origin'])


def review_task(store, path, human_attested=False):
    obj = c.load(path)
    if 'schema_version' in obj:
        record = ledger.task_review(store, path, human_attested)
        return dict(id=record['id'], task=record['task'], origin=record['origin'], validity=record['status'],
                    effective_validity=ledger.validity(store, record['bundle'],
                                                       dict(id=record['task'], version=record['task_version'])))
    c.fields(obj, ['bundle', 'task', 'reviewer', 'reason', 'validity'], ['origin'])
    for value in obj.values():
        c.text(value)
    c.require(obj['validity'] in ('approved', 'rejected', 'unreviewed'), 'invalid task review')
    bundle = store.get('bundle', obj['bundle'])
    task = next((t for t in bundle['tasks'] if t['id'] == obj['task']), None)
    c.require(task is not None, 'unknown task')
    bundle_ref = dict(id=bundle['id'], version=bundle['version'], sha256=c.identity(bundle))
    key = c.identity([bundle_ref, task['id'], task['version']])
    record = ledger.append_review(store, 'task_review', key, dict(bundle=bundle_ref, task=task['id'],
                         task_version=task['version'], reviewer=obj['reviewer'], reason=obj['reason'],
                         status=obj['validity'], origin=provenance(obj, human_attested)))
    return dict(id=record['id'], task=obj['task'], origin=record['origin'], validity=obj['validity'],
                effective_validity=ledger.validity(store, bundle_ref, task))


def reliability(store, evaluation):
    ev = store.get('semantic', evaluation)
    references = ReferenceIndex(store)
    counts = dict(true_positive=0, true_negative=0, false_positive=0, false_negative=0, missing_reference=0,
                  human_unknown=0, evaluator_unknown=0, synthetic_reference=0,
                  unattested_reference=0, not_applicable=0)
    cases = []
    for row in ev['judgments']:
        for key in ('evidence_sha256', 'response_sha256', 'error_sha256'):
            if row.get(key):
                store.read_blob(row[key])
        ref = references.current(ev, row)
        if ref is None:
            key = 'missing_reference'
        elif ref.get('origin', 'unattested') != 'human':
            key = ref.get('origin', 'unattested') + '_reference'
        elif ref['verdict'] == 'unknown':
            key = 'human_unknown'
        elif row['verdict'] == 'unknown':
            key = 'evaluator_unknown'
        elif 'not_applicable' in (ref['verdict'], row['verdict']):
            key = 'not_applicable'
        elif row['verdict'] == ref['verdict']:
            key = 'true_positive' if row['verdict'] == 'met' else 'true_negative'
        else:
            key = 'false_positive' if row['verdict'] == 'met' else 'false_negative'
        counts[key] += 1
        cases.append(dict(run=row['run'], draft=row['verdict'], processing=row['status'],
                          reference=ref['verdict'] if ref else None, comparison=key,
                          reference_origin=ref.get('origin', 'unattested') if ref else None,
                          failure=row.get('failure'), error_kind=row.get('error_kind')))
    disagree = counts['false_positive'] + counts['false_negative']
    agree = counts['true_positive'] + counts['true_negative']
    compared = agree + disagree
    bundle_key = f"{ev['bundle']['id']}@{ev['bundle']['version']}"
    bundle = store.get('bundle', bundle_key)
    task = next(t for t in bundle['tasks'] if t['id'] == ev['task'])
    validity = ledger.validity(store, ev['bundle'], task)
    return dict(cases=cases, task_validity=validity, evaluation=evaluation, total=len(ev['judgments']), compared=compared,
                status='compared' if compared else 'unverified', disagreement=disagree,
                model=ev['model'], rubric_sha256=ev['rubric_sha256'],
                grader_status_counts=dict(Counter(j['status'] for j in ev['judgments'])),
                agree=agree, agreement_rate=agree/compared if compared else None,
                rates=dict(agreement=rate(agree, compared), disagreement=rate(disagree, compared),
                           false_positive=rate(counts['false_positive'], counts['false_positive'] + counts['true_negative']),
                           false_negative=rate(counts['false_negative'], counts['false_negative'] + counts['true_positive'])),
                **counts)
