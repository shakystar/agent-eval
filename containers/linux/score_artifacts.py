"""Post-hoc Inspect contract over actual runtime receipts and artifacts.

No runtime client or model execution handle is available in this process.
These rules validate integration evidence, not professional task quality.
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from inspect_ai import score
from inspect_ai.log import EvalConfig, EvalDataset, EvalLog, EvalSample, EvalSpec, read_eval_log, write_eval_log
from inspect_ai.model import ModelOutput
from inspect_ai.scorer import Score, accuracy, scorer


@scorer(metrics=[accuracy()])
def receipt_contract():
    async def grade(state, target):
        receipt = state.metadata['receipt']
        valid = receipt['status'] == 'completed' and receipt['generation'] == 1
        if state.sample_id == 'producer':
            valid = valid and receipt['artifact_valid'] and bool(state.output.completion)
        else:
            valid = valid and state.metadata['handoff_verified']
        return Score(value='C' if valid else 'I', metadata={'criterion_version': 'receipt-v1'})
    return grade


@scorer(metrics=[accuracy()])
def negative_control():
    async def grade(state, target):
        return Score(value='I', explanation='Deliberately rejecting criterion: append regression control.')
    return grade


@scorer(metrics=[accuracy()])
def failure_control():
    async def grade(state, target):
        raise ValueError('deliberate scorer error')
    return grade


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_bundle(bundle):
    document = bundle['document']
    actual = hashlib.sha256(document.encode('utf-8')).hexdigest()
    producer = bundle['receipts']['producer']
    if actual != producer['artifact']['sha256']:
        raise ValueError('artifact hash mismatch')
    if bundle['backend'] == 'codex':
        review = json.loads(bundle['review'])
        if review['source_sha256'] != actual or review['verdict'] not in ('accept', 'revise'):
            raise ValueError('review handoff mismatch')
    for task_id, receipt in bundle['receipts'].items():
        if receipt['task']['id'] != task_id or not receipt['attempt_id']:
            raise ValueError('receipt identity mismatch')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    bundle = json.loads(args.bundle.read_text())
    verify_bundle(bundle)
    samples = []
    for task_id, receipt in bundle['receipts'].items():
        text = bundle['document'] if task_id == 'producer' else bundle['review']
        samples.append(EvalSample(id=task_id, epoch=1, input=receipt['task']['input'], target='',
                                 output=ModelOutput.from_content('mockllm/model', text),
                                 metadata={'receipt': receipt, 'run_id': bundle['run_id'],
                                           'execution_owner': 'role-runtime', 'handoff_verified': True}))
    log = EvalLog(status='success', total_samples=2, samples=samples,
                  eval=EvalSpec(created=datetime.now(timezone.utc).isoformat(),
                                task='saved_runtime_contract', eval_id=bundle['run_id'],
                                dataset=EvalDataset(samples=2), model='mockllm/model', config=EvalConfig()))
    args.output.mkdir(parents=True, exist_ok=True)
    original = args.output / 'original.eval'
    first = score(log, receipt_contract(), model='mockllm/model', display='none')
    assert all(s.scores['receipt_contract'].value == 'C' for s in first.samples)
    write_eval_log(first, original)
    before = digest(original)
    loaded = read_eval_log(original)
    assert {s.metadata['receipt']['attempt_id'] for s in loaded.samples} == {
        r['attempt_id'] for r in bundle['receipts'].values()}
    second = score(loaded, negative_control(), model='mockllm/model', action='append', display='none')
    write_eval_log(second, args.output / 'rescored.eval')
    assert all(s.scores['receipt_contract'].value == 'C' and s.scores['negative_control'].value == 'I'
               for s in second.samples)
    try:
        score(loaded, failure_control(), model='mockllm/model', display='none')
    except ValueError as exc:
        assert str(exc) == 'deliberate scorer error'
    else:
        raise AssertionError('scorer failure was not observed')
    corrupt = {**bundle, 'document': bundle['document'] + 'tampered'}
    try:
        verify_bundle(corrupt)
    except ValueError:
        pass
    else:
        raise AssertionError('modified artifact accepted')
    assert digest(original) == before
    result = dict(status='passed', samples=2, receipt_identity_preserved=True,
                  original_log_sha256=before, append_preserved=True, scoring_error_observed=True,
                  tampered_artifact_rejected=True, external_grader_model_calls=0,
                  scope='integration rules only; no task-quality or skill-effect conclusion')
    (args.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
