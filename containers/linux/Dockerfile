FROM golang:1.26.11-bookworm@sha256:dc40a13b61304647ed7e5d581d246b86413dfc29d63c6d018310feb93cd98fc0 AS go
FROM python:3.12.3-bookworm@sha256:25dee7f137aa44c4962d21346385737eb81954b6f06f519fcc348b67f6483d3c
COPY --from=go /usr/local/go /usr/local/go
ENV PATH="/usr/local/go/bin:${PATH}" GOTOOLCHAIN=local GOMAXPROCS=4 GOFLAGS=-p=4 \
    UV_PYTHON_DOWNLOADS=never UV_NO_PROGRESS=1 PYTHONUNBUFFERED=1
COPY role-orchestrator /opt/src/role-orchestrator
COPY role-runtime /opt/src/role-runtime
COPY inspect /opt/src/inspect
COPY inspect-requirements.txt /opt/inspect-requirements.txt
RUN python -m pip install --no-cache-dir uv==0.13.9 && \
    uv sync --frozen --no-dev --project /opt/src/role-orchestrator && \
    python -m venv /opt/inspect-env && \
    /opt/inspect-env/bin/pip install --no-cache-dir -r /opt/inspect-requirements.txt && \
    /opt/inspect-env/bin/pip check
WORKDIR /opt/src/role-runtime
RUN chmod +x scripts/go.sh && ./scripts/go.sh mod download && \
    ./scripts/go.sh build -o bin/ ./cmd/runtime-workflow ./cmd/runtime-bridge && \
    ./scripts/go.sh test -race -run '^$' ./internal/engine ./internal/control ./internal/lifecycle
RUN test "$(git -C /opt/src/role-runtime rev-parse HEAD)" = 2be08fc0787c4ac67b934ff1f178806958021634 && \
    test "$(git -C /opt/src/role-orchestrator rev-parse HEAD)" = 5d2b51840e56284b6902e41cf76a00bc486dc3a2 && \
    test "$(git -C /opt/src/inspect rev-parse HEAD)" = ec5d110b1704a6eb31e2efedec59a12190df80e1 && \
    useradd --uid 1000 --create-home evaluator && mkdir -p /home/evaluator/.codex && \
    chown -R evaluator:evaluator /opt/src /home/evaluator/.codex
COPY --chown=evaluator:evaluator integration /opt/agent-eval
ENV PYTHONPATH=/opt/src/role-orchestrator
USER evaluator
WORKDIR /opt/src/role-orchestrator
ENTRYPOINT ["/opt/src/role-orchestrator/.venv/bin/python", "/opt/agent-eval/run_suite.py"]
