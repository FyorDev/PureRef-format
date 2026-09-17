"""The version-neutral scene model.

Readers for every .pur generation produce a `Scene`; writers consume one. The
model is shaped like the richer 2.x format, because 1.x maps into it without
loss: a 1.x image instance is an `ImageItem`, a 1.x text item is a `NoteItem`,
and 1.x has no groups or drawings.

Fields a given generation cannot express are reported by `Scene.losses(version)`
rather than dropped silently, and bytes a reader did not interpret are kept in
`extras` so that load/save round-trips stay faithful.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace
from fractions import Fraction
from math import cos, radians, sin
from pathlib import Path as FilePath

from . import imagesize
from .qt import Path

# Version tags accepted by the writers; `latest` resolves to the newest one.
VERSION_1 = '1.10'
VERSION_2_0 = '2.0'
VERSION_2_1 = '2.1'
VERSIONS = (VERSION_1, VERSION_2_0, VERSION_2_1)
LATEST = VERSION_2_1

# items_images.flags, GraphicsImageItem::RenderFlag.
RENDER_SMOOTH = 0x1
RENDER_GRAYSCALE = 0x2

# items_images.playback_state.
PLAYBACK_STATIC = 0
PLAYBACK_STOPPED = 1
PLAYBACK_PAUSED = 2
PLAYBACK_PLAYING = 3

# items_groups.lock_mode.
LOCK_OPEN = 0
LOCK_CLOSED = 1

# Stroke.style, the trailing int of a serialized stroke.
STROKE_ROUND = 0      # solid, rounded ends: what PureRef writes
STROKE_DASHED = 1
STROKE_FLAT = 2       # solid, square ends, which widens the item's bounds

NOTE_COMFORTABLE = 'comfortable'
NOTE_COMPACT = 'compact'
NOTE_STYLES = {NOTE_COMFORTABLE: 0, NOTE_COMPACT: 1}


@dataclass
class Transform:
    """A 2D affine transform, stored the way both formats store it."""

    m11: float = 1.0
    m12: float = 0.0
    m21: float = 0.0
    m22: float = 1.0
    dx: float = 0.0
    dy: float = 0.0

    @classmethod
    def translate(cls, dx: float, dy: float) -> 'Transform':
        return cls(dx=dx, dy=dy)

    @classmethod
    def scale(cls, x: float, y: float | None = None) -> 'Transform':
        return cls(m11=x, m22=x if y is None else y)

    @classmethod
    def rotate(cls, degrees: float) -> 'Transform':
        angle = radians(degrees)
        return cls(m11=cos(angle), m12=sin(angle), m21=-sin(angle), m22=cos(angle))

    @classmethod
    def compose(cls, *, x: float = 0.0, y: float = 0.0, scale_x: float = 1.0,
                scale_y: float = 1.0, rotation: float = 0.0) -> 'Transform':
        """Rotate, then scale, then translate: the order the app's gizmo uses."""
        angle = radians(rotation)
        cosine, sine = cos(angle), sin(angle)
        return cls(m11=scale_x * cosine, m12=scale_x * sine,
                   m21=-scale_y * sine, m22=scale_y * cosine, dx=x, dy=y)

    @classmethod
    def from_matrix9(cls, values) -> 'Transform':
        m11, m12, _, m21, m22, _, dx, dy, _ = values
        return cls(m11, m12, m21, m22, dx, dy)

    def to_matrix9(self) -> list[float]:
        return [self.m11, self.m12, 0.0, self.m21, self.m22, 0.0, self.dx, self.dy, 1.0]

    @property
    def is_identity(self) -> bool:
        return self.to_matrix9() == Transform().to_matrix9()

    def map(self, x: float, y: float) -> tuple[float, float]:
        return (self.m11 * x + self.m21 * y + self.dx,
                self.m12 * x + self.m22 * y + self.dy)

    def scaled(self, factor: float) -> 'Transform':
        return replace(self, m11=self.m11 * factor, m12=self.m12 * factor,
                       m21=self.m21 * factor, m22=self.m22 * factor)


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
    def from_file(cls, path, *, link: bool = False) -> 'Resource':
        path = FilePath(path)
        data = path.read_bytes()
        fmt, width, height = imagesize.identify(data)
        source = str(path.resolve()).replace('\\', '/')
        return cls(width, height, None if link else data, fmt, source)

    @classmethod
    def from_bytes(cls, data: bytes, *, width: int | None = None,
                   height: int | None = None, format: str | None = None,
                   source: str = '') -> 'Resource':
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
    children: list['Item'] = field(default_factory=list)
    extras: dict = field(default_factory=dict)

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

    def add(self, child: 'Item') -> 'Item':
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

    resource: Resource | None = None
    # Image pixels are mapped into item coordinates by this transform; the app
    # centers the image, so the default translates by (-width/2, -height/2).
    pixel_transform: Transform | None = None
    # The visible boundary in centered-pixel coordinates; a rectangle unless cropped.
    bounds: Path | None = None
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

    def crop(self, left: float, top: float, width: float, height: float) -> 'ImageItem':
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

    def scale(self, factor: float) -> 'ImageItem':
        self.transform = self.transform.scaled(factor)
        return self

    def scale_to_width(self, width: float) -> 'ImageItem':
        current = self.size[0]
        return self.scale(width / current) if current else self

    def scale_to_height(self, height: float) -> 'ImageItem':
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


def _multiply(outer: Transform, inner: Transform) -> Transform:
    """`inner` first, then `outer`: how a parent transforms its children."""
    return Transform(
        m11=inner.m11 * outer.m11 + inner.m12 * outer.m21,
        m12=inner.m11 * outer.m12 + inner.m12 * outer.m22,
        m21=inner.m21 * outer.m11 + inner.m22 * outer.m21,
        m22=inner.m21 * outer.m12 + inner.m22 * outer.m22,
        dx=inner.dx * outer.m11 + inner.dy * outer.m21 + outer.dx,
        dy=inner.dx * outer.m12 + inner.dy * outer.m22 + outer.dy)


@dataclass
class View:
    """Where the canvas was last looked at."""

    zoom: float = 1.0
    x: int = 0
    y: int = 0


@dataclass
class Scene:
    """A whole .pur file: resources, a tree of items and some view state."""

    items: list[Item] = field(default_factory=list)
    canvas: tuple[float, float, float, float] = (-10000.0, -10000.0, 10000.0, 10000.0)
    view: View = field(default_factory=View)
    source_version: str | None = None
    extras: dict = field(default_factory=dict)

    # --- construction ---------------------------------------------------------

    def add(self, item: Item, parent: Item | None = None) -> Item:
        (parent.children if parent is not None else self.items).append(item)
        return item

    def add_image(self, source, *, parent: Item | None = None, link: bool = False,
                  **options) -> ImageItem:
        """Add an image from a path, raw bytes or an existing `Resource`."""
        if isinstance(source, Resource):
            resource = source
        elif isinstance(source, (bytes, bytearray)):
            resource = Resource.from_bytes(bytes(source), **{
                key: options.pop(key) for key in ('width', 'height', 'format', 'source')
                if key in options})
        else:
            resource = Resource.from_file(source, link=link)
            options.setdefault('name', FilePath(source).stem)
        resource = self.share(resource)
        x, y = options.pop('x', 0.0), options.pop('y', 0.0)
        transform = options.pop('transform', None) or Transform.compose(
            x=x, y=y, scale_x=options.pop('scale_x', 1.0),
            scale_y=options.pop('scale_y', 1.0), rotation=options.pop('rotation', 0.0))
        crop = options.pop('crop', None)
        item = ImageItem(resource=resource, transform=transform, **options)
        if crop is not None:
            item.crop(*crop)
        return self.add(item, parent)

    def add_note(self, text: str = '', *, parent: Item | None = None, x: float = 0.0,
                 y: float = 0.0, **options) -> NoteItem:
        item = NoteItem(text=text, transform=Transform.translate(x, y), **options)
        return self.add(item, parent)

    def add_group(self, *, parent: Item | None = None, x: float = 0.0, y: float = 0.0,
                  **options) -> GroupItem:
        item = GroupItem(transform=Transform.translate(x, y), **options)
        return self.add(item, parent)

    def add_drawing(self, strokes, *, parent: Item | None = None, x: float = 0.0,
                    y: float = 0.0, **options) -> DrawItem:
        item = DrawItem(strokes=list(strokes), transform=Transform.translate(x, y),
                        **options)
        return self.add(item, parent)

    def share(self, resource: Resource) -> Resource:
        """Return the equal resource already in the scene, so instances share one."""
        for existing in self.resources:
            if existing.identity() == resource.identity():
                return existing
        return resource

    # --- inspection -----------------------------------------------------------

    def walk(self):
        for item in self.items:
            yield from item.walk()

    def of_kind(self, *kinds: type):
        return [item for item in self.walk() if isinstance(item, kinds)]

    @property
    def images(self) -> list[ImageItem]:
        return self.of_kind(ImageItem)

    @property
    def notes(self) -> list[NoteItem]:
        return self.of_kind(NoteItem)

    @property
    def groups(self) -> list[GroupItem]:
        return self.of_kind(GroupItem)

    @property
    def drawings(self) -> list[DrawItem]:
        return self.of_kind(DrawItem)

    @property
    def resources(self) -> list[Resource]:
        """Distinct resources, in the order their first instance appears."""
        seen, unique = set(), []
        for item in self.images:
            key = item.resource.identity()
            if key not in seen:
                seen.add(key)
                unique.append(item.resource)
        return unique

    def parents(self) -> dict[int, Item]:
        """A child-id to parent map, so lookups do not rescan the tree."""
        found = {}
        for item in self.walk():
            for child in item.children:
                found[id(child)] = item
        return found

    def world_transform(self, target: Item, parents: dict | None = None) -> Transform:
        """The transform of `target` with every ancestor folded in."""
        parents = self.parents() if parents is None else parents
        chain = []
        item = target
        while item is not None:
            chain.append(item)
            item = parents.get(id(item))
        result = Transform()
        for item in reversed(chain):
            result = _multiply(result, item.transform)
        return result

    def content_bounds(self, *, padding: float = 0.0):
        """The rectangle the scene's content occupies, or None when empty."""
        corners = []
        parents = self.parents()
        for item in self.walk():
            world = self.world_transform(item, parents)
            if isinstance(item, ImageItem):
                x0, y0, x1, y1 = item.bounds.bounding_box()
            elif isinstance(item, DrawItem) and item.strokes:
                boxes = [stroke.path.bounding_box() for stroke in item.strokes]
                x0 = min(box[0] for box in boxes)
                y0 = min(box[1] for box in boxes)
                x1 = max(box[2] for box in boxes)
                y1 = max(box[3] for box in boxes)
            elif isinstance(item, NoteItem):
                width, height = item.fixed_size
                width = width if width > 0 else 200.0
                height = height if height > 0 else 60.0
                x0, y0, x1, y1 = -width / 2, -height / 2, width / 2, height / 2
            else:
                continue
            corners.extend(world.map(x, y) for x, y in
                           ((x0, y0), (x1, y0), (x1, y1), (x0, y1)))
        if not corners:
            return None
        xs = [x for x, _ in corners]
        ys = [y for _, y in corners]
        return (min(xs) - padding, min(ys) - padding,
                max(xs) + padding, max(ys) + padding)

    def parent_of(self, target: Item) -> Item | None:
        for item in self.walk():
            if any(child is target for child in item.children):
                return item
        return None

    def losses(self, version: str) -> list[str]:
        """What writing this scene as `version` would drop or approximate."""
        if version not in VERSIONS:
            raise ValueError(f'Unknown version {version!r}; expected one of {VERSIONS}')
        if version == VERSION_2_0:
            preview = getattr(self.extras.get('v2', {}).get('envelope'), 'thumbnail', b'')
            return ['the preview image: the 2.0 header has no thumbnail field'] \
                if preview else []
        if version != VERSION_1:
            return []
        reasons = []
        if self.groups:
            reasons.append(f'{len(self.groups)} group(s): 1.x has no groups, '
                           'their children move to the canvas')
        if self.drawings:
            reasons.append(f'{len(self.drawings)} drawing(s): 1.x has no drawings')
        if any(item.flags != RENDER_SMOOTH for item in self.images):
            reasons.append('render flags (bilinear/grayscale): not stored by 1.x')
        if any(item.playback.state != PLAYBACK_STATIC for item in self.images):
            reasons.append('animation playback state: not stored by 1.x')
        if any(note.opacity != 1.0 for note in self.notes):
            reasons.append("note opacity: 1.x keeps a note's alpha in its text colour")
        if any(item.resource.linked for item in self.images):
            reasons.append('linked images: 1.x stores a link, but PureRef 1.x resolves it '
                           'and embeds the file on its next save')
        if any(note.html for note in self.notes):
            reasons.append('note HTML: 1.x notes are plain text')
        if any(item.comment for item in self.walk()):
            reasons.append('item comments: 1.x has no comment field')
        formats = {item.resource.format.upper() for item in self.images
                   if not item.resource.linked} - {'PNG'}
        if formats:
            reasons.append(f'{", ".join(sorted(formats))} image data: '
                           're-encoded as PNG, which 1.x is limited to')
        return reasons
