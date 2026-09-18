"""Turn SQLite bytes into a connection and back.

`sqlite3.Connection.serialize`/`deserialize` (Python 3.11+, and only when SQLite
was built with the serialize API) keep everything in memory. Where they are
missing, a private temporary file is used instead, so the rest of the package
never has to care which path it got.
"""
from __future__ import annotations

import sqlite3
import tempfile
from contextlib import contextmanager
from pathlib import Path

from ..qt import FormatError

IN_MEMORY = hasattr(sqlite3.Connection, 'serialize')


@contextmanager
def _reading(what: str):
    """SQLite complaints about a file are format errors, not stray exceptions.

    A damaged .pur reaches SQLite as a damaged database, and it reports that
    whenever the corruption is touched -- opening, listing tables, reading a
    page. A damaged schema can also carry a column name that is not UTF-8, which
    sqlite3 decodes itself, outside `text_factory`, and raises on. Callers of
    this package should only ever have to catch `FormatError`.
    """
    try:
        yield
    except (sqlite3.Error, UnicodeDecodeError) as error:
        raise FormatError(f'{what}: {error}') from error


def _text(raw: bytes):
    """TEXT cells as Python text, or as bytes when they are not valid UTF-8.

    PureRef keeps serialized payloads in TEXT cells with every byte mapped to the
    code point of the same value, so a healthy file decodes cleanly. A damaged one
    can hold a sequence that is not UTF-8 at all, and sqlite3's default factory
    raises `UnicodeDecodeError` from inside the cursor for it. Handing back the
    bytes keeps the cell readable and lets the value layer report it as unparsed.
    """
    try:
        return raw.decode()
    except UnicodeDecodeError:
        return raw


class Database:
    """A scene database, opened from bytes or created empty."""

    def __init__(self, data: bytes | None = None, *, pragmas=(), read_only: bool = False):
        self._directory = None
        if IN_MEMORY:
            self.connection = sqlite3.connect(':memory:')
            for pragma in pragmas:
                self.connection.execute(pragma)
            if data is not None:
                with _reading('loading the database'):
                    # Present exactly when IN_MEMORY is true, which is what that
                    # flag tests for; typeshed does not know about either.
                    self.connection.deserialize(bytes(data))  # type: ignore[attr-defined]
        else:
            self._directory = tempfile.TemporaryDirectory(prefix='pureref-')
            self._path = Path(self._directory.name) / 'scene.sqlite'
            if data is not None:
                self._path.write_bytes(bytes(data))
            self.connection = sqlite3.connect(self._path)
            for pragma in pragmas:
                self.connection.execute(pragma)
        self.connection.row_factory = sqlite3.Row
        self.connection.text_factory = _text
        if read_only:
            self.connection.execute('PRAGMA query_only=ON')

    def __enter__(self) -> Database:
        return self

    def __exit__(self, *_) -> None:
        self.close()

    def to_bytes(self) -> bytes:
        self.connection.commit()
        if self._directory is None:
            return self.connection.serialize()  # type: ignore[attr-defined]
        return self._path.read_bytes()

    def rows(self, table: str) -> list[dict]:
        with _reading(f'reading {table}'):
            cursor = self.connection.execute(f'SELECT * FROM {table}')
            return [dict(row) for row in cursor]

    def table_names(self) -> list[str]:
        with _reading('listing the tables'):
            cursor = self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            names = [row[0] for row in cursor]
        if not all(isinstance(name, str) for name in names):
            raise FormatError('the schema holds a table name that is not text')
        return names

    def insert(self, table: str, **values) -> None:
        names = ','.join(values)
        placeholders = ','.join('?' for _ in values)
        self.connection.execute(f'INSERT INTO {table} ({names}) VALUES ({placeholders})',
                                list(values.values()))

    def integrity(self) -> list[str]:
        with _reading('checking integrity'):
            return [row[0] for row in self.connection.execute('PRAGMA integrity_check')]

    def pragma(self, name: str):
        with _reading(f'reading PRAGMA {name}'):
            return self.connection.execute(f'PRAGMA {name}').fetchone()[0]

    def close(self) -> None:
        self.connection.close()
        if self._directory is not None:
            self._directory.cleanup()
            self._directory = None
