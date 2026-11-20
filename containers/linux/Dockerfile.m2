FROM agent-eval-linux:m0
USER root
RUN /opt/inspect-env/bin/pip install --no-cache-dir openai==3.55.0 && /opt/inspect-env/bin/pip check
USER evaluator
WORKDIR /opt/agent-eval-m2
COPY --chown=evaluator:evaluator agent_eval ./agent_eval
COPY --chown=evaluator:evaluator tests ./tests
COPY --chown=evaluator:evaluator examples ./examples
ENV PYTHONPATH=/opt/agent-eval-m2
ENTRYPOINT ["/opt/inspect-env/bin/python", "-m", "agent_eval"]
