"""Turn SQLite bytes into a connection and back.

`sqlite3.Connection.serialize`/`deserialize` (Python 3.11+, and only when SQLite
was built with the serialize API) keep everything in memory. Where they are
missing, a private temporary file is used instead, so the rest of the package
never has to care which path it got.
"""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

IN_MEMORY = hasattr(sqlite3.Connection, 'serialize')


class Database:
    """A scene database, opened from bytes or created empty."""

    def __init__(self, data: bytes | None = None, *, pragmas=(), read_only: bool = False):
        self._directory = None
        if IN_MEMORY:
            self.connection = sqlite3.connect(':memory:')
            for pragma in pragmas:
                self.connection.execute(pragma)
            if data is not None:
                self.connection.deserialize(bytes(data))
        else:
            self._directory = tempfile.TemporaryDirectory(prefix='pureref-')
            self._path = Path(self._directory.name) / 'scene.sqlite'
            if data is not None:
                self._path.write_bytes(bytes(data))
            self.connection = sqlite3.connect(self._path)
            for pragma in pragmas:
                self.connection.execute(pragma)
        self.connection.row_factory = sqlite3.Row
        if read_only:
            self.connection.execute('PRAGMA query_only=ON')

    def __enter__(self) -> 'Database':
        return self

    def __exit__(self, *_) -> None:
        self.close()

    def to_bytes(self) -> bytes:
        self.connection.commit()
        if self._directory is None:
            return self.connection.serialize()
        return self._path.read_bytes()

    def rows(self, table: str) -> list[dict]:
        cursor = self.connection.execute(f'SELECT * FROM {table}')
        return [dict(row) for row in cursor]

    def table_names(self) -> list[str]:
        cursor = self.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        return [row[0] for row in cursor]

    def insert(self, table: str, **values) -> None:
        names = ','.join(values)
        placeholders = ','.join('?' for _ in values)
        self.connection.execute(f'INSERT INTO {table} ({names}) VALUES ({placeholders})',
                                list(values.values()))

    def integrity(self) -> list[str]:
        return [row[0] for row in self.connection.execute('PRAGMA integrity_check')]

    def pragma(self, name: str):
        return self.connection.execute(f'PRAGMA {name}').fetchone()[0]

    def close(self) -> None:
        self.connection.close()
        if self._directory is not None:
            self._directory.cleanup()
            self._directory = None
