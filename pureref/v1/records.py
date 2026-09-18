"""The 1.x layouts, declared once.

`reader.py` and `writer.py` both work from these, so a field cannot be read in
one order and written in another, and the tables in `docs/format-v1.md` are
generated from the same declarations (`tools/generate_docs.py`).

Field names starting with an underscore are regions whose meaning is not
settled. They are read, kept and written back rather than treated as padding,
because PureRef hands them back unchanged and a file should not lose them by
passing through this package.
"""
from __future__ import annotations

import struct

from ..geometry import Transform
from ..qt import Cursor, FormatError, Path
from ..records import (F64, I8, I32, U16, U32, U64, Codec, Field, Matrix6,
                       NullableUtf16String, PointF, Raw, Record, Rect, Tuple,
                       Utf16String, ZeroMarker)

COLOUR = Tuple('H', 3, 'three uint16 channels')


def placement(what: str) -> list[Field]:
    """The five fields every item carries: where it is, which id, how high.

    Both item records hold these, in this order, between their own head and
    tail, so they are declared once and spliced into each.
    """
    return [
        Field('linear', Matrix6, default=(1.0, 0.0, 0.0, 0.0, 1.0, 0.0),
              doc='the linear part of the transform; m13 and m23 are rewritten as 0'),
        Field('position', PointF, default=(0.0, 0.0),
              doc=f'the {what} on the canvas'),
        Field('_constant_one', F64, default=1.0,
              doc='rewritten as 1.0 whatever it held'),
        Field('id', U32, default=0, doc='item id'),
        Field('z', F64, default=1.0, doc='stacking'),
    ]


def to_transform(values: dict) -> tuple[Transform, tuple[float, float]]:
    """A record's placement as a `Transform`, plus the two ignored terms.

    PureRef stores a 3x3 linear part but rewrites m13 and m23 as 0, so those two
    are carried on the item rather than folded into the transform.
    """
    m11, m12, m13, m21, m22, m23 = values['linear']
    x, y = values['position']
    return Transform(m11, m12, m21, m22, x, y), (m13, m23)


def from_transform(transform: Transform | None,
                   perspective: tuple[float, float] | None = None) -> dict:
    """The inverse: the placement fields for a transform, ready for `write`."""
    transform = transform or Transform()
    m13, m23 = perspective or (0.0, 0.0)
    return {'linear': (transform.m11, transform.m12, m13,
                       transform.m21, transform.m22, m23),
            'position': (transform.dx, transform.dy)}


class CropOutline(Codec):
    """The crop outline: a count, then a kind and a point per corner.

    Closed, and in centred pixel coordinates — an uncropped 64x32 image spans
    (-32,-16) to (32,16), the same convention 2.x uses for `image_bounds`.
    """

    def read(self, cursor: Cursor) -> Path:
        count = cursor.read('I')
        if count > cursor.remaining // 20:
            raise FormatError(f'implausible crop point count {count}')
        elements = []
        for _ in range(count):
            kind = cursor.read('I')
            x, y = cursor.read('2d')
            elements.append((kind, x, y))
        return Path(elements)

    def write(self, buffer: bytearray, value) -> None:
        elements = value.elements if value is not None else []
        buffer += struct.pack('>I', len(elements))
        for kind, x, y in elements:
            buffer += struct.pack('>Idd', kind, x, y)

    @property
    def description(self) -> str:
        return 'uint32 count, then uint32 kind and two doubles each'


# --- the 224-byte header ------------------------------------------------------

HEADER = Record('header', [
    Field('_version_length', U32, default=8,
          doc='byte length of the version string'),
    Field('_version', Raw(8), default='1.10'.encode('utf-16-be'),
          doc='UTF-16BE "1.10" — the format version, which 1.11.1 still writes'),
    Field('item_count', U16, default=0, doc='image items plus root note items'),
    Field('image_count', U16, default=0, doc='image items'),
    Field('reference_offset', U64, default=0,
          doc='where the reference table starts'),
    Field('_application_length', U32, default=12,
          doc='byte length of the application-version string'),
    Field('application_version', Raw(12), default=b'',
          doc='UTF-16BE "1.10.4" or "1.11.1"; PureRef accepts it zero-filled'),
    Field('_checksum_length', U32, default=64,
          doc='byte length of the checksum string'),
    Field('checksum', Raw(64), default=b'',
          doc='UTF-16BE MD5 hex of everything from offset 108'),
    Field('id_count', U32, default=0, doc='number of item ids'),
    Field('canvas', Rect, default=(0.0, 0.0, 0.0, 0.0), doc='canvas rectangle'),
    Field('zoom', F64, default=1.0, doc='view zoom'),
    Field('_unknown_152', Raw(24), default=b'',
          doc='zero in every observed file; preserved'),
    Field('zoom_y', F64, default=1.0, doc='view zoom again, vertically'),
    Field('_unknown_184', Raw(24), default=b'',
          doc='zero in every observed file; preserved'),
    Field('zoom_multiplier', F64, default=1.0, doc='always 1.0'),
    Field('view_x', I32, default=0, doc='view x'),
    Field('view_y', I32, default=0, doc='view y'),
])

# --- item blocks --------------------------------------------------------------

IMAGE_ITEM = Record('image item', [
    Field('brute_force', ZeroMarker(), default=False,
          doc='four zero bytes, present for an image recovered by brute force'),
    Field('source', NullableUtf16String(), default=None,
          doc='"BruteForceLoaded" for recovered images'),
    Field('name', NullableUtf16String(), default=None,
          when=lambda values: not values.get('brute_force'),
          doc='omitted entirely for brute-force loaded images'),
    Field('opacity', F64, default=1.0,
          doc='1.0 when opaque; PureRef stores it as a float'),
    *placement('image centre'),
    Field('before_crop', Matrix6, default=(1.0, 0.0, 0.0, 0.0, 1.0, 0.0),
          doc='the transform before cropping, for "reset cropping"'),
    Field('crop_offset', PointF, default=(0.0, 0.0), doc='crop offset'),
    Field('crop_scale', F64, default=1.0, doc='crop scale'),
    Field('bounds', CropOutline(), default=None,
          doc='the crop outline, closed, in centred pixel coordinates'),
    Field('_tail', Raw(21),
          doc='PureRef writes 0.0, 1, 0, 2000, 2000; kept, no observed effect'),
    Field('children', U32, default=0, doc='number of note children'),
])

NOTE_ITEM = Record('note item', [
    Field('text', Utf16String(), default='', doc='plain text, not HTML'),
    *placement('note position'),
    Field('foreground_kind', I8, default=1, doc='1 = RGB, 2 = HSV'),
    Field('foreground_opacity', U16, default=0xFFFF, doc='16-bit alpha'),
    Field('foreground_rgb', COLOUR, default=(0xFFFF, 0xFFFF, 0xFFFF),
          doc='red green blue, or hue saturation value when the kind is 2'),
    Field('_colour_gap', Raw(2), doc='zero in every observed file'),
    Field('background_kind', I8, default=1, doc='1 = RGB, 2 = HSV'),
    Field('background_opacity', U16, default=5000, doc='16-bit alpha; PureRef defaults to 5000'),
    Field('background_rgb', COLOUR, default=(0, 0, 0), doc='background channels'),
    Field('_tail', Raw(2),
          doc='zero in every observed file, and it belongs before the count'),
    Field('children', U32, default=0, doc='number of note children'),
])

# --- the reference table ------------------------------------------------------

REFERENCE = Record('reference', [
    Field('id', U32, default=0, doc='image item id'),
    Field('start', U64, default=0, doc='start of its image data or instance slot'),
    Field('end', U64, default=0, doc='end of the same'),
])

RECORDS = {record.name: record
           for record in (HEADER, IMAGE_ITEM, NOTE_ITEM, REFERENCE)}
