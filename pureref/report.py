"""Describe a scene: the backing for `pureref info`."""
from __future__ import annotations

from .model import (DrawItem, GroupItem, ImageItem, NoteItem, PLAYBACK_STATIC,
                    RENDER_GRAYSCALE, Scene)


def summary(scene: Scene) -> dict:
    """A JSON-friendly overview: versions, counts, resources and the item tree."""
    report = {
        'version': scene.source_version,
        'canvas': list(scene.canvas),
        'view': {'zoom': scene.view.zoom, 'x': scene.view.x, 'y': scene.view.y},
        'counts': {
            'items': sum(1 for _ in scene.walk()),
            'images': len(scene.images),
            'notes': len(scene.notes),
            'groups': len(scene.groups),
            'drawings': len(scene.drawings),
            'resources': len(scene.resources),
        },
        'resources': [_resource(resource) for resource in scene.resources],
        'items': [_item(item) for item in scene.items],
        'problems': [{'code': problem.code, 'detail': str(problem)}
                     for problem in scene.problems],
    }
    report.update(_provenance(scene))
    return report


def _provenance(scene: Scene) -> dict:
    stored = scene.v1
    modern = scene.v2
    if stored is not None:
        return {'container': {
            'checksum': stored.checksum,
            'checksum_valid': stored.checksum_valid,
            'application_version': stored.application_version,
            'folder': stored.folder}}
    if modern is not None and modern.envelope is not None:
        envelope = modern.envelope
        return {'container': {
            'checksum': envelope.checksum,
            'checksum_valid': envelope.checksum_valid,
            'application_version': envelope.application_version,
            'database_bytes': envelope.database_size,
            'thumbnail_bytes': len(envelope.thumbnail or b''),
            'user_version': modern.user_version,
            'integrity': modern.integrity,
            'unknown_tables': modern.unknown_tables}}
    return {}


def _resource(resource) -> dict:
    return {
        'format': resource.format,
        'width': resource.width,
        'height': resource.height,
        'bytes': None if resource.linked else len(resource.data),
        'linked': resource.linked,
        'checksum': resource.checksum,
        'source': resource.source,
    }


def _item(item) -> dict:
    described = {
        'kind': item.kind(),
        'name': item.name,
        'x': round(item.transform.dx, 3),
        'y': round(item.transform.dy, 3),
        'z': item.z,
        'order': str(item.order) if item.order is not None else None,
        'opacity': item.opacity,
        'comment': item.comment,
    }
    if isinstance(item, ImageItem):
        width, height = item.size
        described.update(
            resource=item.resource.source or item.resource.checksum,
            pixels=list(item.resource.size),
            size=[round(width, 2), round(height, 2)],
            cropped=len(item.bounds.elements) != 5 or _is_cropped(item),
            grayscale=bool(item.flags & RENDER_GRAYSCALE),
            smooth=item.smooth)
        if item.playback.state != PLAYBACK_STATIC:
            described['playback'] = vars(item.playback)
    elif isinstance(item, NoteItem):
        described.update(text=_shorten(item.text), rich_text=item.html is not None,
                         style=item.style, background=item.background_color)
    elif isinstance(item, GroupItem):
        described.update(lock_mode=item.lock_mode, background=item.background_color)
    elif isinstance(item, DrawItem):
        described.update(strokes=len(item.strokes),
                         styles=sorted({stroke.style for stroke in item.strokes}))
    if item.children:
        described['children'] = [_item(child) for child in item.children]
    return described


def _is_cropped(item: ImageItem) -> bool:
    x0, y0, x1, y1 = item.bounds.bounding_box()
    width, height = item.resource.size
    return round(x1 - x0) != width or round(y1 - y0) != height


def _shorten(text: str, limit: int = 60) -> str:
    flat = ' '.join(text.split())
    return flat if len(flat) <= limit else flat[:limit - 1] + '…'


def text_report(scene: Scene) -> str:
    """The same overview as prose, for a terminal."""
    data = summary(scene)
    container = data.get('container', {})
    lines = [f'PureRef {data["version"]} file']
    if container:
        checksum = container.get('checksum_valid')
        state = 'valid' if checksum else ('invalid' if checksum is False else 'unknown')
        lines.append(f'  checksum {state}, written by PureRef '
                     f'{container.get("application_version") or "unknown"}')
        if container.get('integrity') not in (None, ['ok']):
            lines.append(f'  sqlite integrity: {container["integrity"]}')
        if container.get('unknown_tables'):
            lines.append(f'  unknown tables: {", ".join(container["unknown_tables"])}')
    counts = data['counts']
    lines.append('  ' + ', '.join(f'{value} {name}' for name, value in counts.items()))
    lines.append(f'  canvas {data["canvas"]}, zoom {data["view"]["zoom"]:g}')
    for resource in data['resources']:
        where = resource['source'] or '(embedded, no path)'
        size = 'linked' if resource['linked'] else f'{resource["bytes"]} bytes'
        lines.append(f'  image {resource["width"]}x{resource["height"]} '
                     f'{resource["format"]}, {size}: {where}')
    for problem in data['problems']:
        lines.append(f'  problem ({problem["code"]}): {problem["detail"]}')
    lines.extend(_item_lines(data['items'], 1))
    return '\n'.join(lines)


def _item_lines(items, depth: int) -> list[str]:
    lines = []
    for item in items:
        detail = ''
        if item['kind'] == 'image':
            detail = f' {item["size"][0]:g}x{item["size"][1]:g}'
            detail += ' cropped' if item.get('cropped') else ''
            detail += ' grayscale' if item.get('grayscale') else ''
        elif item['kind'] == 'note':
            detail = f' {item["text"]!r}'
        elif item['kind'] == 'draw':
            detail = f' {item["strokes"]} stroke(s)'
        name = item['name'] or ''
        lines.append(f'{"  " * depth}{item["kind"]} at ({item["x"]:g}, {item["y"]:g})'
                     f'{detail} {name}'.rstrip())
        lines.extend(_item_lines(item.get('children', []), depth + 1))
    return lines
