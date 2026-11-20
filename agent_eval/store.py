"""SQLite index plus immutable, hash-verified local source blobs."""
from contextlib import contextmanager
import json
import sqlite3
import os
import tempfile
from pathlib import Path
from .contracts import ContractError, canonical, digest, identity, require


@contextmanager
def operation_lock(directory, key):
    # A separate database per operation gives a cross-platform, crash-released
    # process lock without holding a write transaction on the shared store.
    directory.mkdir(exist_ok=True)
    lock = sqlite3.connect(directory / identity(key), timeout=0)
    try:
        try:
            lock.execute('BEGIN IMMEDIATE')
        except sqlite3.OperationalError as exc:
            if exc.sqlite_errorcode in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                raise ContractError('operation already in progress') from exc
            raise
        yield
    finally:
        lock.close()


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / 'blobs').mkdir(exist_ok=True)
        self.db = sqlite3.connect(self.root / 'index.sqlite')
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS objects(kind TEXT, id TEXT, body TEXT NOT NULL, PRIMARY KEY(kind,id));
            CREATE TABLE IF NOT EXISTS revisions(
                kind TEXT NOT NULL, id TEXT NOT NULL, body TEXT NOT NULL,
                sequence INTEGER PRIMARY KEY);
            CREATE INDEX IF NOT EXISTS revision_key ON revisions(kind,id,sequence);
            CREATE TABLE IF NOT EXISTS slots(experiment TEXT, task TEXT, condition TEXT, repeat INTEGER,
                run TEXT UNIQUE, PRIMARY KEY(experiment,task,condition,repeat));
        ''')

    def close(self):
        self.db.close()

    def put(self, kind, key, body):
        old = self.db.execute('SELECT body FROM objects WHERE kind=? AND id=?', (kind, key)).fetchone()
        encoded = canonical(body)
        if old:
            require(old[0] == encoded, f'{kind} identity/content conflict')
            return False
        self.db.execute('INSERT INTO objects VALUES(?,?,?)', (kind, key, encoded))
        return True

    def find(self, kind, key):
        row = self.db.execute('SELECT body FROM objects WHERE kind=? AND id=?', (kind, key)).fetchone()
        return json.loads(row[0]) if row else None

    def get(self, kind, key):
        value = self.find(kind, key)
        require(value is not None, f'unknown {kind}: {key}')
        return value

    def all(self, kind):
        return [json.loads(r[0]) for r in self.db.execute('SELECT body FROM objects WHERE kind=? ORDER BY rowid', (kind,))]

    def latest(self, kind, key):
        row = self.db.execute(
            'SELECT body FROM revisions WHERE kind=? AND id=? ORDER BY sequence DESC LIMIT 1',
            (kind, key)).fetchone()
        return json.loads(row[0]) if row else self.find(kind, key)

    def observed(self, kind, key, value):
        if self.find(kind, key) == value:
            return True
        return self.db.execute('SELECT 1 FROM revisions WHERE kind=? AND id=? AND body=? LIMIT 1',
                               (kind, key, canonical(value))).fetchone() is not None

    def current_runs(self):
        for base in self.all('run'):
            yield self.latest('run', base['id'])

    def observe(self, kind, key, value):
        if self.find(kind, key) is None:
            self.put(kind, key, value)
        elif self.latest(kind, key) != value:
            self.db.execute('INSERT INTO revisions(kind,id,body) VALUES(?,?,?)',
                            (kind, key, canonical(value)))

    def reserve_execution(self, experiment, slot, binding):
        require(self.find('run', slot['id']) is None, 'slot already has imported evidence')
        self.slot(experiment, slot)
        self.put('execution_binding', slot['id'], binding)

    def blob(self, data):
        sha = digest(data)
        path = self.root / 'blobs' / sha
        if path.exists():
            require(path.read_bytes() == data, 'stored blob corruption')
            return sha
        # Publish complete bytes atomically when several graders save the same hash.
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as pending:
            temporary = Path(pending.name)
        try:
            temporary.write_bytes(data)
            try:
                os.link(temporary, path)
            except FileExistsError:
                require(path.read_bytes() == data, 'stored blob corruption')
        finally:
            temporary.unlink(missing_ok=True)
        return sha

    def read_blob(self, sha):
        require(isinstance(sha, str) and len(sha) == 64 and all(c in '0123456789abcdef' for c in sha), 'invalid blob hash')
        p = self.root / 'blobs' / sha
        require(p.is_file(), 'missing evidence blob')
        data = p.read_bytes()
        require(digest(data) == sha, 'evidence blob corruption')
        return data

    def slot(self, exp, run):
        slot = (exp, run['task'], run['condition'], run['repeat'], run['id'])
        row = self.db.execute('SELECT run FROM slots WHERE experiment=? AND task=? AND condition=? AND repeat=?', slot[:4]).fetchone()
        if row:
            require(row[0] == run['id'], 'planned slot already has a run; M1 does not select retries automatically')
        else:
            try:
                self.db.execute('INSERT INTO slots VALUES(?,?,?,?,?)', slot)
            except sqlite3.IntegrityError as exc:
                raise ContractError('run already assigned to another slot') from exc
