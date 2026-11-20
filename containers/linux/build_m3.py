"""Build the M3 image from the three local source trees (including local changes)."""
import argparse
from pathlib import Path
from shutil import copy2, copytree, ignore_patterns
import subprocess
from tempfile import TemporaryDirectory


def main():
    project = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, default=project.parent/'role-runtime')
    parser.add_argument('--orchestrator', type=Path, default=project.parent/'role-orchestrator')
    parser.add_argument('--tag', default='agent-eval-m3:dev')
    args = parser.parse_args()
    with TemporaryDirectory() as temp:
        context = Path(temp)
        for root, name in [(project, 'agent_eval'), (project, 'tests'), (project, 'examples'),
                           (args.orchestrator, 'role_orchestrator'), (args.runtime, 'cmd/runtime-bridge'),
                           (args.runtime, 'internal')]:
            copytree(root/name, context/name, ignore=ignore_patterns('__pycache__', '*.pyc'))
        for name in ('go.mod', 'go.sum'):
            copy2(args.runtime/name, context/name)
        for name in ('Dockerfile.m3', 'm3-entrypoint.py'):
            copy2(project/'containers/linux'/name, context/name)
        subprocess.run(['docker','build','-f','Dockerfile.m3','-t',args.tag,'.'],cwd=context,check=True)


if __name__ == '__main__':
    main()
