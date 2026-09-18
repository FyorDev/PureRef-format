"""Arrange images into a tidy rectangle.

This is the placement from the original PureRef-format generator, kept because
it is the whole point of the tool: normalize every image to the same height,
split the strip into rows until the result is roughly square, then scale each row
to the same width so the edges line up exactly.
"""
from __future__ import annotations

import re

from .items import ImageItem


def natural_key(text: str):
    """Sort '2.jpg' before '10.jpg'."""
    return [int(part) if part.isdigit() else part.lower()
            for part in re.split(r'(\d+)', str(text))]


def pack_rows(items: list[ImageItem], *, target_width: float = 1000.0,
              row_height: float = 1000.0, spacing: float = 0.0,
              origin: tuple[float, float] = (0.0, 0.0)) -> None:
    """Place `items` in rows, in place, in the order given."""
    images = [item for item in items if isinstance(item, ImageItem)]
    if not images:
        return
    for item in images:
        item.scale_to_height(row_height)
    _place(_rows(images, row_height), target_width, row_height, spacing, origin)


def _rows(images: list[ImageItem], row_height: float):
    """Halve the strip of images until it is no longer much wider than tall."""
    total_width = sum(item.size[0] for item in images)
    rows = [images]
    while len(rows) * 2 * row_height < total_width:
        total_width /= 2.0
        halved = []
        for row in rows:
            cut, remaining = 0, total_width
            while cut < len(row) and remaining > 0:
                remaining -= row[cut].size[0]
                cut += 1
            halved.append(row[:cut])
            halved.append(row[cut:])
        rows = halved
    return [row for row in rows if row]


def _place(rows, target_width: float, row_height: float, spacing: float,
           origin: tuple[float, float]) -> None:
    x_origin, y_origin = origin
    y = y_origin
    for row in rows:
        row_width = sum(item.size[0] for item in row)
        if not row_width:
            continue
        factor = (target_width - spacing * (len(row) - 1)) / row_width
        x = x_origin
        for item in row:
            item.scale(factor)
            width, height = item.size
            item.x = x + width / 2
            item.y = y + height / 2
            x += width + spacing
        y += row_height * factor + spacing
