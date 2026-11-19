"""Reproducible M1 validation. Saved live logs stay private; no model execution."""
import argparse
import copy
import io
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent_eval import contracts as c, service, inspect_adapter
from agent_eval.store import Store
from agent_eval.report import report
from test_m1 import example


def cli_smoke(root):
    example.make(root/'input')
    store=root/'cli-store'
    prefix=[sys.executable,'-m','agent_eval','--store',str(store)]
    commands=[['bundle',str(root/'input/bundle.json')],['experiment',str(root/'input/experiment.json')],
              ['import',str(root/'input/evidence.json')],['import',str(root/'input/evidence.json')],
              ['input','m1-demo','decision'],['evaluate','m1-demo','first','--reviewer','validator','--reason','contract'],
              ['evaluate','m1-demo','second','--reviewer','validator','--reason','repeat evaluation','--parent','first'],
              ['report','m1-demo','second','--output',str(root/'report')]]
    outputs=[]
    for command in commands:
        result=subprocess.run(prefix+command,capture_output=True,text=True)
        if result.returncode:
            raise AssertionError(f'CLI {command[0]} failed: {result.stderr}')
        outputs.append(json.loads(result.stdout))
    assert outputs[3]['duplicate']
    assert example.PRIVATE not in json.dumps(outputs[4])
    obj=c.load(root/'report/report.json')
    assert obj['conditions'][0]['provisional_success_rate']['value']==1/3
    duplicate=subprocess.run(prefix+commands[-1],capture_output=True,text=True)
    assert duplicate.returncode==2
    return {'commands_passed':len(commands),'duplicate_report_write_rejected':True,
            'baseline_provisional_success':{'numerator':1,'denominator':3},'model_calls':0},obj


def live_reuse(source,root):
    raw=source.read_bytes(); original=c.digest(raw)
    native=inspect_adapter.read(raw)
    b,e,m=example.make(root)
    template=b['tasks'][0]
    b['tasks']=[]
    for sample in native['samples']:
        t=copy.deepcopy(template);t['id']=str(sample['id'])
        t['criteria']=[{'id':'nonempty','version':'1','required':True,'kind':'artifact',
                        'rule':{'type':'nonempty','source':'output'}}]
        b['tasks'].append(t)
    e.update(id='m0-live-reuse',repetitions=1,conditions=[e['conditions'][0]])
    e['bundle']={'id':b['id'],'version':b['version'],'sha256':c.identity(b)}
    e['conditions'][0]['target']={'adapter':'role-orchestrator','version':'5d2b51840e56284b6902e41cf76a00bc486dc3a2','execution_owner':'role-runtime','retry_owner':'role-runtime','auth_method':'existing Codex ChatGPT login'}
    e['conditions'][0]['model']={'name':'gpt-6-astra','settings':{'reasoning_effort':'medium'},'missing_reason':None}
    e['conditions'][0]['environment']={k:'not independently revalidated in M1; see M0 record' for k in example.ENV}
    e['hypothesis']='Verify product importer over already completed M0 evidence, not task quality.'
    m.update(id='m0-live-evidence',experiment=e['id'],format='inspect',runs=[])
    p=root/'source.eval';p.write_bytes(raw)
    m['source']={'id':'original','path':p.name,'sha256':original}
    _,_,old=example.make(root/'template')
    for sample in native['samples']:
        original_sample=next(s for s in native['semantic']['samples'] if s['id']==sample['id'] and s['epoch']==sample['epoch'])
        receipt=original_sample['metadata']['receipt']
        r=copy.deepcopy(old['runs'][0]);r.update(id='saved-'+str(sample['id']),task=str(sample['id']),
            attempt_id=receipt['attempt_id'],receipt=receipt['attempt_id'],execution_status=receipt['status'],
            environment=e['conditions'][0]['environment'],sample_id=sample['id'],epoch=sample['epoch'])
        m['runs'].append(r)
    example.write(root,'bundle.json',b);example.write(root,'experiment.json',e);example.write(root,'evidence.json',m)
    store=Store(root/'store')
    try:
        service.register_bundle(store,root/'bundle.json');service.register_experiment(store,root/'experiment.json')
        with patch('socket.socket.connect',side_effect=AssertionError('network forbidden')),patch('subprocess.Popen',side_effect=AssertionError('execution forbidden')):
            service.import_evidence(store,root/'evidence.json')
            assert service.import_evidence(store,root/'evidence.json')['duplicate']
            first=service.evaluate(store,e['id'],'first','validator','saved evidence')
            second=service.evaluate(store,e['id'],'second','validator','regrade','first')
        assert all(j['verdict']=='met' for j in second['judgments'])
        assert store.get('evaluation','first')==first
        assert len(store.all('run'))==len(native['samples'])
        assert {r['attempt_id'] for r in store.all('run')}=={s['metadata']['receipt']['attempt_id'] for s in native['semantic']['samples']}
        assert c.digest(source.read_bytes())==original
        return {'status':'passed','samples':len(native['samples']),'original_sha256':original,
                'original_unchanged':True,'original_attempt_ids_preserved':True,'duplicate_import_no_extra_runs':True,'regrade_history_preserved':True,
                'new_model_calls':0,'process_launches_during_import_and_regrade':0,
                'scope':'Nonempty artifact contract only; M0 execution metadata is preserved in native source, not revalidated.'}
    finally:
        store.close()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--live-log',type=Path);args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    suite=unittest.defaultTestLoader.discover(str(Path(__file__).parent),pattern='test_m1.py')
    class Result(unittest.TextTestResult):
        def __init__(self,*a,**kw):super().__init__(*a,**kw);self.passed=[]
        def addSuccess(self,test):super().addSuccess(test);self.passed.append(test.id())
    stream=io.StringIO();started=time.monotonic()
    result=unittest.TextTestRunner(stream=stream,verbosity=2,resultclass=Result).run(suite)
    (args.output/'tests.txt').write_text(stream.getvalue(),encoding='utf-8')
    require_success=result.wasSuccessful() and not result.skipped
    if not require_success:
        print(stream.getvalue());raise SystemExit(1)
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        smoke,demo=cli_smoke(root)
        live=live_reuse(args.live_log,root/'live') if args.live_log else None
    summary={'schema_version':1,'date':'2026-11-20','status':'passed','python':platform.python_version(),
             'platform':platform.system(),'image_id':os.environ.get('AGENT_EVAL_IMAGE_ID'),'backend':inspect_adapter.backend(),'tests_passed':len(result.passed),
             'test_ids':result.passed,'skipped':0,'failed':0,'cli':smoke,'saved_m0_live_log':live,
             'external_model_calls':0,'elapsed_seconds':round(time.monotonic()-started,3),
             'source_sha256':{str(p.relative_to(Path(__file__).parents[1])).replace(chr(92),'/'):c.digest(p.read_text(encoding='utf-8-sig').replace('\r\n','\n').encode())
                              for directory in ('agent_eval','tests','examples/m1') for p in (Path(__file__).parents[1]/directory).glob('*.py')}}
    example.write(args.output,'results.json',summary);example.write(args.output,'example-report.json',demo)
    print(json.dumps({'status':'passed','tests':len(result.passed),'cli_commands':smoke['commands_passed'],'saved_live_samples':live['samples'] if live else None}))


if __name__=='__main__':main()
