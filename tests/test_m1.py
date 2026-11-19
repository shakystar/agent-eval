import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from agent_eval import contracts as c, service
from agent_eval.store import Store
from agent_eval.report import report, rate

spec=importlib.util.spec_from_file_location('example',Path(__file__).parents[1]/'examples/m1/create_example.py')
example=importlib.util.module_from_spec(spec);spec.loader.exec_module(example)


class FixtureCase(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.bundle,self.exp,self.evidence=example.make(self.root)
        self.store=Store(self.root/'store')
        service.register_bundle(self.store,self.root/'bundle.json')
        service.register_experiment(self.store,self.root/'experiment.json')

    def tearDown(self):
        self.store.close();self.temp.cleanup()

    def write(self,name,value):
        return example.write(self.root,name,value)

    def ingest(self):
        return service.import_evidence(self.store,self.root/'evidence.json')


class CoreTests(FixtureCase):
    def test_input_excludes_private_criteria(self):
        p=service.execution_input(self.store,'m1-demo','decision')
        encoded=json.dumps(p)
        self.assertNotIn(example.PRIVATE,encoded)
        self.assertNotIn('criteria',p)
        self.assertNotIn('evaluation',p)
        self.assertEqual(p['inputs'][0]['id'],'input.txt')

    def test_missing_duplicate_unknown_schema_and_hash(self):
        for change in ('missing','duplicate','schema','hash','unknown'):
            b=copy.deepcopy(self.bundle)
            if change=='missing': del b['tasks'][0]['completion']
            if change=='duplicate': b['tasks'].append(copy.deepcopy(b['tasks'][0]))
            if change=='schema': b['schema_version']=2
            if change=='hash': b['tasks'][0]['inputs'][0]['sha256']='0'*64
            if change=='unknown': b['surprise']=True
            with self.subTest(change=change),self.assertRaises((c.ContractError,KeyError)):
                service.register_bundle(self.store,self.write('invalid.json',b))

    def test_path_escape_and_private_alias_rejected(self):
        b=copy.deepcopy(self.bundle);b['tasks'][0]['inputs'][0]['path']='../outside.txt'
        with self.assertRaises(c.ContractError): service.register_bundle(self.store,self.write('invalid.json',b))
        b=copy.deepcopy(self.bundle);b['tasks'][0]['evaluation']=b['tasks'][0]['inputs']
        with self.assertRaises(c.ContractError): service.register_bundle(self.store,self.write('invalid.json',b))

    def test_experiment_is_immutable_and_bound_to_bundle(self):
        e=copy.deepcopy(self.exp);e['bundle']['sha256']='0'*64
        with self.assertRaises(c.ContractError):service.register_experiment(self.store,self.write('e.json',e))
        e=copy.deepcopy(self.exp);e['hypothesis']='Changed after registration'
        with self.assertRaises(c.ContractError):service.register_experiment(self.store,self.write('e.json',e))

    def test_import_idempotence_survives_restart(self):
        self.assertFalse(self.ingest()['duplicate'])
        self.store.close();self.store=Store(self.root/'store')
        self.assertTrue(self.ingest()['duplicate'])
        self.assertEqual(len(self.store.all('run')),3)
        self.assertIsNone(self.store.get('run','run-3')['output_sha256'])

    def test_conflict_atomic_rollback(self):
        self.ingest()
        e=copy.deepcopy(self.evidence);e['runs'][0]['execution_status']='failed'
        with self.assertRaises(c.ContractError):service.import_evidence(self.store,self.write('conflict.json',e))
        self.assertEqual(self.store.get('run','run-1')['execution_status'],'completed')
        self.assertEqual(len(self.store.all('run')),3)

    def test_missing_source_and_corrupt_artifact_rejected(self):
        (self.root/'output-1.txt').write_text('tampered')
        with self.assertRaises(c.ContractError):self.ingest()
        self.assertEqual(self.store.all('run'),[])
        (self.root/'source.json').unlink()
        with self.assertRaises(c.ContractError):self.ingest()

    def test_slot_collision_and_unsupported_format(self):
        e=copy.deepcopy(self.evidence);e['runs'][1]['repeat']=1
        with self.assertRaises(c.ContractError):service.import_evidence(self.store,self.write('bad.json',e))
        self.assertEqual(self.store.all('run'),[])
        e=copy.deepcopy(self.evidence);e['format']='harbor'
        with self.assertRaises(c.ContractError):service.import_evidence(self.store,self.write('bad.json',e))

    def test_duplicate_json_key_and_nonfinite(self):
        for value in ['{"id":1,"id":2}','{"x":NaN}']:
            p=self.root/'bad.json';p.write_text(value)
            with self.assertRaises(c.ContractError):c.load(p)
        self.assertIsNone(rate(0,0)['value'])

    def test_evidence_alias_cannot_double_count(self):
        self.ingest()
        e=copy.deepcopy(self.evidence);e['id']='alias'
        with self.assertRaises(c.ContractError):service.import_evidence(self.store,self.write('alias.json',e))
        self.assertEqual(len(self.store.all('run')),3)

    def test_rules_strict_json_pointer_and_values(self):
        from agent_eval.inspect_adapter import apply_rule
        rule={'type':'json_equals','source':'output','pointer':'/a~1b/0','value':True}
        self.assertTrue(apply_rule('{"a/b":[true]}',rule))
        rule['pointer']='/a~1b/-1'
        self.assertFalse(apply_rule('{"a/b":[true]}',rule))
        rule['pointer']='/a~1b/00'
        self.assertFalse(apply_rule('{"a/b":[true]}',rule))
        rule['pointer']='';rule['value']={'x':1}
        self.assertFalse(apply_rule('{"x":true}',rule))
        self.assertFalse(apply_rule('{"x":0,"x":1}',rule))
        self.assertFalse(apply_rule('{"x":NaN}',rule))
        self.assertTrue(apply_rule('hello',{'type':'contains','source':'output','value':'ell'}))
        self.assertFalse(apply_rule('  ',{'type':'nonempty','source':'output'}))
        with self.assertRaises(c.ContractError):c.rule({'type':'json_equals','source':'output','pointer':'/~2','value':0})

    def test_core_report_without_inspect_import(self):
        code="import sys; import agent_eval.service, agent_eval.report; assert 'inspect_ai' not in sys.modules"
        result=subprocess.run([sys.executable,'-c',code],capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)


try:
    import inspect_ai
    INSPECT=True
except ImportError:
    INSPECT=False


@unittest.skipUnless(INSPECT,'optional Inspect adapter not installed')
class AdapterTests(FixtureCase):
    def test_regrade_append_error_and_no_execution(self):
        self.ingest()
        before={s['sha256']:self.store.read_blob(s['sha256']) for s in self.store.all('source')}
        with patch('socket.socket.connect',side_effect=AssertionError('network forbidden')):
            first=service.evaluate(self.store,'m1-demo','grade-1','tester','initial')
            b=copy.deepcopy(self.bundle);b['version']='2';b['tasks'][0]['version']='2'
            criterion=b['tasks'][0]['criteria'][0];criterion['version']='2';criterion['rule']['value']='revise'
            service.register_bundle(self.store,self.write('b2.json',b))
            second=service.evaluate(self.store,'m1-demo','grade-2','tester','changed criterion','grade-1','m1-fixture@2')
        self.assertEqual(first['judgments'][0]['verdict'],'met')
        self.assertEqual(second['judgments'][0]['verdict'],'unmet')
        self.assertEqual(second['parent'],'grade-1')
        self.assertEqual(self.store.get('evaluation','grade-1'),first)
        with patch('agent_eval.inspect_adapter.apply_rule',side_effect=RuntimeError(example.PRIVATE)):
            third=service.evaluate(self.store,'m1-demo','grade-error','tester','error control','grade-2')
        self.assertEqual(third['judgments'][0]['processing'],'error')
        self.assertEqual(third['judgments'][0]['verdict'],'unknown')
        self.assertNotIn(example.PRIVATE,json.dumps(report(self.store,'m1-demo','grade-error')))
        self.assertEqual(len(self.store.all('run')),3)
        for sha,data in before.items():self.assertEqual(self.store.read_blob(sha),data)

    def test_report_denominators_missing_and_confounds(self):
        self.ingest();service.evaluate(self.store,'m1-demo','grade','tester','counts')
        obj=report(self.store,'m1-demo','grade');base,changed=obj['conditions']
        self.assertEqual(base['planned'],3)
        self.assertEqual(base['provisional_success_rate']['value'],1/3)
        self.assertEqual(base['provisional_judgeable_success_rate']['value'],1/2)
        self.assertEqual(base['overall_confirmed_success_rate']['numerator'],0)
        self.assertEqual(changed['missing_run_rate']['value'],1)
        self.assertTrue(changed['comparable'])
        self.assertEqual(base['missing_measurement_rates']['cost']['value'],1)
        self.assertNotIn(example.PRIVATE,json.dumps(obj))
        self.assertNotIn('revise',json.dumps(obj))

    def test_blob_tamper_blocks_regrade(self):
        self.ingest();sha=self.store.get('run','run-1')['output_sha256']
        (self.store.root/'blobs'/sha).write_bytes(b'changed')
        with self.assertRaises(c.ContractError):service.evaluate(self.store,'m1-demo','grade','tester','tamper')
        self.assertFalse(self.store.all('evaluation'))

    def test_unplanned_condition_and_actual_environment_are_separate(self):
        exp=copy.deepcopy(self.exp)
        exp['conditions'][1]['target']['version']='2'
        exp['id']='confounded'
        service.register_experiment(self.store,self.write('confounded.json',exp))
        evidence=copy.deepcopy(self.evidence);evidence['experiment']='confounded'
        evidence['runs'][0]['environment']['reset']='unverified'
        service.import_evidence(self.store,self.write('env.json',evidence))
        service.evaluate(self.store,'confounded','grade','tester','comparability')
        obj=report(self.store,'confounded','grade')
        self.assertFalse(obj['conditions'][0]['comparable'])
        self.assertIn('actual_environment_differs_from_plan',obj['conditions'][0]['comparison_reasons'])
        self.assertIn('target.version',obj['conditions'][1]['unplanned_differences'])
        self.assertFalse(obj['conditions'][1]['comparable'])

    def test_criterion_change_requires_version_and_input_change_is_rejected(self):
        self.ingest()
        b=copy.deepcopy(self.bundle);b['version']='2'
        b['tasks'][0]['criteria'][0]['rule']['value']='revise'
        with self.assertRaises(c.ContractError):
            service.register_bundle(self.store,self.write('v2.json',b))
        b['version']='3';b['tasks'][0]['version']='3'
        b['tasks'][0]['criteria'][0]['version']='3'
        b['tasks'][0]['completion']='different task'
        service.register_bundle(self.store,self.write('v3.json',b))
        with self.assertRaises(c.ContractError):
            service.evaluate(self.store,'m1-demo','bad','tester','changed task',bundle_ref='m1-fixture@3')

    def test_report_refuses_modified_original(self):
        self.ingest();service.evaluate(self.store,'m1-demo','grade','tester','integrity')
        sha=self.store.all('source')[0]['sha256']
        (self.store.root/'blobs'/sha).write_bytes(b'tamper')
        with self.assertRaises(c.ContractError):report(self.store,'m1-demo','grade')

    def native(self):
        from inspect_ai.log import EvalLog,EvalSpec,EvalDataset,EvalConfig,EvalSample,EvalError,write_eval_log
        from inspect_ai.model import ModelOutput
        from inspect_ai.scorer import Score
        samples=[]
        for i in range(1,4):
            s=EvalSample(id=i,epoch=1,input='public',target=example.PRIVATE,
                output=ModelOutput.from_content('mockllm/model','{"decision":"accept"}'),
                scores={'native':Score(value=0.5) if i==1 else Score.unscored(reason='fixture')} if i<3 else None)
            if i==1:s.error=EvalError(message='earlier grading failure',traceback='fixture',traceback_ansi='fixture')
            samples.append(s)
        log=EvalLog(status='cancelled',total_samples=3,samples=samples,
            eval=EvalSpec(created='2026-11-20T00:00:00Z',task='untrusted_task',task_file=str(self.root/'evil.py'),
                eval_id='native-demo',dataset=EvalDataset(samples=3),model='untrusted/provider',config=EvalConfig()))
        (self.root/'evil.py').write_text("raise AssertionError('task code executed')")
        path=self.root/'source.eval';write_eval_log(log,path)
        e=copy.deepcopy(self.evidence);e['format']='inspect'
        e['source']={'id':'source','path':path.name,'sha256':c.digest(path.read_bytes())}
        for i,r in enumerate(e['runs'],1):r.update(sample_id=i,epoch=1)
        self.write('native.json',e)
        return log,e

    def test_native_passive_import_states_and_reserialization(self):
        from inspect_ai.log import write_eval_log,read_eval_log
        log,e=self.native()
        with patch('socket.socket.connect',side_effect=AssertionError('network forbidden')):
            service.import_evidence(self.store,self.root/'native.json')
        r=self.store.get('run','run-1')
        self.assertEqual(r['native']['scores']['native']['score']['value'],0.5)
        self.assertTrue(r['native']['error'])
        self.assertEqual(self.store.get('run','run-2')['native']['scores']['native']['state'],'unscored')
        self.assertEqual(self.store.get('run','run-3')['native']['scores'],{})
        p=self.root/'roundtrip.eval';write_eval_log(read_eval_log(self.root/'source.eval'),p)
        e['source'].update(path=p.name,sha256=c.digest(p.read_bytes()))
        self.assertTrue(service.import_evidence(self.store,self.write('again.json',e))['duplicate'])
        self.assertEqual(len(self.store.all('run')),3)
        service.evaluate(self.store,'m1-demo','safe-grade','tester','explicit rule only')
        self.assertEqual(self.store.get('evaluation','safe-grade')['judgments'][0]['verdict'],'met')

    def test_native_conflict_and_invalid_sample_map(self):
        from inspect_ai.log import write_eval_log
        log,e=self.native();service.import_evidence(self.store,self.root/'native.json')
        log.samples[0].input='changed';p=self.root/'conflict.eval';write_eval_log(log,p)
        e['source'].update(path=p.name,sha256=c.digest(p.read_bytes()))
        with self.assertRaises(c.ContractError):service.import_evidence(self.store,self.write('conflict.json',e))
        log,e=self.native();e['runs'][0]['epoch']=2
        with self.assertRaises(c.ContractError):service.import_evidence(self.store,self.write('missing.json',e))


if __name__=='__main__':unittest.main()
