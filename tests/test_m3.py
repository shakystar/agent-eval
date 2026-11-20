import copy
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from agent_eval import contracts as c, execution, service
from agent_eval.store import Store
from examples.m3.create_example import make


@unittest.skipUnless(shutil.which('runtime-bridge') and importlib.util.find_spec('role_orchestrator'),
                     'requires the M3 Go bridge and orchestrator environment')
class ExecutionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.store = Store(self.root/'store')
        self.addCleanup(self.store.close)
        self.inputs = self.root/'inputs'
        make(self.inputs)
        service.register_bundle(self.store,self.inputs/'bundle.json')
        service.register_experiment(self.store,self.inputs/'experiment.json')

    def execute(self, condition, repeat=1, bridge='runtime-bridge'):
        return execution.execute(self.store,'notice-m3-fixture','notice',condition,repeat,bridge,'codex')

    def test_isolation_receipts_and_idempotence(self):
        one = self.execute('solo')
        two = self.execute('solo',2)
        self.assertNotEqual(one['runtime_run'],two['runtime_run'])
        self.assertNotEqual(one['stages'][0]['attempt_id'],two['stages'][0]['attempt_id'])
        self.assertEqual(self.execute('solo',bridge='/missing'),one)
        self.assertEqual(len(self.store.all('run')),2)
        row = one['stages'][0]
        raw = self.store.read_blob(row['input_sha256']).decode()
        self.assertIn('14:00',raw)
        self.assertNotIn('Fail contradictory claims',raw)
        self.assertEqual(c.loads(self.store.read_blob(row['receipt_sha256']))['task']['input'],raw)
        self.assertEqual(c.loads(self.store.read_blob(row['wire_sha256']))['attempt_id'],row['attempt_id'])

    def test_revision_and_injections(self):
        control = self.execute('team')
        material = self.execute('material')
        fault = self.execute('fault')
        self.assertEqual([r['stage'] for r in control['stages']],['write','review','revise','final-review'])
        self.assertEqual(control['review'],'accept')
        self.assertEqual(material['stages'][1]['before_sha256'],control['stages'][1]['input_sha256'])
        self.assertNotEqual(material['stages'][1]['input_sha256'],material['stages'][1]['before_sha256'])
        self.assertEqual(fault['injections'][0]['recovery'],'read_succeeded')
        self.assertEqual(fault['stages'][1]['input_sha256'],control['stages'][1]['input_sha256'])
        self.assertEqual(self.execute('fault'),fault)
        self.assertEqual(len(self.store.all('tool_failure')),1)

    def test_interrupted_request_never_replayed(self):
        from role_orchestrator.runtime import Runtime
        with patch.object(Runtime,'execute',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.execute('solo')
        with patch.object(Runtime,'execute',side_effect=AssertionError('unexpected replay')):
            run = self.execute('solo')
        self.assertEqual(run['status'],'uncertain')
        self.assertEqual(self.store.get('run',run['id'])['execution_status'],'uncertain')

    def test_interrupted_after_native_success_recovers_same_receipt(self):
        from role_orchestrator.runtime import Runtime
        execute = Runtime.execute

        def interrupt_after_receipt(runtime, request):
            execute(runtime, request)
            raise KeyboardInterrupt

        with patch.object(Runtime, 'execute', interrupt_after_receipt):
            with self.assertRaises(KeyboardInterrupt):
                self.execute('solo')
        with patch.object(Runtime, 'execute', side_effect=AssertionError('unexpected replay')):
            recovered = self.execute('solo')
        self.assertEqual(recovered['status'], 'completed')
        self.assertEqual(len(self.store.all('execution_intent')), 1)
        self.assertEqual(len(self.store.all('run')), 1)

    def test_unsupported_features_fail_before_runtime(self):
        exp = c.load(self.inputs/'experiment.json')
        cond = exp['conditions'][0]
        for key,value in [('model',dict(name='override',settings={},missing_reason=None)),
                          ('skills',[dict(id='missing',version='1')])]:
            with self.assertRaises(c.ContractError):
                execution.validate(dict(cond,**{key:value}),exp['budget']['execution'])
        with self.assertRaises(c.ContractError):
            execution.validate(cond,dict(mode='enforced'))
        invalid = copy.deepcopy(cond)
        invalid['workflow']['injections'] = [dict(id='fault',kind='tool_failure',stage='write',tool='network')]
        with self.assertRaises(c.ContractError):
            execution.validate(invalid,exp['budget']['execution'])

    def test_cancelled_predispatch_failure_preserves_native_reason(self):
        from role_orchestrator.runtime import Runtime
        def cancel(runtime, request):
            from role_orchestrator.contracts import attempt_id
            run = 'm3-'+c.identity(['notice-m3-fixture','notice','solo',1])
            runtime_root = self.store.root/'executions'/run/'runtime'
            stage = request['id']
            wire = dict(**request,schema_version=1,run_id=runtime.identity['run_id'],
                        attempt_id=attempt_id(runtime.identity['run_id'],stage))
            rec = dict(task=dict(id=stage,input=request['input'],role=request['role']),status='canceled',
                       result=dict(failure=dict(execution='not_started',code='timeout',stage='account_read')))
            for folder, data in [('bridge-attempts',wire), ('tasks',rec)]:
                dest = runtime_root/folder/(c.identity([stage])+'.json')
                dest.parent.mkdir(parents=True,exist_ok=True)
                dest.write_text(c.canonical(data))
            (runtime_root/'bridge-attempts'/('attempt-'+c.identity([wire['attempt_id']])+'.json')).write_text(c.canonical(stage))
            raise RuntimeError('execution_failed')
        with patch.object(Runtime,'execute',cancel):
            result = self.execute('solo')
        self.assertEqual(result['status'],'cancelled')
        self.assertEqual(result['stages'][0]['failure']['execution'],'not_started')

    def test_unreached_intervention_and_no_unnecessary_revision(self):
        exp = c.load(self.inputs/'experiment.json')
        exp['id'] = 'early'
        cond = next(x for x in exp['conditions'] if x['id']=='material')
        cond['workflow']['fixture']['review']['verdict'] = 'accept'
        cond['workflow']['injections'][0]['stage'] = 'revise'
        path = self.root/'early.json'
        path.write_text(c.canonical(exp))
        service.register_experiment(self.store,path)
        result = execution.execute(self.store,'early','notice','material',1,'runtime-bridge','codex')
        self.assertEqual(len(result['stages']),2)
        self.assertEqual(result['injections'][0]['count'],0)

    def test_imported_slot_never_dispatches_again(self):
        from role_orchestrator.runtime import Runtime
        target = Store(self.root/'other')
        self.addCleanup(target.close)
        service.register_bundle(target, self.inputs/'bundle.json')
        service.register_experiment(target, self.inputs/'experiment.json')
        original = service.import_evidence

        def copy_manifest(store, path, **options):
            original(target, path)
            return original(store, path, **options)
        with patch.object(service, 'import_evidence', copy_manifest):
            self.execute('solo')
        with patch.object(Runtime, 'execute', side_effect=AssertionError('duplicate dispatch')):
            with self.assertRaisesRegex(c.ContractError, 'already has imported evidence'):
                execution.execute(target, 'notice-m3-fixture', 'notice', 'solo', 1, '/missing', 'codex')
        self.assertFalse(target.all('execution_intent'))

    def test_late_receipt_preserves_history_without_dispatch(self):
        from role_orchestrator.attempts import AttemptReader
        from role_orchestrator.runtime import Runtime
        with patch.object(AttemptReader, 'read', return_value=None):
            early = self.execute('team')
        self.assertEqual(early['status'], 'uncertain')
        args = (self.store, 'notice-m3-fixture', 'notice', 'team', 1, 'runtime-bridge', '/missing')
        with patch.object(Runtime, 'execute', side_effect=AssertionError('unexpected dispatch')):
            known = execution.execute(*args, inspect_only=True)
            self.assertEqual(known['status'], 'prepared')
            self.assertEqual(known['stages'][0]['status'], 'completed')
            self.assertEqual(execution.execute(*args, inspect_only=True), known)
        self.assertEqual(early, self.store.get('execution_result', early['id']))
        self.assertEqual(self.store.get('run', early['id'])['execution_status'], 'uncertain')
        self.assertEqual(len(self.store.all('execution_intent')), 1)
        final = self.execute('team')
        self.assertEqual(final['status'], 'completed')
        self.assertEqual(len(self.store.all('execution_intent')), 4)
        self.assertEqual(final['stages'][0]['attempt_id'], early['stages'][0]['attempt_id'])
        self.assertEqual(next(self.store.current_runs())['execution_status'], 'completed')

    def test_oversized_encoded_frame_never_starts(self):
        exp = c.load(self.inputs/'experiment.json')
        exp['id'] = 'escaped'
        exp['conditions'][0]['workflow']['fixture']['write'] = '\\' * 31000
        path = self.root/'escaped.json'
        path.write_text(c.canonical(exp))
        service.register_experiment(self.store, path)
        with self.assertRaisesRegex(ValueError, 'frame limit'):
            execution.execute(self.store, 'escaped', 'notice', 'solo', 1, 'runtime-bridge', 'codex')
        self.assertFalse(self.store.all('execution_intent'))
        self.assertFalse(self.store.all('execution_binding'))

    def test_failed_handoff_recovery_is_durable(self):
        from agent_eval.execution_journal import StageJournal
        with patch.object(StageJournal, 'read_text', side_effect=OSError('unavailable')):
            failed = self.execute('fault')
        self.assertEqual(failed['status'], 'failed')
        self.assertEqual(failed['stages'][-1]['failure']['execution'], 'not_started')
        self.assertEqual(failed['injections'][0]['recovery'], 'read_failed')
        self.assertEqual(failed, self.execute('fault'))
        self.assertEqual(len(self.store.all('tool_failure')), 1)
        self.assertEqual(len(self.store.all('execution_intent')), 1)

    def test_fixture_writer_preserves_exact_text(self):
        expected = '{"notice":"ready"}'
        exp = c.load(self.inputs/'experiment.json')
        exp['id'] = 'json-artifact'
        exp['conditions'][0]['workflow']['fixture']['write'] = expected
        path = self.root/'fixture.json'
        path.write_text(c.canonical(exp))
        service.register_experiment(self.store, path)
        run = execution.execute(self.store, exp['id'], 'notice', 'solo', 1, 'runtime-bridge', 'codex')
        self.assertEqual(self.store.read_blob(run['document']).decode(), expected)

    def test_review_evidence_error_is_not_a_model_verdict(self):
        from agent_eval.execution_journal import StageJournal
        read_text = StageJournal.read_text
        def read(journal, sha):
            text = read_text(journal, sha)
            if '"verdict"' in text:
                raise c.ContractError('stored review evidence corrupted')
            return text
        with patch.object(StageJournal, 'read_text', read):
            with self.assertRaisesRegex(c.ContractError, 'evidence corrupted'):
                self.execute('team')
        self.assertFalse(self.store.all('execution_result'))
        result = self.execute('team')
        self.assertEqual(result['review'], 'accept')
        self.assertEqual(len(self.store.all('execution_intent')), 4)

    def test_late_solo_receipt_does_not_change_prior_evaluation(self):
        from role_orchestrator.attempts import AttemptReader
        from role_orchestrator.runtime import Runtime
        from agent_eval.report import report
        exp = 'notice-m3-fixture'
        with patch.object(AttemptReader, 'read', return_value=None):
            early = self.execute('solo')
        with patch('agent_eval.inspect_adapter.backend', return_value={'name':'test','version':'1'}):
            service.evaluate(self.store, exp, 'before', 'tester', 'original')
        before = report(self.store, exp, 'before')
        with patch.object(Runtime, 'execute', side_effect=AssertionError('model replay')):
            final = execution.execute(self.store, exp, 'notice','solo', 1, 'runtime-bridge','/missing',
                                      inspect_only=True)
        self.assertEqual(final['status'], 'completed')
        self.assertEqual(final['runtime_run'], early['runtime_run'])
        self.assertEqual(self.store.latest('run', early['id'])['output_sha256'], final['document'])
        self.assertEqual(report(self.store, exp, 'before')['conditions'], before['conditions'])

    def test_handoff_size_known_before_reviewer_submission(self):
        exp = c.load(self.inputs/'experiment.json')
        exp['id'] = 'large-handoff'
        cond = next(x for x in exp['conditions'] if x['id']=='material')
        cond['workflow']['fixture']['write'] = 'a' * 30000
        cond['workflow']['injections'][0]['text'] = 'b' * 40000
        path = self.root/'large.json'
        path.write_text(c.canonical(exp))
        service.register_experiment(self.store, path)
        run = execution.execute(self.store,exp['id'],'notice','material',1,'runtime-bridge','codex')
        self.assertEqual(run['status'],'failed')
        self.assertEqual(run['stages'][1]['failure']['execution'],'not_started')
        self.assertEqual(run['injections'][0]['count'],0)
        self.assertEqual(len(self.store.all('execution_intent')),1)
