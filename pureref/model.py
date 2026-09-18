"""The version-neutral scene model, gathered in one place.

Readers for every `.pur` generation produce a `Scene`; writers consume one. The
model is shaped like the richer 2.x format, because 1.x maps into it without
loss: a 1.x image instance is an `ImageItem`, a 1.x text item is a `NoteItem`,
and 1.x has no groups or drawings.

It is written across a few modules, each with one job, and re-exported here so
that `from pureref.model import ...` reaches all of it:

    constants.py   the numbers both formats store, and what they mean
    geometry.py    `Transform`, the affine transform both formats keep
    resources.py   `Resource`, an image a scene refers to
    items.py       `Item` and the four kinds of item
    scene.py       `Scene` and `View`, plus what a format cannot express
    carriers.py    what a file held that the model does not name

Fields a given generation cannot express are reported by `Scene.losses(version)`
rather than dropped silently, and whatever a reader did not interpret is kept on
`Item.v1`/`Item.v2` and `Scene.v1`/`Scene.v2`, one typed carrier per generation,
so that load/save round-trips stay faithful.
"""
from __future__ import annotations

from .carriers import V1File, V1Image, V1Note, V2File, V2Item
from .constants import (LATEST, LOCK_CLOSED, LOCK_OPEN, NOTE_COMFORTABLE, NOTE_COMPACT,
                        NOTE_STYLE_NAMES, NOTE_STYLES, PLAYBACK_PAUSED, PLAYBACK_PLAYING,
                        PLAYBACK_STATIC, PLAYBACK_STOPPED, RENDER_GRAYSCALE,
                        RENDER_SMOOTH, STROKE_DASHED, STROKE_FLAT, STROKE_ROUND,
                        VERSION_1, VERSION_2_0, VERSION_2_1, VERSIONS)
from .geometry import Transform, multiply
from .items import DrawItem, GroupItem, ImageItem, Item, NoteItem, Playback, Stroke
from .resources import Resource
from .scene import Scene, View

__all__ = [
    # the model
    'Scene', 'View', 'Item', 'ImageItem', 'NoteItem', 'GroupItem', 'DrawItem',
    'Resource', 'Transform', 'Stroke', 'Playback', 'multiply',
    # what a file carried beyond it
    'V1Image', 'V1Note', 'V1File', 'V2Item', 'V2File',
    # the constants
    'VERSIONS', 'VERSION_1', 'VERSION_2_0', 'VERSION_2_1', 'LATEST',
    'RENDER_SMOOTH', 'RENDER_GRAYSCALE',
    'PLAYBACK_STATIC', 'PLAYBACK_STOPPED', 'PLAYBACK_PAUSED', 'PLAYBACK_PLAYING',
    'LOCK_OPEN', 'LOCK_CLOSED',
    'STROKE_ROUND', 'STROKE_DASHED', 'STROKE_FLAT',
    'NOTE_COMFORTABLE', 'NOTE_COMPACT', 'NOTE_STYLES', 'NOTE_STYLE_NAMES',
]
