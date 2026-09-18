"""The things a scene holds: images, notes, groups and drawings.

`Item` is what they share -- a transform relative to the parent, stacking, an
opacity, children -- and the four subclasses add what their kind stores. There
are exactly four, because the application defines exactly four: the typeinfo in
the binary lists GraphicsImageItem, GraphicsTextItem, GraphicsGroupItem and
GraphicsDrawItem and nothing else.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from fractions import Fraction

from .carriers import V1Image, V1Note, V2Item
from .constants import (NOTE_COMFORTABLE, NOTE_STYLES, PLAYBACK_STATIC,
                        RENDER_GRAYSCALE, RENDER_SMOOTH, STROKE_DASHED, STROKE_ROUND,
                        LOCK_CLOSED)
from .geometry import Transform
from .qt import Path
from .resources import Resource

@dataclass
class Playback:
    state: int = PLAYBACK_STATIC
    frame: int = 0
    speed: float = 1.0


@dataclass
class Stroke:
    """One freehand or straight stroke of a drawing item.

    `style` is the stroke's appearance: STROKE_ROUND, STROKE_DASHED or
    STROKE_FLAT. `point` is a transient point the application uses while a stroke
    is being drawn; it is (0, 0) in every saved file and has no visible effect.
    """

    path: Path = field(default_factory=Path)
    rgba: tuple[int, int, int, int] = (46, 132, 170, 200)
    width: float = 5.0
    style: int = STROKE_ROUND
    point: tuple[float, float] = (0.0, 0.0)

    def __post_init__(self):
        if any(not 0 <= channel <= 255 for channel in self.rgba):
            raise ValueError('Stroke colors are 8-bit RGBA')
        if self.width <= 0:
            raise ValueError('Stroke width must be positive')

    @classmethod
    def line(cls, start, end, **options) -> Stroke:
        """A straight stroke from `start` to `end`, both (x, y)."""
        return cls(path=Path.line(*start, *end), **options)

    @classmethod
    def freehand(cls, points, **options) -> Stroke:
        """A stroke through `points`, the way the brush tool records one."""
        return cls(path=Path.polyline(points), **options)

    @property
    def dashed(self) -> bool:
        return self.style == STROKE_DASHED

    @dashed.setter
    def dashed(self, value: bool) -> None:
        self.style = STROKE_DASHED if value else STROKE_ROUND


@dataclass
class Item:
    """Anything on the canvas. Transforms are relative to the parent."""

    name: str | None = None
    transform: Transform = field(default_factory=Transform)
    z: float | None = None
    order: Fraction | None = None
    opacity: float = 1.0
    locked: bool = False
    # The note PureRef attaches through its comment dialog: free text, shown in
    # the item's tooltip. 1.x has nowhere to put it.
    comment: str | None = None
    children: list[Item] = field(default_factory=list)
    # What the file carried that the model does not name, one typed carrier per
    # generation: an item comes from one or the other, never both.
    v1: V1Image | V1Note | None = None
    v2: V2Item | None = None

    @property
    def x(self) -> float:
        return self.transform.dx

    @x.setter
    def x(self, value: float) -> None:
        self.transform = replace(self.transform, dx=value)

    @property
    def y(self) -> float:
        return self.transform.dy

    @y.setter
    def y(self, value: float) -> None:
        self.transform = replace(self.transform, dy=value)

    def add(self, child: Item) -> Item:
        self.children.append(child)
        return child

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()

    def kind(self) -> str:
        return type(self).__name__.removesuffix('Item').lower()


@dataclass
class ImageItem(Item):
    """One placement of a resource on the canvas, positioned at its center."""

    # All three are set by the time construction finishes: an image item without
    # a resource is refused, and the other two are derived from it when a caller
    # leaves them out. They are declared as what they always are so that callers
    # do not have to narrow away a None that cannot happen; the defaults exist
    # only because every field after the base class ones needs one.
    resource: Resource = None  # type: ignore[assignment]
    # Image pixels are mapped into item coordinates by this transform; the app
    # centers the image, so the default translates by (-width/2, -height/2).
    pixel_transform: Transform = None  # type: ignore[assignment]
    # The visible boundary in centered-pixel coordinates; a rectangle unless cropped.
    bounds: Path = None  # type: ignore[assignment]
    flags: int = RENDER_SMOOTH
    playback: Playback = field(default_factory=Playback)

    def __post_init__(self):
        if self.resource is None:
            raise ValueError('An image item needs a resource')
        width, height = self.resource.size
        if self.pixel_transform is None:
            self.pixel_transform = Transform.translate(-width / 2, -height / 2)
        if self.bounds is None:
            self.bounds = Path.centered_rectangle(width, height)

    @property
    def smooth(self) -> bool:
        return bool(self.flags & RENDER_SMOOTH)

    @property
    def grayscale(self) -> bool:
        return bool(self.flags & RENDER_GRAYSCALE)

    def crop(self, left: float, top: float, width: float, height: float) -> ImageItem:
        """Crop in source pixel coordinates, measured from the top left."""
        if width <= 0 or height <= 0:
            raise ValueError('Crop dimensions must be positive')
        full_width, full_height = self.resource.size
        x0, y0 = left - full_width / 2, top - full_height / 2
        self.bounds = Path.rectangle(x0, y0, x0 + width, y0 + height)
        return self

    @property
    def size(self) -> tuple[float, float]:
        """On-canvas size of the visible area, ignoring rotation."""
        x0, y0, x1, y1 = self.bounds.bounding_box()
        return (abs((x1 - x0) * self.transform.m11) + abs((y1 - y0) * self.transform.m21),
                abs((x1 - x0) * self.transform.m12) + abs((y1 - y0) * self.transform.m22))

    def scale(self, factor: float) -> ImageItem:
        self.transform = self.transform.scaled(factor)
        return self

    def scale_to_width(self, width: float) -> ImageItem:
        current = self.size[0]
        return self.scale(width / current) if current else self

    def scale_to_height(self, height: float) -> ImageItem:
        current = self.size[1]
        return self.scale(height / current) if current else self


@dataclass
class NoteItem(Item):
    """A note. 2.x stores rich text; 1.x stores plain text plus colors."""

    text: str = ''
    html: str | None = None
    text_color: str | None = None
    background_color: str | None = None
    fixed_size: tuple[float, float] = (-1.0, -1.0)
    style: str = NOTE_COMFORTABLE

    def __post_init__(self):
        if self.style not in NOTE_STYLES:
            raise ValueError(f'Note style must be one of {sorted(NOTE_STYLES)}')


@dataclass
class GroupItem(Item):
    """A 2.x group; its geometry comes from its children."""

    background_color: str | None = None
    lock_mode: int = LOCK_CLOSED


@dataclass
class DrawItem(Item):
    """A 2.x drawing: one or more strokes in the item's coordinates."""

    strokes: list[Stroke] = field(default_factory=list)
