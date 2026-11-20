import json
import sqlite3
from unittest.mock import AsyncMock, Mock, patch

from agent_eval import contracts, graders, semantic
from test_m1 import FixtureCase


class RecoveryTests(FixtureCase):
    def grade(self):
        return semantic.grade(self.store, 'm1-demo', 'decision', 'private.txt', 'audit', 'test')

    def test_budget_checked_before_provider(self):
        # Create a separate valid experiment with an enforced zero-token limit.
        from agent_eval import service
        exp = dict(self.exp, id='zero', budget=dict(self.exp['budget'], evaluation=dict(
            mode='enforced', limit=0, unit='tokens', missing_reason=None)))
        service.register_experiment(self.store, self.write('zero.json', exp))
        with patch.object(graders, 'provider') as provider, self.assertRaises(contracts.ContractError):
            semantic.grade(self.store, 'zero', 'decision', 'private.txt', 'audit', 'test')
        provider.assert_not_called()

    def test_checkpoint_resume_and_concurrent_writer(self):
        self.ingest()
        calls = []
        async def call(key, prompt, payload):
            with sqlite3.connect(self.store.root/'index.sqlite', timeout=0) as db:
                db.execute('BEGIN IMMEDIATE')
            with self.assertRaises(contracts.ContractError):
                with semantic.evaluation_lock(self.store.root, 'audit'):
                    self.fail('duplicate grading owner')
            calls.append(key)
            if len(calls) == 2:
                raise KeyboardInterrupt()
            return '{"verdict":"met","reason":"observed"}', {}
        provider = Mock(backend={'name':'fixture'}, call=call)
        with patch.object(graders, 'provider', return_value=provider):
            with self.assertRaises(KeyboardInterrupt):
                self.grade()
            self.assertEqual(len(self.store.all('grading_result')), 1)
            self.grade()
        self.assertEqual(len(calls), 2)
        rows = self.store.get('semantic', 'audit')['judgments']
        self.assertEqual([row['status'] for row in rows], ['graded','scorer_error','missing_output'])
        self.assertEqual(rows[1]['failure']['execution'], 'unknown')

    def test_legacy_reference_reuse_and_correction(self):
        self.ingest()
        provider = Mock(backend={'name':'fixture'}, call=AsyncMock(return_value=(
            '{"verdict":"met","reason":"observed"}', {})))
        with patch.object(graders, 'provider', return_value=provider):
            self.grade()
        initial = dict(evaluation='audit',run='run-1',reviewer='human',reason='initial',verdict='unknown')
        with self.store.db:
            self.store.put('semantic_review', contracts.identity(['audit','run-1']), initial)
        semantic.reparse(self.store, 'audit', 'reparsed')
        self.assertEqual(semantic.reliability(self.store, 'reparsed')['human_unknown'], 1)
        ref = dict(initial, evaluation='reparsed', reason='corrected', verdict='met')
        path = self.write('ref.json', ref)
        semantic.review(self.store, path)
        semantic.review(self.store, path)
        self.assertEqual(semantic.reliability(self.store, 'audit')['agree'], 1)
        self.assertEqual([r['previous'] for r in self.store.all('reference_revision')], [initial])

    def test_codex_failure_contract_reaches_report(self):
        self.ingest()
        exe = self.root/'grader'
        failure = dict(version=1, stage='turn_submit', code='timeout', execution='unknown',
                       retryable=False, attempts=1)
        exe.write_text('#!/bin/sh\ncat >/dev/null\necho '+ "'" +json.dumps(dict(failure=failure))+"' >&2\nexit 1\n")
        exe.chmod(0o700)
        with patch.dict('os.environ', AGENT_EVAL_CODEX_GRADER=str(exe)):
            semantic.grade(self.store,'m1-demo','decision','private.txt','failed','codex-adapter/test')
        report = semantic.reliability(self.store,'failed')
        self.assertEqual(report['cases'][0]['failure'], failure)
        self.assertEqual(report['cases'][0]['error_kind'], 'dispatch')
