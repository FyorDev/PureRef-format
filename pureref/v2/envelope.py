"""The PureRef 2.x container: a SQLite database with a displaced prefix.

A `.pur` is an ordinary SQLite database whose first `H` bytes were replaced by a
PureRef header and appended to the end instead:

    offset 0   header                H bytes
    offset H   database[H:N]         N - H bytes
    offset N   database[0:H]         H bytes

So the database is `file[N:] + file[H:N]`; carving from the `SQLite format 3`
signature to the end of the file only recovers the displaced prefix.

Two header layouts exist. Both start with a format-version QString, a reserved
word, the database length N, an application-version QString and an MD5 checksum
QString. The `2.1` layout then stores a thumbnail QByteArray, and `2.0` ends at
the checksum. The checksum covers everything after the checksum field, so it
includes the thumbnail and both database halves, but not the reconstructed
database as such.
"""
from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass, field

from ..qt import Cursor, FormatError, pack_bytes, pack_string

SQLITE_MAGIC = b'SQLite format 3\0'
VERSION_2_0 = '2.0'
VERSION_2_1 = '2.1'
# 2.1 and 2.2 share a layout; 2.2 is accepted by 2.0.3 but has not been seen.
LAYOUTS = {VERSION_2_0: 'no thumbnail', VERSION_2_1: 'thumbnail'}
CHECKSUM_DIGITS = 32


@dataclass
class Envelope:
    """Everything in the file that is not the database."""

    format_version: str = VERSION_2_1
    application_version: str = '2.1.3'
    thumbnail: bytes = b''
    reserved: int = 0
    checksum: str | None = None
    checksum_valid: bool | None = None
    database_size: int | None = None
    header_size: int | None = None
    extras: dict = field(default_factory=dict)

    @property
    def has_thumbnail_field(self) -> bool:
        return self.format_version != VERSION_2_0


def unwrap(data: bytes) -> tuple[Envelope, bytes]:
    """Split a `.pur` into its envelope and the reconstructed database bytes."""
    blob = bytes(data)
    cursor = Cursor(blob)
    version = cursor.read_string()
    if version not in LAYOUTS:
        raise FormatError(f'Unsupported .pur format version {version!r}; '
                          f'known layouts: {sorted(LAYOUTS)}')
    reserved = cursor.read('I')
    database_size = cursor.read('Q')
    application_version = cursor.read_string()
    checksum = cursor.read_string()
    checksum_start = cursor.pos
    thumbnail = b''
    if version != VERSION_2_0:
        thumbnail = cursor.read_bytes() or b''
    header_size = cursor.pos
    if database_size < header_size or database_size + header_size != len(blob):
        raise FormatError('Header length and database size do not add up; '
                          'the file is truncated or not a .pur')
    database = blob[database_size:] + blob[header_size:database_size]
    _check_database(database)
    envelope = Envelope(
        format_version=version, application_version=application_version or '',
        thumbnail=thumbnail, reserved=reserved, checksum=checksum,
        checksum_valid=hashlib.md5(blob[checksum_start:]).hexdigest() == checksum,
        database_size=database_size, header_size=header_size)
    return envelope, database


def wrap(database: bytes, envelope: Envelope | None = None) -> bytes:
    """Put a database back into a `.pur`, computing a fresh checksum."""
    envelope = envelope or Envelope()
    if envelope.format_version not in LAYOUTS:
        raise ValueError(f'Unsupported format version {envelope.format_version!r}')
    _check_database(database)
    thumbnail = bytes(envelope.thumbnail or b'')
    if thumbnail and not envelope.has_thumbnail_field:
        raise ValueError('The 2.0 header has no thumbnail field; '
                         'write 2.1 or drop the thumbnail')
    preview = pack_bytes(thumbnail) if envelope.has_thumbnail_field else b''
    prefix = (pack_string(envelope.format_version)
              + struct.pack('>IQ', envelope.reserved, len(database))
              + pack_string(envelope.application_version))
    header_size = len(prefix) + len(pack_string('0' * CHECKSUM_DIGITS)) + len(preview)
    if header_size > len(database):
        raise FormatError('Header is larger than the database it displaces')
    tail = preview + database[header_size:] + database[:header_size]
    checksum = envelope.checksum if envelope.extras.get('keep_checksum') else None
    return prefix + pack_string(checksum or hashlib.md5(tail).hexdigest()) + tail


def _check_database(database: bytes) -> None:
    if not database.startswith(SQLITE_MAGIC):
        raise FormatError('Reconstructed data is not a SQLite database')
    page_size = struct.unpack('>H', database[16:18])[0]
    page_size = 65536 if page_size == 1 else page_size
    if page_size < 512 or page_size & (page_size - 1) or len(database) % page_size:
        raise FormatError('Implausible SQLite page size or database length')
