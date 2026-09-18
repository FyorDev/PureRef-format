"""What a file could not tell us, and what a format cannot keep.

Reading a `.pur` should not fail because one value inside it is unfamiliar: a
future PureRef will add types, and a file full of perfectly good images should
still open. Anything the readers cannot interpret becomes a `Problem` on the
scene and an `Unparsed` value that is written back untouched.

`Loss` is the other direction — something the scene holds that the target format
has nowhere to put. Both subclass `str` so they print and compare as the message
they carry, while code that wants to branch can read `.code`.
"""
from __future__ import annotations

from dataclasses import dataclass


class _Message(str):
    """A message that also carries a machine-readable code."""

    code: str

    def __new__(cls, code: str, detail: str):
        message = super().__new__(cls, detail)
        message.code = code
        return message

    def __repr__(self) -> str:
        return f'{type(self).__name__}({self.code!r}, {str(self)!r})'


class Loss(_Message):
    """Something a target format cannot express, reported before writing."""


class Problem(_Message):
    """Something in a file this package could not interpret."""

    where: str | None

    def __new__(cls, code: str, detail: str, where: str | None = None):
        message = super().__new__(cls, code, detail if where is None
                                  else f'{where}: {detail}')
        message.where = where
        return message


@dataclass(frozen=True)
class Unparsed:
    """A serialized value kept verbatim because its type is not understood.

    `cell` is exactly what came out of SQLite, so writing it back reproduces the
    original bytes; `type_id` and `type_name` are what the QVariant header said.
    """

    type_id: int
    type_name: str | None
    payload: bytes
    cell: str

    def __str__(self) -> str:
        name = self.type_name or f'type {self.type_id}'
        return f'<unparsed {name}, {len(self.payload)} bytes>'
