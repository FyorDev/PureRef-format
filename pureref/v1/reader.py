"""Read a PureRef 1.10 / 1.11.1 file into a `Scene`.

The layouts live in `records.py`; this module only walks the file's sections and
maps the values onto the model. Nothing is consumed destructively, so the offsets
in the header and in the reference table can be used directly, and anything not
modelled is kept on `item.v1` so a save reproduces the file.
"""
from __future__ import annotations

from .. import imagesize
from ..model import (VERSION_1, ImageItem, Item, V1File, V1Image,
                     V1Note, NoteItem, Resource, Scene, Transform, View)
from ..qt import Cursor, FormatError
from . import format as fmt
from .records import HEADER, IMAGE_ITEM, NOTE_ITEM, REFERENCE, to_transform


def read(data: bytes) -> Scene:
    blob = bytes(data)
    if len(blob) < fmt.HEADER_SIZE:
        raise FormatError('Too short to be a PureRef 1.x file')
    header = _read_header(blob)
    slots, items_start = _read_image_section(blob, header)
    parsed = _read_items(blob, header, items_start)
    references = _read_references(blob, header)
    return _assemble(blob, header, slots, parsed, references)


# --- header -------------------------------------------------------------------

def _read_header(blob: bytes) -> dict:
    header = HEADER.read(Cursor(blob))
    if header['_version'] != fmt.VERSION_STRING.encode('utf-16-be'):
        raise FormatError('Not a PureRef 1.10 stream')
    if not fmt.HEADER_SIZE <= header['reference_offset'] <= len(blob):
        raise FormatError('Reference table offset outside the file')
    header['bytes'] = blob[:fmt.HEADER_SIZE]
    return header


def _text(raw: bytes) -> str | None:
    return raw.decode('utf-16-be', 'replace').rstrip('\0') or None


# --- image section ------------------------------------------------------------

def _read_image_section(blob: bytes, header: dict) -> tuple[list[dict], int]:
    """The embedded PNGs and the four-byte slots between them, with addresses.

    Returns the entries and the offset where the item blocks start, because the
    reference table at the end of the file points at these address ranges.
    """
    slots: list[dict] = []
    limit = header['reference_offset']
    pos = fmt.HEADER_SIZE
    while pos < limit:
        start = blob.find(fmt.PNG_HEAD, pos, limit)
        boundary = start if start != -1 else limit
        while pos < boundary:
            # Anything before the next PNG is a four-byte slot: a link marker or
            # the id of the instance that owns the image data.
            if _looks_like_item(blob, pos, limit):
                return slots, pos
            slots.append({'start': pos, 'end': pos + 4, 'ref': blob[pos:pos + 4]})
            pos += 4
        if start == -1:
            return slots, pos
        end = blob.find(fmt.PNG_FOOT, start, limit)
        if end == -1:
            raise FormatError('Embedded PNG without an IEND chunk')
        end += len(fmt.PNG_FOOT)
        slots.append({'start': start, 'end': end, 'data': blob[start:end]})
        pos = end
    return slots, pos


def _looks_like_item(blob: bytes, pos: int, limit: int) -> bool:
    cursor = Cursor(blob, pos)
    try:
        end = cursor.read('Q')
        marker = cursor.read('I')
    except FormatError:
        return False
    return marker in fmt.ITEM_MARKERS and pos < end <= limit


# --- item blocks --------------------------------------------------------------

def _read_items(blob: bytes, header: dict, start: int) -> dict:
    """Read the item blocks in file order, then the trailing folder string."""
    cursor = Cursor(blob, start)
    limit = header['reference_offset']
    roots: list[Item] = []
    images: list[tuple[int, ImageItem]] = []
    while cursor.pos < limit and _looks_like_item(blob, cursor.pos, limit):
        item, values = _read_item(cursor, limit)
        if isinstance(item, ImageItem):
            images.append((values['id'], item))
        roots.append(item)
    folder = cursor.read_string() if cursor.pos < limit else None
    return {'roots': roots, 'images': images, 'folder': folder}


def _read_item(cursor: Cursor, limit: int) -> tuple[Item, dict]:
    """The item and the record it came from, so callers need not re-read fields."""
    end = cursor.read('Q')
    length = cursor.read('I')
    cursor.take(length)                      # the class name, already identified
    record = IMAGE_ITEM if length == fmt.IMAGE_ITEM_MARKER else NOTE_ITEM
    values = record.read(cursor)
    values['trailing'] = cursor.take(end - cursor.pos) if cursor.pos != end else b''
    item = (_image_item(values) if record is IMAGE_ITEM else _note_item(values))
    for _ in range(values['children']):
        child, _ = _read_item(cursor, limit)
        item.children.append(child)
    return item, values


def _carrier(item: ImageItem) -> V1Image:
    """The 1.x data an image item was read with, narrowed to its own type."""
    stored = item.v1
    if not isinstance(stored, V1Image):     # only if a caller replaced it
        stored = V1Image()
        item.v1 = stored
    return stored


def _image_item(values: dict) -> ImageItem:
    transform, perspective = to_transform(values)
    before_m11, before_m12, before_m13, before_m21, before_m22, before_m23 = \
        values['before_crop']
    source = values['source']
    stored = V1Image(
        source=source,
        brute_force=values['brute_force'],
        before_crop=Transform(before_m11, before_m12, before_m21, before_m22),
        before_crop_perspective=(before_m13, before_m23),
        crop_offset=values['crop_offset'],
        crop_scale=values['crop_scale'],
        perspective=perspective,
        tail=values['_tail'],
        trailing=values['trailing'],
        id=values['id'])
    return ImageItem(name=values['name'], transform=transform, z=values['z'],
                     opacity=values['opacity'], bounds=values['bounds'],
                     resource=_placeholder(), v1=stored)


def _note_item(values: dict) -> NoteItem:
    transform, perspective = to_transform(values)
    foreground = fmt.read_colour(values['foreground_kind'], values['foreground_opacity'],
                                 values['foreground_rgb'])
    background = fmt.read_colour(values['background_kind'], values['background_opacity'],
                                 values['background_rgb'])
    stored = V1Note(
        foreground=foreground['colour'], foreground_hsv=foreground['hsv'],
        background=background['colour'], background_hsv=background['hsv'],
        colour_gap=values['_colour_gap'], tail=values['_tail'],
        trailing=values['trailing'], perspective=perspective, id=values['id'])
    return NoteItem(transform=transform, z=values['z'], text=values['text'],
                    text_color=fmt.color_to_argb(*foreground['colour']),
                    background_color=fmt.color_to_argb(*background['colour']),
                    v1=stored)


# --- references and assembly --------------------------------------------------

def _read_references(blob: bytes, header: dict) -> dict[int, tuple[int, int]]:
    cursor = Cursor(blob, header['reference_offset'])
    references = {}
    while cursor.remaining >= fmt.REFERENCE_SIZE:
        record = REFERENCE.read(cursor)
        references[record['id']] = (record['start'], record['end'])
    return references


def _placeholder() -> Resource:
    """Stand-in until the reference table says which image an instance uses."""
    return Resource(1, 1, b'', 'PNG')


def _assemble(blob, header: dict, slots, parsed, references) -> Scene:
    by_start = {slot['start']: slot for slot in slots}
    owners: dict[int, Resource] = {}
    instances: list[tuple[int, ImageItem, dict]] = []
    for item_id, item in parsed['images']:
        start = references.get(item_id, (None, None))[0]
        slot = by_start.get(start)
        if slot is None:
            raise FormatError(f'Image item {item_id} has no usable reference')
        instances.append((item_id, item, slot))
        stored = _carrier(item)
        stored.address = (slot['start'], slot['end'])
        if 'data' in slot:
            owners[item_id] = _resource_for(slot['data'], item, stored.source)
        elif slot['ref'] == fmt.LINK_SLOT:
            owners[item_id] = _resource_for(None, item, stored.source)
    for item_id, item, slot in instances:
        resource = owners.get(item_id)
        if resource is None:
            owner_id = int.from_bytes(slot['ref'], 'big')
            if owner_id not in owners:
                raise FormatError(f'Instance {item_id} points at unknown item {owner_id}')
            resource = owners[owner_id]
        item.resource = resource
        item.pixel_transform = Transform.translate(-resource.width / 2,
                                                   -resource.height / 2)
    scene = Scene(items=parsed['roots'], canvas=header['canvas'],
                  view=View(header['zoom'], header['view_x'], header['view_y']),
                  source_version=VERSION_1)
    scene.v1 = V1File(
        header=header['bytes'],
        application_version=_text(header['application_version']),
        checksum=_text(header['checksum']),
        checksum_valid=_text(header['checksum']) == fmt.checksum(blob),
        folder=parsed['folder'])
    return scene


def _resource_for(data: bytes | None, item: ImageItem, source: str | None) -> Resource:
    """1.x stores no pixel size: read it from the PNG, or fall back to the crop
    outline, which spans the original pixels when nothing was cropped."""
    image_format, width, height = 'PNG', 0, 0
    if data:
        try:
            image_format, width, height = imagesize.identify(data)
        except imagesize.UnknownImage:
            width = height = 0
    if not width or not height:
        x0, y0, x1, y1 = item.bounds.bounding_box()
        width, height = max(1, round(x1 - x0)), max(1, round(y1 - y0))
    if source in (None, fmt.BRUTE_FORCE_SOURCE):
        source = ''
    return Resource(width, height, data, image_format,
                    source or ('missing' if data is None else ''))
