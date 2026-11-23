"""Verify recorded v0.1.0 handoffs using Linux, the real fixture bridge and two source trees.

From the directory containing the candidate role-orchestrator and agent-eval
checkouts, with the local baseline image already built:

    docker run --rm --network none --read-only --tmpfs /tmp \
      -v "$PWD/role-orchestrator:/candidate:ro" \
      -v "$PWD/agent-eval/docs/milestones/v0.1.1/evidence:/evidence:ro" \
      --entrypoint /opt/src/role-orchestrator/.venv/bin/python \
      agent-eval-m3:v011-baseline /evidence/legacy_handoff_regression.py --candidate /candidate
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory


LEGACY_SHA = '6935f81582aa5e1f0e8414cbf4bba31e47089fd9'
LEGACY_PACKAGE = 'edd2f999113a9a2f5ef1b4de45f7a6bff169e9aeb8d395fbde417fca04a9e135'
CANDIDATE_SHA = '2ac1621890141f69fb2f603467eb1f288bed392f'
CANDIDATE_PACKAGE = '547a4cf82bd15222c71c3e3e076ac8a1b3635cd812f858692ac54d29adeafbba'
PLAN = {
    'slot': 'report',
    'required_fields': ['title'],
    'producer': dict(member='acl-007', instruction='Write a report', model='gpt-6.2-sol', effort='medium'),
    'consumer': dict(member='acl-005', instruction='Read the report', model='gpt-6.2-astra', effort='high'),
}

# Interrupt the old CLI precisely after its submitted-intent transaction and
# before the Go call. For candidate replay, any dispatch attempt fails the test,
# including calls that the runtime would have served from its cache.
CHILD = """
import os, sys
from role_orchestrator import handoff_runner as runner
mode = sys.argv.pop(1)
if mode in ('interrupt', 'observe'):
    def forbid(*args, **kwargs):
        os._exit(86 if mode == 'interrupt' else 87)
    runner.Runtime.execute = forbid
raise SystemExit(runner.main())
"""


def fingerprint(root, files, *, normalize_newlines=False):
    total = hashlib.sha256()
    for path in sorted(files):
        raw = path.read_bytes()
        if normalize_newlines:
            raw = raw.replace(b'\r\n', b'\n')
        total.update(path.relative_to(root).as_posix().encode() + b'\0' + hashlib.sha256(raw).digest())
    return total.hexdigest()


def package(root):
    return fingerprint(root, (root / 'role_orchestrator').rglob('*.py'), normalize_newlines=True)


def runtime_files(state):
    return fingerprint(state, (p for p in (state / 'runtime').rglob('*') if p.is_file()))


def invoke(source, state, bridge, op, *, mode='normal', **fields):
    cmd = [sys.executable, '-c', CHILD, mode, '--state', str(state),
           '--runtime', str(bridge), '--backend', 'fixture']
    result = subprocess.run(cmd, cwd=state.parent, text=True, capture_output=True, timeout=30,
                            env={**os.environ, 'PYTHONPATH': str(source), 'PYTHONDONTWRITEBYTECODE': '1'},
                            input=json.dumps(dict(plan=PLAN, op=op, **fields)))
    if mode == 'interrupt':
        assert result.returncode == 86, (result.stdout, result.stderr)
        return
    assert result.returncode == 0, (op, mode, result.returncode, result.stdout, result.stderr)
    return json.loads(result.stdout)


def compare(baseline, candidate, bridge, state, scenario):
    pending = scenario == 'pending'
    invoke(baseline, state, bridge, 'publish-initial', payload={} if pending else {'title': 'fixture'})
    validation = invoke(baseline, state, bridge, 'validate')
    if pending:
        assert validation['state'] == 'needs_revision'
    elif scenario == 'uncertain':
        invoke(baseline, state, bridge, 'consume', mode='interrupt', fixture={'read': True})
    else:
        completion = invoke(baseline, state, bridge, 'consume', fixture={'read': True})
        assert completion['state'] == 'completed'

    old = invoke(baseline, state, bridge, 'status')
    expected = {'pending': 'blocked', 'completed': 'completed', 'uncertain': 'uncertain'}[scenario]
    assert old['state'] == expected
    before = runtime_files(state)
    for _ in range(2):
        current = invoke(candidate, state, bridge, 'status', mode='observe')
        for key in ('state', 'slots', 'receipt_id', 'open_requests'):
            assert current[key] == old[key], (scenario, key, old[key], current[key])
        if pending:
            repeated = invoke(candidate, state, bridge, 'validate', mode='observe')
            assert repeated['request_id'] == validation['request_id']
        else:
            replay = invoke(candidate, state, bridge, 'consume', mode='observe', fixture={'read': False})
            if scenario == 'completed':
                assert replay == completion, (completion, replay)
            else:
                assert replay['state'] == 'uncertain'
    assert runtime_files(state) == before
    return dict(legacy_status=expected, candidate_status=current['state'], candidate_dispatches=0,
                runtime_files_unchanged=True, fresh_process_replays=2)


def main():
    if not __debug__:
        raise RuntimeError('run this verification without Python optimization')
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline', type=Path, default=Path('/opt/src/role-orchestrator'))
    p.add_argument('--candidate', required=True, type=Path)
    p.add_argument('--bridge', type=Path, default=shutil.which('runtime-bridge'))
    args = p.parse_args()
    baseline, candidate = args.baseline.resolve(), args.candidate.resolve()
    assert package(baseline) == LEGACY_PACKAGE, 'baseline package differs from the pinned Git source (LF-normalized)'
    candidate_digest = package(candidate)
    assert candidate_digest == CANDIDATE_PACKAGE, 'candidate package differs from the pinned Git source (LF-normalized)'
    with TemporaryDirectory() as d:
        results = {s: compare(baseline, candidate, args.bridge, Path(d) / s, s)
                   for s in ('completed', 'pending', 'uncertain')}
    assert package(candidate) == candidate_digest, 'candidate changed during verification'
    print(json.dumps(dict(legacy_source=LEGACY_SHA, legacy_package_lf_sha256=LEGACY_PACKAGE, candidate_source=CANDIDATE_SHA,
                          candidate_package_lf_sha256=candidate_digest, bridge_sha256=hashlib.sha256(args.bridge.read_bytes()).hexdigest(),
                          backend='fixture', members=['acl-007', 'acl-005'], scenarios=results), indent=2))


if __name__ == '__main__':
    main()
