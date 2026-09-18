"""Shared constants and small helpers for the 1.10 / 1.11.1 binary format.

The layouts themselves live in `records.py`, which is the only description of
them in the package; what is left here is what surrounds them -- the header size
and checksum span, the PNG markers the image section is scanned with, the class
name lengths items are recognized by, and the 16-bit colour conversions notes
need.

The header turns out to be the same idea as the 2.x envelope: a version QString,
some counts, the offset where the reference table starts, an application-version
QString and an MD5 checksum QString. PureRef 1.11.1 still writes `1.10` there, so
the string is a format version rather than an application version.
"""
from __future__ import annotations

import hashlib
import struct

HEADER_SIZE = 224
VERSION_STRING = '1.10'
CHECKSUM_SLICE = slice(44, 108)
CHECKSUM_COVERS = 108

PNG_HEAD = bytes([137, 80, 78, 71, 13, 10, 26, 10])
PNG_FOOT = bytes([0, 0, 0, 0, 73, 69, 78, 68, 174, 66, 96, 130])

# uint32 byte length of each item class name, which is how items are recognized.
IMAGE_ITEM_MARKER = 34   # len("GraphicsImageItem") * 2
TEXT_ITEM_MARKER = 32    # len("GraphicsTextItem") * 2
ITEM_MARKERS = (IMAGE_ITEM_MARKER, TEXT_ITEM_MARKER)
IMAGE_ITEM_NAME = 'GraphicsImageItem'
TEXT_ITEM_NAME = 'GraphicsTextItem'

BRUTE_FORCE_SOURCE = 'BruteForceLoaded'
LINK_SLOT = b'\xff\xff\xff\xff'
REFERENCE_SIZE = 20

# Bytes each item keeps after the fields this implementation understands. They are
# constant in everything observed, and are carried through unchanged when present.
IMAGE_TAIL_SIZE = 25
TEXT_TAIL_SIZE = 6
IMAGE_TAIL_DEFAULT = (struct.pack('>d', 0.0) + struct.pack('>I', 1)
                      + struct.pack('>b', 0) + struct.pack('>q', -1))
TEXT_TAIL_DEFAULT = struct.pack('>H', 0)


def checksum(data: bytes) -> str:
    return hashlib.md5(bytes(data[CHECKSUM_COVERS:])).hexdigest()


def sixteen_bit(channel: int) -> int:
    """8-bit channel to the 16-bit value PureRef 1.x stores."""
    return min(0xFFFF, max(0, channel) * 257)


def eight_bit(channel: int) -> int:
    return min(255, max(0, channel) // 257)


def color_to_argb(opacity: int, rgb) -> str:
    red, green, blue = (eight_bit(value) for value in rgb)
    return f'#{eight_bit(opacity):02x}{red:02x}{green:02x}{blue:02x}'


def argb_to_color(argb: str | None) -> tuple[int, list[int]]:
    """'#AARRGGBB' or '#RRGGBB' to the (opacity, rgb) pair 1.x stores."""
    if not argb:
        return 0xFFFF, [0xFFFF, 0xFFFF, 0xFFFF]
    text = argb.lstrip('#')
    if len(text) == 6:
        text = 'ff' + text
    if len(text) != 8:
        raise ValueError(f'Expected #AARRGGBB or #RRGGBB, got {argb!r}')
    values = [int(text[index:index + 2], 16) for index in range(0, 8, 2)]
    return sixteen_bit(values[0]), [sixteen_bit(value) for value in values[1:]]


def read_colour(kind: int, opacity: int, channels) -> dict:
    """One stored colour: `{'hsv': …, 'colour': (opacity, rgb)}`.

    Kind 2 means the channels are HSV, which is normalized to RGB here; the flag
    is kept so a file that stored HSV can be written back the way it came.
    """
    values = list(channels)
    if kind == 2:
        values = hsv_to_rgb16(values)
    return {'hsv': kind == 2, 'colour': (opacity, values)}


def hsv_to_rgb16(values) -> list[int]:
    """PureRef stores a color as either RGB or HSV; normalize HSV to RGB."""
    import colorsys
    hue, saturation, value = values
    channels = colorsys.hsv_to_rgb(hue / 35900, saturation / 0xFFFF, value / 0xFFFF)
    return [int(channel * 0xFFFF) for channel in channels]
