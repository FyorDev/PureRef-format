"""The PureRef 2.0 / 2.1 format: a SQLite database in a displaced-prefix wrapper.

Three levels, depending on how much interpretation you want:

    pureref.read(path)                     a Scene
    v2.Document.open(data)                  envelope, rows and database bytes
    v2.envelope.unwrap(data)                just the container arithmetic
"""
from . import cells, database, envelope, schema, values
from .document import Document
from .reader import read
from .writer import write

__all__ = ['read', 'write', 'Document', 'cells', 'database', 'envelope', 'schema',
           'values']
