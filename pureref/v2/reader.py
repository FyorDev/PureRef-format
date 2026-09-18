"""Turn a 2.0 / 2.1 document into a `Scene`.

An item's kind comes from which subtype table holds its id, not from a column in
`items`. Two rules keep a file readable when it contains something new:

* a cell whose serialized type is not understood becomes an `Unparsed` value,
  recorded as a problem and written back verbatim — a future PureRef adding a
  type must not make a file with perfectly good images unopenable;
* columns and tables this package does not model are kept on the scene so that
  nothing is silently lost between reading and inspecting.
"""
from __future__ import annotations

from ..model import (DrawItem, GroupItem, ImageItem, Item, NoteItem, Playback,
                     Resource, Scene, Transform, View)
from ..problems import Problem
from ..qt import Path
from . import schema, values
from .document import Document

NOTE_STYLE_NAMES = {0: 'comfortable', 1: 'compact'}


def read(data: bytes) -> Scene:
    with Document.open(data) as document:
        return build_scene(document)


def build_scene(document: Document) -> Scene:
    return _Builder(document).build()


class _Builder:
    """Collects problems while it interprets, instead of raising on the first."""

    def __init__(self, document: Document):
        self.document = document
        self.problems: list[Problem] = []

    # --- helpers --------------------------------------------------------------

    def value(self, cell, reader, where: str, column: str):
        """Decode one cell, or keep it verbatim and note why."""
        if cell is None:
            return None, None
        decoded, complaint = values.decode(cell, reader)
        if complaint is not None:
            self.problems.append(Problem('unparsed-value', complaint,
                                         f'{where}.{column}'))
        return decoded, complaint

    def extra_columns(self, row, table: str) -> dict:
        known = set(schema.columns(table))
        return {name: value for name, value in row.items() if name not in known}

    # --- the build ------------------------------------------------------------

    def build(self) -> Scene:
        tables = set(self.document.tables())
        rows = {name: self.document.rows(name)
                for name in schema.TABLES if name in tables}
        resources = self._resources(rows.get('images', []))
        subtypes = {name: {row['id']: row for row in rows.get(name, [])}
                    for name in schema.ITEM_TABLES}
        items: dict[int, Item] = {}
        parents: dict[int, int | None] = {}
        for row in rows.get('items', []):
            item_id = row['id']
            items[item_id] = self._item(row, subtypes, resources)
            parent = row.get('parent')
            parents[item_id] = None if parent is None or parent < 0 else parent
        scene = Scene(items=_assemble_tree(items, parents),
                      source_version=self.document.envelope.format_version)
        metadata = (rows.get('metadata') or [{}])[0]
        self._apply_metadata(scene, metadata)
        scene.problems = self.problems
        scene.extras['v2'] = {
            'envelope': self.document.envelope,
            'metadata': metadata,
            'unknown_tables': self.document.unknown_tables(),
            'user_version': self.document.user_version(),
            'integrity': self.document.integrity(),
        }
        return scene

    def _resources(self, image_rows) -> dict[int, Resource]:
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

    def _item(self, row, subtypes, resources) -> Item:
        item_id = row['id']
        where = f'item {item_id}'
        unparsed: dict[str, object] = {}
        transform, complaint = self.value(row.get('transform'), values.read_transform,
                                          where, 'transform')
        if complaint:
            unparsed['transform'] = transform
        order, complaint = self.value(row.get('sort_order'), values.read_order,
                                      where, 'sort_order')
        if complaint:
            unparsed['sort_order'] = order
            order = None
        common = dict(
            name=row.get('name'),
            transform=transform if isinstance(transform, Transform) else Transform(),
            z=row.get('z'),
            order=order,
            opacity=1.0 if row.get('opacity') is None else float(row['opacity']),
            locked=bool(row.get('locked')),
            # Declared INTEGER but holding the comment text; SQLite's integer
            # affinity turns a numeric-looking comment into a number, so anything
            # that comes back is rendered as text again.
            comment=None if row.get('comment') is None else str(row['comment']),
            extras={'v2': {'id': item_id, 'row': self.extra_columns(row, 'items'),
                           'unparsed': unparsed}})
        if item_id in subtypes['items_images']:
            return self._image(subtypes['items_images'][item_id], resources, common, where)
        if item_id in subtypes['items_notes']:
            return self._note(subtypes['items_notes'][item_id], common, where)
        if item_id in subtypes['items_groups']:
            return self._group(subtypes['items_groups'][item_id], common)
        if item_id in subtypes['items_drawings']:
            return self._drawing(subtypes['items_drawings'][item_id], common, where)
        # An item with no subtype row renders as nothing; keep it so that saving
        # does not quietly delete it.
        common['extras']['v2']['orphan'] = True
        self.problems.append(Problem('orphan-item', 'no subtype row', where))
        return Item(**common)

    def _image(self, row, resources, common, where) -> ImageItem:
        unparsed = common['extras']['v2']['unparsed']
        resource = resources.get(row.get('image'))
        if resource is None:
            self.problems.append(Problem(
                'missing-image', f'references image {row.get("image")!r}', where))
            resource = Resource(1, 1, b'', 'PNG')
        common['extras']['v2']['image_row'] = self.extra_columns(row, 'items_images')
        pixel, complaint = self.value(row.get('image_transform'), values.read_transform,
                                      where, 'image_transform')
        if complaint:
            unparsed['image_transform'] = pixel
            pixel = None
        bounds, complaint = self.value(row.get('image_bounds'), values.read_bounds,
                                       where, 'image_bounds')
        if complaint:
            unparsed['image_bounds'] = bounds
            bounds = None
        return ImageItem(
            resource=resource,
            pixel_transform=pixel if isinstance(pixel, Transform) else None,
            bounds=bounds if isinstance(bounds, Path) else None,
            flags=int(row.get('flags') or 0),
            playback=Playback(int(row.get('playback_state') or 0),
                              int(row.get('playback_frame') or 0),
                              float(row.get('playback_speed') or 1.0)),
            **common)

    def _note(self, row, common, where) -> NoteItem:
        style = row.get('style') or 0
        extras = common['extras']['v2']
        extras['note_style'] = style
        extras['note_row'] = self.extra_columns(row, 'items_notes')
        size, complaint = self.value(row.get('fixed_size'), values.read_size,
                                     where, 'fixed_size')
        if complaint:
            extras['unparsed']['fixed_size'] = size
            size = None
        return NoteItem(
            html=row.get('text'),
            text=_plain_text(row.get('text') or ''),
            text_color=row.get('text_color'),
            background_color=row.get('background_color'),
            fixed_size=size if isinstance(size, tuple) else (-1.0, -1.0),
            style=NOTE_STYLE_NAMES.get(style, 'compact'),
            **common)

    def _group(self, row, common) -> GroupItem:
        common['extras']['v2']['group_row'] = self.extra_columns(row, 'items_groups')
        return GroupItem(background_color=row.get('background_color'),
                         lock_mode=int(row.get('lock_mode') or 0), **common)

    def _drawing(self, row, common, where) -> DrawItem:
        common['extras']['v2']['drawing_row'] = self.extra_columns(row, 'items_drawings')
        strokes, complaint = self.value(row.get('strokes'), values.read_strokes,
                                        where, 'strokes')
        if complaint:
            common['extras']['v2']['unparsed']['strokes'] = strokes
            strokes = []
        return DrawItem(strokes=strokes or [], **common)

    def _apply_metadata(self, scene: Scene, metadata) -> None:
        rectangle, complaint = self.value(metadata.get('scene_rect'), values.read_rect,
                                          'metadata', 'scene_rect')
        if isinstance(rectangle, tuple) and not complaint:
            x, y, width, height = rectangle
            scene.canvas = (x, y, x + width, y + height)
        view, complaint = self.value(metadata.get('view_transform'),
                                     values.read_transform, 'metadata', 'view_transform')
        zoom = view.m11 if isinstance(view, Transform) and not complaint else 1.0
        scene.view = View(zoom=zoom,
                          x=int(metadata.get('horizontal_scroll') or 0),
                          y=int(metadata.get('vertical_scroll') or 0))


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


def _plain_text(html: str) -> str:
    """A best-effort plain-text version of a note, for 1.x and for summaries."""
    import re
    from html import unescape
    without_head = re.sub(r'(?is)<(head|style|script).*?</\1>', '', html)
    blocks = re.sub(r'(?i)<(br|/p|/div|/li)\s*/?>', '\n', without_head)
    return unescape(re.sub(r'(?s)<[^>]*>', '', blocks)).strip()
