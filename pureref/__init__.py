"""Read, write and convert PureRef `.pur` files.

    import pureref

    scene = pureref.read('board.pur')          # 1.10, 2.0 or 2.1, detected
    scene.add_image('new.png', x=200, y=0)
    pureref.write(scene, 'board-2.1.pur')      # newest format by default

Both generations load into the same `Scene` model, so converting is reading one
and writing the other. `pureref.write` returns what the target format cannot
express, and refuses to overwrite an existing file unless asked.
"""
from __future__ import annotations

from pathlib import Path

from .model import (LATEST, LOCK_CLOSED, LOCK_OPEN, NOTE_COMFORTABLE, NOTE_COMPACT,
                    STROKE_DASHED, STROKE_FLAT, STROKE_ROUND,
                    PLAYBACK_PAUSED, PLAYBACK_PLAYING, PLAYBACK_STATIC, PLAYBACK_STOPPED,
                    RENDER_GRAYSCALE, RENDER_SMOOTH, VERSION_1, VERSION_2_0, VERSION_2_1,
                    VERSIONS, DrawItem, GroupItem, ImageItem, Item, NoteItem, Playback,
                    Resource, Scene, Stroke, Transform, View)
from .problems import Loss, Problem, Unparsed
from .qt import FormatError, Path as CropPath
from . import layout, report, transcode, v1, v2

__all__ = [
    'read', 'read_bytes', 'write', 'write_bytes', 'convert', 'detect', 'summary',
    'layout', 'report', 'transcode', 'v1', 'v2',
    'Scene', 'Item', 'ImageItem', 'NoteItem', 'GroupItem', 'DrawItem', 'Resource',
    'Stroke', 'Transform', 'View', 'Playback', 'CropPath', 'FormatError',
    'Loss', 'Problem', 'Unparsed',
    'VERSIONS', 'VERSION_1', 'VERSION_2_0', 'VERSION_2_1', 'LATEST',
    'RENDER_SMOOTH', 'RENDER_GRAYSCALE', 'PLAYBACK_STATIC', 'PLAYBACK_STOPPED',
    'PLAYBACK_PAUSED', 'PLAYBACK_PLAYING', 'LOCK_OPEN', 'LOCK_CLOSED',
    'NOTE_COMFORTABLE', 'NOTE_COMPACT',
    'STROKE_ROUND', 'STROKE_DASHED', 'STROKE_FLAT',
]

__version__ = '2.0.0'

_V1_MAGIC = b'\x00\x00\x00\x08' + '1.10'.encode('utf-16-be')


def detect(data: bytes) -> str:
    """Return the format version of a `.pur`: '1.10', '2.0' or '2.1'."""
    blob = bytes(data[:64])
    if blob.startswith(_V1_MAGIC):
        return VERSION_1
    from .qt import Cursor
    try:
        version = Cursor(blob).read_string()
    except FormatError as error:
        raise FormatError('Not a PureRef file') from error
    if version in v2.envelope.LAYOUTS:
        return version
    raise FormatError(f'Unrecognized PureRef format version {version!r}')


def read_bytes(data: bytes) -> Scene:
    """Parse a `.pur` from memory, whichever generation it is."""
    version = detect(data)
    return v1.read(data) if version == VERSION_1 else v2.read(data)


def read(path) -> Scene:
    return read_bytes(Path(path).read_bytes())


def write_bytes(scene: Scene, *, version: str = LATEST, **options) -> bytes:
    """Serialize `scene`. Extra options go to the backend for that version."""
    if version == VERSION_1:
        return v1.write(scene, **options)
    if version in (VERSION_2_0, VERSION_2_1):
        return v2.write(scene, format_version=version, **options)
    raise ValueError(f'Unknown version {version!r}; expected one of {VERSIONS}')


def write(scene: Scene, path, *, version: str = LATEST, overwrite: bool = False,
          **options) -> list[str]:
    """Write `scene` to `path` and return what the format could not keep.

    Existing files are left alone unless `overwrite=True`, because a `.pur` is
    usually somebody's canvas.
    """
    losses = scene.losses(version)
    data = write_bytes(scene, version=version, **options)
    Path(path).write_bytes(data) if overwrite else _write_new(Path(path), data)
    return losses


def convert(source, target, *, version: str = LATEST, overwrite: bool = False,
            **options) -> list[str]:
    """Read any `.pur` and write it as `version`, returning what was lost."""
    return write(read(source), target, version=version, overwrite=overwrite, **options)


def summary(scene: Scene) -> dict:
    """A readable overview of a scene, used by `pureref info`."""
    from .report import summary as _summary
    return _summary(scene)


def _write_new(path: Path, data: bytes) -> None:
    with path.open('xb') as stream:
        stream.write(data)
