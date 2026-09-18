"""Turn a 2.0 / 2.1 document into a `Scene`.

An item's kind comes from which subtype table holds its id, not from a column in
`items`. Two rules keep a file readable when it contains something new:

* a cell whose serialized type is not understood becomes an `Unparsed` value,
  recorded as a problem and written back verbatim — a future PureRef adding a
  type must not make a file with perfectly good images unopenable;
* columns and tables this package does not model are kept on `Item.v2` and
  `Scene.v2` so that nothing is silently lost between reading and inspecting.
"""
from __future__ import annotations

from typing import Any

from ..model import (DrawItem, GroupItem, ImageItem, Item, NoteItem, Playback,
                     Resource, Scene, Transform, V2File, V2Item, View)
from ..problems import Problem
from ..qt import FormatError, Path
from . import cells, schema, values
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

    def value(self, row, table: str, column: str, where: str, carried=None):
        """Decode one serialized cell, the way `cells.py` says that column reads.

        A cell that cannot be read is kept verbatim on the carrier and noted as a
        problem, and the caller gets it back so it can fall back to a default.
        """
        cell = row.get(column)
        if cell is None:
            return None, None
        decoded, complaint = values.decode(cell, cells.reader_for(table, column))
        if complaint is not None:
            self.problems.append(Problem('unparsed-value', complaint,
                                         f'{where}.{column}'))
            if carried is not None:
                carried.unparsed[column] = decoded
        return decoded, complaint

    def number(self, value, where: str, column: str, default, *, whole=True):
        """A numeric column as a number, or the default with a problem noted.

        SQLite columns are typed by affinity, not enforced, and a damaged page
        can put a blob where an integer belongs. One nonsensical cell should cost
        that one field, not the whole file.
        """
        if value is None:
            return default
        try:
            return int(value) if whole else float(value)
        except (TypeError, ValueError):
            self.problems.append(Problem(
                'non-numeric-value', f'{value!r:.40} is not a number',
                f'{where}.{column}'))
            return default

    def text(self, value, where: str, column: str):
        """A text column as text. A damaged cell arrives as bytes instead.

        `Database` hands back the raw bytes of a TEXT cell that is not valid
        UTF-8 rather than raising from inside the cursor, so the rest of a file
        stays readable; what reaches the model is still always text.
        """
        if isinstance(value, (bytes, bytearray)):
            self.problems.append(Problem('undecodable-text', 'not valid UTF-8',
                                         f'{where}.{column}'))
            return bytes(value).decode('utf-8', 'replace')
        return value

    def extra_columns(self, row, table: str) -> dict:
        known = set(schema.columns(table))
        return {name: value for name, value in row.items() if name not in known}

    # --- the build ------------------------------------------------------------

    def build(self) -> Scene:
        tables = set(self.document.tables())
        rows = {name: self.document.rows(name)
                for name in schema.TABLES if name in tables}
        for name, table_rows in rows.items():
            # Every table in this schema is keyed by id. Without it the file is
            # not a PureRef database, whatever the table names say.
            if table_rows and 'id' not in table_rows[0]:
                raise FormatError(f'the {name} table has no id column')
        resources = self._resources(rows.get('images', []))
        subtypes = {name: {row['id']: row for row in rows.get(name, [])}
                    for name in schema.ITEM_TABLES}
        items: dict[int, Item] = {}
        parents: dict[int, int | None] = {}
        for row in rows.get('items', []):
            item_id = row['id']
            items[item_id] = self._item(row, subtypes, resources)
            parent = self.number(row.get('parent'), f'item {item_id}', 'parent', -1)
            parents[item_id] = None if parent < 0 else parent
        scene = Scene(items=_assemble_tree(items, parents),
                      source_version=self.document.envelope.format_version)
        metadata = (rows.get('metadata') or [{}])[0]
        self._apply_metadata(scene, metadata)
        scene.problems = self.problems
        scene.v2 = V2File(envelope=self.document.envelope,
                          metadata=metadata,
                          unknown_tables=self.document.unknown_tables(),
                          user_version=self.document.user_version(),
                          integrity=self.document.integrity())
        return scene

    def _resources(self, image_rows) -> dict[int, Resource]:
        resources = {}
        for row in image_rows:
            data = row.get('data')
            where = f'image {row.get("id")}'
            resources[row['id']] = Resource(
                width=max(1, self.number(row.get('width'), where, 'width', 1)),
                height=max(1, self.number(row.get('height'), where, 'height', 1)),
                data=bytes(data) if data is not None else None,
                format=self.text(row.get('format'), where, 'format') or 'PNG',
                source=self.text(row.get('source'), where, 'source') or '',
                origin=self.text(row.get('origin'), where, 'origin'),
                checksum=self.text(row.get('checksum'), where, 'checksum'))
        return resources

    def _item(self, row, subtypes, resources) -> Item:
        item_id = row['id']
        where = f'item {item_id}'
        carried = V2Item(id=item_id, columns=self.extra_columns(row, 'items'))
        transform, _ = self.value(row, 'items', 'transform', where, carried)
        order, complaint = self.value(row, 'items', 'sort_order', where, carried)
        if complaint:
            order = None
        common = dict(
            name=self.text(row.get('name'), where, 'name'),
            transform=transform if isinstance(transform, Transform) else Transform(),
            z=self.number(row.get('z'), where, 'z', None, whole=False),
            order=order,
            opacity=self.number(row.get('opacity'), where, 'opacity', 1.0,
                                whole=False),
            locked=bool(row.get('locked')),
            # Declared INTEGER but holding the comment text; SQLite's integer
            # affinity turns a numeric-looking comment into a number, so anything
            # that comes back is rendered as text again.
            comment=None if row.get('comment') is None
            else str(self.text(row['comment'], where, 'comment')),
            v2=carried)
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
        carried.orphan = True
        self.problems.append(Problem('orphan-item', 'no subtype row', where))
        return Item(**common)

    def _image(self, row, resources, common, where) -> ImageItem:
        carried = common['v2']
        resource = resources.get(row.get('image'))
        if resource is None:
            self.problems.append(Problem(
                'missing-image', f'references image {row.get("image")!r}', where))
            resource = Resource(1, 1, b'', 'PNG')
        carried.subtype_columns = self.extra_columns(row, 'items_images')
        pixel, _ = self.value(row, 'items_images', 'image_transform', where, carried)
        bounds, _ = self.value(row, 'items_images', 'image_bounds', where, carried)
        # What could not be read is left out entirely: `ImageItem` derives the
        # centring transform and the full-image outline from the resource, which
        # is the best guess available and keeps the item usable.
        geometry: dict[str, Any] = {}
        if isinstance(pixel, Transform):
            geometry['pixel_transform'] = pixel
        if isinstance(bounds, Path):
            geometry['bounds'] = bounds
        return ImageItem(
            resource=resource,
            **geometry,
            flags=self.number(row.get('flags'), where, 'flags', 0),
            playback=Playback(
                self.number(row.get('playback_state'), where, 'playback_state', 0),
                self.number(row.get('playback_frame'), where, 'playback_frame', 0),
                self.number(row.get('playback_speed'), where, 'playback_speed', 1.0,
                            whole=False) or 1.0),
            **common)

    def _note(self, row, common, where) -> NoteItem:
        style = self.number(row.get('style'), where, 'style', 0)
        carried = common['v2']
        carried.note_style = style
        carried.subtype_columns = self.extra_columns(row, 'items_notes')
        size, _ = self.value(row, 'items_notes', 'fixed_size', where, carried)
        html = self.text(row.get('text'), where, 'text')
        return NoteItem(
            html=html,
            text=_plain_text(html or ''),
            text_color=self.text(row.get('text_color'), where, 'text_color'),
            background_color=self.text(row.get('background_color'), where,
                                       'background_color'),
            fixed_size=size if isinstance(size, tuple) else (-1.0, -1.0),
            style=NOTE_STYLE_NAMES.get(style, 'compact'),
            **common)

    def _group(self, row, common) -> GroupItem:
        common['v2'].subtype_columns = self.extra_columns(row, 'items_groups')
        where = f'item {row.get("id")}'
        return GroupItem(background_color=self.text(row.get('background_color'),
                                                    where, 'background_color'),
                         lock_mode=self.number(row.get('lock_mode'), where,
                                               'lock_mode', 0), **common)

    def _drawing(self, row, common, where) -> DrawItem:
        carried = common['v2']
        carried.subtype_columns = self.extra_columns(row, 'items_drawings')
        strokes, complaint = self.value(row, 'items_drawings', 'strokes', where, carried)
        if complaint:
            strokes = []
        return DrawItem(strokes=strokes or [], **common)

    def _apply_metadata(self, scene: Scene, metadata) -> None:
        rectangle, complaint = self.value(metadata, 'metadata', 'scene_rect', 'metadata')
        if isinstance(rectangle, tuple) and not complaint:
            x, y, width, height = rectangle
            scene.canvas = (x, y, x + width, y + height)
        view, complaint = self.value(metadata, 'metadata', 'view_transform', 'metadata')
        zoom = view.m11 if isinstance(view, Transform) and not complaint else 1.0
        scene.view = View(
            zoom=zoom,
            x=self.number(metadata.get('horizontal_scroll'), 'metadata',
                          'horizontal_scroll', 0),
            y=self.number(metadata.get('vertical_scroll'), 'metadata',
                          'vertical_scroll', 0))


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
                                    getattr(item.v2, 'id', None) or 0))


def _plain_text(html: str) -> str:
    """A best-effort plain-text version of a note, for 1.x and for summaries."""
    import re
    from html import unescape
    without_head = re.sub(r'(?is)<(head|style|script).*?</\1>', '', html)
    blocks = re.sub(r'(?i)<(br|/p|/div|/li)\s*/?>', '\n', without_head)
    return unescape(re.sub(r'(?s)<[^>]*>', '', blocks)).strip()
