"""Deprecated compatibility layer for the pre-2.0 `purformat` module.

`purformat` only ever handled the 1.10 format and its own object graph. Both live
on as a thin shim over the `pureref` package, which reads and writes 1.10, 2.0
and 2.1 through one model:

    import pureref
    scene = pureref.read('board.pur')
    pureref.write(scene, 'board.pur', overwrite=True)
"""
import warnings

from . import items, purformat, read, write
from .purformat import PurFile

warnings.warn('purformat is deprecated; use the pureref package instead',
              DeprecationWarning, stacklevel=2)

__all__ = ['PurFile', 'items', 'purformat', 'read', 'write']
