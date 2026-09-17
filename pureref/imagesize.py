"""Read image format and pixel size from encoded bytes, without Pillow.

PureRef stores the encoded file, its declared format and its pixel size, so a
writer needs the size before it can place an image. Keeping this in the standard
library means the core package has no dependencies.
"""
from __future__ import annotations

import struct

PNG_MAGIC = b'\x89PNG\r\n\x1a\n'
JPEG_SOF = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}


class UnknownImage(ValueError):
    """Raised when the header is not one of the recognized formats."""


def identify(data: bytes) -> tuple[str, int, int]:
    """Return (format, width, height); format matches PureRef's `images.format`."""
    for probe in (_png, _gif, _bmp, _webp, _tiff, _jpeg):
        result = probe(data)
        if result is not None:
            return result
    raise UnknownImage('Unrecognized image header; pass the size explicitly')


def _png(data):
    if not data.startswith(PNG_MAGIC) or len(data) < 24:
        return None
    if data[12:16] != b'IHDR':
        raise UnknownImage('PNG without a leading IHDR chunk')
    width, height = struct.unpack('>II', data[16:24])
    return 'PNG', width, height


def _gif(data):
    if data[:6] not in (b'GIF87a', b'GIF89a') or len(data) < 10:
        return None
    width, height = struct.unpack('<HH', data[6:10])
    return 'GIF', width, height


def _bmp(data):
    if not data.startswith(b'BM') or len(data) < 26:
        return None
    width, height = struct.unpack('<ii', data[18:26])
    return 'BMP', abs(width), abs(height)


def _webp(data):
    if data[:4] != b'RIFF' or data[8:12] != b'WEBP':
        return None
    chunk = data[12:16]
    if chunk == b'VP8X' and len(data) >= 30:
        width = int.from_bytes(data[24:27], 'little') + 1
        height = int.from_bytes(data[27:30], 'little') + 1
        return 'WEBP', width, height
    if chunk == b'VP8 ' and len(data) >= 30 and data[23:26] == b'\x9d\x01\x2a':
        width, height = struct.unpack('<HH', data[26:30])
        return 'WEBP', width & 0x3FFF, height & 0x3FFF
    if chunk == b'VP8L' and len(data) >= 25:
        bits = int.from_bytes(data[21:25], 'little')
        return 'WEBP', (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    raise UnknownImage('Unsupported WebP variant; pass the size explicitly')


def _tiff(data):
    if data[:4] not in (b'II*\0', b'MM\0*'):
        return None
    order = '<' if data[:2] == b'II' else '>'
    offset = struct.unpack(order + 'I', data[4:8])[0]
    if offset + 2 > len(data):
        raise UnknownImage('Truncated TIFF directory')
    found = {}
    for index in range(struct.unpack(order + 'H', data[offset:offset + 2])[0]):
        entry = offset + 2 + 12 * index
        if entry + 12 > len(data):
            break
        tag, kind = struct.unpack(order + 'HH', data[entry:entry + 4])
        if tag in (256, 257):
            fmt = order + ('H' if kind == 3 else 'I')
            size = struct.calcsize(fmt)
            found[tag] = struct.unpack(fmt, data[entry + 8:entry + 8 + size])[0]
    if 256 not in found or 257 not in found:
        raise UnknownImage('TIFF without width/height tags; pass the size explicitly')
    return 'TIFF', found[256], found[257]


def _jpeg(data):
    if not data.startswith(b'\xff\xd8'):
        return None
    pos = 2
    while pos < len(data):
        if data[pos] != 0xFF:
            raise UnknownImage('Malformed JPEG marker')
        while pos < len(data) and data[pos] == 0xFF:
            pos += 1
        if pos >= len(data):
            break
        marker, pos = data[pos], pos + 1
        if marker in (0xDA, 0xD9):  # start of scan / end of image
            break
        if marker == 0x01 or 0xD0 <= marker <= 0xD8:  # standalone markers
            continue
        if pos + 2 > len(data):
            break
        length = int.from_bytes(data[pos:pos + 2], 'big')
        if length < 2 or pos + length > len(data):
            break
        if marker in JPEG_SOF and length >= 8:
            height, width = struct.unpack('>HH', data[pos + 3:pos + 7])
            return 'JPG', width, height
        pos += length
    raise UnknownImage('JPEG without a size header')
