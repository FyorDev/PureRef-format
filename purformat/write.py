"""Deprecated: writes the old `PurFile` objects through the new 1.x writer.

Kept so code written against `purformat` keeps working. New code should use
`pureref.write`, which can also write the 2.x format.
"""
from pureref import imagesize, v1
from pureref.model import (VERSION_1, ImageItem, V1File, V1Image,
                           V1Note, NoteItem, Resource, Scene, Transform, View)
from pureref.qt import Path

LINK_BINARY = b'\xff\xff\xff\xff'


def write_pur_file(pur_file, filepath: str):
    data = v1.write(to_scene(pur_file))
    with open(filepath, 'wb') as stream:
        stream.write(data)


def to_scene(pur_file) -> Scene:
    """Translate the old object graph into a `Scene`."""
    scene = Scene(canvas=tuple(pur_file.canvas),
                  view=View(pur_file.zoom, pur_file.xCanvas, pur_file.yCanvas),
                  source_version=VERSION_1)
    scene.v1 = V1File(folder=getattr(pur_file, 'folderLocation', '') or '')
    for image in pur_file.images:
        resource = _resource(image)
        for transform in image.transforms:
            scene.items.append(_image_item(resource, transform))
    for text_item in pur_file.text:
        scene.items.append(_note(text_item))
    return scene


def _resource(image) -> Resource:
    data = bytes(image.pngBinary)
    source = image.transforms[0].source if image.transforms else ''
    if data == LINK_BINARY:
        return Resource(1, 1, None, 'PNG', source or 'missing')
    width, height = 0, 0
    try:
        _, width, height = imagesize.identify(data)
    except imagesize.UnknownImage:
        pass
    if not width:
        points = image.transforms[0].points if image.transforms else [[0, 1], [0, 1]]
        width = max(1, round(max(points[0]) - min(points[0])))
        height = max(1, round(max(points[1]) - min(points[1])))
    return Resource(width, height, data, 'PNG',
                    '' if source == 'BruteForceLoaded' else source)


def _image_item(resource: Resource, transform) -> ImageItem:
    brute_force = transform.source == 'BruteForceLoaded'
    item = ImageItem(
        name=None if brute_force else transform.name,
        transform=_transform(transform),
        z=transform.zLayer,
        resource=resource,
        bounds=Path([(0 if index == 0 else 1, x, y) for index, (x, y)
                     in enumerate(zip(transform.points[0], transform.points[1],
                                      strict=False))]),
        v1=V1Image(
            source=transform.source,
            brute_force=brute_force,
            before_crop=Transform(*_pairs(transform.matrixBeforeCrop)),
            crop_offset=(transform.xCrop, transform.yCrop),
            crop_scale=transform.scaleCrop))
    item.children = [_note(child) for child in transform.textChildren]
    return item


def _note(text_item) -> NoteItem:
    note = NoteItem(
        transform=_transform(text_item),
        z=text_item.zLayer,
        text=text_item.text,
        v1=V1Note(
            foreground=(text_item.opacity, list(text_item.rgb)),
            background=(text_item.opacityBackground, list(text_item.rgbBackground))))
    note.children = [_note(child) for child in text_item.textChildren]
    return note


def _transform(item) -> Transform:
    m11, m12, m21, m22 = item.matrix
    return Transform(m11, m12, m21, m22, item.x, item.y)


def _pairs(matrix):
    return (matrix[0], matrix[1], matrix[2], matrix[3])
