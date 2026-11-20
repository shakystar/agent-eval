"""Persist stage evidence and observations for the bounded runtime workflow."""
from role_orchestrator.contracts import RequestNotStarted, attempt_id, preflight_request
from role_orchestrator.workflow.review import STAGES, request

from . import contracts as c


def intervention(injection, stage, row, recovery='read_succeeded'):
    if not injection:
        return None
    base = dict(id=injection['id'], stage=stage, kind=injection['kind'])
    if injection['kind'] == 'tool_failure':
        return dict(base, status='applied', count=1, tool='read_handoff',
                    error='temporarily_unavailable', recovery=recovery)
    if row['status'] == 'completed':
        return dict(base, status='applied', count=1)
    if row.get('failure', {}).get('execution') == 'not_started':
        return dict(base, status='not_applied', count=0, reason='model_not_started')
    return dict(base, status='uncertain', count=None)


class StageJournal:
    def __init__(self, store, run, reader, runtime=None):
        self.store = store
        self.run = run
        self.reader = reader
        self.runtime = runtime

    def key(self, stage):
        return c.identity([self.run, stage])

    def known(self, stage):
        key = self.key(stage)
        return self.store.find('execution_intent', key) or self.store.find('execution_stage', key)

    def save_input(self, payload):
        return self.store.blob(c.canonical(payload).encode())

    def read_text(self, sha):
        return self.store.read_blob(sha).decode()

    def mark_fault(self, stage, sha, fault):
        with self.store.db:
            return self.store.put('tool_failure', self.key(fault['id']),
                                  dict(stage=stage, tool='read_handoff', input_sha256=sha,
                                       error='temporarily_unavailable'))

    def handoff_failure(self, stage):
        row = self.store.latest('execution_stage', self.key(stage))
        return row if row and row.get('error') == 'handoff_read_failed' else None

    def handoff_failed(self, stage, sha, injection, error):
        row = dict(stage=stage, role=STAGES[stage], status='failed', error='handoff_read_failed',
                   attempt_id=attempt_id(self.reader.run_id, stage), handoff_sha256=sha,
                   failure=dict(stage='read_handoff', code=type(error).__name__, execution='not_started'))
        row['injection'] = intervention(injection, stage, row, recovery='read_failed')
        with self.store.db:
            self.store.observe('execution_stage', self.key(stage), row)
        return row

    def receipt(self, logical, intent, error):
        row = dict(intent, status='uncertain', error=error)
        observation = self.reader.read(intent['attempt_id'])
        if observation is None:
            return row
        wire, native = observation
        message = c.loads(wire)
        c.require(all(message[k] == v for k, v in logical.items()), 'runtime request mismatch')
        record = c.loads(native)
        row.update(receipt_sha256=self.store.blob(native), wire_sha256=self.store.blob(wire),
                   native_status=record['status'])
        if record['status'] == 'succeeded':
            data = record['result']
            row.update(status='completed', output_sha256=self.store.blob(data.get('text', '').encode()),
                       session=data.get('session'))
        else:
            failure = record.get('result', {}).get('failure') or {}
            row['failure'] = failure
            if failure.get('execution') not in ('unknown', 'started'):
                row['status'] = {'failed':'failed', 'rejected':'failed',
                                 'canceled':'cancelled'}.get(record['status'], 'uncertain')
        return row

    def dispatch(self, stage, payload, before, injection):
        key = self.key(stage)
        text = c.canonical(payload)
        logical = request(stage, text)
        intent = dict(stage=stage, attempt_id=attempt_id(self.reader.run_id, stage),
                      input_sha256=self.store.blob(text.encode()), before_sha256=before,
                      instruction_sha256=c.digest(logical['instruction'].encode()), role=logical['role'])
        original_intent = self.store.find('execution_intent', key)
        c.require(original_intent is None or original_intent == intent, 'stage intent changed')
        saved = self.store.latest('execution_stage', key)
        if saved:
            c.require(all(saved.get(k) == v for k, v in intent.items()), 'stage identity or input changed')
            if saved['status'] != 'uncertain':
                return saved
        error = saved.get('error') if saved else None
        row = None
        if self.runtime is not None:
            try:
                preflight_request(logical, self.reader.run_id)
            except RequestNotStarted:
                row = self.not_started(intent)
            if row is None:
                with self.store.db:
                    fresh = self.store.put('execution_intent', key, intent)
                if fresh:
                    try:
                        self.runtime.execute(logical)
                    except RequestNotStarted:
                        row = self.not_started(intent)
                    except (ValueError, RuntimeError, OSError) as exc:
                        error = type(exc).__name__
        if row is None:
            row = self.receipt(logical, intent, error)
        row['injection'] = intervention(injection, stage, row)
        with self.store.db:
            self.store.observe('execution_stage', key, row)
        return row

    @staticmethod
    def not_started(intent):
        return dict(intent, status='failed', error='stage_input_limit',
                    failure=dict(stage='request_validation', execution='not_started'))
