"""Which column holds which serialized value, and how it is read and written.

A handful of 2.x columns hold a QDataStream QVariant rather than a plain SQLite
value. Every one of them is declared here once, with both directions, so a column
cannot be decoded one way and encoded another -- the mistake that is otherwise
invisible until a file loads with the wrong geometry. `values.py` is where those
encodings live; this is the map from column to encoding.

`reader.py` looks a column up by name; `writer.py` encodes through the same entry
unless the reader kept the cell verbatim because it could not be understood.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from . import values
from .values import big_rational_cell, path_cell, rect_cell, size_cell, transform_cell


# --- the map ------------------------------------------------------------------


@dataclass(frozen=True)
class Cell:
    """One serialized column: `read` a cell into a value, `write` it back."""

    read: Callable
    write: Callable
    doc: str = ''        # the serialized type, for the generated column tables


CELLS: dict[str, dict[str, Cell]] = {
    'items': {
        'transform': Cell(values.read_transform,
                          lambda transform: transform_cell(transform.to_matrix9()),
                          'QTransform'),
        'sort_order': Cell(values.read_order, big_rational_cell,
                           'BigRational'),
    },
    'items_images': {
        'image_transform': Cell(values.read_transform,
                                lambda transform: transform_cell(transform.to_matrix9()),
                                'QTransform'),
        'image_bounds': Cell(values.read_bounds, path_cell,
                             'QPainterPath'),
    },
    'items_notes': {
        'fixed_size': Cell(values.read_size, lambda size: size_cell(*size),
                           'QSizeF'),
    },
    'items_drawings': {
        'strokes': Cell(values.read_strokes, values.strokes_cell,
                        'QList<GraphicsDrawItem::Stroke>'),
    },
    'metadata': {
        'scene_rect': Cell(values.read_rect, lambda rect: rect_cell(*rect),
                           'QRectF'),
        'view_transform': Cell(values.read_transform,
                               lambda transform: transform_cell(transform.to_matrix9()),
                               'QTransform'),
    },
}


def cell_for(table: str, column: str) -> Cell:
    try:
        return CELLS[table][column]
    except KeyError:
        raise KeyError(f'{table}.{column} is not a serialized column') from None


def reader_for(table: str, column: str) -> Callable:
    return cell_for(table, column).read


def encode(table: str, column: str, value):
    """Serialize `value` the way that column stores it."""
    return cell_for(table, column).write(value)
