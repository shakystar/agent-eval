"""Check M5.1 against independent, fixed expectations with the offline M3 fixture bridge."""
import argparse
import copy
import json
import subprocess
import sys
from contextlib import closing
from pathlib import Path

from agent_eval import collaboration, contracts as c
from agent_eval.store import Store
from examples.m1.create_example import ref, write
from examples.m3.create_example import make as make_notice
from validate_m4 import ENTRYPOINT, evidence_fingerprint

ORCHESTRATOR = '/opt/src/role-orchestrator/.venv/bin/python'
NO_CODEX = '/nonexistent-m51-codex'
DRAFT = 'Checkout pauses 14:00-15:00 UTC. Browsing remains available.'
FINAL = DRAFT + ' Retry checkout after 15:00 UTC.'
ITEMS = {'outage': '14:00-15:00 UTC', 'browsing': 'Browsing remains available.',
         'retry': 'Retry checkout after 15:00 UTC.'}


def cli(root, *args, expected=0, control=None):
    cmd = [sys.executable, str(ENTRYPOINT)]
    if control:
        # Inject faults at the native evidence boundary before invoking the same CLI.
        # A later report sees only the ordinary persisted receipts.
        controls = {
            'read_failed': ('agent_eval.execution_journal.StageJournal.read_text',
                            "side_effect=OSError('fixture handoff read failure')"),
            'write_unobserved': ('role_orchestrator.attempts.AttemptReader.read', 'return_value=None'),
        }
        target, injection = controls[control]
        code = ("from unittest.mock import patch\nfrom agent_eval.cli import main\n"
                f"with patch({target!r}, {injection}): raise SystemExit(main())")
        cmd = [ORCHESTRATOR, '-c', code]
    proc = subprocess.run([*cmd, '--store', str(root/'store'), *map(str, args)],
                          capture_output=True, text=True, encoding='utf-8')
    assert proc.returncode == expected, (args, proc.stdout, proc.stderr)
    return json.loads(proc.stdout)


def make_cases(root):
    inputs = root/'inputs'
    make_notice(inputs)
    bundle = c.load(inputs/'bundle.json')
    bundle.update(id='m51-maintenance-handoff', family='maintenance-handoff')
    task, = bundle['tasks']
    task['criteria'] = [dict(id=key, version='1', required=True, kind='artifact',
                             rule=dict(type='contains', source='output', value=value))
                        for key, value in ITEMS.items()]
    task['inputs'] = [ref(inputs, 'brief.txt', 'Write the following fixed statements in the notice. ' + FINAL)]
    task['evaluation'] = [ref(inputs, 'rubric.txt', 'Require the three literal statements in the delivered notice.')]
    task['completion'] = 'Deliver all three fixed statements.'
    task['required_handoff'] = [dict(id=key, contains=value) for key, value in ITEMS.items()]
    binding = cli(root, 'bundle', write(inputs, 'bundle.json', bundle))
    exp = c.load(inputs/'experiment.json')
    exp.update(id='m51-outcomes', bundle=binding, baseline='accepted', repetitions=1,
               hypothesis='Exercise final delivery and observed collaboration outcomes with fixed controls.')
    _, team, _, fault = exp['conditions']
    team['workflow']['fixture'].update(write=DRAFT, revise=FINAL,
                                      review=dict(verdict='revise', reason='Missing retry instruction.'))
    accepted = copy.deepcopy(team)
    accepted['id'] = 'accepted'
    accepted['workflow']['fixture']['review'] = dict(verdict='accept', reason='Approved as supplied.')
    team['id'] = 'corrected'
    absent = copy.deepcopy(fault)
    absent['id'] = 'output-only'
    exp['conditions'] = [accepted, team, absent]
    exp['varying_fields'] = ['workflow.fixture.review.verdict', 'workflow.fixture.review.reason',
                             'workflow.injections', 'workflow.fixture.write', 'workflow.fixture.revise']
    assert cli(root, 'experiment', write(inputs, 'outcomes.json', exp)) == exp['id']
    assert 'required_handoff' not in cli(root, 'input', exp['id'], task['id'])
    fault['workflow']['fixture'] = team['workflow']['fixture']
    recovery = dict(exp, id='m51-recovery', repetitions=3, conditions=[fault], baseline=fault['id'])
    assert cli(root, 'experiment', write(inputs, 'recovery.json', recovery)) == recovery['id']
    return exp, recovery


def saved_output(root, exp):
    inputs = root/'inputs'
    evidence = c.load(inputs/'evidence.json')
    run = evidence['runs'][0]
    run.update(id='saved-only', attempt_id='saved-only-1', task='notice', condition='output-only',
               environment=exp['conditions'][-1]['environment'], receipt=None)
    source = dict(schema_version=1, id='m51-output-only', records=[
        dict(id=run['id'], output=ref(inputs, 'output-only.txt', FINAL), missing_reason=None)])
    evidence.update(id='m51-output-evidence', experiment=exp['id'], runs=[run],
                    source=ref(inputs, 'm51-source.json', c.canonical(source)))
    assert cli(root, 'import', write(inputs, 'saved.json', evidence))['duplicate'] is False


def run_cases(root, exp, recovery):
    def execute(experiment, condition, repeat, **kwargs):
        return cli(root, 'execute', experiment, 'notice', condition, repeat, '--codex', NO_CODEX, **kwargs)

    accepted = execute(exp['id'], 'accepted', 1)
    assert accepted['review'] == 'accept' and accepted['document'] == c.digest(DRAFT.encode())
    corrected = execute(exp['id'], 'corrected', 1)
    assert [s['stage'] for s in corrected['stages']] == ['write', 'review', 'revise', 'final-review']
    assert corrected['stages'][0]['output_sha256'] == accepted['document']
    assert corrected['document'] == c.digest(FINAL.encode()) and corrected['review'] == 'accept'
    saved_output(root, exp)
    recovered = execute(recovery['id'], 'fault', 1)
    failed = execute(recovery['id'], 'fault', 2, control='read_failed', expected=1)
    unreached = execute(recovery['id'], 'fault', 3, control='write_unobserved', expected=1)
    assert recovered['injections'][0]['recovery'] == 'read_succeeded'
    assert failed['injections'][0]['recovery'] == 'read_failed'
    assert unreached['injections'][0]['status'] == 'not_applied'
    assert all(r['backend'] == 'fixture' and r['binding']['codex'] == NO_CODEX
               for r in (accepted, corrected, recovered, failed, unreached))


def grade(root, store, exp, check):
    prior = None
    original = None
    fingerprint = evidence_fingerprint(store)
    for label in ('initial', 'regrade'):
        evaluation = exp['id'] + '-' + label
        parent = ['--parent', prior['evaluation']] if prior else []
        result = cli(root, 'evaluate', exp['id'], evaluation, '--reviewer', 'fixture-validator',
                     '--reason', label, *parent)
        assert result['errors'] == 0 and result['judgments'] == 9
        output = root/evaluation
        cli(root, 'report', exp['id'], evaluation, '--output', output)
        report = c.load(output/'report.json')
        md = (output/'report.md').read_text(encoding='utf-8')
        assert report['confirmation'] == 'draft'
        check(report, md)
        if prior is None:
            original = store.get('evaluation', evaluation)
            prior = report
        else:
            assert report['conditions'] == prior['conditions'] and report['parent_evaluation'] == prior['evaluation']
            assert store.get('evaluation', prior['evaluation']) == original
        assert evidence_fingerprint(store) == fingerprint
    return dict(evidence_sha256=fingerprint, original_evaluation_sha256=c.identity(original),
                validated_reports=[exp['id']+'-'+label for label in ('initial','regrade')])


def check_markdown(markdown, cond):
    # Compare within the correct condition, not just a token somewhere in the full document.
    section = markdown.split('\n## ' + cond['condition'] + '\n', 1)[1].split('\n## ', 1)[0]
    lines = section.splitlines()
    for label, field in [('Required handoff items', 'required_handoff_rate'), ('Fault recovery', 'recovery_success_rate')]:
        metric = cond[field]
        prefix = f"| {label} | {metric['numerator']}/{metric['denominator']} |"
        line, = [line for line in lines if line.startswith(prefix)]
        assert all(f'{reason}={n}' in line for reason, n in metric['reason_counts'].items()), line
        if metric['missing_reason']:
            assert metric['missing_reason'] in line, line
        excluded_column = line.split('|')[-2].strip()
        assert excluded_column == ', '.join(f'{k}={v}' for k, v in sorted(metric['excluded_slots'].items()))
    assert '| Task | Repeat | Execution | Artifact verdict | Outcome | Exclusion |' in lines
    for row in cond['runs']:
        reasons = {reason for reason in (row['artifact_reason'], row['exclusion_reason']) if reason}
        prefix = '| ' + ' | '.join(map(str, (row['task'], row['repeat'], row['status'], row['artifact_verdict'], row['outcome']))) + ' | '
        line, = [line for line in lines if line.startswith(prefix)]
        assert set(filter(None, line[len(prefix):-1].strip().split(', '))) == reasons, line


def check_rate(metric, numerator, denominator, reasons, missing=None):
    assert (metric['numerator'], metric['denominator']) == (numerator, denominator), metric
    assert metric['reason_counts'] == reasons, metric
    if missing:
        assert metric['value'] is None and metric['missing_reason'] == missing, metric
    else:
        assert metric['value'] == numerator / denominator and metric['missing_reason'] is None, metric


def check_outcomes(report, markdown):
    conditions = {cond['condition']: cond for cond in report['conditions']}
    assert conditions.keys() == {'accepted', 'corrected', 'output-only'}
    for name, expected in [('accepted', 'unmet'), ('corrected', 'met'), ('output-only', 'met')]:
        cond = conditions[name]
        row, = cond['runs']
        assert (row['outcome'], row['artifact_verdict']) == (expected, expected)
        if name == 'output-only':
            assert row['handoff']['items'] == dict.fromkeys(ITEMS, 'unknown')
            check_rate(cond['required_handoff_rate'], 0, 3, {'missing_handoff_evidence': 3}, 'missing_handoff_evidence')
            check_rate(cond['recovery_success_rate'], 0, 0, {'missing_injection_evidence': 1}, 'zero_denominator')
        else:
            assert row['handoff']['items'] == {'outage': 'delivered', 'browsing': 'delivered', 'retry': 'absent'}
            check_rate(cond['required_handoff_rate'], 2, 3, {'item_absent': 1})
            check_rate(cond['recovery_success_rate'], 0, 0, {'no_fault_planned': 1}, 'zero_denominator')
        check_markdown(markdown, cond)


def check_recovery(report, markdown):
    fault, = report['conditions']
    assert [row['artifact_verdict'] for row in fault['runs']] == ['met', 'unknown', 'unknown']
    assert fault['runs'][1]['artifact_reason'] == 'final_artifact_not_reached'
    assert [row['outcome'] for row in fault['runs']] == ['met', 'unknown', 'unknown']
    check_rate(fault['required_handoff_rate'], 2, 9, {'item_absent': 1, 'missing_handoff_evidence': 6})
    check_rate(fault['recovery_success_rate'], 1, 2, {'stage_not_reached': 1, 'read_failed': 1})
    assert fault['recovery_success_rate']['excluded_slots'] == {'stage_not_reached': 1}
    assert fault['required_handoff_rate']['excluded_slots'] == {}
    check_markdown(markdown, fault)


def check_uncertain_application():
    # The bounded fixture has definitive tool-read observations. Exercise a
    # declared but unconfirmed application separately from those six CLI slots.
    plan = {'injections': [dict(kind='tool_failure', id='outage', stage='review', tool='read_handoff')]}
    audit = {'injections': [dict(id='outage', status='uncertain', count=None)]}
    observed = collaboration.recovery_observation(plan, audit)
    assert observed == 'application_uncertain'
    row = {'handoff': {'items': {}, 'reason': 'no_required_handoff_items'}, 'fault_recovery': observed}
    check_rate(collaboration.condition_metrics([row])['recovery_success_rate'],
               0, 0, {'application_uncertain': 1}, 'zero_denominator')


def run(root):
    if not __debug__:
        raise RuntimeError('Run validation without -O.')
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise ValueError('A fresh output directory is required.')
    check_uncertain_application()
    exp, recovery = make_cases(root)
    run_cases(root, exp, recovery)
    with closing(Store(root/'store')) as store:
        before = len(store.all('execution_intent'))
        results = [grade(root, store, exp, check_outcomes), grade(root, store, recovery, check_recovery)]
        assert len(store.all('execution_intent')) == before
    summary = dict(validation='M5.1', cases=6, external_model_calls=0, fixture_executions=5,
                   saved_output_imports=1, regrade_execution_intents_added=0, experiments=results)
    write(root, 'validation.json', summary)
    print(json.dumps(summary))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    run(parser.parse_args().output)
