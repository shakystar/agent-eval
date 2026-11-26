import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

here = Path(__file__).resolve().parent

sys.path.insert(0,os.environ['PREFLIGHT_ORCHESTRATOR'])
from role_orchestrator.assignment import observe
from role_orchestrator.m1_evidence import verify_m1
bridge = Path(os.environ['PREFLIGHT_BRIDGE']).resolve()
peer = here/'peer.py'
def digest(data):
    return hashlib.sha256(data).hexdigest()
def run(mode, out):
    out.mkdir()
    ids = dict(run_id='run-shared',attempt_id='attempt-shared')
    req = dict(schema_version=1, **ids, id='task-shared',role='reviewer',instruction='Review',input='synthetic',traceparent='00-'+'1'*32+'-'+'2'*16+'-03')
    data = (json.dumps(req)+'\n').encode()
    env = dict(os.environ,PREFLIGHT_CASE=str(out),PREFLIGHT_MODE=mode)
    cmd = [bridge,'--state',out/'runtime','--backend','codex','--codex',peer]
    calls = out/'calls.jsonl'
    def count():
        return len(calls.read_text().splitlines()) if calls.exists() else 0
    with (out/'first.stderr').open('wb') as err, subprocess.Popen(cmd, env=env, stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=err) as first:
        first.stdin.write(data)
        first.stdin.close()
        first.stdin=None
        try:
            deadline=time.monotonic()+12
            while not (out/'wire.json').exists():
                if first.poll() is not None or time.monotonic()>deadline:
                    raise RuntimeError('first submission did not reach peer')
                time.sleep(.02)
            overlap=subprocess.run(cmd,input=data,env=env,capture_output=True,timeout=8)
            (out/'overlap.stderr').write_bytes(overlap.stderr)
            (out/'overlap.stdout').write_bytes(overlap.stdout)
            assert first.poll() is None and count()==1
        finally:
            (out/'release').touch()
        initial=json.loads(first.communicate(timeout=40)[0])
        assert first.returncode==0
    def inspect():
        plan=dict(task_id=req['id'],member_id=req['role'],expected_role_version='v1',input_sha256=digest(req['input'].encode()),instruction=req['instruction'])
        obs=observe(bridge,out,ids,plan)
        return verify_m1([obs],assignment_id=req['id'],member_id=req['role'],role_version='v1')
    receipt,=(out/'runtime/tasks').glob('*.json')
    before=digest(receipt.read_bytes())
    n=count()
    resumed=subprocess.run(cmd,input=data,env=env,capture_output=True,timeout=40,check=True)
    after=json.loads(resumed.stdout)
    result=inspect()
    assert overlap.returncode!=0 and 'state store already owned' in overlap.stderr.decode().lower(),overlap.stderr
    assert n==1 and count()==n and after['stats']['submitted']==0 and before==digest(receipt.read_bytes())
    if mode=='lost':
        assert initial['status']=='error' and after['error_code']=='execution_blocked' and result['action']=='hold'
    else:
        assert initial['status']=='succeeded' and after['cached'] and result['action']=='accept'
    report=dict(mode=mode,logical_request_sha256=digest(data),overlap_exit=overlap.returncode,overlap_error=overlap.stderr.decode().strip(),initial=initial,restart=after,verified=result,receipt_sha256=before,first_calls=1,overlap_new_calls=0,restart_new_calls=0)
    if mode=='success':
        # Deliver a byte-identical captured start at the synthetic backend during a second replay window.
        # The extra submission bypasses the bridge deliberately, as a positive control for the counter.
        prior=count()
        wire=(out/'wire.json').read_bytes()
        injected=subprocess.run([peer,'app-server'],env=env,input=wire,capture_output=True,check=True,timeout=5)
        duplicate=subprocess.run(cmd,env=env,input=data,capture_output=True,check=True,timeout=12)
        output=json.loads(injected.stdout.splitlines()[-1])['params']['turn']['items'][0]['text']
        events=[json.loads(line) for line in calls.read_text().splitlines()]
        assert output==initial['text'] and json.loads(duplicate.stdout)['cached'] and before==digest(receipt.read_bytes())
        assert count()-prior==1 and len({e['turn'] for e in events})==2 and len({e['request_sha256'] for e in events})==1
        report['injected_control']=dict(expected_new_calls=0,actual_new_calls=count()-prior,audit='reject',product_view=inspect()['action'],same_output=True,same_receipt=True)
    return report
dest=Path(sys.argv[1]).resolve()
dest.mkdir()
report=[run(mode,dest/mode) for mode in ['success','lost']]
(dest/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print([(r['mode'],r['verified']['action']) for r in report])
