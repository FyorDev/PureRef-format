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
