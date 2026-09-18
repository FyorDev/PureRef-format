"""Generate the layout tables in `docs/` from the record declarations.

A format document and a parser drift apart the moment they are written by hand
twice. The tables between the markers below are produced from
`pureref/v1/records.py`, which is also what the reader and the writer use, so a
field cannot be documented one way and parsed another. `tests/test_docs.py`
fails when a checked-in document no longer matches, and

    python -m tools.generate_docs

rewrites them in place. The prose around the markers is written by hand and is
left alone.
"""
from __future__ import annotations

import sys
from pathlib import Path

from pureref.records import Record
from pureref.v1 import records as v1

ROOT = Path(__file__).resolve().parent.parent
BEGIN = '<!-- generated: {name} -->'
END = '<!-- end generated -->'

# document -> section name -> (record, whether the fields sit at fixed offsets)
DOCUMENTS = {
    'docs/format-v1.md': {
        'header': (v1.HEADER, True),
        'image-item': (v1.IMAGE_ITEM, False),
        'note-item': (v1.NOTE_ITEM, False),
        'reference': (v1.REFERENCE, True),
    },
}


def table(record: Record, offsets: bool) -> str:
    """One markdown table for `record`, in declaration order."""
    head = (['Offset', 'Size'] if offsets else []) + ['Field', 'Encoding', 'Meaning']
    align = (['---:', '---:'] if offsets else []) + ['---', '---', '---']
    rows = []
    at = 0
    for entry in record.fields:
        size = entry.codec.size
        cells = []
        if offsets:
            if size is None:                      # a fixed table cannot have one
                raise ValueError(f'{record.name}.{entry.name} has no fixed size')
            cells = [str(at), str(size)]
            at += size
        rows.append(cells + [f'`{entry.name}`', entry.codec.description,
                             entry.doc or '—'])
    lines = ['| ' + ' | '.join(head) + ' |', '|' + '|'.join(align) + '|']
    lines += ['| ' + ' | '.join(row) + ' |' for row in rows]
    if offsets:
        lines.append('')
        lines.append(f'Total: {record.size} bytes.')
    return '\n'.join(lines)


def rewrite(text: str, sections: dict) -> str:
    """Replace every marked region; anything else in the document is kept."""
    for name, (record, offsets) in sections.items():
        begin = BEGIN.format(name=name)
        start = text.index(begin) + len(begin)
        end = text.index(END, start)
        text = text[:start] + '\n' + table(record, offsets) + '\n' + text[end:]
    return text


def main(argv) -> int:
    check = '--check' in argv
    stale = []
    for name, sections in DOCUMENTS.items():
        path = ROOT / name
        current = path.read_text()
        wanted = rewrite(current, sections)
        if current == wanted:
            continue
        stale.append(name)
        if not check:
            path.write_text(wanted)
    if check and stale:
        print('out of date, run python -m tools.generate_docs: ' + ', '.join(stale))
        return 1
    print('updated: ' + ', '.join(stale) if stale else 'already up to date')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
