"""Read a PureRef 2.0 / 2.1 file into a `Scene`.

An item's kind comes from which subtype table holds its id, not from a column in
`items`. Rows are read whole so that columns this package does not model — and
any column a future PureRef adds — survive in `extras` for a later save.
"""
from __future__ import annotations

from ..model import (DrawItem, GroupItem, ImageItem, Item, NoteItem, Playback,
                     Resource, Scene, Transform, View)
from ..qt import FormatError
from . import schema, values
from .database import Database
from .envelope import unwrap

NOTE_STYLE_NAMES = {0: 'comfortable', 1: 'compact'}


def read(data: bytes) -> Scene:
    envelope, database = unwrap(data)
    with Database(database, read_only=True) as db:
        return _build(envelope, db)


def _build(envelope, db: Database) -> Scene:
    tables = set(db.table_names())
    unknown_tables = sorted(tables - set(schema.TABLES))
    rows = {name: db.rows(name) for name in schema.TABLES if name in tables}
    resources = _resources(rows.get('images', []))
    subtypes = {name: {row['id']: row for row in rows.get(name, [])}
                for name in schema.ITEM_TABLES}
    items: dict[int, Item] = {}
    parents: dict[int, int | None] = {}
    for row in rows.get('items', []):
        item_id = row['id']
        items[item_id] = _item(row, subtypes, resources)
        parent = row.get('parent')
        parents[item_id] = None if parent is None or parent < 0 else parent
    roots = _assemble_tree(items, parents)
    metadata = (rows.get('metadata') or [{}])[0]
    scene = Scene(items=roots, source_version=envelope.format_version)
    _apply_metadata(scene, metadata)
    scene.extras['v2'] = {
        'envelope': envelope,
        'metadata': metadata,
        'unknown_tables': unknown_tables,
        'user_version': db.pragma('user_version'),
        'integrity': db.integrity(),
    }
    return scene


def _resources(image_rows) -> dict[int, Resource]:
    resources = {}
    for row in image_rows:
        data = row.get('data')
        resources[row['id']] = Resource(
            width=max(1, int(row.get('width') or 1)),
            height=max(1, int(row.get('height') or 1)),
            data=bytes(data) if data is not None else None,
            format=row.get('format') or 'PNG',
            source=row.get('source') or '',
            origin=row.get('origin'),
            checksum=row.get('checksum'))
    return resources


def _item(row, subtypes, resources) -> Item:
    common = dict(
        name=row.get('name'),
        transform=_transform(row.get('transform')),
        z=row.get('z'),
        order=_order(row.get('sort_order')),
        opacity=1.0 if row.get('opacity') is None else float(row['opacity']),
        locked=bool(row.get('locked')),
        extras={'v2': {'id': row['id'], 'comment': row.get('comment'),
                       'row': _extra_columns(row, 'items')}})
    item_id = row['id']
    if item_id in subtypes['items_images']:
        return _image_item(subtypes['items_images'][item_id], resources, common)
    if item_id in subtypes['items_notes']:
        return _note_item(subtypes['items_notes'][item_id], common)
    if item_id in subtypes['items_groups']:
        return _group_item(subtypes['items_groups'][item_id], common)
    if item_id in subtypes['items_drawings']:
        return _draw_item(subtypes['items_drawings'][item_id], common)
    # An item with no subtype row renders as nothing; keep it as a bare item so a
    # save does not quietly delete it.
    common['extras']['v2']['orphan'] = True
    return Item(**common)


def _image_item(row, resources, common) -> ImageItem:
    resource = resources.get(row.get('image'))
    if resource is None:
        raise FormatError(f'Image item {row["id"]} references missing image '
                          f'{row.get("image")!r}')
    common['extras']['v2']['image_row'] = _extra_columns(row, 'items_images')
    return ImageItem(
        resource=resource,
        pixel_transform=_transform(row.get('image_transform')),
        bounds=values.read_bounds(row['image_bounds']) if row.get('image_bounds') else None,
        flags=int(row.get('flags') or 0),
        playback=Playback(int(row.get('playback_state') or 0),
                          int(row.get('playback_frame') or 0),
                          float(row.get('playback_speed') or 1.0)),
        **common)


def _note_item(row, common) -> NoteItem:
    style = row.get('style') or 0
    extras = common['extras']['v2']
    extras['note_style'] = style
    extras['note_row'] = _extra_columns(row, 'items_notes')
    return NoteItem(
        html=row.get('text'),
        text=_plain_text(row.get('text') or ''),
        text_color=row.get('text_color'),
        background_color=row.get('background_color'),
        fixed_size=values.read_size(row['fixed_size']) if row.get('fixed_size') else (-1.0, -1.0),
        style=NOTE_STYLE_NAMES.get(style, 'compact'),
        **common)


def _group_item(row, common) -> GroupItem:
    common['extras']['v2']['group_row'] = _extra_columns(row, 'items_groups')
    return GroupItem(background_color=row.get('background_color'),
                     lock_mode=int(row.get('lock_mode') or 0), **common)


def _draw_item(row, common) -> DrawItem:
    common['extras']['v2']['drawing_row'] = _extra_columns(row, 'items_drawings')
    strokes = values.read_strokes(row['strokes']) if row.get('strokes') else []
    return DrawItem(strokes=strokes, **common)


def _extra_columns(row, table: str) -> dict:
    """Columns this package does not model, so they can be written back."""
    known = set(schema.columns(table))
    return {name: value for name, value in row.items() if name not in known}


def _transform(cell) -> Transform:
    return values.read_transform(cell) if cell else Transform()


def _order(cell):
    return values.read_order(cell) if cell else None


def _assemble_tree(items: dict[int, Item], parents) -> list[Item]:
    roots = []
    for item_id, item in items.items():
        parent_id = parents.get(item_id)
        if parent_id is None or parent_id not in items or _loops(item_id, parents):
            roots.append(item)
        else:
            items[parent_id].children.append(item)
    _sort_siblings(roots)
    for item in items.values():
        _sort_siblings(item.children)
    return roots


def _loops(item_id: int, parents) -> bool:
    """A parent chain that comes back around would make an endless tree."""
    seen = {item_id}
    current = parents.get(item_id)
    while current is not None:
        if current in seen:
            return True
        seen.add(current)
        current = parents.get(current)
    return False


def _sort_siblings(siblings: list[Item]) -> None:
    """PureRef orders siblings by sort_order, comparing rationals."""
    siblings.sort(key=lambda item: (item.order is None, item.order or 0,
                                    item.extras.get('v2', {}).get('id', 0)))


def _apply_metadata(scene: Scene, metadata) -> None:
    if metadata.get('scene_rect'):
        x, y, width, height = values.read_rect(metadata['scene_rect'])
        scene.canvas = (x, y, x + width, y + height)
    zoom = 1.0
    if metadata.get('view_transform'):
        zoom = values.read_transform(metadata['view_transform']).m11
    scene.view = View(zoom=zoom,
                      x=int(metadata.get('horizontal_scroll') or 0),
                      y=int(metadata.get('vertical_scroll') or 0))


def _plain_text(html: str) -> str:
    """A best-effort plain-text version of a note, for 1.x and for summaries."""
    import re
    from html import unescape
    without_head = re.sub(r'(?is)<(head|style|script).*?</\1>', '', html)
    blocks = re.sub(r'(?i)<(br|/p|/div|/li)\s*/?>', '\n', without_head)
    return unescape(re.sub(r'(?s)<[^>]*>', '', blocks)).strip()
