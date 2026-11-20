"""Run offline integration checks and optionally replay the archived handoff evaluation."""
import argparse
import io
import json
import os
import platform
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent_eval import contracts as c,service,review,inspect_adapter
from agent_eval.store import Store
from agent_eval.semantic import SavedJudge
from agent_eval.reliability import reliability
from agent_eval.report import report,markdown
from examples.m2.create_handoff import make
from examples.m1.create_example import write


def cli_check(root):
    b,e,m,ref,tr=make(root/'input',origin='human')
    prefix=[sys.executable,'-m','agent_eval','--store',str(root/'store')]
    commands=[['bundle',str(root/'input/bundle.json')],['experiment',str(root/'input/experiment.json')],
              ['import',str(root/'input/evidence.json')],['task-review',str(root/'input/task-review.json'),'--human-attested'],
              ['reference',str(root/'input/reference.json'),'--human-attested'],
              ['semantic-requests',e['id'],'--output',str(root/'requests.json')]]
    count=0
    def call(command):
        nonlocal count
        p=subprocess.run(prefix+command,capture_output=True,text=True)
        if p.returncode: raise AssertionError(f'CLI {command[0]} failed: '+p.stderr)
        count+=1;return json.loads(p.stdout)
    for command in commands:
        receipt = call(command)
        if command[0] == 'task-review':
            assert receipt['origin'] == 'human' and receipt['effective_validity'] == 'approved'
    packets=c.load(root/'requests.json');responses={}
    labels=[x['verdict'] for x in ref['cases']]
    for packet,label in zip(packets,labels):
        responses[packet['request_sha256']]=json.dumps({'verdict':label,'rationale':'synthetic CLI fixture',
            'citations':[{'source':'output','quote':packet['payload']['sources']['output']}]},ensure_ascii=False)
    write(root,'responses.json',{'schema_version':1,'evaluator':{'id':'cli-fixture','kind':'synthetic','version':'1','model':'fixture','settings':{}},'responses':responses})
    call(['semantic-evaluate',e['id'],'grade','--reviewer','validator','--reason','fixture','--responses',str(root/'responses.json')])
    call(['reliability','grade','--reference','handoff-reference@1','--output',str(root/'reliability.json')])
    call(['report',e['id'],'grade','--output',str(root/'report')])
    assert c.load(root/'reliability.json')['status']=='unverified'
    assert c.load(root/'report/report.json')['conditions'][0]['overall_confirmed_success_rate']['numerator']==0
    store=Store(root/'store')
    try:
        ev=store.get('evaluation','grade')
        record={'schema_version':1,'id':'synthetic-review','evaluation':'grade','judgment':ev['judgments'][0]['id'],
                'verdict':'met','supersedes':None,**{k:ref[k] for k in review.AUDIT},'origin':'synthetic'}
        write(root,'review.json',record)
    finally:store.close()
    call(['judgment-review',str(root/'review.json')])
    return {'commands_passed':count,'synthetic_judge_not_marked_verified':True,'no_automatic_confirmation':True,'external_model_calls':0}


def replay_live(source,output):
    import shutil
    from unittest.mock import patch
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        shutil.copytree(source/'store',root/'store')
        shutil.copyfile(source/'saved-judge-responses.json',root/'responses.json')
        store=Store(root/'store')
        try:
            original=store.get('evaluation','live-judge')
            before={s['sha256']:store.read_blob(s['sha256']) for s in store.all('source')}
            with patch('subprocess.Popen',side_effect=AssertionError('no process')),patch('socket.socket.connect',side_effect=AssertionError('no network')):
                ev=service.evaluate(store,'m2-calibration','final-offline-replay','validator','Final build over preserved live responses','live-judge',judge=SavedJudge(root/'responses.json'))
            assert [j['verdict'] for j in ev['judgments']]==[j['verdict'] for j in original['judgments']]
            assert store.get('evaluation','live-judge')==original
            for sha,data in before.items():assert store.read_blob(sha)==data
            result=reliability(store,'final-offline-replay','handoff-reference@1')
            assert result['status'] == 'measured_on_human_references'
            assert result['agreement'] == {'numerator': 4, 'denominator': 4, 'value': 1.0, 'missing_reason': None}
            public=report(store,'m2-calibration','final-offline-replay')
            confirmed = sum(j['confirmation'] == 'confirmed' for j in ev['judgments'])
            assert confirmed == 0 and public['confirmation'] == 'draft'
            write(output,'replayed-reliability.json',result);write(output,'example-report.json',public)
            (output/'example-report.md').write_text(markdown(public),encoding='utf-8')
            return {'status':'passed','samples':len(ev['judgments']),'new_model_calls':0,'original_unchanged':True,
                    'agreement':result['agreement'],'human_confirmed_model_judgments':confirmed}
        finally:store.close()


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--saved-live-root',type=Path)
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    class Result(unittest.TextTestResult):
        def __init__(self,*a,**kw):super().__init__(*a,**kw);self.passed=[]
        def addSuccess(self,test):super().addSuccess(test);self.passed.append(test.id())
    output=io.StringIO()
    suite=unittest.TestSuite(unittest.defaultTestLoader.discover(str(Path(__file__).parent),pattern=pattern)
                             for pattern in ('test_m1*.py','test_m2*.py','test_review_integration.py'))
    result=unittest.TextTestRunner(stream=output,verbosity=2,resultclass=Result).run(suite)
    (args.output/'tests.txt').write_text(output.getvalue(),encoding='utf-8')
    if not result.wasSuccessful() or result.skipped:
        print(output.getvalue());raise SystemExit(1)
    with tempfile.TemporaryDirectory() as tmp:smoke=cli_check(Path(tmp))
    base=Path(__file__).parents[1]
    replay=None
    if args.saved_live_root:
        replay=replay_live(args.saved_live_root,args.output)
    summary={'status':'passed','image_id':os.environ.get('AGENT_EVAL_IMAGE_ID'),
             'python':platform.python_version(),'backend':inspect_adapter.backend(),'tests_passed':len(result.passed),
             'saved_live_replay':replay,'test_ids':result.passed,'failures':0,'skipped':0,'cli':smoke,'external_model_calls':0,
             'source_sha256':{str(f.relative_to(base)).replace(chr(92),'/'):c.digest(f.read_text(encoding='utf-8-sig').encode())
                              for folder in ('agent_eval','tests','examples/m2') for f in (base/folder).glob('*.py')}}
    write(args.output,'results.json',summary)
    print(json.dumps({'status':'passed','tests':len(result.passed),'cli_commands':smoke['commands_passed']}))


if __name__=='__main__':main()
