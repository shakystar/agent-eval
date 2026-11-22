"""Run the two-bundle M4 fixture regression using the installed M3 CLI (Linux)."""
import argparse
from collections import Counter
from contextlib import closing
from dataclasses import dataclass
import json
from pathlib import Path
import re
import subprocess
import sys

from agent_eval import contracts as c
from agent_eval.store import Store
from examples.m1.create_example import ref, write
from examples.m3.create_example import make as make_notice


PROJECT = Path(__file__).resolve().parents[1]
ENTRYPOINT = Path('/opt/agent-eval-m3/entrypoint.py')
FIELDS = ('available', 'reorder', 'order_units')
# Independent regression oracle. Do not derive these answers from the bundle's scorer.
ANSWERS = {'inventory-a': (1, True, 6), 'inventory-b': (3, False, 0), 'inventory-c': (9, False, 0)}
FIXTURE_OUTPUT = '{"available":0,"reorder":false,"order_units":0}'


@dataclass(frozen=True)
class Case:
    name: str
    output: str | None
    verdicts: tuple[str, ...]


def inventory_cases(task):
    available, reorder, quantity = ANSWERS[task]
    # Reversing keys also checks that object ordering is irrelevant.
    correct = dict(order_units=quantity, reorder=reorder, available=available)
    other_action = dict(correct, reorder=not reorder, order_units=4 if not reorder else 0)
    typed = {
        'inventory-a': (dict(correct, available=True), ('unmet', 'met', 'met')),
        'inventory-b': (dict(correct, reorder=0), ('met', 'unmet', 'met')),
        'inventory-c': (dict(correct, order_units=0.0), ('met', 'met', 'unmet')),
    }
    typed_output, typed_verdicts = typed[task]
    fixture_verdicts = ('unmet', 'unmet', 'unmet') if reorder else ('unmet', 'met', 'met')
    return [
        Case('bridge-fixed-output', FIXTURE_OUTPUT, fixture_verdicts),
        Case('correct-reordered-keys', json.dumps(correct), ('met', 'met', 'met')),
        Case('wrong-policy-branch', json.dumps(other_action), ('met', 'unmet', 'unmet')),
        Case('wrong-quantity', json.dumps(dict(correct, order_units=quantity+1)), ('met', 'met', 'unmet')),
        Case('wrong-json-type', json.dumps(typed_output), typed_verdicts),
        Case('malformed-json', '{"available":', ('unmet',) * 3),
        Case('captured-empty', '', ('unmet',) * 3),
        Case('missing-output', None, ('unknown',) * 3),
    ]


def saved_cases(directory, experiment, cases):
    directory.mkdir()
    records, runs = [], []
    environment = experiment['conditions'][0]['environment']
    for task, controls in cases.items():
        for repeat, case in enumerate(controls[1:], 2):
            run = f"{experiment['id']}-{task}-{case.name}"
            output = ref(directory, run+'.txt', case.output) if case.output is not None else None
            records.append(dict(id=run, output=output, missing_reason=None if output else 'output not captured'))
            measurements = {key: dict(value=None, unit=unit, scope='execution', completeness='missing',
                                      missing_reason='saved fixture')
                            for key, unit in [('time', 'seconds'), ('tokens', 'tokens'), ('cost', 'USD')]}
            runs.append(dict(id=run, task=task, condition='solo', repeat=repeat, attempt_id=run,
                             execution_status='completed' if output else 'uncertain', environment=environment,
                             receipt=None, started=None, ended=None, measurements=measurements))
    source_id = experiment['id']+'-saved'
    source = ref(directory, 'source.json', json.dumps(dict(schema_version=1, id=source_id, records=records)))
    return write(directory, 'evidence.json', dict(schema_version=1, id=source_id, experiment=experiment['id'],
                                                  format='saved-output-v1', runs=runs, source=source))


def expected_projection(directory, task):
    public = {key: task[key] for key in ('version', 'allowed_actions', 'outputs')}
    public['task'] = task['id']
    public['inputs'] = [dict(id=item['id'], sha256=item['sha256'], text=c.reference(item, directory).decode())
                        for item in task['inputs']]
    return public


def fixture_execution(cli, store, experiment, task, projection, output, private_texts):
    args = ('execute', experiment, task, 'solo', 1)
    run = cli(*args)
    assert run['backend'] == 'fixture' and run['status'] == 'completed' and len(run['stages']) == 1
    assert cli(*args, '--bridge', '/missing-m4-bridge') == run, 'completed slot resubmitted or changed'
    stage = run['stages'][0]
    wire = c.loads(store.read_blob(stage['wire_sha256']))
    receipt = c.loads(store.read_blob(stage['receipt_sha256']))
    prompt = store.read_blob(stage['input_sha256']).decode()
    assert wire['attempt_id'] == stage['attempt_id'] and receipt['status'] == 'succeeded'
    assert wire['input'] == receipt['task']['input'] == prompt
    assert store.read_blob(run['document']).decode() == output
    assert stage['output_sha256'] == run['document']
    payload = c.loads(prompt)
    # The fixture backend sends its canned reply along with the projected task.
    # Checking the projection alone would miss a leaked rubric in the rest of the wire.
    assert payload == {'task': projection, 'fixture_text': output}
    assert all(output not in source['text'] for source in projection['inputs'])
    for private in private_texts:
        assert private not in prompt and private not in c.canonical(wire) and private not in c.canonical(projection)
    return dict(run=run['id'], attempt=stage['attempt_id'], input_sha256=stage['input_sha256'],
                wire_sha256=stage['wire_sha256'], receipt_sha256=stage['receipt_sha256'],
                output_sha256=run['document'], backend=run['backend'])


def evidence_fingerprint(store):
    kinds = ('run', 'evidence', 'source', 'execution_intent', 'execution_stage', 'execution_result')
    records = {kind: store.all(kind) for kind in kinds}
    records['current_runs'] = list(store.current_runs())
    for source in records['source']:
        store.read_blob(source['sha256'])
    for run in records['current_runs']:
        if run['output_sha256']:
            store.read_blob(run['output_sha256'])
    return c.identity(records)


def check_grade(store, report, evaluation, cases, criteria, receipts):
    judgments = {(j['run'], j['criterion']): j for j in evaluation['judgments']}
    assert len(judgments) == len(evaluation['judgments'])
    assert report['task_validity'] == dict.fromkeys(cases, 'unreviewed')
    assert report['confirmation'] == 'draft' and report['conclusion'].startswith('withheld')
    condition, = report['conditions']
    assert condition['overall_confirmed_success_rate']['value'] is None
    rows = {(r['task'], r['repeat']): r for r in condition['runs']}
    assert condition['planned'] == condition['imported'] == len(rows) == sum(map(len, cases.values()))
    summary = []
    for task, controls in cases.items():
        for repeat, case in enumerate(controls, 1):
            row = rows[task, repeat]
            run = store.get('run', row['run'])
            expected_run = receipts[task]['run'] if repeat == 1 else f"{report['experiment']}-{task}-{case.name}"
            assert row['run'] == expected_run and row['scorer_errors'] == 0
            expected_hash = c.digest(case.output.encode()) if case.output is not None else None
            assert run['output_sha256'] == expected_hash
            items = {}
            for key, verdict in zip(criteria, case.verdicts, strict=True):
                j = judgments.pop((expected_run, key))
                assert j['verdict'] == verdict and j['processing'] == 'completed', (task, case.name, key, j)
                assert j['evidence_sha256'] == expected_hash and j['confirmation'] == 'draft'
                items[key] = verdict
            outcome = 'unknown' if case.output is None else ('unmet' if 'unmet' in case.verdicts else 'met')
            assert row['outcome'] == outcome and row['item_counts'] == dict(Counter(case.verdicts))
            summary.append(dict(task=task, repeat=repeat, case=case.name, outcome=outcome, items=items))
    assert not judgments
    return summary


def check_bundle(cli, store, root, bundle_path, experiment, cases, criteria, codex_experiment=None):
    bundle = c.load(bundle_path)
    solo, = experiment['conditions']
    assert solo['workflow']['backend'] == 'fixture' and solo['target']['auth_method'] == 'none'
    binding = cli('bundle', bundle_path)
    assert binding == experiment['bundle']
    tasks = {t['id']: t for t in bundle['tasks']}
    assert tasks.keys() == cases.keys()
    private_texts = [c.reference(r, bundle_path.parent).decode().splitlines()[0]
                     for task in tasks.values() for r in task['evaluation']]
    if codex_experiment:
        live_id = cli('experiment', codex_experiment)
    exp = cli('experiment', write(root, experiment['id']+'.json', experiment))
    receipts = {}
    for task, controls in cases.items():
        projection = cli('input', exp, task)
        assert projection == expected_projection(bundle_path.parent, tasks[task])
        if codex_experiment:
            assert cli('input', live_id, task) == projection
            public_text = '\n'.join(item['text'] for item in projection['inputs'])
            assert not re.search(r'"(?:available|reorder|order_units)"\s*:\s*(?:-?\d|true|false)', public_text)
        receipts[task] = fixture_execution(cli, store, exp, task, projection, controls[0].output, private_texts)
    manifest = saved_cases(root/(exp+'-import'), experiment, cases)
    assert cli('import', manifest)['duplicate'] is False
    snapshot = evidence_fingerprint(store)
    assert cli('import', manifest)['duplicate'] is True
    reports, grades = [], []
    for phase in ('initial', 'regrade'):
        evaluation_id = exp+'-'+phase
        parent = ['--parent', grades[0]['id']] if grades else []
        result = cli('evaluate', exp, evaluation_id, '--reviewer', 'm4-fixture', '--reason', phase, *parent)
        assert result['errors'] == 0
        cli('report', exp, evaluation_id, '--output', root/evaluation_id)
        report = c.load(root/evaluation_id/'report.json')
        assert report['criterion_bundle'] == binding and report['parent_evaluation'] == (parent[-1] if parent else None)
        markdown = (root/evaluation_id/'report.md').read_text(encoding='utf-8')
        assert all(private not in c.canonical(report) and private not in markdown for private in private_texts)
        ev = store.get('evaluation', evaluation_id)
        summary = check_grade(store, report, ev, cases, criteria, receipts)
        assert result['judgments'] == sum(len(row['items']) for row in summary)
        grades.append(ev)
        reports.append(report)
    assert reports[0]['conditions'] == reports[1]['conditions']
    assert store.get('evaluation', grades[0]['id']) == grades[0] and evidence_fingerprint(store) == snapshot
    return dict(bundle=binding, experiment=exp, planned=len(summary), judgments_per_grade=result['judgments'],
                outcomes=dict(Counter(row['outcome'] for row in summary)), validity=reports[0]['task_validity'],
                original_evaluation_sha256=c.identity(grades[0]), evidence_state_sha256=snapshot,
                initial=grades[0]['id'], child=grades[1]['id'], fixture_receipts=receipts, cases=summary)


def run(root, inventory_path):
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise ValueError('M4 validation requires an empty output directory.')
    if not __debug__:
        raise RuntimeError('M4 assertions require Python without -O.')

    def cli(*args):
        result = subprocess.run([sys.executable, str(ENTRYPOINT), '--store', str(root/'store'), *map(str, args)],
                                check=True, stdout=subprocess.PIPE, text=True, encoding='utf-8')
        return json.loads(result.stdout)

    notice = root/'notice'
    make_notice(notice)
    exp = c.load(notice/'experiment.json')
    exp.update(id='m4-notice-fixture', repetitions=3, conditions=exp['conditions'][:1], varying_fields=[])
    notice_output = exp['conditions'][0]['workflow']['fixture']['write']
    notice_cases = {'notice': [Case('bridge-notice', notice_output, ('met',)),
                               Case('captured-empty', '', ('unmet',)), Case('missing-output', None, ('unknown',))]}
    inventory_cases_by_task = {task: inventory_cases(task) for task in ANSWERS}
    published = inventory_path.with_name('experiment.json')
    inventory_exp = c.load(published)
    solo, = inventory_exp['conditions']
    assert solo['workflow']['backend'] == 'codex' and 'fixture' not in solo['workflow']
    inventory_exp.update(id='m4-inventory-fixture', repetitions=len(next(iter(inventory_cases_by_task.values()))))
    solo['workflow'].update(backend='fixture', fixture=dict(write=FIXTURE_OUTPUT))
    solo['target']['auth_method'] = 'none'
    solo['model']['missing_reason'] = 'deterministic fixture'
    with closing(Store(root/'store')) as store:
        notice_result = check_bundle(cli, store, root, notice/'bundle.json', exp, notice_cases, ('has-notice',))
        inventory_result = check_bundle(cli, store, root, inventory_path, inventory_exp, inventory_cases_by_task,
                                        FIELDS, codex_experiment=published)
        assert len(store.all('execution_intent')) == len(store.all('execution_result')) == 4
        assert len(store.all('evaluation')) == 4 and len(list(store.current_runs())) == 27
    result = dict(schema_version=1, validation='m4-two-bundle-cli', backend='fixture', real_model_calls=0,
                  published_codex_experiment=c.load(published)['id'], conclusions='withheld_unreviewed_tasks',
                  fixture_wire_contains_canned_output=True, bundles=[notice_result, inventory_result])
    write(root, 'summary.json', result)
    print(json.dumps({r['bundle']['id']: r['outcomes'] for r in result['bundles']}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path, help='Fresh writable directory in the M3 container.')
    parser.add_argument('--inventory-bundle', type=Path,
                        default=PROJECT/'bundles/inventory-reconciliation/v1/bundle.json')
    options = parser.parse_args()
    run(options.output, options.inventory_bundle)
