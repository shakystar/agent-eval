"""Create a small saved-evidence example; no model or external dependency."""
import json
from pathlib import Path
from agent_eval.contracts import digest, identity

PRIVATE = 'PRIVATE_GRADING_CANARY'
ENV = {'initial_state':'empty-v1','reset':'verified','isolation':'per-repeat','shared_state':'artifacts-only','session_policy':'role-isolated'}


def write(root, name, obj):
    p = root/name
    p.write_text(json.dumps(obj,indent=2)+'\n',encoding='utf-8')
    return p


def ref(root, name, text):
    data = text.encode()
    (root/name).write_bytes(data)
    return {'id':name,'path':name,'sha256':digest(data)}


def make(root):
    root = Path(root); root.mkdir(parents=True,exist_ok=True)
    task = {'id':'decision','version':'1','domain':'contract-fixture','source':'agent-eval synthetic fixture',
            'inputs':[ref(root,'input.txt','Return a JSON decision using the supplied task data.')],
            'evaluation':[ref(root,'private.txt',PRIVATE)],'allowed_actions':['read supplied input'],
            'outputs':['JSON document'],'completion':'Required decision field is valid.',
            'criteria':[{'id':'decision-field','version':'1','required':True,'kind':'artifact',
                         'rule':{'type':'json_equals','source':'output','pointer':'/decision','value':'accept'}}],
            'reference_path':['Example route only; not scored.'],'validity':'unreviewed'}
    bundle = {'schema_version':1,'id':'m1-fixture','version':'1','split':'calibration','family':'m1-contract','tasks':[task]}
    write(root,'bundle.json',bundle)
    condition = {'id':'baseline','target':{'adapter':'saved-output','version':'1','execution_owner':'fixture',
                 'retry_owner':'fixture','auth_method':'none'},'model':{'name':None,'settings':{},'missing_reason':'synthetic'},
                 'roles':[{'id':'writer','version':'1'}],'skills':[],'environment':ENV.copy()}
    changed = json.loads(json.dumps(condition)); changed['id']='changed'; changed['model']['settings']={'temperature':0.2}
    budget = {'limit':None,'unit':'USD','mode':'observational','missing_reason':'no live execution'}
    exp = {'schema_version':1,'id':'m1-demo','hypothesis':'Exercise stored evidence contracts.',
           'bundle':{'id':bundle['id'],'version':bundle['version'],'sha256':identity(bundle)},
           'baseline':'baseline','conditions':[condition,changed],'repetitions':3,
           'budget':{'execution':budget,'evaluation':budget},'varying_fields':['model.settings.temperature'],
           'comparison_policy':'same-task-criteria-budget'}
    write(root,'experiment.json',exp)
    runs=[]; records=[]
    for i, output in enumerate(['{"decision":"accept"}','{"decision":"revise"}',None],1):
        rid=f'run-{i}'
        runs.append({'id':rid,'task':'decision','condition':'baseline','repeat':i,'attempt_id':f'attempt-{i}',
                     'execution_status':'completed' if output else 'uncertain','environment':ENV.copy(),
                     'started':None,'ended':None,'receipt':None,
                     'measurements':{k:{'value':None,'unit':u,'scope':'execution','completeness':'missing','missing_reason':'fixture'}
                                     for k,u in [('time','seconds'),('tokens','tokens'),('cost','USD')]}})
        records.append({'id':rid,'output':ref(root,f'output-{i}.txt',output) if output else None,
                        'missing_reason':'not captured' if output is None else None})
    source={'schema_version':1,'id':'saved-demo','records':records}
    p=write(root,'source.json',source)
    evidence={'schema_version':1,'id':'evidence-demo','experiment':'m1-demo','format':'saved-output-v1',
              'source':{'id':'source','path':p.name,'sha256':digest(p.read_bytes())},'runs':runs}
    write(root,'evidence.json',evidence)
    return bundle,exp,evidence


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path)
    make(p.parse_args().directory)
