"""Generate a public maintenance-notice task and controlled execution conditions."""
import argparse
import copy
from pathlib import Path

from agent_eval.contracts import load
from agent_eval.execution import ENVIRONMENT
from examples.m2.create_example import make as make_notice
from examples.m1.create_example import write


def make(root, backend='fixture'):
    make_notice(root)
    exp = load(root/'experiment.json')
    exp.update(id='notice-m3-'+backend, baseline='solo', repetitions=2,
               varying_fields=['roles','workflow.scenario','workflow.max_revisions','workflow.injections',
                               'workflow.fixture.review.verdict','workflow.fixture.review.reason','workflow.fixture.revise',
                               'workflow.fixture.final-review.verdict','workflow.fixture.final-review.reason'], hypothesis='Inspect independent writer and review runs.')
    notice = 'Checkout pauses 14:00–15:00 UTC. Browsing remains available. Retry checkout after 15:00 UTC.'
    base = dict(id='solo', roles=[dict(id='writer',version='v1')], skills=[], environment=ENVIRONMENT,
                target=dict(adapter='role-orchestrator/runtime-bridge',version='1',execution_owner='role-runtime',
                            retry_owner='role-runtime',auth_method='codex' if backend=='codex' else 'none'),
                model=dict(name=None,settings={},missing_reason='runtime inherits local Codex config' if backend=='codex' else 'fixture'),
                workflow=dict(backend=backend,scenario='solo',max_revisions=0,injections=[]))
    if backend == 'fixture':
        base['workflow']['fixture'] = dict(write=notice)
    team = copy.deepcopy(base)
    team['id'] = 'team'
    team['roles'].append(dict(id='reviewer',version='v1'))
    team['workflow'].update(scenario='collaboration',max_revisions=1)
    if backend == 'fixture':
        team['workflow']['fixture'].update(review=dict(verdict='revise',reason='Use a shorter notice.'),
                                           revise=notice, **{'final-review':dict(verdict='accept',reason='Complete.')})
    material = copy.deepcopy(team)
    material.update(id='material')
    material['workflow']['injections'] = [dict(id='update',stage='review',kind='material',
                                              text='Also check that the notice identifies the timezone.')]
    fault = copy.deepcopy(team)
    fault.update(id='fault')
    fault['workflow']['injections'] = [dict(id='unavailable',stage='review',kind='tool_failure',tool='read_handoff')]
    exp['conditions'] = [base, team, material, fault]
    write(root,'experiment.json',exp)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory',type=Path)
    parser.add_argument('--backend',choices=['fixture','codex'],default='fixture')
    args = parser.parse_args()
    make(args.directory,args.backend)
