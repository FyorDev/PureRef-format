"""A whole `.pur` in memory: resources, a tree of items, and some view state.

Readers for every generation produce a `Scene`; writers consume one. What a
target format cannot express is reported by `losses(version)` before a write
drops it, and what a reader could not interpret is on `problems` and on the
carriers rather than gone.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path as FilePath
from typing import TypeVar

from .carriers import V1File, V2File
from .constants import (PLAYBACK_STATIC, RENDER_SMOOTH, VERSION_1,
                        VERSION_2_0, VERSIONS)
from .geometry import Transform, multiply
from .items import DrawItem, GroupItem, ImageItem, Item, NoteItem
from .problems import Loss, Problem
from .resources import Resource

# `Scene.add` hands back exactly the item kind it was given.
ItemT = TypeVar('ItemT', bound=Item)

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
    # As on `Item`: what the file held beyond what the model names.
    v1: V1File | None = None
    v2: V2File | None = None
    # What a reader could not interpret; empty for a file this package fully
    # understands. Reading never raises for these.
    problems: list[Problem] = field(default_factory=list)

    # --- construction ---------------------------------------------------------

    def add(self, item: ItemT, parent: Item | None = None) -> ItemT:
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
        current: Item | None = target
        while current is not None:
            chain.append(current)
            current = parents.get(id(current))
        result = Transform()
        for item in reversed(chain):
            result = multiply(result, item.transform)
        return result

    def content_bounds(self, *, padding: float = 0.0):
        """The rectangle the scene's content occupies, or None when empty."""
        corners: list[tuple[float, float]] = []
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

    def losses(self, version: str) -> list[Loss]:
        """What writing this scene as `version` would drop or approximate."""
        if version not in VERSIONS:
            raise ValueError(f'Unknown version {version!r}; expected one of {VERSIONS}')
        if version == VERSION_2_0:
            preview = getattr(getattr(self.v2, 'envelope', None), 'thumbnail', b'')
            return [Loss('thumbnail', 'the preview image: the 2.0 header has no '
                         'thumbnail field')] if preview else []
        if version != VERSION_1:
            return []
        reasons = []
        if self.groups:
            reasons.append(Loss('groups', f'{len(self.groups)} group(s): 1.x has no '
                                'groups, their children move to the canvas'))
        if self.drawings:
            reasons.append(Loss('drawings',
                                f'{len(self.drawings)} drawing(s): 1.x has no drawings'))
        if any(item.flags != RENDER_SMOOTH for item in self.images):
            reasons.append(Loss('render-flags',
                                'render flags (bilinear/grayscale): not stored by 1.x'))
        if any(item.playback.state != PLAYBACK_STATIC for item in self.images):
            reasons.append(Loss('playback',
                                'animation playback state: not stored by 1.x'))
        if any(note.opacity != 1.0 for note in self.notes):
            reasons.append(Loss('note-opacity',
                                "note opacity: 1.x keeps a note's alpha in its text colour"))
        if any(item.resource.linked for item in self.images):
            reasons.append(Loss('linked-images',
                                'linked images: 1.x stores a link, but PureRef 1.x '
                                'resolves it and embeds the file on its next save'))
        if any(note.html for note in self.notes):
            reasons.append(Loss('note-html', 'note HTML: 1.x notes are plain text'))
        if any(item.comment for item in self.walk()):
            reasons.append(Loss('comments', 'item comments: 1.x has no comment field'))
        formats = {item.resource.format.upper() for item in self.images
                   if not item.resource.linked} - {'PNG'}
        if formats:
            reasons.append(Loss('image-format',
                                f'{", ".join(sorted(formats))} image data: re-encoded '
                                'as PNG, which 1.x is limited to'))
        return reasons
