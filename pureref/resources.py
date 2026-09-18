"""An image a scene refers to, embedded or linked.

Both formats let several items share one resource, and both deduplicate: 1.x by
address through its reference table, 2.x by checksum or by path. `identity()` is
that key, so a writer can group instances the way the application does.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path as FilePath

from . import imagesize

@dataclass
class Resource:
    """An image, either embedded or linked to a path on disk."""

    width: int
    height: int
    data: bytes | None = None
    format: str = 'PNG'
    source: str = ''
    origin: str | None = None
    checksum: str | None = None

    def __post_init__(self):
        if self.width <= 0 or self.height <= 0:
            raise ValueError('Image dimensions must be positive')
        if self.data is not None and self.checksum is None:
            self.checksum = hashlib.md5(self.data).hexdigest()
        if self.data is None and not self.source:
            raise ValueError('A linked resource needs a source path')

    @classmethod
    def from_file(cls, path, *, link: bool = False) -> Resource:
        path = FilePath(path)
        data = path.read_bytes()
        fmt, width, height = imagesize.identify(data)
        source = str(path.resolve()).replace('\\', '/')
        return cls(width, height, None if link else data, fmt, source)

    @classmethod
    def from_bytes(cls, data: bytes, *, width: int | None = None,
                   height: int | None = None, format: str | None = None,
                   source: str = '') -> Resource:
        if width is None or height is None or format is None:
            detected, detected_width, detected_height = imagesize.identify(data)
            format = format or detected
            width = width or detected_width
            height = height or detected_height
        return cls(width, height, data, format, source)

    @property
    def linked(self) -> bool:
        return self.data is None

    @property
    def size(self) -> tuple[int, int]:
        return (self.width, self.height)

    def identity(self):
        """Deduplication key: embedded images by checksum, linked ones by path."""
        return ('linked', self.source) if self.linked else ('embedded', self.checksum)
