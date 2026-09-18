"""Write a `Scene` as a PureRef 2.0 / 2.1 file.

Ids, sibling order and stacking are assigned here: PureRef renumbers `z` and
`sort_order` to 1..n per parent on every save of its own, so writing small
integers matches what the application would have written anyway. Ids that came
from a file are kept, which makes load/save cycles stable.
"""
from __future__ import annotations

import html as html_module

from ..model import (NOTE_STYLES, VERSION_2_0, VERSION_2_1, DrawItem, GroupItem,
                     ImageItem, Item, NoteItem, Scene)
from ..problems import Unparsed
from ..qt import big_rational_cell, rect_cell, size_cell, transform_cell
from . import schema, values
from .database import Database
from .envelope import Envelope, wrap

DEFAULT_APPLICATION_VERSION = '2.1.3'
DEFAULT_NOTE_FONT = 'Open Sans'
DEFAULT_NOTE_SIZE = 22
DEFAULT_NOTE_COLOR = '#eaeaea'


def write(scene: Scene, *, format_version: str = VERSION_2_1,
          application_version: str | None = None, thumbnail: bytes | None = None,
          scene_rect: tuple[float, float, float, float] | None = None,
          edit=None) -> bytes:
    """Serialize `scene`.

    `thumbnail` is optional JPEG or PNG preview bytes. `scene_rect` is the canvas
    rectangle to record; left unset, a rectangle that came from a 2.x file is kept
    and anything else is left empty, which makes PureRef compute the framing. A
    1.x canvas is deliberately not reused here: there it is the scrollable area,
    not the content rectangle 2.x stores.

    `edit` is called with the open `Database` once every row is in place, for
    anything this package does not model — the escape hatch that keeps SQL an
    option without making it the interface.
    """
    previous = scene.extras.get('v2', {})
    stored = previous.get('envelope')
    preview = thumbnail if thumbnail is not None else getattr(stored, 'thumbnail', b'')
    if preview and format_version == VERSION_2_0:
        if thumbnail:
            raise ValueError('The 2.0 header has no thumbnail field; '
                             'write 2.1 or drop the thumbnail')
        preview = b''  # a preview carried over from a 2.1 file has nowhere to go
    envelope = Envelope(
        format_version=format_version,
        application_version=application_version or getattr(
            stored, 'application_version', None) or DEFAULT_APPLICATION_VERSION,
        thumbnail=preview)
    with Database(pragmas=schema.PRAGMAS) as db:
        schema.create(db.connection)
        resources = _write_resources(db, scene)
        _write_items(db, scene, resources)
        _write_metadata(db, scene, envelope, scene_rect)
        if edit is not None:
            edit(db)
        database = db.to_bytes()
    return wrap(database, envelope)


def _write_resources(db: Database, scene: Scene) -> dict[tuple, int]:
    ids = {}
    for index, resource in enumerate(scene.resources):
        ids[resource.identity()] = index
        db.insert('images', id=index,
                  source_type=2 if resource.linked else 1,
                  origin=resource.origin if resource.origin is not None else resource.source,
                  source=resource.source,
                  format=resource.format,
                  checksum=resource.checksum,
                  data=resource.data,
                  width=resource.width,
                  height=resource.height)
    return ids


def _write_items(db: Database, scene: Scene, resources) -> None:
    ids = _assign_ids(scene)
    for parent, siblings in _sibling_groups(scene):
        for index, item in enumerate(siblings):
            kept = _unparsed(item)
            db.insert('items',
                      id=ids[id(item)],
                      parent=-1 if parent is None else ids[id(parent)],
                      name=item.name,
                      transform=kept.get('transform',
                                         transform_cell(item.transform.to_matrix9())),
                      sort_order=kept.get('sort_order', big_rational_cell(
                          item.order if item.order is not None else index + 1)),
                      z=float(ids[id(item)] + 1 if item.z is None else item.z),
                      opacity=float(item.opacity),
                      locked=int(bool(item.locked)),
                      comment=item.comment)
            _write_subtype(db, item, ids[id(item)], resources)


def _write_subtype(db: Database, item: Item, item_id: int, resources) -> None:
    # Columns the reader kept in `extras` but this package does not model are not
    # written back: PureRef drops unknown columns on its own next save anyway.
    # Values it could not interpret *are* written back, exactly as they arrived.
    kept = _unparsed(item)
    if isinstance(item, ImageItem):
        db.insert('items_images', id=item_id,
                  image=resources[item.resource.identity()],
                  image_transform=kept.get(
                      'image_transform', transform_cell(item.pixel_transform.to_matrix9())),
                  image_bounds=kept.get('image_bounds', item.bounds.cell()),
                  flags=int(item.flags),
                  playback_state=int(item.playback.state),
                  playback_frame=int(item.playback.frame),
                  playback_speed=float(item.playback.speed))
    elif isinstance(item, NoteItem):
        db.insert('items_notes', id=item_id,
                  text=item.html if item.html is not None else note_html(item),
                  text_color=item.text_color,
                  background_color=item.background_color or '',
                  fixed_size=kept.get('fixed_size', size_cell(*item.fixed_size)),
                  style=NOTE_STYLES[item.style])
    elif isinstance(item, GroupItem):
        db.insert('items_groups', id=item_id,
                  background_color=item.background_color,
                  lock_mode=int(item.lock_mode))
    elif isinstance(item, DrawItem):
        db.insert('items_drawings', id=item_id,
                  strokes=kept.get('strokes', values.strokes_cell(item.strokes)))


def _write_metadata(db: Database, scene: Scene, envelope: Envelope,
                    scene_rect) -> None:
    kept = dict(scene.extras.get('v2', {}).get('metadata') or {})
    row = {name: kept.get(name) for name in schema.columns('metadata')}
    row.update(
        id=0,
        application_version=envelope.application_version,
        scene_rect=_scene_rect(scene, scene_rect, kept.get('scene_rect')),
        view_transform=transform_cell([scene.view.zoom, 0.0, 0.0,
                                       0.0, scene.view.zoom, 0.0, 0.0, 0.0, 1.0]),
        horizontal_scroll=int(scene.view.x),
        vertical_scroll=int(scene.view.y),
        thumbnail=envelope.thumbnail or None,
        saved=1)
    db.insert('metadata', **row)


def _scene_rect(scene: Scene, explicit, stored):
    rectangle = explicit
    if rectangle is None and scene.source_version in (VERSION_2_0, VERSION_2_1):
        rectangle = scene.canvas
    if rectangle is None:
        return stored
    x0, y0, x1, y1 = rectangle
    return rect_cell(x0, y0, x1 - x0, y1 - y0)


def _unparsed(item: Item) -> dict[str, str]:
    """The cells a reader could not interpret, ready to be written back."""
    return {column: value.cell for column, value
            in item.extras.get('v2', {}).get('unparsed', {}).items()
            if isinstance(value, Unparsed)}


def _assign_ids(scene: Scene) -> dict[int, int]:
    """Keep the ids a file came with when they are complete and unique."""
    items = list(scene.walk())
    stored = [item.extras.get('v2', {}).get('id') for item in items]
    if all(value is not None for value in stored) and len(set(stored)) == len(stored):
        return {id(item): value for item, value in zip(items, stored)}
    return {id(item): index for index, item in enumerate(items)}


def _sibling_groups(scene: Scene):
    """Yield (parent, children) pairs, parents before their children."""
    queue = [(None, scene.items)]
    while queue:
        parent, siblings = queue.pop(0)
        yield parent, siblings
        for item in siblings:
            if item.children:
                queue.append((item, item.children))


def note_html(note: NoteItem) -> str:
    """Wrap a note's plain text in the small HTML document PureRef accepts."""
    color = '' if note.text_color else f'color:{DEFAULT_NOTE_COLOR};'
    return ('<html><body style="'
            f'font-family:{html_module.escape(DEFAULT_NOTE_FONT, quote=True)};'
            f'font-size:{DEFAULT_NOTE_SIZE}px;{color}">'
            '<p style="white-space:pre-wrap;margin:0">'
            f'{html_module.escape(note.text)}</p></body></html>')
