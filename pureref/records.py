"""Declare a binary record once and read or write it either way.

The 1.x format is a sequence of fixed records, and the tempting way to handle it
is a reader that walks the fields and a writer that repeats them in the same
order. That is what this package did, and every field discovered meant editing
both lists in lockstep, with nothing checking they still agreed.

So a record is a list of `Field(name, codec)` and both directions come from it:

    IMAGE_ITEM.read(cursor)            -> dict of values
    IMAGE_ITEM.write(buffer, values)   -> bytes in the same order

A codec is anything with `read(cursor)` and `write(buffer, value)`. Regions whose
meaning is unknown are `Raw(n)` fields — named, documented and carried through,
rather than paddings that quietly drop what a file had there.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field as dataclass_field
from typing import Any, Callable

from .qt import Cursor, FormatError, pack_string

NULL = 0xFFFFFFFF


class Codec:
    """Reads one value from a cursor and writes it back."""

    size: int | None = None      # fixed byte count, when there is one

    def read(self, cursor: Cursor) -> Any:      # pragma: no cover - interface
        raise NotImplementedError

    def write(self, buffer: bytearray, value: Any) -> None:  # pragma: no cover
        raise NotImplementedError

    @property
    def description(self) -> str:
        return type(self).__name__.lower()


@dataclass(frozen=True)
class Scalar(Codec):
    """One `struct` value, big-endian like everything in a `.pur`."""

    format: str
    label: str

    @property
    def size(self) -> int:
        return struct.calcsize('>' + self.format)

    def read(self, cursor: Cursor):
        return cursor.read(self.format)

    def write(self, buffer: bytearray, value) -> None:
        buffer += struct.pack('>' + self.format, value)

    @property
    def description(self) -> str:
        return self.label


U8 = Scalar('B', 'uint8')
I8 = Scalar('b', 'int8')
U16 = Scalar('H', 'uint16')
U32 = Scalar('I', 'uint32')
I32 = Scalar('i', 'int32')
U64 = Scalar('Q', 'uint64')
I64 = Scalar('q', 'int64')
F64 = Scalar('d', 'double')


@dataclass(frozen=True)
class Tuple(Codec):
    """Several scalars of the same kind, read and written together."""

    format: str
    count: int
    label: str

    @property
    def size(self) -> int:
        return struct.calcsize('>' + str(self.count) + self.format)

    def read(self, cursor: Cursor) -> tuple:
        return tuple(cursor.read(f'{self.count}{self.format}'))

    def write(self, buffer: bytearray, value) -> None:
        if len(value) != self.count:
            raise ValueError(f'{self.label} needs {self.count} values')
        buffer += struct.pack(f'>{self.count}{self.format}', *value)

    @property
    def description(self) -> str:
        return self.label


PointF = Tuple('d', 2, 'two doubles: x, y')
Matrix6 = Tuple('d', 6, 'six doubles: m11 m12 m13 m21 m22 m23')
Rect = Tuple('d', 4, 'four doubles')


@dataclass(frozen=True)
class Raw(Codec):
    """Bytes kept exactly as they are, because their meaning is not settled."""

    length: int
    label: str = 'bytes'

    @property
    def size(self) -> int:
        return self.length

    def read(self, cursor: Cursor) -> bytes:
        return cursor.take(self.length)

    def write(self, buffer: bytearray, value) -> None:
        data = bytes(value or b'')
        if len(data) > self.length:
            raise ValueError(f'{self.label}: {len(data)} bytes into {self.length}')
        buffer += data + bytes(self.length - len(data))

    @property
    def description(self) -> str:
        return f'{self.length} {self.label}'


class Utf16String(Codec):
    """A Qt QString: a byte count, then UTF-16BE."""

    def read(self, cursor: Cursor) -> str:
        return cursor.read_string() or ''

    def write(self, buffer: bytearray, value) -> None:
        buffer += pack_string(value or '')

    @property
    def description(self) -> str:
        return 'QString'


class NullableUtf16String(Utf16String):
    """The same, except `0xffffffff` in the length means there is no string."""

    def read(self, cursor: Cursor) -> str | None:
        if cursor.peek('i') == -1:
            cursor.skip(4)
            return None
        return cursor.read_string()

    def write(self, buffer: bytearray, value) -> None:
        if value is None:
            buffer += struct.pack('>i', -1)
        else:
            buffer += pack_string(value)

    @property
    def description(self) -> str:
        return 'QString or -1 for none'


class ZeroMarker(Codec):
    """Four zero bytes that are there or not; True when present.

    PureRef writes them in front of the source of a brute-force loaded image.
    """

    def read(self, cursor: Cursor) -> bool:
        if cursor.remaining >= 4 and cursor.peek('I') == 0:
            cursor.skip(4)
            return True
        return False

    def write(self, buffer: bytearray, value) -> None:
        if value:
            buffer += struct.pack('>I', 0)

    @property
    def description(self) -> str:
        return 'uint32 0, only when present'


@dataclass
class Field:
    """One named piece of a record."""

    name: str
    codec: Codec
    default: Any = None
    when: Callable[[dict], bool] | None = None
    doc: str = ''

    @property
    def kept(self) -> bool:
        """False for fields that only exist to describe padding."""
        return not self.name.startswith('_')


@dataclass
class Record:
    """An ordered list of fields, readable and writable in one declaration."""

    name: str
    fields: list[Field] = dataclass_field(default_factory=list)

    def read(self, cursor: Cursor, values: dict | None = None) -> dict:
        values = dict(values or {})
        for entry in self.fields:
            if entry.when is not None and not entry.when(values):
                # A field the file does not carry still lands in the result, as
                # its default, so callers see a complete record either way.
                values.setdefault(entry.name, entry.default)
                continue
            try:
                values[entry.name] = entry.codec.read(cursor)
            except FormatError as error:
                raise FormatError(f'{self.name}.{entry.name}: {error}') from error
        return values

    def write(self, buffer: bytearray, values: dict) -> bytearray:
        for entry in self.fields:
            if entry.when is not None and not entry.when(values):
                continue
            value = values.get(entry.name, entry.default)
            if value is None and entry.default is not None:
                value = entry.default
            entry.codec.write(buffer, value)
        return buffer

    def to_bytes(self, values: dict) -> bytes:
        return bytes(self.write(bytearray(), values))

    @property
    def size(self) -> int | None:
        """Total byte count, when every field has a fixed one."""
        total = 0
        for entry in self.fields:
            if entry.codec.size is None or entry.when is not None:
                return None
            total += entry.codec.size
        return total

    def describe(self) -> list[tuple[str, str, str]]:
        """(field, encoding, note) rows, for generating documentation."""
        return [(entry.name, entry.codec.description, entry.doc)
                for entry in self.fields]
