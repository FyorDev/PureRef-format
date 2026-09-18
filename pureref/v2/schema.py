"""The 2.x SQLite schema, and what PureRef expects of it.

PureRef reads and migrates its database by column *name* (`PRAGMA table_info`,
`ALTER TABLE ... ADD COLUMN`), which has three consequences for a writer:

* column order is free — 2.0.3 and 2.1.3 declare the same columns in different
  orders and load each other's files;
* extra columns and tables load with a warning and are dropped on the next save;
* missing columns are fatal, so the full column set below must be present.

`PRAGMA user_version` is the compatibility gate: a lower value is migrated
silently, a higher one makes PureRef refuse the file as "from a newer version".
"""
from __future__ import annotations

PAGE_SIZE = 4096
AUTO_VACUUM = 1           # FULL
APPLICATION_ID = 940753918  # 0x3812c3fe
USER_VERSION = 200101

PRAGMAS = (
    f'PRAGMA page_size={PAGE_SIZE}',
    f'PRAGMA auto_vacuum={AUTO_VACUUM}',
    f'PRAGMA application_id={APPLICATION_ID}',
    f'PRAGMA user_version={USER_VERSION}',
    "PRAGMA encoding='UTF-8'",
)

# Declared in the order PureRef 2.1.3 emits, purely for familiarity.
TABLES = {
    'images': (
        'id INTEGER PRIMARY KEY', 'source_type INTEGER', 'origin TEXT', 'source TEXT',
        'format TEXT', 'checksum TEXT', 'data BLOB', 'width INTEGER', 'height INTEGER'),
    'metadata': (
        'id INTEGER PRIMARY KEY', 'scene_rect TEXT', 'application_version TEXT',
        'view_transform TEXT', 'thumbnail BLOB', 'horizontal_scroll INTEGER',
        'vertical_scroll INTEGER', 'last_save_path TEXT', 'last_load_path TEXT',
        'last_load_checksum TEXT', 'saved INTEGER'),
    'items': (
        'parent INTEGER', 'id INTEGER PRIMARY KEY', 'name TEXT', 'transform BLOB',
        'sort_order BLOB', 'z REAL', 'opacity REAL', 'locked INTEGER',
        'comment INTEGER'),
    'items_images': (
        'image INTEGER', 'playback_speed REAL', 'id INTEGER PRIMARY KEY',
        'playback_state INTEGER', 'image_transform BLOB', 'image_bounds BLOB',
        'playback_frame INTEGER', 'flags INTEGER'),
    'items_drawings': ('id INTEGER PRIMARY KEY', 'strokes BLOB'),
    'items_notes': (
        'text_color TEXT', 'id INTEGER PRIMARY KEY', 'fixed_size TEXT',
        'background_color TEXT', 'text TEXT', 'style INTEGER'),
    'items_groups': (
        'id INTEGER PRIMARY KEY', 'background_color TEXT', 'lock_mode INTEGER'),
}

ITEM_TABLES = ('items_images', 'items_notes', 'items_groups', 'items_drawings')

# What each column holds. This is the only description of the columns in the
# package: docs/format-v2.md is generated from it, and a test fails when a
# column is added without one, so the schema cannot grow a silent field.
NOTES = {
    'images': {
        'id': 'resource id, referenced by items_images.image',
        'source_type': '1 embedded, 2 linked; there is no third value',
        'origin': 'where the image originally came from, a path or a URL',
        'source': 'the path a linked image is loaded from, rewritten when it is found again',
        'format': 'not normalised: the lowercase file extension when imported from a path, the uppercase detected format otherwise',
        'checksum': 'MD5 of the embedded bytes, the deduplication key; NULL when linked',
        'data': 'the image bytes; NULL when linked',
        'width': 'pixel width, of the stored bytes -- a downscaled import stores the smaller size',
        'height': 'pixel height, likewise',
    },
    'metadata': {
        'id': 'always 0: the table holds one row',
        'scene_rect': 'the content rectangle, unioned with the origin',
        'application_version': 'the PureRef that saved the file, matching the envelope',
        'view_transform': 'the view onto the scene; its scale is the zoom',
        'horizontal_scroll': 'the pan, in view coordinates',
        'vertical_scroll': 'the pan, likewise',
        'thumbnail': 'the preview image, duplicated here and in the 2.1 envelope',
        'last_save_path': 'the directory of the last save, which seeds the save dialog',
        'last_load_path': 'the path the scene is associated with; after a save, that file',
        'last_load_checksum': 'the header checksum of the file the scene was loaded from',
        'saved': '0 when the scene had never been associated with a .pur before this save',
    },
    'items': {
        'id': 'object id; which subtype table holds it decides what kind of item it is',
        'parent': 'the parent object id, -1 for a root',
        'name': 'display name, nullable',
        'transform': 'the item placement, relative to its parent',
        'sort_order': 'sibling order, renumbered to 1..n on every save',
        'z': 'stacking, renumbered likewise',
        'opacity': 'alpha multiplier',
        'locked': 'lock flag',
        'comment': 'the comment text, despite the INTEGER declaration; shown in the tooltip',
    },
    'items_images': {
        'id': 'the item id this row describes',
        'image': 'which images row supplies the pixels; several items can share one',
        'image_transform': 'maps image pixels into item coordinates, translating by (-w/2, -h/2), which is why an image item is positioned at its centre',
        'image_bounds': 'the visible outline in centred pixel coordinates: a closed rectangle unless cropped',
        'flags': 'bit 0x1 bilinear sampling, bit 0x2 the grayscale filter; nothing else is read',
        'playback_state': '0 still, 2 paused at playback_frame, 3 playing',
        'playback_frame': 'the frame a paused animation shows',
        'playback_speed': 'playback multiplier; a float widened into a REAL',
    },
    'items_notes': {
        'id': 'the item id this row describes',
        'text': 'Qt rich text, not plain text',
        'text_color': 'the default colour, used when the HTML carries none',
        'background_color': '#AARRGGBB or #RRGGBB, empty for the default',
        'fixed_size': '(-1, -1) means the note sizes itself to its text',
        'style': '0 Comfortable, 1 Compact; other values render like Compact',
    },
    'items_groups': {
        'id': 'the item id this row describes',
        'background_color': '#AARRGGBB; the geometry comes from the children',
        'lock_mode': 'GraphicsGroupItem::LockMode: 0 Open, 1 Closed',
    },
    'items_drawings': {
        'id': 'the item id this row describes',
        'strokes': 'the whole drawing, in one cell',
    },
}


def note(table: str, column: str) -> str:
    return NOTES.get(table, {}).get(column, '')


def declaration(table: str, column: str) -> str:
    """The column as it is declared, e.g. `data BLOB`."""
    for entry in TABLES[table]:
        if entry.split()[0] == column:
            return entry
    raise KeyError(f'{table}.{column}')


SCHEMA = '\n'.join(f'CREATE TABLE {name} ({",".join(columns)});'
                   for name, columns in TABLES.items())


def columns(table: str) -> tuple[str, ...]:
    return tuple(column.split()[0] for column in TABLES[table])


def create(connection) -> None:
    connection.executescript(SCHEMA)


def missing_columns(connection) -> dict[str, list[str]]:
    """Columns PureRef needs that this database does not have."""
    gaps = {}
    for table in TABLES:
        rows = connection.execute(f'PRAGMA table_info({table})').fetchall()
        present = {row[1] for row in rows}
        if not present:
            gaps[table] = list(columns(table))
            continue
        absent = [name for name in columns(table) if name not in present]
        if absent:
            gaps[table] = absent
    return gaps
