"""Regression coverage for the two generations of review records in a single store."""
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

from agent_eval import contracts as c, review, reviews
from agent_eval.store import Store


class MixedReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = Store(self.root / 'store')
        self.addCleanup(self.store.close)
        self.task = dict(id='handoff', version='1')
        bundle = dict(id='demo', version='1', tasks=[self.task])
        self.bundle = dict(id='demo', version='1', sha256=c.identity(bundle))
        evaluation = dict(id='e', experiment='x', bundle=self.bundle, task='handoff', model='fixture',
                          rubric_sha256='rubric', judgments=[dict(run='r', verdict='met', status='graded')])
        with self.store.db:
            self.store.put('bundle', 'demo@1', bundle)
            self.store.put('semantic', 'e', evaluation)

    def write(self, name, obj):
        path = self.root / name
        path.write_text(json.dumps(obj), encoding='utf-8')
        return path

    def test_unattested_and_synthetic_never_replace_human_reference(self):
        compact = dict(evaluation='e', run='r', reviewer='one', verdict='met', reason='review')
        with self.store.db:
            self.store.put('semantic_review', 'legacy', compact)
        self.assertEqual(reviews.reliability(self.store, 'e')['unattested_reference'], 1)
        synthetic = self.write('synthetic.json', dict(compact, origin='synthetic', verdict='unmet'))
        reviews.review(self.store, synthetic)
        result = reviews.reliability(self.store, 'e')
        self.assertEqual((result['synthetic_reference'], result['compared']), (1, 0))
        human = self.write('human.json', dict(compact, origin='human'))
        with self.assertRaisesRegex(c.ContractError, 'attestation'):
            reviews.review(self.store, human)
        reviews.review(self.store, human, True)
        reviews.review(self.store, synthetic)
        result = reviews.reliability(self.store, 'e')
        self.assertEqual((result['agree'], result['compared'], result['cases'][0]['reference_origin']),
                         (1, 1, 'human'))

    def test_legacy_approval_needs_attestation_and_both_formats_share_head(self):
        compact = dict(bundle='demo@1', task='handoff', reviewer='reviewer', reason='checked', validity='approved')
        with self.store.db:
            self.store.put('task_review', 'old-record', compact)
        self.assertEqual(review.validity(self.store, self.bundle, self.task), 'unreviewed')
        path = self.write('compact.json', compact)
        reviews.review_task(self.store, path, True)
        reviews.review_task(self.store, path, True)
        records = self.store.all('task_review')
        self.assertEqual(len(records), 2)
        revoke = dict(schema_version=1, id='revoke', bundle=self.bundle, task='handoff', task_version='1',
                      status='rejected', supersedes=records[-1]['id'], reviewer='reviewer', origin='human',
                      source='review', created='2026-01-01T00:00:00+00:00', reason='scope changed')
        reviews.review_task(self.store, self.write('revoke.json', revoke), True)
        self.assertEqual(reviews.reliability(self.store, 'e')['task_validity'], 'rejected')
        self.assertEqual(review.validity(self.store, self.bundle, self.task), 'rejected')
        self.assertEqual(self.store.all('task_review')[0], compact)

    def test_reference_on_missing_output_is_not_a_comparable_verdict(self):
        ev = self.store.get('semantic', 'e')
        ev.update(id='missing', judgments=[dict(run='no-output', verdict='unknown', status='missing_output')])
        with self.store.db:
            self.store.put('semantic', ev['id'], ev)
        item = dict(evaluation='missing', run='no-output', verdict='unmet', reviewer='one', reason='independent')
        reviews.review(self.store, self.write('missing.json', item), True)
        report = reviews.reliability(self.store, 'missing')
        self.assertEqual(report['cases'][0]['reference'], 'unmet')
        self.assertEqual((report['evaluator_unknown'], report['compared'], report['status']),
                         (1, 0, 'unverified'))

    def test_concurrent_reviews_cannot_create_two_successors(self):
        gate = Barrier(2)
        def submit(revision):
            writer = Store(self.store.root)
            try:
                gate.wait(timeout=10)
                review.append_review(writer, 'judgment_review', 'subject', dict(id=revision, supersedes=None))
                return 'written'
            except c.ContractError:
                return 'stale'
            finally:
                writer.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertCountEqual(pool.map(submit, ('first', 'second')), ['written', 'stale'])
        self.assertEqual(len(self.store.all('judgment_review')), 1)
