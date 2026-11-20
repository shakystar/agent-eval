"""M3 execution through role-orchestrator's versioned Go bridge."""
from datetime import datetime, timezone
import hashlib
import shutil
import tempfile
from pathlib import Path

from . import contracts as c
from . import service
from .store import operation_lock

ENVIRONMENT = dict(initial_state='empty-v1', reset='verified', isolation='per-repeat',
                   shared_state='shared-role-workspace-and-handoffs', session_policy='role-isolated')


def file_digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def validate(condition, budget):
    from role_orchestrator.workflow.review import STAGES, review_value
    w = condition['workflow']
    c.fields(w, ['backend', 'scenario', 'max_revisions', 'injections'], ['fixture'])
    backend, scenario = w['backend'], w['scenario']
    c.require(backend in ('fixture', 'codex') and scenario in ('solo', 'collaboration'), 'unsupported workflow')
    c.require(type(w['max_revisions']) is int and w['max_revisions'] in (0, 1), 'unsupported revision limit')
    c.require(scenario != 'solo' or w['max_revisions'] == 0, 'solo has no revision stage')
    stages = ['write'] if scenario == 'solo' else ['write', 'review']
    if w['max_revisions']:
        stages += ['revise', 'final-review']
    expected_roles = [dict(id=k, version='v1') for k in dict.fromkeys(STAGES[s] for s in stages)]
    c.require(condition['roles'] == expected_roles and not condition['skills'], 'unsupported roles or skills')
    c.require(condition['environment'] == ENVIRONMENT, 'unsupported environment')
    c.require(condition['model']['name'] is None and not condition['model']['settings'],
              'bridge v1 inherits model settings; explicit overrides unsupported')
    expected = dict(adapter='role-orchestrator/runtime-bridge', version='1', execution_owner='role-runtime',
                    retry_owner='role-runtime', auth_method='none' if backend == 'fixture' else 'codex')
    c.require(condition['target'] == expected, 'unsupported execution target')
    c.require(budget['mode'] == 'observational', 'bridge v1 cannot enforce the requested execution budget')
    c.unique(w['injections'])
    c.require(len(w['injections']) <= 1, 'only one intervention per condition supported')
    for inj in w['injections']:
        c.require(inj['stage'] in stages, 'unsupported injection stage')
        if inj['kind'] == 'material':
            c.fields(inj, ['id', 'kind', 'stage', 'text'])
            c.text(inj['text'])
        else:
            c.fields(inj, ['id', 'kind', 'stage', 'tool'])
            c.require(inj['kind'] == 'tool_failure' and inj['tool'] == 'read_handoff' and
                      inj['stage'] != 'write', 'unsupported tool failure')
    if backend == 'fixture':
        c.fields(w.get('fixture'), stages)
        for stage in stages:
            value = w['fixture'][stage]
            if STAGES[stage] == 'reviewer':
                review_value(value)
            else:
                c.text(value)
    else:
        c.require('fixture' not in w, 'fixture output cannot be passed to a live backend')
    return w


def import_result(store, result, exp, task_id, condition_id, repeat):
    run = result['id']
    receipt = store.blob(c.canonical(result).encode())
    original = store.get('execution_result', run)
    evidence_id = run if original == result else run+'-'+receipt
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        def file(name, data):
            (root/name).write_bytes(data)
            return dict(id=name, path=name, sha256=c.digest(data))
        output = None
        if result['document']:
            output = file('output.txt', store.read_blob(result['document']))
        source = dict(schema_version=1,id=evidence_id,records=[dict(id=run,output=output,
                      missing_reason=None if output else 'no writer output')])
        measurements = {k:dict(value=None,unit=u,scope='execution',completeness='missing',
                               missing_reason='bridge v1 does not report this measurement')
                        for k,u in [('time','seconds'),('tokens','tokens'),('cost','USD')]}
        duration = (datetime.fromisoformat(result['ended']) - datetime.fromisoformat(result['started'])).total_seconds()
        if duration >= 0:
            measurements['time'].update(value=duration, scope='wall_elapsed_including_recovery',
                                        completeness='complete', missing_reason=None)
        record = dict(id=run, task=task_id, condition=condition_id, repeat=repeat,
                      attempt_id=result['runtime_run'], execution_status=result['status'],
                      receipt=receipt, environment=ENVIRONMENT,
                      started=result['started'],ended=result['ended'],measurements=measurements)
        manifest = dict(schema_version=1,id=evidence_id,experiment=exp,format='saved-output-v1',
                        source=file('source.json', c.canonical(source).encode()), runs=[record])
        path = root/'manifest.json'
        path.write_text(c.canonical(manifest))
        service.import_evidence(store, path, execution_receipt=receipt)


def execute(store, experiment, task_id, condition_id, repeat, bridge, codex, *, inspect_only=False):
    exp, tasks = service.context(store, experiment)
    condition = next((x for x in exp['conditions'] if x['id'] == condition_id), None)
    c.require(task_id in tasks and condition and 'workflow' in condition, 'unknown task or execution condition')
    c.require(type(repeat) is int and 1 <= repeat <= exp['repetitions'], 'repeat outside plan')
    run = 'm3-'+c.identity([experiment, task_id, condition_id, repeat])
    with operation_lock(store.root/'execution-locks', run):
        result = store.latest('execution_result', run)
        binding = store.find('execution_binding', run)
        imported = store.find('run', run)
        if result and imported is None:
            # Complete a crash-interrupted initial import before publishing revisions.
            import_result(store, store.get('execution_result', run), experiment, task_id, condition_id, repeat)
        if imported:
            c.require(binding and result, 'slot already has imported evidence')
            first = store.get('execution_result', run)
            c.require(imported['receipt'] == c.identity(first), 'imported evidence conflicts with local execution')
        cached = result and result['status'] not in ('uncertain', 'prepared')
        if result and not inspect_only and result['status'] == 'uncertain' and not shutil.which(bridge):
            cached = True
        if not cached:
            c.require(not inspect_only or binding, 'no local execution to reconcile')
            result = _run(store, exp, task_id, tasks[task_id], condition, run, repeat, bridge, codex,
                          binding, result, inspect_only or bool(result and result['status'] == 'uncertain'))
        import_result(store, result, experiment, task_id, condition_id, repeat)
    return result


def _run(store, exp, task_id, task, condition, run, repeat, bridge, codex, binding, previous, inspect):
    from role_orchestrator import attempts, contracts, runtime
    from role_orchestrator.workflow import review
    from .execution_journal import StageJournal

    plan = validate(condition, exp['budget']['execution'])
    projected = service.execution_input(store, exp['id'], task_id)
    exe = shutil.which(bridge)
    c.require(exe, 'runtime-bridge executable required')
    binary = Path(exe).resolve()
    try:
        attempts.require_capabilities(binary)
    except ValueError as error:
        if inspect:
            raise c.ContractError(str(error)) from error
        raise c.PreflightError(str(error)) from error
    state = (store.root/'executions'/run).resolve()
    c.require(not binding or state.is_dir(), 'execution state lost; recovery required')
    active = None
    if inspect:
        run_id = previous['runtime_run'] if previous else runtime.existing_run_id(state)
    else:
        for stage in review.STAGES:
            preview = review.initial_payload(plan, stage, projected)
            for item in plan['injections']:
                if item['kind'] == 'material' and item['stage'] == stage:
                    preview['additional_material'] = item['text']
            try:
                contracts.preflight_request(review.request(stage, c.canonical(preview)), 'r-'+'0'*32)
            except contracts.RequestNotStarted as error:
                raise c.PreflightError(f'{stage}: {error}') from error
        target = dict(protocol='runtime-bridge/v1', bridge_sha256=file_digest(binary),
                      client_sha256=file_digest(Path(runtime.__file__)),
                      contract_sha256=file_digest(Path(contracts.__file__)),
                      workflow_sha256=file_digest(Path(review.__file__)), task=task['version'],
                      condition=c.identity(condition), codex=codex)
        if plan['backend'] == 'codex':
            cli = shutil.which(codex)
            c.require(cli, 'Codex executable required')
            codex = str(Path(cli).resolve())
            target.update(codex=codex, codex_sha256=file_digest(Path(codex)))
        c.require(binding or not state.exists() or not any(state.iterdir()), 'unexpected pre-existing run state')
        with store.db:
            store.db.execute('BEGIN IMMEDIATE')
            slot = dict(task=task_id, condition=condition['id'], repeat=repeat, id=run)
            if binding:
                c.require(binding == target, 'execution binding changed; use read-only reconciliation')
            else:
                store.reserve_execution(exp['id'], slot, target)
            if store.find('execution_start', run) is None:
                store.put('execution_start', run, datetime.now(timezone.utc).isoformat())
            state.mkdir(parents=True, exist_ok=True)
        binding = target
        active = runtime.Runtime(str(binary), state, plan['backend'], codex)
        run_id = active.identity['run_id']
    reader = attempts.AttemptReader(binary, state, run_id)
    journal = StageJournal(store, run, reader, active)
    try:
        observation = review.run_review(plan, projected, journal, inspection_only=inspect,
                                        legacy_fixture='workflow_sha256' not in binding)
    finally:
        if active is not None:
            active.close()
    if previous and all(previous.get(k) == value for k,value in observation.items()):
        return previous
    result = dict(observation, id=run, runtime_run=run_id, backend=plan['backend'], scenario=plan['scenario'],
                  binding=binding, started=store.get('execution_start', run),
                  ended=datetime.now(timezone.utc).isoformat())
    with store.db:
        store.observe('execution_result', run, result)
    return result
