"""Human reference history and reliability reports for stored evaluations."""
from collections import Counter

from . import contracts as c
from .report import rate


def reference_key(ev, row):
    return c.identity([ev['experiment'], ev['bundle'], ev['task'], ev['rubric_sha256'],
                       row['run'], row.get('evidence_sha256')])


class ReferenceIndex:
    def __init__(self, store):
        self.latest = {}
        self.legacy = {}
        evaluations = {ev['id']: ev for ev in store.all('semantic')}
        for ref in store.all('semantic_review'):
            ev = evaluations[ref['evaluation']]
            row = next(j for j in ev['judgments'] if j['run'] == ref['run'])
            self.legacy.setdefault(reference_key(ev, row), []).append(ref)
        for ref in store.all('reference_revision'):
            self.latest[ref['key']] = ref

    def current(self, ev, row):
        key = reference_key(ev, row)
        if key in self.latest:
            return self.latest[key]['review']
        records = self.legacy.get(key, [])
        for ref in records:
            if ref['evaluation'] == ev['id']:
                return ref
        if len({ref['verdict'] for ref in records}) == 1:
            return records[-1]
        return None


def review(store, path):
    obj = c.load(path)
    c.fields(obj, ['evaluation', 'run', 'reviewer', 'reason', 'verdict'])
    for value in obj.values():
        c.text(value)
    c.require(obj['verdict'] in ('met', 'unmet', 'unknown'), 'invalid human verdict')
    ev = store.get('semantic', obj['evaluation'])
    row = next((j for j in ev['judgments'] if j['run'] == obj['run']), None)
    c.require(row is not None, 'unknown evaluated run')
    key = reference_key(ev, row)
    with store.db:
        store.db.execute('BEGIN IMMEDIATE')
        index = ReferenceIndex(store)
        previous = index.latest.get(key)
        current = index.current(ev, row)
        if current != obj:
            revision = 1 if previous is None else previous['revision'] + 1
            store.put('reference_revision', c.identity([key, revision]),
                      dict(key=key, revision=revision, review=obj, previous=current))
    return dict(evaluation=obj['evaluation'], run=obj['run'])


def review_task(store, path):
    obj = c.load(path)
    c.fields(obj, ['bundle', 'task', 'reviewer', 'reason', 'validity'])
    for value in obj.values():
        c.text(value)
    c.require(obj['validity'] in ('approved', 'rejected'), 'invalid task review')
    bundle = store.get('bundle', obj['bundle'])
    c.require(any(t['id'] == obj['task'] for t in bundle['tasks']), 'unknown task')
    with store.db:
        store.put('task_review', c.identity([c.identity(bundle), obj['task']]), obj)
    return dict(task=obj['task'], validity=obj['validity'])


def reliability(store, evaluation):
    ev = store.get('semantic', evaluation)
    references = ReferenceIndex(store)
    counts = dict(true_positive=0, true_negative=0, false_positive=0, false_negative=0, missing_reference=0,
                  human_unknown=0, evaluator_unknown=0)
    cases = []
    for row in ev['judgments']:
        for key in ('evidence_sha256', 'response_sha256', 'error_sha256'):
            if row.get(key):
                store.read_blob(row[key])
        ref = references.current(ev, row)
        if ref is None:
            key = 'missing_reference'
        elif ref['verdict'] == 'unknown':
            key = 'human_unknown'
        elif row['verdict'] == 'unknown':
            key = 'evaluator_unknown'
        elif row['verdict'] == ref['verdict']:
            key = 'true_positive' if row['verdict'] == 'met' else 'true_negative'
        else:
            key = 'false_positive' if row['verdict'] == 'met' else 'false_negative'
        counts[key] += 1
        cases.append(dict(run=row['run'], draft=row['verdict'], processing=row['status'],
                          reference=ref['verdict'] if ref else None, comparison=key,
                          failure=row.get('failure'), error_kind=row.get('error_kind')))
    disagree = counts['false_positive'] + counts['false_negative']
    agree = counts['true_positive'] + counts['true_negative']
    compared = agree + disagree
    bundle_key = f"{ev['bundle']['id']}@{ev['bundle']['version']}"
    validity = next((r['validity'] for r in store.all('task_review')
                     if r['bundle'] == bundle_key and r['task'] == ev['task']), 'unreviewed')
    return dict(cases=cases, task_validity=validity, evaluation=evaluation, total=len(ev['judgments']), compared=compared,
                status='compared' if compared else 'unverified', disagreement=disagree,
                model=ev['model'], rubric_sha256=ev['rubric_sha256'],
                grader_status_counts=dict(Counter(j['status'] for j in ev['judgments'])),
                agree=agree, agreement_rate=agree/compared if compared else None,
                rates=dict(agreement=rate(agree, compared), disagreement=rate(disagree, compared),
                           false_positive=rate(counts['false_positive'], counts['false_positive'] + counts['true_negative']),
                           false_negative=rate(counts['false_negative'], counts['false_negative'] + counts['true_positive'])),
                **counts)
