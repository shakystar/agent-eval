"""M0 public-API compatibility probe. Synthetic data; no external model calls.

Run from the repository root. Raw native logs stay under ignored artifacts/.
This is a contract experiment, not the M1 production importer.
"""
import argparse
import asyncio
import copy
import hashlib
import importlib.util
import json
import math
import platform
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from importlib.metadata import version

from inspect_ai import score as rescore
from inspect_ai.log import EvalConfig, EvalDataset, EvalError, EvalLog, EvalSpec, EvalSample, read_eval_log, read_eval_log_async, write_eval_log
from inspect_ai.model import ModelOutput
from inspect_ai.scorer import Score, accuracy, scorer

CALLS = []
PRIVATE = 'PRIVATE_GRADING_CANARY'


def execution_fixture(sample_id, public_input):
    """Deterministic external-execution stand-in, NOT Inspect eval or real runtime."""
    assert PRIVATE not in public_input
    CALLS.append(sample_id)
    return str(sample_id)


@scorer(metrics=[accuracy()])
def criterion_v1():
    async def grade(state, target):
        if state.sample_id == 'error':
            return None  # Existing failed evidence has no verdict.
        if state.sample_id == 'unscored':
            return Score.unscored(reason='excluded')
        if state.sample_id == 'absent':
            return None
        return Score(value='C' if state.output.completion == 'good' else 'I')
    return grade


@scorer(metrics=[accuracy()])
def criterion_v2():
    async def grade(state, target):
        return Score(value='I', explanation='Second criterion intentionally rejects all.')
    return grade


@scorer(metrics=[accuracy()])
def broken_criterion():
    async def grade(state, target):
        raise ValueError('deliberate second scorer failure')
    return grade


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def passive_import(path, index):
    """Preserve native log, refuse conflicting identity; never load task code."""
    if path.suffix != '.eval' or not path.is_file():
        raise ValueError('local .eval file required')
    log = read_eval_log(str(path), resolve_attachments=False)
    key = log.eval.eval_id
    if not key:
        raise ValueError('missing eval identity')
    digest = sha(path)
    if key in index and index[key] != digest:
        raise ValueError('identity/content conflict')
    duplicate = key in index
    index[key] = digest
    return log, duplicate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--orchestrator', type=Path, required=True)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--report', type=Path, default=Path('docs/validation/m0-results.json'))
    args = parser.parse_args()
    Path('artifacts').mkdir(exist_ok=True)
    checks = {}
    with tempfile.TemporaryDirectory(dir='artifacts', prefix='m0-') as tmp:
        root = Path(tmp)
        def execute(ids, scorers):
            samples = []
            for i in ids:
                public_input = 'Public task input'
                output = execution_fixture(i, public_input)
                samples.append(EvalSample(id=i, epoch=1, input=public_input, target=PRIVATE,
                                          output=ModelOutput.from_content('mockllm/model', output)))
            log = EvalLog(status='success', total_samples=len(ids),
                          eval=EvalSpec(created=datetime.now(timezone.utc).isoformat(),
                                        task='m0_synthetic_evidence', eval_id='m0-'+'-'.join(ids),
                                        dataset=EvalDataset(samples=len(ids), sample_ids=ids),
                                        model='mockllm/model', config=EvalConfig()), samples=samples)
            for sample in samples:
                if sample.id == 'error':
                    sample.error = EvalError(message='synthetic saved grading failure',
                                             traceback='fixture', traceback_ansi='fixture')
            return rescore(log, scorers, model='mockllm/model', display='none')

        original = execute(['good', 'bad', 'error', 'unscored'], criterion_v1())
        assert len(CALLS) == 4
        original_path = root / 'original.eval'
        write_eval_log(original, str(original_path))
        original_hash = sha(original_path)
        index = {}
        loaded, duplicate = passive_import(original_path, index)
        assert not duplicate
        assert passive_import(original_path, index)[1]
        samples = {s.id: s for s in loaded.samples}
        assert samples['error'].error is not None
        assert math.isnan(samples['unscored'].scores['criterion_v1'].value)
        assert samples['good'].scores['criterion_v1'].value == 'C'

        for status in ('error', 'cancelled'):
            variant = copy.deepcopy(loaded)
            variant.status = status
            variant.eval.eval_id += '-' + status
            path = root / (status + '.eval')
            write_eval_log(variant, str(path))
            assert passive_import(path, index)[0].status == status
        # These are serialized terminal-state fixtures, not interrupted processes.
        conflict = copy.deepcopy(loaded)
        conflict.samples[0].input = 'changed input'
        conflict_path = root / 'conflict.eval'
        write_eval_log(conflict, str(conflict_path))
        try:
            passive_import(conflict_path, index)
        except ValueError:
            checks['identity_conflict_rejected'] = True
        else:
            raise AssertionError('conflict accepted')

        partial = execute(['good'], criterion_v1())
        # Serialized partial-score fixture; not a claim of sequential native eval execution.
        partial.samples[0].error = EvalError(message='synthetic later scorer failure',
                                            traceback='fixture', traceback_ansi='fixture')
        assert partial.samples[0].error is not None
        assert partial.samples[0].scores['criterion_v1'].value == 'C'
        absent = execute(['absent'], criterion_v1())
        assert not absent.samples[0].scores
        for name, log in [('partial', partial), ('absent', absent)]:
            path = root / (name + '.eval')
            write_eval_log(log, str(path))
            reread, _ = passive_import(path, index)
            assert bool(reread.samples[0].scores) == (name == 'partial')
        checks['C01_native_roundtrip_and_dedup'] = True

        before = len(CALLS)
        first = rescore(loaded, criterion_v2(), model='mockllm/model', action='append', display='none')
        assert first.eval.eval_id == loaded.eval.eval_id
        checks['rescore_keeps_native_eval_id'] = True
        second_path = root / 'second.eval'
        write_eval_log(first, str(second_path))
        second_hash = sha(second_path)
        second = rescore(read_eval_log(str(second_path)), criterion_v2(),
                         model='mockllm/model', action='append', display='none')
        write_eval_log(second, str(root / 'third.eval'))
        assert sha(original_path) == original_hash and sha(second_path) == second_hash
        preserved = next(s for s in second.samples if s.id == 'good').scores
        assert len(preserved) >= 3
        assert preserved['criterion_v1'].value == 'C'
        assert preserved['criterion_v2'].value == 'I'
        assert len(CALLS) == before
        checks['C02_append_rescore_preserves_prior_files'] = True
        try:
            failed = rescore(loaded, broken_criterion(), model='mockllm/model', action='append', display='none')
        except Exception as exc:
            import traceback
            assert 'deliberate second scorer failure' in ''.join(traceback.format_exception(exc))
            checks['rescore_failure_surface'] = type(exc).__name__
        else:
            assert next(s for s in failed.samples if s.id == 'good').error is not None
            checks['rescore_failure_surface'] = 'sample.error'
        assert len(CALLS) == before
        checks['C03_scoring_error_no_execution_replay'] = True

        native = loaded.results.scores[0].metrics['accuracy'].value
        assert native == 0.5
        counts = dict(planned=4, executed=4, judgeable=2, unscored=1, scoring_error=1,
                      success=1, planned_success_rate=0.25, judgeable_success_rate=0.5,
                      native_accuracy=native, native_denominator=2)
        checks['C04_denominators'] = True

        # Poison references are data only. Import must not execute them.
        sentinel = root / 'must-not-exist'
        payload = root / 'untrusted.py'
        payload.write_text(f'from pathlib import Path\nPath({str(sentinel)!r}).touch()\n')
        poison = copy.deepcopy(loaded)
        poison.eval.eval_id += '-untrusted'
        poison.eval.task_file = str(payload)
        poison.eval.model_base_url = 'http://127.0.0.1:1/must-not-contact'
        path = root / 'untrusted.eval'
        write_eval_log(poison, str(path))
        # Create the Windows event-loop self-pipe BEFORE blocking outbound connects.
        from unittest.mock import patch
        async def guarded_read():
            with patch('socket.socket.connect', side_effect=AssertionError('network on import')), \
                 patch('socket.socket.connect_ex', side_effect=AssertionError('network on import')), \
                 patch.object(asyncio.get_running_loop(), 'create_connection',
                              side_effect=AssertionError('network on import')):
                return await read_eval_log_async(str(path), resolve_attachments=False)
        assert asyncio.run(guarded_read()).eval.model_base_url == poison.eval.model_base_url
        assert not sentinel.exists() and len(CALLS) == before
        checks['C07_private_target_and_passive_import'] = True

    # Execute the existing validator, without copying implementation or launching runtime.
    source = args.orchestrator / 'role_orchestrator/contracts.py'
    spec = importlib.util.spec_from_file_location('existing_contracts', source)
    contracts = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(contracts)
    vectors_path = args.orchestrator / 'contracts/v1-vectors.json'
    vectors = json.loads(vectors_path.read_text())
    runtime_vectors = json.loads((args.runtime / 'cmd/runtime-bridge/testdata/v1-vectors.json').read_text())
    assert vectors == runtime_vectors
    for case in vectors:
        try:
            contracts.validate_request(contracts.strict_json(case['wire']))
            valid = True
        except ValueError:
            valid = False
        assert valid == case['valid'], case['name']
    checks['existing_python_validator_shared_vectors'] = len(vectors)
    request = contracts.strict_json(next(c['wire'] for c in vectors if c['name'] == 'valid'))
    response = dict(schema_version=1, run_id=request['run_id'], attempt_id=request['attempt_id'],
                    id=request['id'], status='succeeded', text='good', cached=True,
                    stats={k: 0 for k in contracts.STAT_FIELDS})
    contracts.validate_response(response, request)
    # A synthetic, validated bridge receipt can be represented using public log types.
    # Native 'model' describes the fixture only; execution identity stays in metadata.
    mapped = copy.deepcopy(loaded)
    mapped.eval.eval_id += '-bridge'
    mapped.eval.dataset.samples = 1
    mapped.eval.dataset.sample_ids = [response['id']]
    mapped.total_samples = 1
    mapped.reductions = None
    mapped.samples = [EvalSample(id=response['id'], epoch=1, input=request['input'],
                                target=PRIVATE, output=ModelOutput.from_content('mockllm/model', response['text']),
                                metadata={'execution_owner': 'role-runtime', 'receipt': response,
                                          'role': request['role'], 'run_id': request['run_id'],
                                          'attempt_id': request['attempt_id'], 'synthetic': True})]
    mapped.results = None
    with tempfile.TemporaryDirectory(dir='artifacts', prefix='m0-bridge-') as tmp:
        path = Path(tmp) / 'bridge.eval'
        write_eval_log(mapped, str(path))
        mapped_read, _ = passive_import(path, {})
        assert mapped_read.samples[0].metadata['receipt'] == response
        mapped_scored = rescore(mapped_read, criterion_v1(), model='mockllm/model', display='none')
        assert mapped_scored.samples[0].scores['criterion_v1'].value == 'C'
        assert len(CALLS) == before
    checks['validated_bridge_receipt_to_native_log_and_score'] = True
    result = dict(schema_version=1, recorded_at=datetime.now(timezone.utc).isoformat(),
                  scope='M0 synthetic public API probe; not agent performance',
                  python=platform.python_version(), os=platform.system(), inspect_ai=version('inspect-ai'),
                  inspect_commit='ec5d110b1704a6eb31e2efedec59a12190df80e1',
                  probe_sha256=hashlib.sha256(Path(__file__).read_text(encoding='utf-8').encode('utf-8')).hexdigest(), checks=checks, counts=counts,
                  execution_fixture_calls=before, rescore_execution_calls=len(CALLS)-before,
                  external_model_calls=0, task_validity='not_applicable_contract_fixture',
                  native_eval='not exercised by this posthoc probe; see m0-native-eval-results.json',
                  real_runtime_integration='not_run: orchestrator/engine state store require Linux/macOS',
                  sources={p.name: subprocess.check_output(['git', '-C', str(p), 'rev-parse', 'HEAD'], text=True).strip()
                           for p in (args.orchestrator, args.runtime)},
                  limitations=['C05/C06 capability audit only', 'No human grader calibration',
                               'External execution is a deterministic stand-in, not Inspect eval or Go runtime',
                               'Interrupted and partial-error states are serialized fixtures, not crash recovery',
                               'No production importer or live model integration'])
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
