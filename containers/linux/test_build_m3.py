"""Git 객체에서 M3 어댑터 입력을 준비하는 경로의 회귀 검사."""
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

from build_m3 import archive_adapter


class AdapterArchiveTest(unittest.TestCase):
    def test_requested_commit_is_independent_of_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)

            def git(*args):
                return subprocess.check_output(['git', '-C', str(repo), '-c', 'user.name=test',
                                                '-c', 'user.email=test@example.invalid',
                                                '-c', 'commit.gpgsign=false', *args], text=True).strip()

            git('init', '--quiet')
            source = repo / 'adapter.go'
            source.write_bytes(b'first\n')
            git('add', 'adapter.go')
            git('commit', '--quiet', '-m', 'first')
            first = git('rev-parse', 'HEAD')
            source.write_bytes(b'second\n')
            git('commit', '--quiet', '-am', 'second')
            second = git('rev-parse', 'HEAD')
            source.write_bytes(b'working tree\n')
            (repo / 'untracked').write_bytes(b'untracked\n')

            archive = repo / 'result.tar'
            digests = []
            for commit, content in [(first, b'first\n'), (second, b'second\n')]:
                digests.append(archive_adapter(repo, commit, archive))
                with tarfile.open(archive) as tree:
                    self.assertEqual(tree.getnames(), ['adapter.go'])
                    self.assertEqual(tree.extractfile('adapter.go').read(), content)
            self.assertNotEqual(digests[0], digests[1])
            with self.assertRaisesRegex(ValueError, 'must name a commit'):
                archive_adapter(repo, git('rev-parse', 'HEAD^{tree}'), archive)


if __name__ == '__main__':
    unittest.main()
