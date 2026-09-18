"""What the test modules share: the fixtures, and a row-level 2.x builder.

Most tests work through the public API. The ones that check how a reader handles
a file no writer here would produce -- a parent cycle, an item with no subtype
row, an image item pointing at a resource that is not there -- need to assemble a
database row by row, and that assembly is the same every time.
"""
from __future__ import annotations

from pathlib import Path

from pureref.model import Transform
from pureref.v2 import envelope, schema
from pureref.v2.database import Database
from pureref.v2.values import big_rational_cell, transform_cell

FIXTURES = Path(__file__).resolve().parent / 'fixtures'

# Files PureRef itself wrote, which is what the round-trip tests measure against.
APP_2X = ['app-2.0.3-image', 'app-2.0.3-mixed', 'app-2.0.3-anim', 'app-2.0.3-linked',
          'app-2.0.3-dashed', 'app-2.0.3-comment', 'envelope-2.0']
APP_1X = ['app-1.10.4', 'app-1.11.1']


def fixture(name: str) -> Path:
    """A fixture path, with or without the .pur suffix."""
    path = FIXTURES / name
    return path if path.suffix else path.with_suffix('.pur')


def read_fixture(name: str) -> bytes:
    return fixture(name).read_bytes()


def item_row(item_id: int, parent: int = -1, **overrides) -> dict:
    """An `items` row with everything filled in, for overriding a field or two."""
    row = dict(id=item_id, parent=parent, name=f'item{item_id}',
               transform=transform_cell(Transform().to_matrix9()),
               sort_order=big_rational_cell(item_id + 1),
               z=1.0, opacity=1.0, locked=0, comment=None)
    row.update(overrides)
    return row


def build_2x(tables: dict[str, list[dict]], *, application_version: str = '2.1.3',
             **envelope_options) -> bytes:
    """Wrap the given rows as a 2.x file. The metadata row is filled in."""
    with Database(pragmas=schema.PRAGMAS) as db:
        schema.create(db.connection)
        db.insert('metadata', id=0, application_version=application_version)
        for table, rows in tables.items():
            for row in rows:
                db.insert(table, **row)
        database = db.to_bytes()
    return envelope.wrap(database, envelope.Envelope(
        application_version=application_version, **envelope_options))
