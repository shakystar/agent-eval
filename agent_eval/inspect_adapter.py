"""Explicit, optional Inspect API boundary. Never load scorers/tasks from a log."""
import copy
import json
import math
import tempfile
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from .contracts import require, digest, loads, canonical, ContractError

PIN = 'ec5d110b1704a6eb31e2efedec59a12190df80e1'


def backend():
    v = version('inspect-ai')
    require(v.startswith('0.3.292.dev') and 'gec5d110b1' in v, 'unsupported Inspect build; use pinned M0 source')
    return {'name': 'inspect-ai', 'version': v, 'source_commit': PIN, 'adapter_version': '1'}


def finite(obj):
    if isinstance(obj, float) and not math.isfinite(obj):
        return {'nonfinite': str(obj)}
    if isinstance(obj, dict):
        return {k: finite(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [finite(v) for v in obj]
    return obj


def read(data):
    backend()
    from inspect_ai.log import read_eval_log
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'source.eval'
        path.write_bytes(data)
        log = read_eval_log(path, resolve_attachments=False)
    require(bool(log.eval.eval_id), 'native eval_id required')
    require(bool(log.samples), 'native samples required; header-only log unsupported')
    keys = [(type(s.id).__name__, s.id, s.epoch) for s in log.samples]
    require(len(set(keys)) == len(keys), 'duplicate sample/epoch')
    samples = []
    for s in log.samples:
        scores = {}
        for name, score in (s.scores or {}).items():
            value = score.value
            state = ('unscored' if getattr(score, 'unscored_reason', None) or
                     (isinstance(value, float) and math.isnan(value)) else
                     'missing_score' if value is None else 'scored')
            scores[name] = {'state': state, 'score': finite(score.model_dump(mode='python'))}
        samples.append({'id': s.id, 'epoch': s.epoch, 'output': s.output.completion if s.output else None,
                        'scores': scores, 'error': finite(s.error.model_dump()) if s.error else None})
    # EvalLog.location is excluded by the public model serializer. Original bytes remain separate.
    return {'eval_id': log.eval.eval_id, 'status': log.status, 'samples': samples,
            'semantic': finite(log.model_dump(mode='json')),
            'results': finite(log.results.model_dump(mode='json')) if log.results else None}


def apply_rule(output, rule):
    if rule['type'] == 'nonempty':
        return bool(output.strip())
    if rule['type'] == 'contains':
        return rule['value'] in output
    try:
        value = loads(output)
    except (json.JSONDecodeError, ContractError):
        return False  # Invalid submitted JSON is a task failure, not a grader exception.
    for key in rule['pointer'].split('/')[1:] if rule['pointer'] else []:
        key = key.replace('~1', '/').replace('~0', '~')
        try:
            if isinstance(value, list):
                if not key.isascii() or not key.isdigit() or (len(key) > 1 and key.startswith('0')):
                    return False
                value = value[int(key)]
            else:
                value = value[key]
        except (KeyError, IndexError, ValueError, TypeError):
            return False
    return canonical(value) == canonical(rule['value'])


def evaluate(output, criterion, native_id, sample_id, epoch):
    """A new sanitized log, explicit builtin scorer and mock model; no source code loading."""
    meta = backend()
    from inspect_ai import score
    from inspect_ai.log import EvalLog, EvalSpec, EvalDataset, EvalConfig, EvalSample, write_eval_log
    from inspect_ai.model import ModelOutput
    from inspect_ai.scorer import Score, accuracy, scorer

    @scorer(metrics=[accuracy()])
    def artifact_rule():
        async def grade(state, target):
            passed = apply_rule(state.output.completion, criterion['rule'])
            return Score(value='C' if passed else 'I', metadata={
                'criterion_id': criterion['id'], 'criterion_version': criterion['version']})
        return grade

    log = EvalLog(status='success', total_samples=1,
                  eval=EvalSpec(created=datetime.now(timezone.utc).isoformat(), task='agent_eval_saved_output',
                                eval_id=native_id, dataset=EvalDataset(samples=1),
                                model='mockllm/model', config=EvalConfig()),
                  samples=[EvalSample(id=sample_id, epoch=epoch, input='', target='',
                                      output=ModelOutput.from_content('mockllm/model', output))])
    result = score(log, artifact_rule(), model='mockllm/model', display='none')
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'judgment.eval'
        write_eval_log(result, path)
        data = path.read_bytes()
    value = result.samples[0].scores['artifact_rule'].value
    return {'verdict': 'met' if value == 'C' else 'unmet', 'processing': 'completed',
            'native_value': value, 'backend': meta, 'native_log_sha256': digest(data)}, data


def semantic_score(run, criterion, parsed):
    """Reuse public scorer/log APIs for externally obtained semantic judgments."""
    from inspect_ai import score
    from inspect_ai.log import EvalLog, EvalSpec, EvalDataset, EvalConfig, EvalSample, write_eval_log
    from inspect_ai.model import ModelOutput
    from inspect_ai.scorer import Score, accuracy, scorer

    @scorer(metrics=[accuracy()])
    def semantic_rubric():
        async def grade(state, target):
            metadata = {'criterion_id': criterion['id'], 'criterion_version': criterion['version'],
                        'verdict': parsed['verdict'], 'citations': parsed['citations']}
            if parsed['verdict'] in ('unknown', 'not_applicable'):
                return Score.unscored(reason=parsed['verdict'], explanation=parsed['rationale'], metadata=metadata)
            return Score(value='C' if parsed['verdict'] == 'met' else 'I', explanation=parsed['rationale'], metadata=metadata)
        return grade

    log = EvalLog(status='success', total_samples=1,
                  eval=EvalSpec(created=datetime.now(timezone.utc).isoformat(), task='agent_eval_semantic',
                                eval_id=run['native_id'], dataset=EvalDataset(samples=1), model='mockllm/model', config=EvalConfig()),
                  samples=[EvalSample(id=run.get('sample_id', run['id']), epoch=run.get('epoch', 1), input='', target='',
                                      output=ModelOutput.from_content('mockllm/model', 'Saved artifact: '+run['output_sha256']))])
    result = score(log, semantic_rubric(), model='mockllm/model', display='none')
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp)/'semantic.eval'
        write_eval_log(result, path)
        data = path.read_bytes()
    return {'verdict': parsed['verdict'], 'processing': 'completed', 'backend': backend(),
            'native_log_sha256': digest(data)}, data
