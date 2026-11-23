#!/bin/sh
# Run inside the candidate M3 image. Mount the three checkouts read-only below /src.
set -eu
export PYTHONDONTWRITEBYTECODE=1
export GOMODCACHE=/opt/src/role-runtime/scratch/go-mod
export GOCACHE=/tmp/go-build
export GOPROXY=off
mkdir -p /tmp/v011-bin
cd /src/role-runtime
cp go.mod /tmp/v011.mod
cp go.sum /tmp/v011.sum
go mod edit -modfile=/tmp/v011.mod -replace=github.com/shakystar/codex-adapter=/src/codex-adapter
go build -modfile=/tmp/v011.mod -buildvcs=false -o /tmp/v011-bin/runtime-workflow ./cmd/runtime-workflow
go build -modfile=/tmp/v011.mod -buildvcs=false -o /tmp/v011-bin/workflow-probe ./experiments/workflowprobe
export ROLE_WORKFLOW_BIN=/tmp/v011-bin/runtime-workflow
export ROLE_WORKFLOW_PROBE_BIN=/tmp/v011-bin/workflow-probe
export ROLE_RUNTIME_BIN=/opt/src/role-runtime/bin/runtime-bridge
cd /src/role-orchestrator
export PYTHONPATH=/src/role-orchestrator
python=/opt/src/role-orchestrator/.venv/bin/python
"$python" - <<'PY'
from pathlib import Path

source = Path('/src/role-orchestrator/role_orchestrator')
image = Path('/opt/src/role-orchestrator/role_orchestrator')
if {p.relative_to(source) for p in source.rglob('*.py')} != {p.relative_to(image) for p in image.rglob('*.py')}:
    raise SystemExit('candidate and image contain different Python modules')
for path in source.rglob('*.py'):
    packaged = image / path.relative_to(source)
    if path.read_bytes().replace(b'\r\n', b'\n') != packaged.read_bytes().replace(b'\r\n', b'\n'):
        raise SystemExit(f'image differs from candidate at {packaged}')
PY
"$python" -m unittest discover -s tests -v
