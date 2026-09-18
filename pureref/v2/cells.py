"""Which column holds which serialized value.

Reader and writer both consult this table, so a column cannot be decoded one way
and encoded another. Filled in alongside the record work; for now it documents
the mapping that `reader.py` and `writer.py` implement.
"""
from __future__ import annotations

from . import values

# column -> the reader that interprets it. Everything else is plain SQLite.
CELLS: dict[str, dict[str, object]] = {
    'items': {'transform': values.read_transform, 'sort_order': values.read_order},
    'items_images': {'image_transform': values.read_transform,
                     'image_bounds': values.read_bounds},
    'items_notes': {'fixed_size': values.read_size},
    'items_drawings': {'strokes': values.read_strokes},
    'metadata': {'scene_rect': values.read_rect,
                 'view_transform': values.read_transform},
}


def reader_for(table: str, column: str):
    return CELLS.get(table, {}).get(column)
