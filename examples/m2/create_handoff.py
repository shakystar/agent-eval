"""Four exact cases approved in the source chat; fixture tests default to synthetic provenance."""
import copy
from datetime import datetime, timezone
from pathlib import Path
from agent_eval import contracts as c
from examples.m1.create_example import make as base_make, write, ref


def make(root, origin='synthetic'):
    root=Path(root)
    b,e,m=base_make(root)
    approved=c.load(Path(__file__).with_name('approved-cases.json'))
    b.update(id='incident-handoff',version='1',family='uncertainty-calibration')
    task=b['tasks'][0]
    task.update(id='handoff',version='1',domain='incident-handoff',source='synthetic calibration cases',
                inputs=[ref(root,'brief.txt',approved['input'])],evaluation=[],
                outputs=['장애 인계 문장'],completion=approved['rubric'],reference_path=[],
                criteria=[{'id':'uncertainty','version':'1','required':True,'kind':'artifact',
                           'rule':{'type':'semantic','source':'output','rubric':approved['rubric'],'needs':['output','inputs']}}])
    e.update(id='m2-calibration',hypothesis='Check semantic evaluator agreement on human-reviewed calibration cases.',repetitions=4,
             conditions=[e['conditions'][0]],varying_fields=[],
             bundle={'id':b['id'],'version':b['version'],'sha256':c.identity(b)})
    records=[];runs=[];cases=[]
    for index,item in enumerate(approved['cases'],1):
        r=copy.deepcopy(m['runs'][0]);r.update(id='case-'+item['id'],attempt_id='saved-'+item['id'],task='handoff',repeat=index)
        output=ref(root,item['id']+'.txt',item['output'])
        records.append({'id':r['id'],'output':output,'missing_reason':None});runs.append(r)
        cases.append({'id':item['id'],'run':r['id'],'criterion':'uncertainty','criterion_version':'1',
                      'criterion_sha256':c.identity(task['criteria'][0]),'output_sha256':output['sha256'],
                      'verdict':item['verdict'],'rationale':'Approved candidate label under the stated uncertainty criterion.'})
    source={'schema_version':1,'id':'m2-saved-cases','records':records}
    p=write(root,'source.json',source)
    m.update(id='m2-evidence',experiment=e['id'],runs=runs,
             source={'id':'source','path':p.name,'sha256':c.digest(p.read_bytes())})
    audit={'reviewer':approved['reviewer'] if origin=='human' else 'fixture-reviewer','origin':origin,
           'source':approved['source'] if origin=='human' else 'unit-test fixture, not actual human approval',
           'created':datetime.now(timezone.utc).isoformat(),'reason':approved['confirmation'] if origin=='human' else 'fixture'}
    reference={'schema_version':1,'id':'handoff-reference','version':'1','bundle':e['bundle'],'split':'calibration','cases':cases,**audit}
    review={'schema_version':1,'id':'handoff-approved','bundle':e['bundle'],'task':'handoff','task_version':'1',
            'status':'approved','supersedes':None,**audit}
    for name,obj in [('bundle.json',b),('experiment.json',e),('evidence.json',m),('reference.json',reference),('task-review.json',review)]:write(root,name,obj)
    return b,e,m,reference,review


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('--use-approved-cases',action='store_true')
    args=p.parse_args();make(args.directory,'human' if args.use_approved_cases else 'synthetic')
