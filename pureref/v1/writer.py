"""Write a `Scene` as a PureRef 1.10 / 1.11.1 file.

Layout, in order: the 224-byte header, the image section (each PNG followed by a
four-byte slot per extra instance), the item blocks, the folder string, and the
reference table that ties item ids to image addresses. The header checksum is
written last because it covers everything from offset 108 on.
"""
from __future__ import annotations

import struct

from .. import transcode
from ..model import (VERSION_1, DrawItem, GroupItem, ImageItem, Item, NoteItem, Scene,
                     Transform, _multiply)
from ..qt import pack_string
from . import format as fmt


DEFAULT_CANVAS = (-10000.0, -10000.0, 10000.0, 10000.0)


def write(scene: Scene, *, flatten_groups: bool = True, canvas=None) -> bytes:
    """Serialize `scene`. Groups and drawings cannot be represented and are
    dropped; `Scene.losses('1.10')` reports that before it happens.

    `canvas` is the scrollable area 1.x stores in its header. Unset, a canvas
    that came from a 1.x file is kept, and otherwise one is fitted around the
    content, because 1.x uses this rectangle to frame the scene.
    """
    plan = _Plan(scene, flatten_groups=flatten_groups, canvas=canvas)
    stream = bytearray(plan.header_template())
    plan.write_images(stream)
    plan.write_items(stream)
    stream += pack_string(plan.folder)
    reference_offset = len(stream)
    plan.write_references(stream)
    plan.finish_header(stream, reference_offset)
    stream[fmt.CHECKSUM_SLICE] = fmt.checksum(stream).encode('utf-16-be')
    return bytes(stream)


class _Plan:
    """Decides ids, resource sharing and write order before anything is packed."""

    def __init__(self, scene: Scene, *, flatten_groups: bool, canvas=None):
        self.scene = scene
        self.legacy = scene.extras.get('v1', {})
        self.canvas = canvas or _canvas_for(scene)
        self.folder = self.legacy.get('folder') or ''
        found: list[ImageItem] = []
        self.notes: list[NoteItem] = []
        for item in _flattened(scene.items, flatten_groups):
            if isinstance(item, ImageItem):
                found.append(item)
            elif isinstance(item, NoteItem):
                self.notes.append(item)
        self.owners: dict[tuple, ImageItem] = {}
        self.order: list[tuple] = []
        for item in found:
            key = item.resource.identity()
            if key not in self.owners:
                self.owners[key] = item
                self.order.append(key)
        # Instances are grouped under the image they share, and ids follow that
        # order: PureRef 1.x pairs the image section with the reference table in
        # address order and rejects the file when an id jumps backwards.
        self.images = [item for key in self.order for item in found
                       if item.resource.identity() == key]
        self.ids: dict[int, int] = {id(item): index
                                    for index, item in enumerate(self.images)}
        next_id = len(self.images)
        for root in self.images + self.notes:
            for item in root.walk():
                if isinstance(item, NoteItem) and id(item) not in self.ids:
                    self.ids[id(item)] = next_id
                    next_id += 1
        self.addresses: dict[int, tuple[int, int]] = {}

    # --- header ---------------------------------------------------------------

    def header_template(self) -> bytes:
        """Start from the header we read, if any, so unknown fields survive."""
        template = bytearray(self.legacy.get('header_bytes') or bytes(fmt.HEADER_SIZE))
        template[0:4] = struct.pack('>I', 8)
        template[4:12] = fmt.VERSION_STRING.encode('utf-16-be')
        template[24:28] = struct.pack('>I', 12)
        template[40:44] = struct.pack('>I', 64)
        return bytes(template)

    def finish_header(self, stream: bytearray, reference_offset: int) -> None:
        roots = len(self.images) + len(self.notes)
        stream[12:14] = struct.pack('>H', roots)
        stream[14:16] = struct.pack('>H', len(self.images))
        stream[16:24] = struct.pack('>Q', reference_offset)
        stream[108:112] = struct.pack('>I', roots)
        stream[112:144] = struct.pack('>4d', *self.canvas)
        stream[144:152] = struct.pack('>d', self.scene.view.zoom)
        stream[176:184] = struct.pack('>d', self.scene.view.zoom)
        stream[208:216] = struct.pack('>d', 1.0)
        stream[216:224] = struct.pack('>2i', int(self.scene.view.x), int(self.scene.view.y))

    # --- image section --------------------------------------------------------

    def write_images(self, stream: bytearray) -> None:
        for key in self.order:
            owner = self.owners[key]
            resource = owner.resource
            start = len(stream)
            # 1.x finds embedded images by scanning for PNG signatures, so
            # anything else has to be re-encoded first.
            stream += fmt.LINK_SLOT if resource.linked else transcode.to_png(resource)
            self.addresses[self.ids[id(owner)]] = (start, len(stream))
            for item in self.images:
                if item is owner or item.resource.identity() != key:
                    continue
                slot = len(stream)
                stream += struct.pack('>I', self.ids[id(owner)])
                self.addresses[self.ids[id(item)]] = (slot, len(stream))

    def write_references(self, stream: bytearray) -> None:
        for item in self.images:
            item_id = self.ids[id(item)]
            start, end = self.addresses[item_id]
            stream += struct.pack('>IQQ', item_id, start, end)

    # --- items ----------------------------------------------------------------

    def write_items(self, stream: bytearray) -> None:
        for item in self.images:
            self._write_image_item(stream, item)
        for note in self.notes:
            self._write_note(stream, note)

    def _write_image_item(self, stream: bytearray, item: ImageItem) -> None:
        legacy = item.extras.get('v1', {})
        resource = item.resource
        block = _Block(stream)
        stream += struct.pack('>I', fmt.IMAGE_ITEM_MARKER)
        stream += fmt.IMAGE_ITEM_NAME.encode('utf-16-be')
        source = legacy.get('source', resource.source or fmt.BRUTE_FORCE_SOURCE)
        brute_force = legacy.get('brute_force', source == fmt.BRUTE_FORCE_SOURCE)
        if brute_force:
            stream += struct.pack('>I', 0)
        stream += _optional_string(source)
        if not brute_force:
            stream += _optional_string(item.name)
        stream += struct.pack('>d', legacy.get('leading_one', 1.0))
        stream += _pack_matrix(item.transform, legacy.get('perspective', (0.0, 0.0)))
        stream += struct.pack('>2d', item.transform.dx, item.transform.dy)
        stream += struct.pack('>d', legacy.get('trailing_one', 1.0))
        stream += struct.pack('>I', self.ids[id(item)])
        stream += struct.pack('>d', 1.0 if item.z is None else item.z)
        stream += _pack_matrix(legacy.get('matrix_before_crop') or Transform(),
                               legacy.get('matrix_before_crop_perspective', (0.0, 0.0)))
        offset = legacy.get('crop_offset',
                            (-resource.width / 2, -resource.height / 2))
        stream += struct.pack('>2d', *offset)
        stream += struct.pack('>d', legacy.get('crop_scale', 1.0))
        stream += struct.pack('>I', len(item.bounds.elements))
        for kind, x, y in item.bounds.elements:
            stream += struct.pack('>Idd', kind, x, y)
        stream += _tail(legacy.get('tail'), fmt.IMAGE_TAIL_DEFAULT,
                        len(_notes(item.children)))
        stream += legacy.get('unparsed', b'')
        block.close(stream)
        for note in _notes(item.children):
            self._write_note(stream, note)

    def _write_note(self, stream: bytearray, note: NoteItem) -> None:
        legacy = note.extras.get('v1', {})
        block = _Block(stream)
        stream += struct.pack('>I', fmt.TEXT_ITEM_MARKER)
        stream += fmt.TEXT_ITEM_NAME.encode('utf-16-be')
        stream += pack_string(note.text)
        stream += _pack_matrix(note.transform, legacy.get('perspective', (0.0, 0.0)))
        stream += struct.pack('>2d', note.transform.dx, note.transform.dy)
        stream += struct.pack('>d', legacy.get('trailing_one', 1.0))
        stream += struct.pack('>I', self.ids[id(note)])
        stream += struct.pack('>d', 1.0 if note.z is None else note.z)
        stream += _pack_color(legacy.get('foreground'), note.text_color, _WHITE)
        stream += legacy.get('color_gap', b'\0\0')
        stream += _pack_color(legacy.get('background'), note.background_color, _SHADE)
        stream += _tail(legacy.get('tail'), fmt.TEXT_TAIL_DEFAULT,
                        len(_notes(note.children)))
        stream += legacy.get('unparsed', b'')
        block.close(stream)
        for child in _notes(note.children):
            self._write_note(stream, child)


class _Block:
    """An item block starts with the absolute offset just past its own fields."""

    def __init__(self, stream: bytearray):
        self.at = len(stream)
        stream += struct.pack('>Q', 0)

    def close(self, stream: bytearray) -> None:
        stream[self.at:self.at + 8] = struct.pack('>Q', len(stream))


def _canvas_for(scene: Scene):
    if scene.source_version == VERSION_1 and scene.canvas:
        return scene.canvas
    fitted = scene.content_bounds(padding=200.0)
    return fitted or scene.canvas or DEFAULT_CANVAS


def _flattened(items, flatten_groups: bool):
    """Yield items 1.x can hold. Only notes nest there, so anything else that is
    parented to an item moves up to the canvas with its transform folded in."""
    for item in items:
        if isinstance(item, GroupItem):
            if flatten_groups:
                yield from _flattened(_reparent(item, item.children), flatten_groups)
            continue
        if isinstance(item, DrawItem):
            continue
        yield item
        nested = [child for child in item.children if not isinstance(child, NoteItem)]
        if nested:
            yield from _flattened(_reparent(item, nested), flatten_groups)


def _reparent(parent: Item, children):
    """Fold the parent's transform into children that cannot stay nested."""
    moved = []
    for child in children:
        clone = _shallow_copy(child)
        clone.transform = _multiply(parent.transform, child.transform)
        moved.append(clone)
    return moved


def _shallow_copy(item: Item) -> Item:
    from copy import copy
    clone = copy(item)
    clone.children = list(item.children)
    return clone


def _notes(children) -> list[NoteItem]:
    return [child for child in children if isinstance(child, NoteItem)]


def _optional_string(value: str | None) -> bytes:
    return struct.pack('>i', -1) if value is None else pack_string(value)


def _pack_matrix(transform: Transform, perspective) -> bytes:
    m13, m23 = perspective
    return struct.pack('>6d', transform.m11, transform.m12, m13,
                       transform.m21, transform.m22, m23)


# PureRef's own defaults: opaque white text on a faint dark background.
_WHITE = (0xFFFF, [0xFFFF, 0xFFFF, 0xFFFF])
_SHADE = (5000, [0, 0, 0])


def _pack_color(legacy, argb: str | None, default) -> bytes:
    """Colors are stored as either RGB or HSV; this writes the RGB form, which
    is what the reader normalizes HSV values into."""
    if legacy is not None:
        opacity, channels = legacy['color']
    elif argb:
        opacity, channels = fmt.argb_to_color(argb)
    else:
        opacity, channels = default
    return struct.pack('>bH3H', 1, opacity, *channels)


def _tail(stored: bytes | None, default: bytes, child_count: int) -> bytes:
    body = (stored or default)[:len(default)]
    return body + struct.pack('>I', child_count)
