"""Deprecated: fills the old `PurFile` objects from the new 1.x reader.

Kept so code written against `purformat` keeps working. New code should use
`pureref.read`, which also handles the 2.x format.
"""
from pathlib import Path

from pureref import v1
from pureref.model import ImageItem, NoteItem

from .items import PurGraphicsImageItem, PurGraphicsTextItem, PurImage


def read_pur_file(pur_file, filepath: str):
    scene = v1.read(Path(filepath).read_bytes())
    legacy = scene.extras.get('v1', {})
    pur_file.canvas = list(scene.canvas)
    pur_file.zoom = scene.view.zoom
    pur_file.xCanvas, pur_file.yCanvas = scene.view.x, scene.view.y
    pur_file.folderLocation = legacy.get('folder') or ''
    pur_file.images = _images(scene)
    pur_file.text = [_text_item(note) for note in scene.items
                     if isinstance(note, NoteItem)]
    return pur_file


def _images(scene) -> list:
    """The old API groups instances under the image they share."""
    grouped: dict = {}
    for item in scene.images:
        grouped.setdefault(item.resource.identity(), []).append(item)
    images = []
    for instances in grouped.values():
        first = instances[0]
        image = PurImage()
        image.address = list(first.extras.get('v1', {}).get('address', (0, 0)))
        image.pngBinary = (bytearray(b'\xff\xff\xff\xff') if first.resource.linked
                           else bytearray(first.resource.data))
        image.transforms = [_image_item(instance) for instance in instances]
        images.append(image)
    return images


def _image_item(item: ImageItem) -> PurGraphicsImageItem:
    legacy = item.extras.get('v1', {})
    transform = PurGraphicsImageItem()
    transform.id = legacy.get('id', 0)
    transform.zLayer = 1.0 if item.z is None else item.z
    transform.matrix = _matrix(item.transform)
    transform.x, transform.y = item.transform.dx, item.transform.dy
    transform.source = legacy.get('source') or item.resource.source or 'BruteForceLoaded'
    transform.name = item.name if item.name is not None else 'image'
    transform.matrixBeforeCrop = _matrix(legacy.get('matrix_before_crop'))
    transform.xCrop, transform.yCrop = legacy.get(
        'crop_offset', (-item.resource.width / 2, -item.resource.height / 2))
    transform.scaleCrop = legacy.get('crop_scale', 1.0)
    transform.points = [[x for _, x, _ in item.bounds.elements],
                        [y for _, _, y in item.bounds.elements]]
    transform.pointCount = len(item.bounds.elements)
    transform.textChildren = [_text_item(child) for child in item.children
                              if isinstance(child, NoteItem)]
    return transform


def _text_item(note: NoteItem) -> PurGraphicsTextItem:
    legacy = note.extras.get('v1', {})
    text_item = PurGraphicsTextItem()
    text_item.id = legacy.get('id', 0)
    text_item.zLayer = 1.0 if note.z is None else note.z
    text_item.matrix = _matrix(note.transform)
    text_item.x, text_item.y = note.transform.dx, note.transform.dy
    text_item.text = note.text
    foreground = legacy.get('foreground', {}).get('color')
    background = legacy.get('background', {}).get('color')
    if foreground:
        text_item.opacity, text_item.rgb = foreground[0], list(foreground[1])
    if background:
        text_item.opacityBackground = background[0]
        text_item.rgbBackground = list(background[1])
    text_item.textChildren = [_text_item(child) for child in note.children
                              if isinstance(child, NoteItem)]
    return text_item


def _matrix(transform) -> list:
    if transform is None:
        return [1.0, 0.0, 0.0, 1.0]
    return [transform.m11, transform.m12, transform.m21, transform.m22]
