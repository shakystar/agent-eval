"""Run reproducible acceptance and integration checks; any failure is nonzero."""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--mode', choices=['fixture', 'codex'], default='fixture')
parser.add_argument('--state', type=Path, default=Path('/tmp/ae-integration'))
parser.add_argument('--reports', type=Path, default=Path('/results'))
args = parser.parse_args()
args.reports.mkdir(parents=True, exist_ok=True)
if args.mode == 'fixture':
    runtime = '/opt/src/role-runtime'
    subprocess.run([runtime + '/scripts/go.sh', 'vet', './internal/engine', './internal/control', './internal/lifecycle'], cwd=runtime, check=True)
    subprocess.run([runtime + '/scripts/go.sh', 'test', '-race', './internal/engine', './internal/control', './internal/lifecycle', '-count=1'], cwd=runtime, check=True)
    subprocess.run([sys.executable, '-m', 'role_orchestrator.evaluation', '--runtime-source', runtime,
                    '--output', str(args.reports / 'workflow-acceptance.json')], check=True)
    acceptance = json.loads((args.reports / 'workflow-acceptance.json').read_text())
    assert len(acceptance['cases']) == 19 and all(c['status'] == 'passed' for c in acceptance['cases'])
subprocess.run([sys.executable, '/opt/agent-eval/integration_driver.py', '--backend', args.mode,
                '--state', str(args.state), '--report', str(args.reports / (args.mode + '-inspect-integration.json'))], check=True)
