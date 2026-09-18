"""Write a `Scene` as a PureRef 1.10 / 1.11.1 file.

Two halves, deliberately: `plan` decides what goes where — which items 1.x can
hold, which image owns which instance, what id everything gets — and is pure, so
it can be tested without producing a byte. `emit` then walks that plan and fills
in the records from `records.py`, which are the same declarations the reader uses.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

from .. import transcode
from ..model import (VERSION_1, DrawItem, GroupItem, ImageItem, Item,
                     V1Image, V1Note, NoteItem, Scene, multiply)
from ..qt import Path, pack_string
from . import format as fmt
from .records import HEADER, IMAGE_ITEM, NOTE_ITEM, REFERENCE, from_transform

DEFAULT_CANVAS = (-10000.0, -10000.0, 10000.0, 10000.0)


def write(scene: Scene, *, flatten_groups: bool = True, canvas=None) -> bytes:
    """Serialize `scene`. Groups and drawings have no place in 1.x and are
    dropped; `Scene.losses('1.10')` says so before it happens.

    `canvas` is the scrollable area 1.x stores in its header. Unset, a canvas
    that came from a 1.x file is kept and anything else gets one fitted around
    the content, because 1.x frames the scene with it.
    """
    return _emit(_plan(scene, flatten_groups=flatten_groups, canvas=canvas))


# --- planning -----------------------------------------------------------------

@dataclass
class Plan:
    """What the file will contain, before any of it is packed."""

    scene: Scene
    canvas: tuple[float, float, float, float]
    folder: str
    header: bytes
    images: list[ImageItem] = field(default_factory=list)
    notes: list[NoteItem] = field(default_factory=list)
    resources: list[tuple] = field(default_factory=list)      # identity keys, in order
    owners: dict = field(default_factory=dict)                # identity -> owning item
    ids: dict[int, int] = field(default_factory=dict)          # id(item) -> item id

    @property
    def root_count(self) -> int:
        return len(self.images) + len(self.notes)


def _plan(scene: Scene, *, flatten_groups: bool, canvas) -> Plan:
    found: list[ImageItem] = []
    notes: list[NoteItem] = []
    for item in _flattened(scene.items, flatten_groups):
        if isinstance(item, ImageItem):
            found.append(item)
        elif isinstance(item, NoteItem):
            notes.append(item)

    owners: dict = {}
    order: list = []
    for item in found:
        key = item.resource.identity()
        if key not in owners:
            owners[key] = item
            order.append(key)

    # Instances are grouped under the image they share, and ids follow that
    # order: PureRef pairs the image section with the reference table in address
    # order and rejects the file when an id jumps backwards.
    images = [item for key in order for item in found
              if item.resource.identity() == key]
    ids = {id(item): index for index, item in enumerate(images)}
    next_id = len(images)
    for root in images + notes:
        for item in root.walk():
            if isinstance(item, NoteItem) and id(item) not in ids:
                ids[id(item)] = next_id
                next_id += 1

    stored = scene.v1
    return Plan(scene=scene,
                canvas=tuple(canvas or _canvas_for(scene)),
                folder=(stored.folder if stored and stored.folder else ''),
                header=(stored.header if stored else b'') or bytes(fmt.HEADER_SIZE),
                images=images, notes=notes, resources=order, owners=owners, ids=ids)


def _canvas_for(scene: Scene):
    if scene.source_version == VERSION_1 and scene.canvas:
        return scene.canvas
    return scene.content_bounds(padding=200.0) or scene.canvas or DEFAULT_CANVAS


def _flattened(items, flatten_groups: bool):
    """Yield the items 1.x can hold. Only notes nest there, so anything else
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
    from copy import copy
    moved = []
    for child in children:
        clone = copy(child)
        clone.children = list(child.children)
        clone.transform = multiply(parent.transform, child.transform)
        moved.append(clone)
    return moved


# --- emitting -----------------------------------------------------------------

def _emit(plan: Plan) -> bytes:
    stream = bytearray(bytes(fmt.HEADER_SIZE))
    addresses = _emit_images(stream, plan)
    for item in plan.images:
        _emit_image_item(stream, plan, item)
    for note in plan.notes:
        _emit_note(stream, plan, note)
    stream += pack_string(plan.folder)
    reference_offset = len(stream)
    for item in plan.images:
        item_id = plan.ids[id(item)]
        start, end = addresses[item_id]
        REFERENCE.write(stream, {'id': item_id, 'start': start, 'end': end})
    stream[:fmt.HEADER_SIZE] = _emit_header(plan, reference_offset)
    stream[fmt.CHECKSUM_SLICE] = fmt.checksum(bytes(stream)).encode('utf-16-be')
    return bytes(stream)


def _emit_header(plan: Plan, reference_offset: int) -> bytes:
    # Only what a previous header held and this package does not compute is
    # carried over; every structural field comes from the declaration, so a
    # fresh scene cannot inherit zeros where the version string belongs.
    kept = _kept_header(plan.header)
    values = dict(kept)
    values.update(
        item_count=plan.root_count,
        image_count=len(plan.images),
        reference_offset=reference_offset,
        id_count=plan.root_count,
        canvas=plan.canvas,
        zoom=plan.scene.view.zoom,
        zoom_y=plan.scene.view.zoom,
        zoom_multiplier=1.0,
        view_x=int(plan.scene.view.x),
        view_y=int(plan.scene.view.y),
        checksum=b'',
    )
    return HEADER.to_bytes(values)


def _kept_header(blob: bytes) -> dict:
    if len(blob) < fmt.HEADER_SIZE:
        return {}
    from ..qt import Cursor
    previous = HEADER.read(Cursor(blob))
    if previous['_version'] != fmt.VERSION_STRING.encode('utf-16-be'):
        return {}
    return {name: previous[name] for name in
            ('application_version', '_unknown_152', '_unknown_184')}


def _emit_images(stream: bytearray, plan: Plan) -> dict[int, tuple[int, int]]:
    """The image section: each image once, then a slot per extra instance."""
    addresses: dict[int, tuple[int, int]] = {}
    for key in plan.resources:
        owner = plan.owners[key]
        resource = owner.resource
        start = len(stream)
        # 1.x finds embedded images by scanning for PNG signatures, so anything
        # else has to be re-encoded first.
        stream += fmt.LINK_SLOT if resource.linked else transcode.to_png(resource)
        addresses[plan.ids[id(owner)]] = (start, len(stream))
        for item in plan.images:
            if item is owner or item.resource.identity() != key:
                continue
            slot = len(stream)
            stream += struct.pack('>I', plan.ids[id(owner)])
            addresses[plan.ids[id(item)]] = (slot, len(stream))
    return addresses


def _open_block(stream: bytearray, marker: int, name: str) -> int:
    """A block starts with the offset just past its own fields, filled in later."""
    at = len(stream)
    stream += struct.pack('>Q', 0)
    stream += struct.pack('>I', marker)
    stream += name.encode('utf-16-be')
    return at


def _close_block(stream: bytearray, at: int) -> None:
    stream[at:at + 8] = struct.pack('>Q', len(stream))


def _emit_image_item(stream: bytearray, plan: Plan, item: ImageItem) -> None:
    stored = item.v1 if isinstance(item.v1, V1Image) else V1Image()
    resource = item.resource
    source = stored.source if stored.source is not None else (
        resource.source or fmt.BRUTE_FORCE_SOURCE)
    brute_force = stored.brute_force or source == fmt.BRUTE_FORCE_SOURCE
    offset = stored.crop_offset or (-resource.width / 2, -resource.height / 2)
    at = _open_block(stream, fmt.IMAGE_ITEM_MARKER, fmt.IMAGE_ITEM_NAME)
    IMAGE_ITEM.write(stream, {
        'brute_force': brute_force,
        'source': source,
        'name': None if brute_force else item.name,
        'opacity': float(item.opacity),
        **from_transform(item.transform, stored.perspective),
        'id': plan.ids[id(item)],
        'z': 1.0 if item.z is None else item.z,
        'before_crop': from_transform(stored.before_crop,
                                      stored.before_crop_perspective)['linear'],
        'crop_offset': offset,
        'crop_scale': stored.crop_scale,
        'bounds': item.bounds or Path.centered_rectangle(*resource.size),
        '_tail': stored.tail or fmt.IMAGE_TAIL_DEFAULT,
        'children': len(_notes(item.children)),
    })
    stream += stored.trailing
    _close_block(stream, at)
    for note in _notes(item.children):
        _emit_note(stream, plan, note)


def _emit_note(stream: bytearray, plan: Plan, note: NoteItem) -> None:
    stored = note.v1 if isinstance(note.v1, V1Note) else V1Note()
    foreground = stored.foreground or fmt.argb_to_color(note.text_color or '#ffffffff')
    background = stored.background or fmt.argb_to_color(note.background_color or '')
    at = _open_block(stream, fmt.TEXT_ITEM_MARKER, fmt.TEXT_ITEM_NAME)
    NOTE_ITEM.write(stream, {
        'text': note.text,
        **from_transform(note.transform, stored.perspective),
        'id': plan.ids[id(note)],
        'z': 1.0 if note.z is None else note.z,
        # HSV colours are normalised to RGB on read, so they go back as RGB.
        'foreground_kind': 1,
        'foreground_opacity': foreground[0],
        'foreground_rgb': tuple(foreground[1]),
        '_colour_gap': stored.colour_gap,
        'background_kind': 1,
        'background_opacity': background[0],
        'background_rgb': tuple(background[1]),
        '_tail': stored.tail,
        'children': len(_notes(note.children)),
    })
    stream += stored.trailing
    _close_block(stream, at)
    for child in _notes(note.children):
        _emit_note(stream, plan, child)


def _notes(children) -> list[NoteItem]:
    return [child for child in children if isinstance(child, NoteItem)]
