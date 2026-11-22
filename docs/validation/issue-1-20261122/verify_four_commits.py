"""이미지 내부 파일을 고정 Git blob과 대조하고 공개 가능한 검증 결과를 stdout에 쓴다."""
import hashlib
import json
from pathlib import Path
import subprocess

from build_four_commits import ROOT, TAG, PINS, BASE


def output(*args):
    return subprocess.check_output(args, text=True).strip()


def git_hashes(repo, package):
    rows = output('git', '-C', str(ROOT / repo), 'ls-tree', '-r', PINS[repo], '--', package)
    hashes = {}
    for row in rows.splitlines():
        metadata, name = row.split('\t', 1)
        blob = subprocess.check_output(['git', '-C', str(ROOT / repo), 'cat-file', 'blob', metadata.split()[2]])
        hashes[name] = hashlib.sha256(blob).hexdigest()
    return hashes


def verify():
    info = json.loads(output('docker', 'image', 'inspect', TAG))[0]
    image = info['Id']
    for repo, pin in PINS.items():
        if info['Config']['Labels'].get('org.agent-eval.commit.' + repo) != pin:
            raise ValueError(f'commit label mismatch: {repo}')
    base = json.loads(output('docker', 'image', 'inspect', BASE))[0]
    layers = base['RootFS']['Layers']
    if not layers or info['RootFS']['Layers'][:len(layers)] != layers:
        raise ValueError('image layers do not match the pinned M2 base')

    def run(command, *args):
        return output('docker', 'run', '--rm', '--network=none', '--entrypoint', command, image, *args)

    inspect_tree = """
import hashlib, json, sys
from pathlib import Path
root = Path(sys.argv[1])
print(json.dumps({
    str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
    for p in (root / sys.argv[2]).rglob('*') if p.is_file() and '__pycache__' not in p.parts
}))
"""
    trees = {}
    for repo, package, folder in [('agent-eval', 'agent_eval', '/opt/agent-eval-m3'),
                                  ('agent-eval', 'bundles', '/opt/agent-eval-m3'),
                                  ('role-orchestrator', 'role_orchestrator', '/opt/src/role-orchestrator')]:
        expected = git_hashes(repo, package)
        observed = json.loads(run('python', '-c', inspect_tree, folder, package))
        if not expected or expected != observed:
            raise ValueError(f'file set or content mismatch: {package}')
        # 경로→SHA-256 사전을 키 순서대로 공백 없는 UTF-8 JSON으로 직렬화한다.
        manifest = json.dumps(observed, sort_keys=True, separators=(',', ':')).encode('utf-8')
        trees[package] = {'files': len(observed), 'manifest_sha256': hashlib.sha256(manifest).hexdigest()}

    binary = '/opt/src/role-runtime/bin/runtime-bridge'
    versions = run('go', 'version', '-m', binary).splitlines()
    dependency = next((i for i, line in enumerate(versions)
                       if line.strip().split()[:2] == ['dep', 'github.com/shakystar/codex-adapter']), None)
    if dependency is None or versions[dependency + 1].strip().split() != ['=>', '/tmp/pinned-codex-adapter', '(devel)']:
        raise ValueError('missing local adapter replacement')
    capabilities = json.loads(run(binary, '--capabilities'))
    if capabilities != {'bridge': 1, 'fixture_text': 1, 'inspect_attempt': 1}:
        raise ValueError('unexpected bridge capabilities')
    return {'image': image, 'base': BASE, 'platform': info['Os'] + '/' + info['Architecture'],
            'source_commits': PINS, 'verified_trees': trees, 'local_adapter_replacement_verified': True,
            'runtime_bridge_sha256': run('sha256sum', binary).split()[0], 'bridge_capabilities': capabilities}


if __name__ == '__main__':
    print(json.dumps(verify(), indent=2))
