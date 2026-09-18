"""What a file carried that the model does not name.

One carrier per generation, and an item comes from one or the other: `Item.v1`
and `Scene.v1` for a 1.x file, `Item.v2` and `Scene.v2` for a 2.x one. They exist
so that reading a file and writing it again reproduces it -- the pre-crop
transform 1.x keeps for "reset cropping", the exact 16-bit note colours, the 2.x
row ids, the envelope, a cell whose type this package did not understand, and any
column a later PureRef adds.

Nothing here is needed to build a scene from scratch; a writer fills in sane
values for all of it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .geometry import Transform

if TYPE_CHECKING:          # the envelope is a 2.x thing; the model only holds it
    from .v2.envelope import Envelope

@dataclass
class V1Image:
    """1.x fields an image item carries that the model has no home for.

    They exist so a file written by PureRef 1.x comes back byte for byte: the
    pre-crop transform it keeps for "reset cropping", the two perspective terms
    it stores and then ignores, and the trailing block it hands back unchanged.
    """

    source: str | None = None
    brute_force: bool = False
    before_crop: Transform = field(default_factory=lambda: Transform())
    before_crop_perspective: tuple[float, float] = (0.0, 0.0)
    crop_offset: tuple[float, float] | None = None
    crop_scale: float = 1.0
    perspective: tuple[float, float] = (0.0, 0.0)
    tail: bytes = b''
    trailing: bytes = b''
    address: tuple[int, int] | None = None
    id: int | None = None


@dataclass
class V1Note:
    """A 1.x note's exact 16-bit colours, so writing reproduces them."""

    foreground: tuple[int, list[int]] | None = None
    foreground_hsv: bool = False
    background: tuple[int, list[int]] | None = None
    background_hsv: bool = False
    colour_gap: bytes = b'\0\0'
    tail: bytes = b'\0\0'
    perspective: tuple[float, float] = (0.0, 0.0)
    trailing: bytes = b''
    id: int | None = None


@dataclass
class V1File:
    """What a 1.x header held beyond the model's canvas and view."""

    header: bytes = b''
    application_version: str | None = None
    checksum: str | None = None
    checksum_valid: bool | None = None
    folder: str | None = None


@dataclass
class V2Item:
    """What a 2.x row carried beyond the columns the model names.

    `id` is the row's primary key, kept so a load/save cycle does not renumber a
    file. `unparsed` holds cells whose serialized type this package did not
    understand, keyed by column; they are written back exactly as they arrived,
    which is what lets a file from a newer PureRef survive the trip. `columns`
    and `subtype_columns` are columns a future schema added, recorded for
    inspection — PureRef itself drops them on its next save.
    """

    id: int | None = None
    unparsed: dict = field(default_factory=dict)
    columns: dict = field(default_factory=dict)
    subtype_columns: dict = field(default_factory=dict)
    # An item with no row in any subtype table: it renders as nothing, and is
    # kept only so that saving does not silently delete it.
    orphan: bool = False
    # A note's style id as stored, when it is not one this package names.
    note_style: int | None = None


@dataclass
class V2File:
    """The parts of a 2.x file outside the item tables."""

    envelope: Envelope | None = None
    metadata: dict = field(default_factory=dict)
    unknown_tables: list = field(default_factory=list)
    user_version: int | None = None
    integrity: list[str] = field(default_factory=list)
