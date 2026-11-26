import sys
from pathlib import Path
import hashlib,json,os,subprocess
q=Path(__file__).resolve().parent

sys.path.insert(0,os.environ['PREFLIGHT_ORCHESTRATOR'])
from role_orchestrator.assignment import observe
from role_orchestrator.m1_evidence import verify_m1
out=Path(sys.argv[1]).resolve();out.mkdir();(out/'release').touch()
bridge=Path(os.environ['PREFLIGHT_BRIDGE']).resolve()
ids=dict(run_id='run-shared',attempt_id='attempt-shared')
req=dict(schema_version=1,**ids,id='task-shared',role='reviewer',instruction='Review',input='synthetic',traceparent='00-'+'1'*32+'-'+'2'*16+'-03')
env=dict(os.environ,PREFLIGHT_CASE=str(out),PREFLIGHT_MODE='success')
cmd=[bridge,'--state',out/'runtime','--backend','codex','--codex',q/'double_wire.py']
def submit():
    return json.loads(subprocess.run(cmd,input=(json.dumps(req)+'\n').encode(),env=env,capture_output=True,check=True,timeout=20).stdout)
initial=submit()
rf,=(out/'runtime/tasks').glob('*.json')
raw=rf.read_bytes()
replay=submit()
events=[json.loads(z) for z in (out/'calls.jsonl').read_text().splitlines()]
plan=dict(member_id='reviewer',expected_role_version='v1',task_id=req['id'],input_sha256=hashlib.sha256(b'synthetic').hexdigest(),instruction='Review')
verification=verify_m1([observe(bridge,out,ids,plan)],assignment_id=req['id'],member_id='reviewer',role_version='v1')
extra=json.loads((out/'extra-reply.jsonl').read_text().splitlines()[-1])['params']['turn']
assert len(events)==2 and len({x['turn'] for x in events})==2 and len({x['request_sha256'] for x in events})==1
assert extra['items'][0]['text']==initial['text'] and extra['id']!=json.loads(raw)['result']['turn_id']
assert replay['cached'] and rf.read_bytes()==raw and verification['action']=='accept'
report=dict(expected_starts=1,observed_starts=2,request_hash=events[0]['request_sha256'],turn_ids=[x['turn'] for x in events],receipt_sha256=hashlib.sha256(raw).hexdigest(),verifier=verification,boundary_audit='reject' if len(events)>1 else 'accept')
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
