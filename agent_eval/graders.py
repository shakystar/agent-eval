"""Providers for one grading request. Failure metadata describes model dispatch."""
import asyncio
import os
from pathlib import Path
import shutil
import subprocess

from . import contracts as c
from . import inspect_adapter


class GraderFailure(Exception):
    def __init__(self, message, failure):
        super().__init__(message)
        self.failure = failure


def unknown_failure(code):
    return dict(version=1, stage='grader_call', code=code, execution='unknown', retryable=False)


class CodexGrader:
    def __init__(self, model, root):
        self.model = model
        self.root = root
        self.executable = shutil.which(os.environ.get('AGENT_EVAL_CODEX_GRADER', 'codex-grader'))
        c.require(self.executable is not None, 'build codex-grader and set AGENT_EVAL_CODEX_GRADER')
        self.backend = dict(name='codex-adapter', executable_sha256=c.digest(Path(self.executable).read_bytes()))

    async def call(self, key, prompt, payload):
        state = (self.root / 'codex-grader' / key).resolve()
        workspace = state / 'workspace'
        workspace.mkdir(parents=True, exist_ok=False)
        request = dict(id=key, sessionKey=key, role='grader', workspace=str(workspace),
                       instructions=prompt, tools=['advisory'], input=payload)
        command = [self.executable, '--model', self.model, '--state', str(state)]
        try:
            result = await asyncio.to_thread(subprocess.run, command, input=c.canonical(request),
                                             text=True, capture_output=True)
        except OSError as error:
            raise GraderFailure(str(error), dict(version=1, stage='adapter_start', code='spawn_failed',
                                                 execution='not_started', retryable=False, attempts=0)) from error
        if result.returncode:
            failure = unknown_failure('unclassified_adapter_exit')
            try:
                event = c.loads(result.stderr)
                candidate = event['failure']
                if candidate['version'] == 1 and candidate['execution'] in ('not_started', 'unknown', 'started', 'completed'):
                    failure = candidate
            except (TypeError, KeyError, ValueError):
                pass
            raise GraderFailure(result.stderr or 'adapter exited without a result', failure)
        receipt = c.loads(result.stdout)
        return receipt.pop('text'), receipt


class InspectGrader:
    def __init__(self, name):
        from inspect_ai.model import get_model
        self.backend = inspect_adapter.backend()
        self.model = get_model(name)

    async def call(self, key, prompt, payload):
        from inspect_ai.model import ChatMessageSystem, ChatMessageUser
        response = await self.model.generate([ChatMessageSystem(content=prompt), ChatMessageUser(content=payload)])
        return response.completion, dict(usage=response.usage.model_dump(mode='json') if response.usage else None)


def provider(name, root):
    if name.startswith('codex-adapter/'):
        model = name.split('/', 1)[1]
        c.text(model)
        return CodexGrader(model, root)
    return InspectGrader(name)
