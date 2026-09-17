"""Read a PureRef 1.10 / 1.11.1 file into a `Scene`.

The stream is walked with a cursor instead of being consumed from the front, so
offsets in the header and in the reference table can be used directly. Every
region this reader does not interpret is kept in `extras` so the writer can put
it back byte for byte.
"""
from __future__ import annotations

from .. import imagesize
from ..model import (VERSION_1, ImageItem, Item, NoteItem, Resource, Scene,
                     Transform, View)
from ..qt import Cursor, FormatError, Path
from . import format as fmt


def read(data: bytes) -> Scene:
    blob = bytes(data)
    if len(blob) < fmt.HEADER_SIZE:
        raise FormatError('Too short to be a PureRef 1.x file')
    header = _Header(blob)
    slots, items_start = _read_image_section(blob, header)
    parsed = _read_items(blob, header, items_start)
    references = _read_references(blob, header)
    return _assemble(blob, header, slots, parsed, references)


class _Header:
    def __init__(self, blob: bytes):
        cursor = Cursor(blob)
        if cursor.read('I') != 8 or cursor.take(8).decode('utf-16-be') != fmt.VERSION_STRING:
            raise FormatError('Not a PureRef 1.10 stream')
        self.bytes = blob[:fmt.HEADER_SIZE]
        self.item_count = cursor.read('H')
        self.image_count = cursor.read('H')
        self.reference_offset = cursor.read('Q')
        self.application_version = _optional_string(blob, 24)
        self.stored_checksum = _optional_string(blob, 40)
        self.canvas = tuple(Cursor(blob, 112).read('4d'))
        self.zoom = Cursor(blob, 144).read('d')
        self.view_x, self.view_y = Cursor(blob, 216).read('2i')
        if not fmt.HEADER_SIZE <= self.reference_offset <= len(blob):
            raise FormatError('Reference table offset outside the file')


def _optional_string(blob: bytes, offset: int) -> str | None:
    text = Cursor(blob, offset).read_string()
    return (text or '').rstrip('\0') or None


def _read_image_section(blob: bytes, header: _Header) -> tuple[list[dict], int]:
    """Return the image section's entries and the offset where items start.

    The entries are the embedded PNGs and the four-byte instance slots between
    them, each with its absolute address range, because the reference table at the
    end of the file points at those ranges.
    """
    slots: list[dict] = []
    pos = fmt.HEADER_SIZE
    while pos < header.reference_offset:
        start = blob.find(fmt.PNG_HEAD, pos, header.reference_offset)
        limit = start if start != -1 else header.reference_offset
        while pos < limit:
            # Anything before the next PNG is a four-byte slot: either a link
            # marker or the id of the instance that owns the image data.
            if _looks_like_item(blob, pos, header):
                return slots, pos
            slots.append({'start': pos, 'end': pos + 4, 'ref': blob[pos:pos + 4]})
            pos += 4
        if start == -1:
            return slots, pos
        end = blob.find(fmt.PNG_FOOT, start, header.reference_offset)
        if end == -1:
            raise FormatError('Embedded PNG without an IEND chunk')
        end += len(fmt.PNG_FOOT)
        slots.append({'start': start, 'end': end, 'data': blob[start:end]})
        pos = end
    return slots, pos


def _looks_like_item(blob: bytes, pos: int, header: _Header) -> bool:
    cursor = Cursor(blob, pos)
    try:
        end = cursor.read('Q')
        marker = cursor.read('I')
    except FormatError:
        return False
    return marker in fmt.ITEM_MARKERS and pos < end <= header.reference_offset


def _read_items(blob: bytes, header: _Header, start: int) -> dict:
    """Read the item blocks in file order, then the trailing folder string."""
    cursor = Cursor(blob, start)
    roots: list[Item] = []
    images: list[tuple[int, ImageItem]] = []
    ids: dict[int, Item] = {}
    while cursor.pos < header.reference_offset and _looks_like_item(blob, cursor.pos, header):
        if cursor.peek('I', 8) == fmt.IMAGE_ITEM_MARKER:
            item_id, item = _read_image_item(cursor, ids)
            images.append((item_id, item))
        else:
            item_id, item = _read_text_item(cursor, ids)
        ids[item_id] = item
        roots.append(item)
    folder = cursor.read_string() if cursor.pos < header.reference_offset else None
    return {'roots': roots, 'images': images, 'ids': ids, 'folder': folder}


def _read_block(cursor: Cursor) -> tuple[int, str]:
    """Read an item block's envelope: its end offset and class name."""
    end = cursor.read('Q')
    length = cursor.read('I')
    return end, cursor.take(length).decode('utf-16-be')


def _read_matrix(cursor: Cursor) -> tuple[Transform, tuple[float, float]]:
    m11, m12, m13, m21, m22, m23 = cursor.read('6d')
    return Transform(m11, m12, m21, m22), (m13, m23)


def _read_image_item(cursor: Cursor, ids) -> tuple[int, ImageItem]:
    end, _ = _read_block(cursor)
    extras: dict = {}
    brute_force = cursor.peek('I') == 0
    if brute_force:
        cursor.skip(4)
        extras['source'] = fmt.BRUTE_FORCE_SOURCE
    if cursor.peek('i') == -1:
        cursor.skip(4)
        extras.setdefault('source', None)
    else:
        extras['source'] = cursor.read_string()
    name = None
    if not brute_force:
        if cursor.peek('i') == -1:
            cursor.skip(4)
        else:
            name = cursor.read_string()
    extras['brute_force'] = brute_force
    # Per-item opacity, which PureRef keeps as a float internally, so a value
    # read back from the application is single-precision.
    opacity = cursor.read('d')
    transform, perspective = _read_matrix(cursor)
    transform.dx, transform.dy = cursor.read('2d')
    extras['perspective'] = perspective
    extras['trailing_one'] = cursor.read('d')
    item_id = cursor.read('I')
    z = cursor.read('d')
    before_crop, before_crop_perspective = _read_matrix(cursor)
    extras['matrix_before_crop'] = before_crop
    extras['matrix_before_crop_perspective'] = before_crop_perspective
    extras['crop_offset'] = cursor.read('2d')
    extras['crop_scale'] = cursor.read('d')
    bounds = _read_crop_path(cursor)
    tail = cursor.take(fmt.IMAGE_TAIL_SIZE)
    extras['tail'] = tail
    child_count = int.from_bytes(tail[21:25], 'big')
    if cursor.pos != end:
        extras['unparsed'] = cursor.take(end - cursor.pos)
    item = ImageItem(name=name, transform=transform, z=z, opacity=opacity,
                     bounds=bounds, resource=_placeholder(), extras={'v1': extras})
    _read_children(cursor, item, child_count, ids)
    return item_id, item


def _read_crop_path(cursor: Cursor) -> Path:
    """The crop outline: a point count, then a flag and a point per entry."""
    count = cursor.read('I')
    if count > cursor.remaining // 20:
        raise FormatError('Implausible crop point count')
    elements = []
    for _ in range(count):
        kind = cursor.read('I')
        x, y = cursor.read('2d')
        elements.append((kind, x, y))
    return Path(elements)


def _read_text_item(cursor: Cursor, ids) -> tuple[int, NoteItem]:
    end, _ = _read_block(cursor)
    extras: dict = {}
    text = cursor.read_string() or ''
    transform, perspective = _read_matrix(cursor)
    transform.dx, transform.dy = cursor.read('2d')
    extras['perspective'] = perspective
    extras['trailing_one'] = cursor.read('d')
    item_id = cursor.read('I')
    z = cursor.read('d')
    extras['foreground'] = _read_color(cursor)
    extras['color_gap'] = cursor.take(2)
    extras['background'] = _read_color(cursor)
    tail = cursor.take(fmt.TEXT_TAIL_SIZE)
    extras['tail'] = tail
    child_count = int.from_bytes(tail[2:6], 'big')
    if cursor.pos != end:
        extras['unparsed'] = cursor.take(end - cursor.pos)
    item = NoteItem(transform=transform, z=z, text=text,
                    text_color=fmt.color_to_argb(*extras['foreground']['color']),
                    background_color=fmt.color_to_argb(*extras['background']['color']),
                    extras={'v1': extras})
    _read_children(cursor, item, child_count, ids)
    return item_id, item


def _read_color(cursor: Cursor) -> dict:
    is_hsv = cursor.read('b') == 2
    opacity = cursor.read('H')
    channels = list(cursor.read('3H'))
    if is_hsv:
        channels = fmt.hsv_to_rgb16(channels)
    return {'hsv': is_hsv, 'color': (opacity, channels)}


def _read_children(cursor: Cursor, parent: Item, count: int, ids) -> None:
    for _ in range(count):
        child_id, child = _read_text_item(cursor, ids)
        ids[child_id] = child
        parent.children.append(child)


def _read_references(blob: bytes, header: _Header) -> dict[int, tuple[int, int]]:
    cursor = Cursor(blob, header.reference_offset)
    references = {}
    while cursor.remaining >= fmt.REFERENCE_SIZE:
        item_id = cursor.read('I')
        references[item_id] = cursor.read('2Q')
    return references


def _placeholder() -> Resource:
    """Stand-in until the reference table says which image an instance uses."""
    return Resource(1, 1, b'', 'PNG')


def _assemble(blob, header: _Header, slots, parsed, references) -> Scene:
    by_start = {slot['start']: slot for slot in slots}
    owners: dict[int, Resource] = {}
    instances: list[tuple[int, ImageItem, dict]] = []
    for item_id, item in parsed['images']:
        start = references.get(item_id, (None, None))[0]
        slot = by_start.get(start)
        if slot is None:
            raise FormatError(f'Image item {item_id} has no usable reference')
        instances.append((item_id, item, slot))
        if 'data' in slot:
            owners[item_id] = _resource_for(slot['data'], item)
        elif slot['ref'] == fmt.LINK_SLOT:
            owners[item_id] = _resource_for(None, item)
    for item_id, item, slot in instances:
        resource = owners.get(item_id)
        if resource is None:
            owner_id = int.from_bytes(slot['ref'], 'big')
            if owner_id not in owners:
                raise FormatError(f'Instance {item_id} points at unknown item {owner_id}')
            resource = owners[owner_id]
        item.resource = resource
        item.pixel_transform = Transform.translate(-resource.width / 2, -resource.height / 2)
        # Where the image data or instance slot sat, which the 1.x reference table
        # points at and the deprecated purformat shim exposes.
        item.extras['v1']['address'] = (slot['start'], slot['end'])
        item.extras['v1']['id'] = item_id
    scene = Scene(items=parsed['roots'], canvas=header.canvas,
                  view=View(header.zoom, header.view_x, header.view_y),
                  source_version=VERSION_1)
    scene.extras['v1'] = {
        'header_bytes': header.bytes,
        'application_version': header.application_version,
        'checksum': header.stored_checksum,
        'checksum_valid': header.stored_checksum == fmt.checksum(blob),
        'folder': parsed['folder'],
    }
    return scene


def _resource_for(data: bytes | None, item: ImageItem) -> Resource:
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
    source = item.extras['v1'].get('source') or ''
    if source == fmt.BRUTE_FORCE_SOURCE:
        source = ''
    return Resource(width, height, data, image_format,
                    source or ('missing' if data is None else ''))
