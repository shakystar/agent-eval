FROM agent-eval-m2:dev AS bridge
USER root
WORKDIR /tmp/m3-runtime-src
COPY go.mod go.sum ./
COPY internal ./internal
COPY cmd/runtime-bridge ./cmd/runtime-bridge
COPY codex-adapter.tar /tmp/codex-adapter.tar
ARG ADAPTER_COMMIT=""
ARG ADAPTER_ARCHIVE_SHA256=""
RUN set -eu; \
    module=github.com/shakystar/codex-adapter; \
    source="/tmp/pinned-codex-adapter/${ADAPTER_COMMIT}"; \
    if [ -n "$ADAPTER_COMMIT" ]; then \
        printf '%s  %s\n' "$ADAPTER_ARCHIVE_SHA256" /tmp/codex-adapter.tar | sha256sum -c -; \
        test "$(git get-tar-commit-id < /tmp/codex-adapter.tar)" = "$ADAPTER_COMMIT"; \
        mkdir -p "$source"; \
        tar xf /tmp/codex-adapter.tar -C "$source"; \
        test "$(cd "$source" && go list -m)" = "$module"; \
        go mod edit "-replace=$module=$source"; \
    else \
        test ! -s /tmp/codex-adapter.tar; test -z "$ADAPTER_ARCHIVE_SHA256"; \
    fi; \
    GOMODCACHE=/opt/src/role-runtime/scratch/go-mod GOCACHE=/opt/src/role-runtime/scratch/go-cache \
        go build -buildvcs=false -o /tmp/runtime-bridge ./cmd/runtime-bridge; \
    if [ -n "$ADAPTER_COMMIT" ]; then \
        go version -m /tmp/runtime-bridge > /tmp/bridge-modules; \
        awk -v mod="$module" -v src="$source" \
            '$1 == "dep" && $2 == mod { if (getline && $1 == "=>" && $2 == src && $3 == "(devel)") ok = 1 } END { exit !ok }' /tmp/bridge-modules; \
    fi

FROM agent-eval-m2:dev
COPY --from=bridge /tmp/runtime-bridge /opt/src/role-runtime/bin/runtime-bridge
COPY role_orchestrator /opt/src/role-orchestrator/role_orchestrator
COPY --chown=evaluator:evaluator agent_eval /opt/agent-eval-m3/agent_eval
COPY --chown=evaluator:evaluator tests /opt/agent-eval-m3/tests
COPY --chown=evaluator:evaluator examples /opt/agent-eval-m3/examples
COPY m3-entrypoint.py /opt/agent-eval-m3/entrypoint.py
WORKDIR /opt/agent-eval-m3
ENV PYTHONPATH=/opt/agent-eval-m3:/opt/src/role-orchestrator PATH=/opt/src/role-runtime/bin:${PATH}
ENTRYPOINT ["python", "/opt/agent-eval-m3/entrypoint.py"]
