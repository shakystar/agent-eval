"""Run one M3 assignment without scoring it.

Use -- to separate launcher options from role_orchestrator.assignment options.
JSON stdin is inherited; native stdout and stderr are kept in private slot files.
The slot is ROOT/ARM/CASE/REPEAT and its binding is ARM/CASE/REPEAT.
Run python -m agent_eval.m3_score separately on that slot after execution stops.
Neither the launcher status nor the native CLI exit code is a scoring verdict.
"""

import argparse
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import sys
import tempfile


_ROLE_OPTIONS = ("lab", "revision", "member", "task", "runtime", "profile")
_CASE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")

# The bridge calls the shim after publishing the plan; never guess the IDs.
_SHIM = """import json
import os
import sys

try:
    with open(sys.argv[1], encoding="utf-8") as stream:
        plan = json.load(stream)
    for field, name in (("run_id", "M3_RUN"), ("attempt_id", "M3_ATTEMPT")):
        value = plan[field]
        if not isinstance(value, str) or not value.strip() or chr(0) in value:
            raise ValueError("invalid plan identity")
        os.environ[name] = value
    os.execv(sys.executable, [sys.executable, sys.argv[2], *sys.argv[3:]])
except (OSError, ValueError, KeyError, TypeError):
    print("M3 codex shim: plan identity or recorder unavailable", file=sys.stderr)
    sys.exit(1)
"""


class _Once(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        if getattr(namespace, self.dest, None) is not None:
            parser.error(f"{option_string} may be specified only once")
        setattr(namespace, self.dest, values)


def _parse(argv):
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--arm", choices=("current", "candidate"), required=True, action=_Once)
    parser.add_argument("--case", required=True, action=_Once)
    parser.add_argument("--repeat", required=True, type=int, action=_Once)
    parser.add_argument("--root", required=True, type=Path, action=_Once)
    parser.add_argument("--backend-executable", required=True, type=Path, action=_Once)
    if "--" in argv:
        split = argv.index("--")
        args, remainder = parser.parse_args(argv[:split]), argv[split + 1:]
    else:
        args, remainder = parser.parse_known_args(argv)
    if not _CASE.fullmatch(args.case) or args.repeat < 0:
        parser.error("expected a safe case label and a nonnegative repeat")
    role = argparse.ArgumentParser(prog=f"{parser.prog} --", allow_abbrev=False, add_help=False)
    for name in _ROLE_OPTIONS:
        role.add_argument(f"--{name}", required=True, action=_Once)
    return args, vars(role.parse_args(remainder))


def _backend(path):
    if not path.is_absolute() or path.name != "codex":
        raise ValueError("expected an absolute codex path")
    target = path.resolve(strict=True)
    if not target.is_file() or not os.access(target, os.X_OK):
        raise ValueError("expected an executable codex file")
    return str(target)


def _slot_path(args):
    parent = args.root.resolve()
    parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    for label in (args.arm, args.case):
        parent = parent / label
        parent.mkdir(mode=0o700, exist_ok=True)
        if not stat.S_ISDIR(parent.lstat().st_mode):
            raise NotADirectoryError(str(parent))
    return parent / str(args.repeat)


def _private_output(path):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    return os.fdopen(fd, "wb")


def _status(status, **paths):
    print(json.dumps({"status": status, **{key: str(path) for key, path in paths.items()}}))


def main(argv=None):
    args, role = _parse(sys.argv[1:] if argv is None else list(argv))
    try:
        backend = _backend(args.backend_executable)
    except (OSError, ValueError, RuntimeError):
        _status("invalid_backend")
        return 2
    try:
        slot = _slot_path(args)
    except (OSError, RuntimeError):
        _status("slot_unavailable")
        return 1
    try:
        slot.mkdir(mode=0o700)
    except FileExistsError:
        _status("slot_exists")
        return 1
    except OSError:
        _status("slot_unavailable")
        return 1

    state = slot / "assignment"
    plan = state / "assignment-v2.plan.json"
    ledger = slot / "ledger.jsonl"
    native_stdout = slot / "assignment.stdout"
    paths = dict(slot=slot, state=state, plan=plan, ledger=ledger, native_stdout=native_stdout)
    package_dir = Path(__file__).resolve().parent
    repo = package_dir.parent
    python = os.path.abspath(sys.executable)
    env = os.environ.copy()
    for key in ("M3_RUN", "M3_ATTEMPT"):
        env.pop(key, None)
    env.update(
        M3_LEDGER=str(ledger),
        M3_ASSIGNMENT=f"{args.arm}/{args.case}/{args.repeat}",
        M3_BACKEND=backend,
        PYTHONDONTWRITEBYTECODE="1",
    )
    inherited = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(repo) + (os.pathsep + inherited if inherited else "")
    command = [python, "-P", "-m", "role_orchestrator.assignment", f"--state={state}", "--backend=codex"]
    command.extend(f"--{name}={role[name]}" for name in _ROLE_OPTIONS)

    try:
        with tempfile.TemporaryDirectory(prefix=".codex-", dir=slot) as directory:
            shim = Path(directory) / "codex"
            shim_args = [python, "-I", "-B", "-c", _SHIM, str(plan), str(package_dir / "m3_recorder.py")]
            shim.write_text("#!/bin/sh\nexec " + shlex.join(shim_args) + ' "$@"\n', encoding="utf-8")
            shim.chmod(0o700)
            env["PATH"] = directory + os.pathsep + env.get("PATH", os.defpath)
            with _private_output(native_stdout) as stdout, _private_output(slot / "assignment.stderr") as stderr:
                result = subprocess.run(command, env=env, stdout=stdout, stderr=stderr, check=False)
    except KeyboardInterrupt:
        _status("interrupted", **paths)
        return 130
    except OSError:
        _status("launch_error", **paths)
        return 1

    _status("assignment_exited" if result.returncode == 0 else "assignment_failed", **paths)
    return result.returncode if result.returncode >= 0 else 128 - result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
