"""Actual owner workflow -> saved evidence -> separate Inspect process."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from role_orchestrator.workflow.client import Client, ControlError

ROOT = Path('/opt/src/role-orchestrator')
BINARY = '/opt/src/role-runtime/bin/runtime-workflow'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--backend', choices=['fixture', 'codex'], default='fixture')
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    if args.state.exists():
        raise ValueError('fresh integration state required; existing evidence must not be overwritten')
    args.state.mkdir(parents=True)
    runtime = args.state / 'runtime'
    run_id = 'linux-' + args.backend
    client = Client(runtime / 'control/runtime.sock', run_id)
    config = ROOT / 'examples' / ('model-document-workflow.json' if args.backend == 'codex' else 'document-workflow.json')
    server = None
    output = (args.state / 'runtime.log').open('a')

    def start():
        nonlocal server
        server = subprocess.Popen([BINARY, '--state', str(runtime), '--run-id', run_id,
                                   '--backend', args.backend, '--codex', '/opt/codex-bin'],
                                  stdout=output, stderr=output)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if server.poll() is not None:
                raise RuntimeError('runtime exited; inspect retained runtime.log')
            try:
                client.call('health.get')
                return
            except (OSError, ValueError):
                time.sleep(.1)
        raise RuntimeError('runtime control did not become ready')

    def stop():
        nonlocal server
        if server and server.poll() is None:
            server.terminate()
            server.wait(timeout=30)
        server = None

    def poll():
        proc = subprocess.run([sys.executable, '-m', 'role_orchestrator.workflow',
                               '--state', str(args.state / 'graph'), '--socket', str(client.path),
                               '--run-id', run_id, '--config', str(config)],
                              cwd=ROOT, text=True, capture_output=True, timeout=30)
        if proc.returncode:
            (args.state / 'graph-error.log').write_text(proc.stderr)
            raise RuntimeError('workflow poll failed; retained graph-error.log')
        return json.loads(proc.stdout)

    def receipts():
        return {name: client.call('receipts.get', task_id=name) for name in ('producer', 'consumer')}

    def attempts():
        cursor = None
        rows = []
        for _ in range(20):
            page = client.call('events.list', after_cursor=cursor, limit=100)
            rows.extend(row['data'] for row in page['items'])
            if page['next_cursor'] == cursor or len(page['items']) < 100:
                return [row for row in rows if row['kind'] == 'attempt.started']
            cursor = page['next_cursor']
        raise RuntimeError('event page budget exceeded')

    try:
        start()
        started = time.monotonic()
        while not poll()['done']:
            if args.backend == 'fixture' and time.monotonic() - started > 60:
                raise RuntimeError('fixture did not finish')
            for task_id in ('producer', 'consumer'):
                try:
                    receipt = client.call('receipts.get', task_id=task_id)
                except ControlError as exc:
                    if exc.code == 'not_found':
                        continue
                    raise
                if receipt['status'] in ('uncertain', 'failed'):
                    raise RuntimeError(f'{task_id} failed; no replay performed')
            # No automatic model-task timeout or failed-work retry.
            time.sleep(.2)
        before = receipts()
        assert all(r['status'] == 'completed' and r['generation'] == 1 for r in before.values())
        assert before['producer']['artifact_valid']
        first_attempts = attempts()
        assert len(first_attempts) == 2
        document_path = runtime / 'artifacts/document.json'
        assert digest(document_path) == before['producer']['artifact']['sha256']
        if args.backend == 'codex':
            review = (runtime / 'artifacts/review.json').read_text()
            assert before['consumer']['artifact_valid']
            assert json.loads(review)['source_sha256'] == digest(document_path)
        else:
            review = 'synthetic consumer completed'
        status_file = runtime / 'model-status.jsonl'
        status_digest = digest(status_file)
        bundle = dict(backend=args.backend, run_id=run_id, receipts=before,
                      document=document_path.read_text(), review=review)
        bundle_path = args.state / 'evidence.json'
        bundle_path.write_text(json.dumps(bundle, ensure_ascii=False))
        # Separate process, interpreter and dependency environment. No execution handle.
        subprocess.run(['/opt/inspect-env/bin/python', '/opt/agent-eval/score_artifacts.py',
                        '--bundle', str(bundle_path), '--output', str(args.state / 'inspect')], check=True)
        assert receipts() == before and attempts() == first_attempts
        assert digest(status_file) == status_digest
        stop()
        start()
        assert poll()['done']
        assert receipts() == before and attempts() == first_attempts
        assert digest(status_file) == status_digest
        scorer_result = json.loads((args.state / 'inspect/result.json').read_text())
        result = dict(status='passed', backend=args.backend, runtime='actual Go process',
                      orchestrator='actual LangGraph/SQLite process', inspect=scorer_result,
                      execution_attempts=2, completed_tasks=2, receipt_generations=[1, 1],
                      rescore_additional_attempts=0, restart_additional_attempts=0,
                      model_status_unchanged_after_rescore_and_restart=True,
                      document_sha256=digest(document_path), image_id=os.environ.get('AGENT_EVAL_IMAGE_ID'),
                      limitations=['Fixed workflow; not arbitrary task injection',
                                   'Rule-based integration evidence, not professional task quality',
                                   'Fixture consumer does not perform semantic review'] if args.backend == 'fixture'
                                  else ['Fixed workflow; not arbitrary task injection',
                                        'No human-confirmed semantic quality evaluation'])
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result))
    finally:
        stop()
        output.close()


if __name__ == '__main__':
    main()
