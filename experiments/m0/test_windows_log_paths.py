"""Regression checks for the pinned Inspect sample-buffer path patch."""
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from inspect_ai.log._recorders.buffer.database import resolve_db_dir, sqlite_readonly_uri


@unittest.skipUnless(os.name == 'nt', 'Windows path regression')
class WindowsBufferPaths(unittest.TestCase):
    def setUp(self):
        Path('artifacts').mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir='artifacts')
        # Keep cleanup on the same extended path used to create the long files.
        self.tmp.name = str(resolve_db_dir(Path(self.tmp.name)))
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).absolute()

    def test_long_path_and_escaped_readonly_roundtrip(self):
        directory = resolve_db_dir(self.base / ('한글 # ' * 12))
        directory.mkdir(parents=True)
        database = directory / ('sample-' * 20 + '.db')
        self.assertGreater(len(str(database)), 260)
        with closing(sqlite3.connect(database)) as connection:
            connection.execute('create table evidence(value text)')
            connection.execute("insert into evidence values ('preserved')")
            connection.commit()
        with closing(sqlite3.connect(sqlite_readonly_uri(database), uri=True)) as connection:
            self.assertEqual(connection.execute('select value from evidence').fetchone(), ('preserved',))
            with self.assertRaises(sqlite3.OperationalError):
                connection.execute("insert into evidence values ('must fail')")

    def test_readonly_missing_database_is_not_created(self):
        database = resolve_db_dir(self.base) / 'missing # 한글.db'
        with self.assertRaises(sqlite3.OperationalError):
            sqlite3.connect(sqlite_readonly_uri(database), uri=True)
        self.assertFalse(database.exists())

    def test_existing_extended_path_is_idempotent(self):
        extended = resolve_db_dir(self.base)
        self.assertTrue(str(extended).startswith('\\\\?\\'))
        self.assertEqual(resolve_db_dir(extended), extended)

    def test_unc_prefix_without_connecting_to_share(self):
        self.assertEqual(str(resolve_db_dir(Path(r'\\server\share\buffer'))),
                         r'\\?\UNC\server\share\buffer')


if __name__ == '__main__':
    unittest.main()
