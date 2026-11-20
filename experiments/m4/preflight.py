"""Probe two task bundles through the released M3 CLI in a fresh Linux store."""
import json
from pathlib import Path
import subprocess
import sys

from agent_eval.contracts import identity, load
from examples.m1.create_example import ref, write
from examples.m3.create_example import make as make_notice


PRIVATE = 'INVENTORY_PREFLIGHT_PRIVATE_RUBRIC'
CORRECT = '{"available":1,"reorder":true,"order_units":6}'
# Repeat 1 uses the bridge. The others exercise saved-output import.
# Counts are ordered as met, unmet, unknown for the three required fields.
CASES = [
    ('fixture', CORRECT, 'met', (3, 0, 0)),
    ('reordered-keys', '{"order_units":6,"reorder":true,"available":1}', 'met', (3, 0, 0)),
    ('wrong-quantity', '{"available":1,"reorder":true,"order_units":5}', 'unmet', (2, 1, 0)),
    ('boolean-as-stock', '{"available":true,"reorder":true,"order_units":6}', 'unmet', (2, 1, 0)),
    ('wrong-action', '{"available":1,"reorder":false,"order_units":6}', 'unmet', (2, 1, 0)),
    ('malformed-json', '{"available":', 'unmet', (0, 3, 0)),
    ('captured-empty-response', '', 'unmet', (0, 3, 0)),
    ('missing-output', None, 'unknown', (0, 0, 3)),
]


def make_inventory(directory, template):
    directory.mkdir()
    ledger = ref(directory, 'ledger.csv', 'event,units\nopening,8\nreceipt,3\nshipment,8\ndamage,2\n')
    policy = ref(directory, 'policy.txt', 'Deduct shipments and damage. If available stock is below 3, '
                 'order up to 7, otherwise order zero. Return JSON with integer available and order_units '
                 'and boolean reorder. Key order is unrestricted.')
    expected = {'available': 1, 'reorder': True, 'order_units': 6}
    task = dict(id='replenish', version='1', domain='inventory reconciliation', source='synthetic ledger',
                inputs=[ledger, policy], evaluation=[ref(directory, 'rubric.txt', PRIVATE)],
                allowed_actions=['read supplied input'], outputs=['JSON replenishment decision'],
                completion='All three required fields agree with the ledger and policy.',
                criteria=[dict(id=key, version='1', kind='artifact', required=True,
                               rule=dict(type='json_equals', source='output', pointer='/'+key, value=value))
                          for key, value in expected.items()], reference_path=[], validity='unreviewed')
    bundle = dict(schema_version=1, id='inventory-preflight', version='1', split='calibration',
                  family='inventory-reconciliation', tasks=[task])
    write(directory, 'bundle.json', bundle)
    exp = load(template)
    exp.update(id='inventory-preflight', bundle=dict(id=bundle['id'], version='1', sha256=identity(bundle)),
               hypothesis='Check reuse of the M3 CLI with a numeric decision.', repetitions=len(CASES))
    solo = exp['conditions'][0]
    solo['workflow']['fixture']['write'] = CORRECT
    write(directory, 'experiment.json', exp)
    records, runs = [], []
    for repeat, (name, output, _, _) in enumerate(CASES[1:], 2):
        records.append(dict(id=name, output=ref(directory, name+'.txt', output) if output is not None else None,
                            missing_reason='output not captured' if output is None else None))
        runs.append(dict(id=name, task=task['id'], condition='solo', repeat=repeat, attempt_id=name,
                         execution_status='uncertain' if output is None else 'completed',
                         environment=solo['environment'], receipt=None, started=None, ended=None,
                         measurements={k: dict(value=None, unit=u, scope='execution', completeness='missing',
                                               missing_reason='synthetic saved output')
                                       for k, u in [('time','seconds'), ('cost','USD'), ('tokens','tokens')]}))
    source = ref(directory, 'source.json', json.dumps(dict(schema_version=1, id='saved-inventory', records=records)))
    return write(directory, 'evidence.json', dict(schema_version=1, id='inventory-cases', experiment=exp['id'],
                                                  format='saved-output-v1', source=source, runs=runs))


def run(root):
    if any(root.iterdir()):
        raise ValueError('Choose an empty output directory for a fresh store.')

    def cli(*args):
        result = subprocess.run([sys.executable, '/opt/agent-eval-m3/entrypoint.py', '--store',
                                 str(root/'store'), *map(str, args)], check=True, stdout=subprocess.PIPE, text=True)
        return json.loads(result.stdout)

    notice, inventory = root/'notice', root/'inventory'
    make_notice(notice)
    exp = load(notice/'experiment.json')
    exp.update(id='notice-preflight', conditions=exp['conditions'][:1], repetitions=1, varying_fields=[])
    template = write(notice, 'experiment.json', exp)
    evidence = make_inventory(inventory, template)
    summary = {}
    for directory, task in [(notice,'notice'), (inventory,'replenish')]:
        binding = cli('bundle', directory/'bundle.json')
        experiment = cli('experiment', directory/'experiment.json')
        projection = cli('input', experiment, task)
        assert set(projection) == {'task', 'version', 'allowed_actions', 'outputs', 'inputs'}
        attempt = cli('execute', experiment, task, 'solo', 1)
        assert attempt == cli('execute', experiment, task, 'solo', 1, '--bridge', '/missing')
        stage = attempt['stages'][0]
        blobs = root/'store'/'blobs'
        prompt = (blobs/stage['input_sha256']).read_text()
        assert load(blobs/stage['receipt_sha256'])['task']['input'] == prompt
        rubric = (directory/'rubric.txt').read_text()
        assert rubric not in prompt and rubric not in (blobs/stage['wire_sha256']).read_text()
        if directory == inventory:
            assert {item['id'] for item in projection['inputs']} == {'ledger.csv', 'policy.txt'}
            assert 'opening,8' in prompt and 'Deduct shipments' in prompt
            assert cli('import', evidence)['duplicate'] is False
            assert cli('import', evidence)['duplicate'] is True
        reports = []
        for suffix in ['initial', 'regrade']:
            grade_id = experiment+'-'+suffix
            parent = ['--parent', experiment+'-initial'] if reports else []
            grade = cli('evaluate', experiment, grade_id, '--reviewer', 'preflight',
                        '--reason', 'Verify saved evidence', *parent)
            expected_judgments = len(CASES) * 3 if directory == inventory else 1
            assert grade['errors'] == 0 and grade['judgments'] == expected_judgments
            cli('report', experiment, grade_id, '--output', root/grade_id)
            report = load(root/grade_id/'report.json')
            assert report['criterion_bundle'] == binding and report['parent_evaluation'] == (parent[-1] if parent else None)
            assert rubric not in json.dumps(report) and rubric not in (root/grade_id/'report.md').read_text()
            reports.append(report['conditions'])
        assert reports[0] == reports[1]
        rows = reports[0][0]['runs']
        expected = CASES if directory == inventory else [('notice', None, 'met', (1,0,0))]
        assert len(rows) == len(expected) and all(row['run'] for row in rows)
        for repeat, ((name, _, outcome, counts), row) in enumerate(zip(expected, rows), 1):
            assert (row['task'], row['repeat'], row['outcome'], row['scorer_errors']) == (task, repeat, outcome, 0), name
            assert tuple(row['item_counts'].get(key, 0) for key in ('met','unmet','unknown')) == counts, name
        summary[task] = dict(bundle=binding, planned=len(rows), outcomes=reports[0][0]['tasks'][task]['outcomes'],
                             judgments_per_evaluation=grade['judgments'], scorer_errors=grade['errors'])
    write(root, 'summary.json', summary)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    run(Path(sys.argv[1]))
