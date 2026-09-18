"""Decode and encode the serialized values PureRef 2.x keeps in SQLite cells.

The cells are declared BLOB but stored with storage class TEXT: the payload's
bytes were mapped to code points U+0000..U+00FF, so Latin-1 recovers them. Each
payload is a QDataStream QVariant record: type id, a null flag, a registered type
name for custom types, then the type's own data.
"""
from __future__ import annotations

import struct
from fractions import Fraction

from ..model import STROKE_ROUND, Stroke, Transform
from ..problems import Unparsed
from ..qt import (TYPE_CUSTOM, TYPE_RECTF, TYPE_SIZEF, TYPE_TRANSFORM, Cursor,
                  FormatError, Path, bytes_to_cell, cell_to_bytes, read_big_rational,
                  read_variant_header, variant_cell)

STROKE_TYPE_NAME = 'QList<GraphicsDrawItem::Stroke>'
# Each stroke starts with a signed-char version. From 100 on, a trailing style
# int follows the stroke's point; a lower value is not a version at all but the
# first byte of the QColor, which is how strokes looked before the version was
# added. PureRef still reads those and rewrites them as version 100.
STROKE_VERSION = 100
STROKE_LEGACY_LIMIT = 99
COLOR_SPEC_RGB = 1


def decode(cell, reader):
    """Read one cell, or keep it verbatim when its type is not understood.

    Returns `(value, complaint)`. A complaint means the value is an `Unparsed`
    carrying the original cell, so a writer can put the bytes back untouched and
    a future PureRef type costs nothing worse than a note on the scene.
    """
    try:
        return reader(cell), None
    except (FormatError, ValueError, struct.error) as error:
        return unparsed(cell), str(error)


def unparsed(cell) -> Unparsed:
    payload = cell_to_bytes(cell)
    type_id, type_name = -1, None
    try:
        type_id, _is_null, type_name = read_variant_header(Cursor(payload))
    except FormatError:
        pass
    text = cell if isinstance(cell, str) else bytes_to_cell(payload)
    return Unparsed(type_id, type_name, payload, text)


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
    if count > cursor.remaining // 43:
        raise FormatError('Implausible stroke count')
    strokes = []
    for _ in range(count):
        version = cursor.read('b')
        if version <= STROKE_LEGACY_LIMIT:
            cursor.pos -= 1          # not a version: the QColor starts here
        spec = cursor.read('b')
        if spec != COLOR_SPEC_RGB:
            raise FormatError(f'Stroke color is not stored as RGB (spec {spec})')
        alpha, red, green, blue, _pad = cursor.read('5H')
        width = cursor.read('d')
        path = Path.read(cursor)
        point = tuple(cursor.read('2d'))
        style = cursor.read('i') if version > STROKE_LEGACY_LIMIT else STROKE_ROUND
        strokes.append(Stroke(path=path, width=width, style=style, point=point,
                              rgba=tuple(channel // 257 for channel in
                                         (red, green, blue, alpha))))
    return strokes


def strokes_cell(strokes) -> str:
    payload = struct.pack('>I', len(strokes))
    for stroke in strokes:
        red, green, blue, alpha = stroke.rgba
        payload += struct.pack('>2b5Hd', STROKE_VERSION, COLOR_SPEC_RGB,
                               alpha * 257, red * 257, green * 257, blue * 257, 0,
                               stroke.width)
        payload += stroke.path.pack()
        payload += struct.pack('>2di', *stroke.point, int(stroke.style))
    return variant_cell(TYPE_CUSTOM, payload, STROKE_TYPE_NAME)
