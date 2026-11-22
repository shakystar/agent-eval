"""고정 M2 이미지와 나란히 체크아웃한 네 저장소에서 Linux M3 이미지를 빌드한다."""
import io
from pathlib import Path
import subprocess
import tarfile
from tempfile import TemporaryDirectory

# <workspace>/agent-eval/docs/validation/issue-1-20261122/build_four_commits.py
ROOT = Path(__file__).resolve().parents[4]
PINS = {
    'agent-eval': '6db70ed063b2d993670f56408da0493524a02bfa',
    'role-orchestrator': '66657b78210fd16697175abec4b1807e95ed1a28',
    'role-runtime': '7b2f83702fac83e4004bf7b105a343872e3e53d6',
    'codex-adapter': '2b8c204b0cb7e3c63c60a3fa7923e4e9ca4d02bb',
}
BASE = 'sha256:1d517bc86d8d0a22cd188ad8f1d0c0c6f899e97d1b29b988c1c64484a9c4ccfc'
TAG = 'agent-eval-m3:inventory-four-6db70ed'


def extract(repo, context, paths=(), prefix=''):
    args = ['git', '-C', str(ROOT / repo), '-c', 'core.autocrlf=false', 'archive', '--format=tar',
            '--prefix=' + prefix, PINS[repo], *paths]
    with tarfile.open(fileobj=io.BytesIO(subprocess.check_output(args))) as tar:
        for member in tar:
            path = (context / member.name).resolve()
            if not path.is_relative_to(context) or not (member.isfile() or member.isdir()):
                raise ValueError(f'unexpected Git archive member: {member.name}')
        tar.extractall(context)


def prepare(context):
    extract('agent-eval', context, ['agent_eval', 'tests', 'examples', 'bundles',
                                    'containers/linux/Dockerfile.m3', 'containers/linux/m3-entrypoint.py'])
    extract('role-orchestrator', context, ['role_orchestrator'])
    extract('role-runtime', context, ['cmd/runtime-bridge', 'internal', 'go.mod', 'go.sum'])
    extract('codex-adapter', context, prefix='adapter-src/')
    recipe_dir = context / 'containers/linux'
    recipe = (recipe_dir / 'Dockerfile.m3').read_text(encoding='utf-8')
    marker = 'RUN GOMODCACHE='
    if recipe.count(marker) != 1:
        raise ValueError('unexpected M3 recipe')
    recipe = recipe.replace(marker, 'COPY adapter-src /tmp/pinned-codex-adapter\n'
                            'RUN go mod edit -replace=github.com/shakystar/codex-adapter=/tmp/pinned-codex-adapter\n'
                            + marker)
    recipe += '\nCOPY --chown=evaluator:evaluator bundles /opt/agent-eval-m3/bundles\n'
    (context / 'Dockerfile.m3').write_text(recipe, encoding='utf-8', newline='\n')
    (context / 'm3-entrypoint.py').write_bytes((recipe_dir / 'm3-entrypoint.py').read_bytes())


def main():
    base = subprocess.check_output(['docker', 'image', 'inspect', '--format', '{{.Id}}',
                                    'agent-eval-m2:dev'], text=True).strip()
    if base != BASE:
        raise RuntimeError('M2 base image ID differs')
    with TemporaryDirectory() as directory:
        context = Path(directory).resolve()
        prepare(context)
        labels = [arg for repo, sha in PINS.items()
                  for arg in ['--label', f'org.agent-eval.commit.{repo}={sha}']]
        subprocess.run(['docker', 'build', '--network=none', *labels, '-f', 'Dockerfile.m3',
                        '-t', TAG, '.'], cwd=context, check=True)


if __name__ == '__main__':
    main()
