"""Build context from exact commits, never copy credentials or working-tree data."""
import argparse
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--context', type=Path, required=True)
for name in ('role-runtime', 'role-orchestrator', 'inspect'):
    parser.add_argument('--' + name, type=Path, required=True)
args = parser.parse_args()
pins = json.loads((HERE / 'sources.json').read_text())
args.context.mkdir(parents=True, exist_ok=True)


def git(*argv, cwd=None):
    return subprocess.check_output(['git', *map(str, argv)], cwd=cwd, text=True).strip()


for name in ('role-runtime', 'role-orchestrator', 'inspect'):
    dest = args.context / name
    if not dest.exists():
        git('clone', '--no-hardlinks', '--no-checkout', getattr(args, name.replace('-', '_')).resolve(), dest.resolve())
        git('config', 'core.autocrlf', 'false', cwd=dest)
        git('checkout', '--detach', pins[name], cwd=dest)
    if git('rev-parse', 'HEAD', cwd=dest) != pins[name] or git('status', '--porcelain', cwd=dest):
        raise ValueError(f'{name}: context must be clean and match sources.json; use a new context')
for name in ('Dockerfile', 'sources.json'):
    (args.context / name).write_text((HERE / name).read_text(), newline='\n')
requirements = (REPO / 'experiments/m0/environment-windows-py312.txt').read_text().splitlines()
requirements = ['inspect-ai @ file:///opt/src/inspect' if line.startswith('inspect-ai @') else line
                for line in requirements if not line.startswith('#')]
(args.context / 'inspect-requirements.txt').write_text('\n'.join(requirements) + '\n', newline='\n')
integration = args.context / 'integration'
integration.mkdir(exist_ok=True)
for name in ('run_suite.py', 'integration_driver.py', 'score_artifacts.py'):
    (integration / name).write_text((HERE / name).read_text(), newline='\n')
print(json.dumps({'context': str(args.context), 'sources': pins}))
