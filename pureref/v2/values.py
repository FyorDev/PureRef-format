"""Decode and encode the serialized values PureRef 2.x keeps in SQLite cells.

The cells are declared BLOB but stored with storage class TEXT: the payload's
bytes were mapped to code points U+0000..U+00FF, so Latin-1 recovers them. Each
payload is a QDataStream QVariant record: type id, a null flag, a registered type
name for custom types, then the type's own data.
"""
from __future__ import annotations

import struct
from fractions import Fraction

from ..model import Stroke, Transform
from ..qt import (TYPE_CUSTOM, TYPE_RECTF, TYPE_SIZEF, TYPE_TRANSFORM, Cursor,
                  FormatError, Path, cell_to_bytes, read_big_rational, read_variant_header,
                  variant_cell)

STROKE_TYPE_NAME = 'QList<GraphicsDrawItem::Stroke>'
STROKE_TAG = 100          # per-stroke serialization marker
COLOR_SPEC_RGB = 1
STROKE_OPTIONS = 20       # trailing bytes, options[19] is the dash flag
DASH_BYTE = 19


def _open(cell, expected_id: int | None = None, expected_name: str | None = None):
    payload = cell_to_bytes(cell)
    if not payload:
        raise FormatError('Empty serialized value')
    cursor = Cursor(payload)
    type_id, is_null, name = read_variant_header(cursor)
    if expected_id is not None and type_id != expected_id:
        raise FormatError(f'Expected QVariant type {expected_id}, found {type_id}')
    if expected_name is not None and name != expected_name:
        raise FormatError(f'Expected {expected_name!r}, found {name!r}')
    if is_null:
        raise FormatError('Serialized value is marked null')
    return cursor


def read_transform(cell) -> Transform:
    return Transform.from_matrix9(_open(cell, TYPE_TRANSFORM).read('9d'))


def read_rect(cell) -> tuple[float, float, float, float]:
    return tuple(_open(cell, TYPE_RECTF).read('4d'))


def read_size(cell) -> tuple[float, float]:
    return tuple(_open(cell, TYPE_SIZEF).read('2d'))


def read_order(cell) -> Fraction:
    return read_big_rational(_open(cell, TYPE_CUSTOM, 'BigRational'))


def read_bounds(cell) -> Path:
    return Path.read(_open(cell, TYPE_CUSTOM, 'QPainterPath'))


def read_strokes(cell) -> list[Stroke]:
    cursor = _open(cell, TYPE_CUSTOM, STROKE_TYPE_NAME)
    count = cursor.read('I')
    if count > cursor.remaining // 44:
        raise FormatError('Implausible stroke count')
    strokes = []
    for _ in range(count):
        tag, spec = cursor.read('2B')
        if tag != STROKE_TAG or spec != COLOR_SPEC_RGB:
            raise FormatError(f'Unsupported stroke marker {tag} or color spec {spec}')
        alpha, red, green, blue, _pad = cursor.read('5H')
        width = cursor.read('d')
        path = Path.read(cursor)
        options = cursor.take(STROKE_OPTIONS)
        strokes.append(Stroke(path=path, width=width, options=options,
                              dashed=bool(options[DASH_BYTE]),
                              rgba=tuple(channel // 257 for channel in
                                         (red, green, blue, alpha))))
    return strokes


def strokes_cell(strokes) -> str:
    payload = struct.pack('>I', len(strokes))
    for stroke in strokes:
        red, green, blue, alpha = stroke.rgba
        payload += struct.pack('>2B5Hd', STROKE_TAG, COLOR_SPEC_RGB,
                               alpha * 257, red * 257, green * 257, blue * 257, 0,
                               stroke.width)
        payload += stroke.path.pack()
        options = bytearray(stroke.options)
        options[DASH_BYTE] = 1 if stroke.dashed else 0
        payload += bytes(options)
    return variant_cell(TYPE_CUSTOM, payload, STROKE_TYPE_NAME)
