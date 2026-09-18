"""A 2.x file as it is on disk, before anything is interpreted.

`Scene` is the convenient view; this is the honest one. It hands back the
envelope, the reconstructed SQLite bytes and the rows exactly as stored, which is
what you want when something is wrong with a file, when PureRef has added a
column this package does not know, or when you would rather write SQL than model
objects.

    with Document.open(Path('board.pur').read_bytes()) as document:
        document.rows('items')          # list of dicts, values untouched
        document.database               # the SQLite bytes
        scene = document.to_scene()     # the interpreted view
"""
from __future__ import annotations

from pathlib import Path

from . import schema
from .database import Database
from .envelope import Envelope, unwrap, wrap


class Document:
    """The envelope plus the database, with no interpretation applied."""

    def __init__(self, envelope: Envelope, database: bytes, *, read_only: bool = True):
        self.envelope = envelope
        self.database = database
        self._handle = Database(database, read_only=read_only)

    @classmethod
    def open(cls, data: bytes, *, read_only: bool = True) -> 'Document':
        envelope, database = unwrap(bytes(data))
        return cls(envelope, database, read_only=read_only)

    @classmethod
    def read(cls, path, *, read_only: bool = True) -> 'Document':
        return cls.open(Path(path).read_bytes(), read_only=read_only)

    # --- the database as it is ------------------------------------------------

    @property
    def connection(self):
        """The live sqlite3 connection, for queries this package does not make."""
        return self._handle.connection

    def tables(self) -> list[str]:
        return self._handle.table_names()

    def rows(self, table: str) -> list[dict]:
        return self._handle.rows(table)

    def unknown_tables(self) -> list[str]:
        return sorted(set(self.tables()) - set(schema.TABLES))

    def missing_columns(self) -> dict[str, list[str]]:
        return schema.missing_columns(self.connection)

    def integrity(self) -> list[str]:
        return self._handle.integrity()

    def user_version(self) -> int:
        return self._handle.pragma('user_version')

    # --- interpretation -------------------------------------------------------

    def to_scene(self):
        from .reader import build_scene
        return build_scene(self)

    def repack(self, envelope: Envelope | None = None) -> bytes:
        """Wrap the database again, which reproduces the original bytes."""
        return wrap(self.database, envelope or self.envelope)

    def close(self) -> None:
        self._handle.close()

    def __enter__(self) -> 'Document':
        return self

    def __exit__(self, *_) -> None:
        self.close()
