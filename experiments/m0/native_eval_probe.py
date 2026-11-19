"""Record native eval compatibility separately from the selected post-hoc path."""
import hashlib
import json
import platform
from pathlib import Path
from importlib.metadata import version

from inspect_ai import Task, eval as run_eval
from inspect_ai.dataset import Sample
from inspect_ai.model import ModelOutput
from inspect_ai.scorer import match
from inspect_ai.solver import solver

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
    result = dict(os=platform.system(), python=platform.python_version(),
                  inspect_ai=version('inspect-ai'),
                  probe_sha256=hashlib.sha256(Path(__file__).read_text(encoding='utf-8').encode('utf-8')).hexdigest())
    try:
        log = run_eval(Task(dataset=[Sample(input='Synthetic input', target='ok')],
                            solver=deterministic(), scorer=match()),
                       model='mockllm/model', display='none',
                       log_dir='artifacts/native-eval', retry_on_error=0)[0]
        result.update(status=log.status)
    except Exception as exc:
        result.update(status='blocked', error_type=type(exc).__name__, error=str(exc))
    result.update(solver_calls=calls, external_model_calls=0)
    path = Path('docs/validation/m0-native-eval-results.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
