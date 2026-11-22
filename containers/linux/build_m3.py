"""로컬 작업 트리로 M3 이미지를 빌드하고 선택적으로 codex-adapter 커밋을 고정한다."""
import argparse
import hashlib
from pathlib import Path
import re
from shutil import copy2, copytree, ignore_patterns
import subprocess
from tempfile import TemporaryDirectory


def archive_adapter(repo, commit, archive):
    """Docker에는 선택한 커밋의 추적 파일만 전달한다."""
    git = ['git', '-C', str(repo), '--no-replace-objects']
    kind = subprocess.check_output([*git, 'cat-file', '-t', commit], text=True).strip()
    if kind != 'commit':
        raise ValueError('--adapter-commit must name a commit object')
    with archive.open('wb') as output:
        subprocess.run([*git, '-c', 'core.autocrlf=false', 'archive', '--format=tar', commit],
                       stdout=output, check=True)
    return hashlib.sha256(archive.read_bytes()).hexdigest()


def main():
    project = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, default=project.parent/'role-runtime')
    parser.add_argument('--orchestrator', type=Path, default=project.parent/'role-orchestrator')
    parser.add_argument('--adapter', type=Path, help='codex-adapter Git 저장소 경로')
    parser.add_argument('--adapter-commit', help='사용할 어댑터 커밋의 전체 SHA-1 (40자리)')
    parser.add_argument('--tag', default='agent-eval-m3:dev')
    args = parser.parse_args()
    if (args.adapter is None) != (args.adapter_commit is None):
        parser.error('--adapter and --adapter-commit must be specified together')
    if args.adapter_commit is not None and not re.fullmatch('[0-9a-f]{40}', args.adapter_commit):
        parser.error('--adapter-commit requires a full lowercase 40-character SHA-1')
    with TemporaryDirectory() as temp:
        context = Path(temp)
        archive = context / 'codex-adapter.tar'
        build_args = []
        if args.adapter is not None:
            try:
                digest = archive_adapter(args.adapter, args.adapter_commit, archive)
            except (OSError, ValueError, subprocess.CalledProcessError) as error:
                parser.exit(1, f'Cannot archive requested adapter commit: {error}\n')
            build_args = ['--build-arg', f'ADAPTER_COMMIT={args.adapter_commit}',
                          '--build-arg', f'ADAPTER_ARCHIVE_SHA256={digest}',
                          '--label', f'org.agent-eval.codex-adapter.commit={args.adapter_commit}',
                          '--label', f'org.agent-eval.codex-adapter.archive-sha256={digest}']
        else:
            archive.touch()
        for root, name in [(project, 'agent_eval'), (project, 'tests'), (project, 'examples'),
                           (args.orchestrator, 'role_orchestrator'), (args.runtime, 'cmd/runtime-bridge'),
                           (args.runtime, 'internal')]:
            copytree(root/name, context/name, ignore=ignore_patterns('__pycache__', '*.pyc'))
        for name in ('go.mod', 'go.sum'):
            copy2(args.runtime/name, context/name)
        for name in ('Dockerfile.m3', 'm3-entrypoint.py'):
            copy2(project/'containers/linux'/name, context/name)
        subprocess.run(['docker', 'build', *build_args, '-f', 'Dockerfile.m3', '-t', args.tag, '.'],
                       cwd=context, check=True)


if __name__ == '__main__':
    main()
