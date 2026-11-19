"""SQLite index plus immutable, hash-verified local source blobs."""
import json
import sqlite3
from pathlib import Path
from .contracts import ContractError, canonical, digest, require


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / 'blobs').mkdir(exist_ok=True)
        self.db = sqlite3.connect(self.root / 'index.sqlite')
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS objects(kind TEXT, id TEXT, body TEXT NOT NULL, PRIMARY KEY(kind,id));
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

    def get(self, kind, key):
        row = self.db.execute('SELECT body FROM objects WHERE kind=? AND id=?', (kind, key)).fetchone()
        require(row is not None, f'unknown {kind}: {key}')
        return json.loads(row[0])

    def all(self, kind):
        return [json.loads(r[0]) for r in self.db.execute('SELECT body FROM objects WHERE kind=? ORDER BY rowid', (kind,))]

    def blob(self, data):
        sha = digest(data)
        path = self.root / 'blobs' / sha
        try:
            with path.open('xb') as f:
                f.write(data)
        except FileExistsError:
            require(path.read_bytes() == data, 'stored blob corruption')
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
