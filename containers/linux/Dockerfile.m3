FROM agent-eval-m2:dev AS bridge
USER root
WORKDIR /tmp/m3-runtime-src
COPY go.mod go.sum ./
COPY internal ./internal
COPY cmd/runtime-bridge ./cmd/runtime-bridge
RUN GOMODCACHE=/opt/src/role-runtime/scratch/go-mod GOCACHE=/opt/src/role-runtime/scratch/go-cache go build -buildvcs=false -o /tmp/runtime-bridge ./cmd/runtime-bridge

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
