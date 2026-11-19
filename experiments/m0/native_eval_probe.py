"""Record native eval compatibility separately from the selected post-hoc path."""
import hashlib
import argparse
import json
import platform
from pathlib import Path
from importlib.metadata import version

from inspect_ai import Task, eval as run_eval
from inspect_ai.dataset import Sample
from inspect_ai.model import ModelOutput
from inspect_ai.scorer import match
from inspect_ai.solver import solver
from inspect_ai.log import read_eval_log
from inspect_ai import score
import inspect_ai.log._recorders.buffer.database as buffer_database

calls = 0


@solver
def deterministic():
    async def run(state, generate):
        global calls
        calls += 1
        state.output = ModelOutput.from_content('mockllm/model', 'ok')
        return state
    return run


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', type=Path, default=Path('artifacts/native-eval-results.json'))
    args = parser.parse_args()
    result = dict(os=platform.system(), python=platform.python_version(),
                  inspect_ai=version('inspect-ai'),
                  buffer_module_sha256=hashlib.sha256(Path(buffer_database.__file__).read_text(encoding='utf-8').encode('utf-8')).hexdigest(),
                  probe_sha256=hashlib.sha256(Path(__file__).read_text(encoding='utf-8').encode('utf-8')).hexdigest())
    try:
        log = run_eval(Task(dataset=[Sample(input='Synthetic input', target='ok')],
                            solver=deterministic(), scorer=match()),
                       model='mockllm/model', display='none',
                       log_dir='artifacts/native-eval', retry_on_error=0)[0]
        result.update(status=log.status)
        if log.status == 'success':
            saved = read_eval_log(log.location)
            assert saved.samples[0].output.completion == 'ok'
            assert saved.samples[0].scores['match'].value == 'C'
            again = score(saved, match(), model='mockllm/model', action='append', display='none')
            assert len(again.samples[0].scores) == 2
            assert calls == 1
            result['native_log_read_and_rescore'] = True
    except Exception as exc:
        result.update(status='blocked', error_type=type(exc).__name__, error=str(exc))
    result.update(solver_calls=calls, external_model_calls=0)
    path = args.report
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
