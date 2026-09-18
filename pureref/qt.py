"""Qt serialization primitives used by both .pur generations.

PureRef 1.x writes Qt-style values straight into its binary stream; PureRef 2.x
writes QDataStream QVariant records into SQLite text cells. Both use big-endian
integers, IEEE-754 binary64 reals, byte-counted UTF-16BE strings and byte-counted
byte arrays, so they share this module.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from fractions import Fraction

NULL_LENGTH = 0xFFFFFFFF

# QVariant type ids as they appear in the stream (not the running Qt's metatype ids).
TYPE_RECTF = 20
TYPE_SIZEF = 22
TYPE_TRANSFORM = 80
TYPE_CUSTOM = 1024

# QPainterPath element kinds.
MOVE_TO, LINE_TO, CURVE_TO, CURVE_DATA = 0, 1, 2, 3


class FormatError(ValueError):
    """Raised when bytes do not match the format they claim to be."""


class Cursor:
    """Forward-only reader over a bytes-like object."""

    def __init__(self, data: bytes, pos: int = 0):
        self.data = data
        self.pos = pos

    def __len__(self):
        return len(self.data)

    @property
    def remaining(self) -> int:
        return len(self.data) - self.pos

    def take(self, count: int) -> bytes:
        if count < 0 or count > self.remaining:
            raise FormatError(f'Truncated field: wanted {count} bytes, {self.remaining} left')
        chunk = bytes(self.data[self.pos:self.pos + count])
        self.pos += count
        return chunk

    def peek(self, fmt: str, offset: int = 0):
        size = struct.calcsize('>' + fmt)
        if offset < 0 or self.pos + offset + size > len(self.data):
            raise FormatError('Truncated field while peeking')
        start = self.pos + offset
        values = struct.unpack('>' + fmt, self.data[start:start + size])
        return values[0] if len(values) == 1 else values

    def read(self, fmt: str):
        values = struct.unpack('>' + fmt, self.take(struct.calcsize('>' + fmt)))
        return values[0] if len(values) == 1 else values

    def skip(self, count: int) -> None:
        self.take(count)

    def read_bytes(self) -> bytes | None:
        """QByteArray: uint32 byte count, then the bytes. 0xffffffff is null."""
        count = self.read('I')
        return None if count == NULL_LENGTH else self.take(count)

    def read_string(self) -> str | None:
        """QString: uint32 *byte* count, then UTF-16BE code units."""
        raw = self.read_bytes()
        if raw is None:
            return None
        if len(raw) % 2:
            raise FormatError('QString with an odd byte count')
        try:
            return raw.decode('utf-16-be')
        except UnicodeDecodeError as error:
            raise FormatError('QString is not valid UTF-16BE') from error


def pack_bytes(value: bytes | None) -> bytes:
    if value is None:
        return struct.pack('>I', NULL_LENGTH)
    return struct.pack('>I', len(value)) + bytes(value)


def pack_string(value: str | None) -> bytes:
    return pack_bytes(None if value is None else value.encode('utf-16-be'))


def pack_matrix9(matrix) -> bytes:
    """QTransform: m11 m12 m13 m21 m22 m23 m31 m32 m33."""
    if len(matrix) != 9:
        raise ValueError('A QTransform needs nine values')
    return struct.pack('>9d', *matrix)


def unpack_matrix9(cursor: Cursor) -> list[float]:
    return list(cursor.read('9d'))


# --- PureRef 2.x cell payloads ------------------------------------------------

def cell_to_bytes(value) -> bytes:
    """Recover a serialized payload from a SQLite cell.

    PureRef stores these payloads with storage class TEXT: every byte was mapped
    to the code point of the same value, so Latin-1 turns the string back into
    the original bytes. True BLOB cells come back as bytes already.
    """
    if value is None:
        return b''
    if isinstance(value, str):
        return value.encode('latin1')
    return bytes(value)


def bytes_to_cell(payload: bytes) -> str:
    """Encode a payload the way PureRef binds it: a Latin-1 mapped string."""
    return bytes(payload).decode('latin1')


def pack_variant(type_id: int, payload: bytes, type_name: str | None = None) -> bytes:
    header = struct.pack('>IB', type_id, 0)
    if type_name is not None:
        header += pack_bytes(type_name.encode('ascii') + b'\0')
    return header + payload


def variant_cell(type_id: int, payload: bytes, type_name: str | None = None) -> str:
    return bytes_to_cell(pack_variant(type_id, payload, type_name))


def read_variant_header(cursor: Cursor) -> tuple[int, bool, str | None]:
    type_id, is_null = cursor.read('IB')
    name = None
    if type_id == TYPE_CUSTOM:
        raw = cursor.read_bytes() or b''
        name = raw.rstrip(b'\0').decode('ascii', 'replace')
    return type_id, bool(is_null), name


def transform_cell(matrix) -> str:
    return variant_cell(TYPE_TRANSFORM, pack_matrix9(matrix))


def rect_cell(x: float, y: float, width: float, height: float) -> str:
    return variant_cell(TYPE_RECTF, struct.pack('>4d', x, y, width, height))


def size_cell(width: float, height: float) -> str:
    return variant_cell(TYPE_SIZEF, struct.pack('>2d', width, height))


# --- BigRational --------------------------------------------------------------

def pack_big_integer(value: int) -> bytes:
    """sign word, 64-bit block count, then 32-bit blocks, least significant first."""
    magnitude = abs(int(value))
    blocks = []
    while magnitude:
        blocks.append(magnitude & 0xFFFFFFFF)
        magnitude >>= 32
    sign = 0 if value == 0 else (1 if value > 0 else NULL_LENGTH)
    return struct.pack('>IQ', sign, len(blocks)) + b''.join(
        struct.pack('>I', block) for block in blocks)


def read_big_integer(cursor: Cursor) -> int:
    sign, count = cursor.read('IQ')
    if sign not in (0, 1, NULL_LENGTH) or count > cursor.remaining // 4:
        raise FormatError('Implausible BigInteger sign or block count')
    value = 0
    for shift in range(count):
        value |= cursor.read('I') << (32 * shift)
    return -value if sign == NULL_LENGTH else value


def pack_big_rational(value) -> bytes:
    order = Fraction(value)
    if order.denominator <= 0:  # Fraction normalizes, so this only guards misuse.
        raise ValueError('A BigRational needs a positive denominator')
    return pack_big_integer(order.numerator) + pack_big_integer(order.denominator)


def big_rational_cell(value) -> str:
    return variant_cell(TYPE_CUSTOM, pack_big_rational(value), 'BigRational')


def read_big_rational(cursor: Cursor) -> Fraction:
    numerator = read_big_integer(cursor)
    denominator = read_big_integer(cursor)
    if denominator == 0:
        raise FormatError('BigRational with a zero denominator')
    return Fraction(numerator, denominator)


# --- QPainterPath -------------------------------------------------------------

@dataclass
class Path:
    """A QPainterPath: (kind, x, y) elements plus its subpath/fill bookkeeping."""

    elements: list[tuple[int, float, float]] = field(default_factory=list)
    subpath_start: int = 0
    fill_rule: int = 0

    @classmethod
    def rectangle(cls, x0: float, y0: float, x1: float, y1: float) -> Path:
        return cls([(MOVE_TO, x0, y0), (LINE_TO, x1, y0), (LINE_TO, x1, y1),
                    (LINE_TO, x0, y1), (LINE_TO, x0, y0)])

    @classmethod
    def centered_rectangle(cls, width: float, height: float) -> Path:
        return cls.rectangle(-width / 2, -height / 2, width / 2, height / 2)

    @classmethod
    def line(cls, x0: float, y0: float, x1: float, y1: float) -> Path:
        """A single segment, which is what a straight stroke is."""
        return cls([(MOVE_TO, x0, y0), (LINE_TO, x1, y1)])

    @classmethod
    def polyline(cls, points) -> Path:
        """An open path through `points`, the shape a freehand stroke has."""
        points = [(float(x), float(y)) for x, y in points]
        if not points:
            return cls()
        head, *rest = points
        return cls([(MOVE_TO, *head)] + [(LINE_TO, x, y) for x, y in rest])

    @classmethod
    def polygon(cls, points) -> Path:
        """A closed path through `points`, the shape a crop outline has."""
        points = [(float(x), float(y)) for x, y in points]
        if points and points[0] != points[-1]:
            points.append(points[0])
        return cls.polyline(points)

    @property
    def points(self) -> list[tuple[float, float]]:
        return [(x, y) for _, x, y in self.elements]

    def bounding_box(self) -> tuple[float, float, float, float]:
        if not self.elements:
            return (0.0, 0.0, 0.0, 0.0)
        xs = [x for _, x, _ in self.elements]
        ys = [y for _, _, y in self.elements]
        return (min(xs), min(ys), max(xs), max(ys))

    def pack(self) -> bytes:
        payload = struct.pack('>I', len(self.elements))
        for kind, x, y in self.elements:
            payload += struct.pack('>idd', kind, x, y)
        if self.elements:
            payload += struct.pack('>ii', self.subpath_start, self.fill_rule)
        return payload

    def cell(self) -> str:
        return variant_cell(TYPE_CUSTOM, self.pack(), 'QPainterPath')

    @classmethod
    def read(cls, cursor: Cursor) -> Path:
        count = cursor.read('I')
        if count > cursor.remaining // 20:
            raise FormatError('Implausible QPainterPath element count')
        elements = [tuple(cursor.read('idd')) for _ in range(count)]
        subpath_start, fill_rule = cursor.read('ii') if count else (0, 0)
        return cls(elements, subpath_start, fill_rule)
