"""Re-encode image data for formats that cannot carry the original bytes.

PureRef 1.x stores every embedded image as PNG: its reader looks for PNG
signatures in the stream, so a JPEG or GIF written there would not be found.
PureRef 2.x embeds the original file, so nothing has to be re-encoded.

Pillow does the re-encoding when it is installed (`pip install pureref-format
[thumbnails]`); without it, writing such a scene as 1.10 fails with an
explanation instead of producing a file PureRef cannot open.
"""
from __future__ import annotations

from .items import ImageItem
from .resources import Resource
from .qt import FormatError


def available() -> bool:
    from importlib.util import find_spec
    return find_spec('PIL') is not None


def to_png(resource: Resource) -> bytes:
    """Return `resource`'s pixels as PNG bytes, re-encoding only if needed."""
    data = resource.data
    if resource.linked or data is None:
        raise FormatError('A linked image has no data to re-encode')
    if resource.format.upper() == 'PNG':
        return data
    try:
        from io import BytesIO

        from PIL import Image
    except ImportError as error:
        raise FormatError(
            f'{resource.format} images have to be re-encoded as PNG for the 1.x '
            'format, which needs Pillow: pip install "pureref-format[thumbnails]" '
            '(or write the scene as 2.1 instead)') from error
    with Image.open(BytesIO(data)) as image:
        frame = image.convert('RGBA' if 'A' in image.getbands() else 'RGB')
        buffer = BytesIO()
        frame.save(buffer, format='PNG', compress_level=7)
        return buffer.getvalue()


def thumbnail(scene, *, size: int = 256, background=(26, 26, 26)) -> bytes:
    """Render a rough 256x256 JPEG preview of a scene's images.

    PureRef's own previews are 256x256 JPEG renders of the canvas; it regenerates
    one on its next save, so this is only a courtesy for file browsers that show
    the embedded preview. Needs Pillow. Notes and drawings are not drawn.
    """
    from io import BytesIO

    from PIL import Image
    placements = []
    for item in scene.walk():
        if isinstance(item, ImageItem) and not item.resource.linked:
            width, height = item.size
            placements.append((item, width, height))
    canvas = Image.new('RGB', (size, size), background)
    if not placements:
        buffer = BytesIO()
        canvas.save(buffer, format='JPEG', quality=80)
        return buffer.getvalue()
    left = min(item.x - width / 2 for item, width, _ in placements)
    right = max(item.x + width / 2 for item, width, _ in placements)
    top = min(item.y - height / 2 for item, _, height in placements)
    bottom = max(item.y + height / 2 for item, _, height in placements)
    span = max(right - left, bottom - top) or 1.0
    scale = size / span
    for item, width, height in placements:
        if item.resource.data is None:
            continue                          # a linked image has nothing to draw
        with Image.open(BytesIO(item.resource.data)) as source:
            box = (max(1, round(width * scale)), max(1, round(height * scale)))
            frame = source.convert('RGB').resize(box)
            x = round(((item.x - width / 2) - left) * scale)
            y = round(((item.y - height / 2) - top) * scale)
            canvas.paste(frame, (x, y))
    buffer = BytesIO()
    canvas.save(buffer, format='JPEG', quality=80)
    return buffer.getvalue()
