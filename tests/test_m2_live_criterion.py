import json
from unittest.mock import AsyncMock, Mock, patch

from agent_eval import contracts as c, graders, semantic, service
from agent_eval.report import report
from test_m1 import FixtureCase


class LiveCriterionTests(FixtureCase):
    def register_criterion(self):
        # Keep the original required rule to check partial-criterion reporting.
        task = self.bundle['tasks'][0]
        self.bundle['id'] = 'grounded-bundle'
        task['criteria'].append(dict(id='grounded', version='1', required=True, kind='artifact',
                                     rule=dict(type='semantic', source='output', needs=['inputs', 'output'],
                                               rubric='Cite the recorded decision.')))
        bundle = service.register_bundle(self.store, self.write('grounded-bundle.json', self.bundle))
        self.exp.update(id='grounded-test', bundle=bundle)
        service.register_experiment(self.store, self.write('grounded-experiment.json', self.exp))
        self.evidence['experiment'] = self.exp['id']
        service.import_evidence(self.store, self.write('grounded-evidence.json', self.evidence))

    def test_criterion_grades_preserve_citations_snapshots_and_ungraded_siblings(self):
        self.register_criterion()
        async def call(key, prompt, wire):
            payload = json.loads(wire)
            self.assertNotIn('cases', payload)
            quote = 'accept' if 'accept' in payload['sources']['output'] else 'unrecorded'
            return json.dumps(dict(verdict='met', rationale='recorded', citations=[
                dict(source='output', quote=quote)])), {'session': key}
        provider = Mock(backend={'name': 'fixture'}, call=call)
        with patch.object(graders, 'provider', return_value=provider):
            result = semantic.grade(self.store, self.exp['id'], 'decision', 'grounded', 'criterion-live', 'mockllm/model')
        self.assertEqual(result['counts'], dict(graded=1, scorer_error=1, missing_output=1))
        ev = self.store.get('evaluation', 'criterion-live')
        self.assertEqual(len(ev['run_snapshots']), 3)
        self.assertEqual(ev['evaluator']['kind'], 'synthetic')
        rows = {(j['run'], j['criterion']): j for j in ev['judgments']}
        hit = rows['run-1', 'grounded']
        self.assertEqual(hit['citations'], [dict(source='output', quote='accept')])
        self.assertEqual(hit['request_sha256'], c.identity(semantic.request(
            self.store, self.store.get('run', 'run-1'), self.bundle['tasks'][0],
            self.bundle['tasks'][0]['criteria'][1])[0]))
        self.assertEqual(rows['run-2', 'grounded']['reason_code'], 'response_format')
        self.assertEqual(rows['run-1', 'decision-field']['reason_code'], 'criterion_not_graded')
        self.assertEqual(report(self.store, self.exp['id'], 'criterion-live')['conditions'][0]['judgeable'], 0)
        with patch.object(graders, 'provider') as forbidden:
            semantic.reparse(self.store, 'criterion-live', 'reparsed')
            forbidden.assert_not_called()
        again = self.store.get('evaluation', 'reparsed')
        self.assertEqual(again['parent'], ev['id'])
        self.assertEqual([(j['verdict'], j['processing']) for j in again['judgments']],
                         [(j['verdict'], j['processing']) for j in ev['judgments']])
        self.assertNotEqual(ev['judgments'][0]['id'], again['judgments'][0]['id'])
        with self.assertRaises(c.ContractError):
            semantic.reparse(self.store, 'criterion-live', 'reparsed')

    def test_unfinished_v2_job_resumes_with_the_original_wire_contract(self):
        self.ingest()
        provider = Mock(backend={'name': 'fixture'}, call=AsyncMock(return_value=(
            '{"verdict":"met","reason":"archived schema"}', {})))
        task = self.bundle['tasks'][0]
        job = dict(id='interrupted-v2', experiment='m1-demo', task='decision', task_version='1',
                   bundle=self.exp['bundle'], rubric='private.txt', rubric_sha256=task['evaluation'][0]['sha256'],
                   model='test', parser_version=2, backend=provider.backend,
                   prompt_sha256=c.digest(semantic.LEGACY_PROMPT.encode()),
                   items=[dict(run='run-1', evidence_sha256=self.store.get('run', 'run-1')['output_sha256'])])
        with self.store.db:
            self.store.put('grading_job', job['id'], job)
        with patch.object(graders, 'provider', return_value=provider):
            result = semantic.grade(self.store, 'm1-demo', 'decision', 'private.txt', job['id'], 'test')
        self.assertEqual(result['counts'], {'graded': 1})
        _, prompt, wire = provider.call.await_args.args
        self.assertEqual(prompt, semantic.LEGACY_PROMPT)
        self.assertEqual(set(json.loads(wire)), {'rubric', 'task', 'artifact'})
        semantic.reparse(self.store, job['id'], 'v2-reparsed')
        self.assertEqual(self.store.get('semantic', 'v2-reparsed')['judgments'][0]['verdict'], 'met')

    def test_private_rubric_rejects_legacy_response_for_new_grade(self):
        self.ingest()
        provider = Mock(backend={'name': 'fixture'}, call=AsyncMock(return_value=(
            '{"verdict":"met","reason":"no evidence"}', {})))
        with patch.object(graders, 'provider', return_value=provider):
            result = semantic.grade(self.store, 'm1-demo', 'decision', 'private.txt', 'new', 'test')
        self.assertEqual(result['counts'], dict(scorer_error=2, missing_output=1))
        semantic.reparse(self.store, 'new', 'new-reparsed')
        self.assertEqual(self.store.get('semantic', 'new-reparsed')['judgments'][0]['error_kind'], 'response_format')
