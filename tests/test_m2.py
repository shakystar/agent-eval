import importlib.util
import unittest
from unittest.mock import patch

from agent_eval import contracts, semantic
from test_m1 import FixtureCase


@unittest.skipUnless(importlib.util.find_spec('inspect_ai'), 'requires pinned Inspect')
class SemanticTests(FixtureCase):
    def test_saved_artifacts_and_independent_reference(self):
        from inspect_ai.model import get_model, ModelOutput, ModelUsage

        self.ingest()
        outputs = [
            ModelOutput.from_content('mockllm/model', '{"verdict":"met","rationale":"artifact matches","citations":[{"source":"output","quote":"decision"}]}'),
            ModelOutput.from_content('mockllm/model', 'malformed')]
        for output in outputs:
            output.usage = ModelUsage(input_tokens=1, output_tokens=1, total_tokens=2)
        model = get_model('mockllm/model', custom_outputs=outputs)
        with patch('inspect_ai.model.get_model', return_value=model):
            result = semantic.grade(self.store, 'm1-demo', 'decision', 'private.txt', 's1', 'mockllm/model')
        self.assertEqual(result['counts'], dict(graded=1, scorer_error=1, missing_output=1))
        original = self.store.get('semantic', 's1')
        self.assertEqual(original['judgments'][1]['error_kind'], 'response_format')
        self.assertEqual(semantic.reliability(self.store, 's1')['status'], 'unverified')
        for run in ('run-1', 'run-2'):
            path = self.write('review.json', dict(evaluation='s1', run=run, reviewer='fixture-human',
                                                  reason='test only', verdict='unmet'))
            semantic.review(self.store, path, True)
        report = semantic.reliability(self.store, 's1')
        self.assertEqual((report['false_positive'], report['compared'], report['evaluator_unknown'],
                          report['missing_reference']), (1, 1, 1, 1))
        self.assertEqual(self.store.get('semantic', 's1'), original)
        with self.assertRaises(contracts.ContractError):
            semantic.grade(self.store, 'm1-demo', 'decision', 'private.txt', 's1', 'mockllm/model')

    def test_confusion_matrix_and_task_validity(self):
        judgments = [
            dict(run=str(i), verdict=v, status='graded')
            for i, v in enumerate(('met', 'met', 'unmet', 'unmet', 'met', 'unknown'))
        ]
        ev = dict(id='matrix', experiment='m1-demo', task='decision', bundle=self.exp['bundle'],
                  model='fixture', rubric_sha256='test', judgments=judgments)
        with self.store.db:
            self.store.put('semantic', 'matrix', ev)
        for i, verdict in enumerate(('met', 'unmet', 'met', 'unmet', 'unmet', 'unknown')):
            semantic.review(self.store, self.write('human.json', dict(
                evaluation='matrix', run=str(i), reviewer='fixture-human', verdict=verdict, reason='test')), True)
        task_review = dict(bundle='m1-fixture@1', task='decision', reviewer='fixture-human',
                           reason='test only', validity='rejected')
        semantic.review_task(self.store, self.write('task-review.json', task_review), True)
        report = semantic.reliability(self.store, 'matrix')
        self.assertEqual(report['task_validity'], 'rejected')
        self.assertEqual(report['compared'], 5)
        self.assertEqual(report['rates']['false_positive']['value'], 2/3)
        self.assertEqual(report['rates']['false_negative']['value'], 1/2)
        self.assertEqual(report['rates']['agreement']['value'], 2/5)
        self.assertEqual(report['human_unknown'], 1)

    def test_reparse_preserves_raw_response_and_original_error(self):
        raw = b'```json\n{"verdict":"met","reason":"valid"}\n```'
        for invalid in ('prefix ' + raw.decode(), raw.decode() + ' suffix'):
            with self.assertRaises(ValueError):
                semantic.verdict(invalid)
        row = dict(run='A', verdict='unknown', status='scorer_error',
                   response_sha256=self.store.blob(raw), error_sha256=self.store.blob(b'parse failed'))
        with self.store.db:
            self.store.put('semantic', 'original', dict(id='original', judgments=[row]))
        semantic.reparse(self.store, 'original', 'parsed')
        parsed = self.store.get('semantic', 'parsed')['judgments'][0]
        self.assertEqual(parsed['verdict'], 'met')
        self.assertEqual(self.store.read_blob(parsed['response_sha256']), raw)
        self.assertEqual(self.store.get('semantic', 'original')['judgments'][0], row)
