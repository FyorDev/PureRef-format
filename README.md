# PureRef-format

Read, write and convert PureRef `.pur` files from Python — **both generations**:
the 1.10 / 1.11.1 binary format and the 2.0 / 2.1 SQLite format. One scene model,
two backends, a command line tool, and no dependencies.

```sh
pip install .

pureref new board.pur ~/references/artist        # a tidy board from a folder
pureref info board.pur                           # what is in a file
pureref convert board.pur board-1.10.pur --format 1.10
```

### Video

The 1.x reverse engineering behind this project:

[![Watch the video](https://img.youtube.com/vi/31lsz3JNtCU/hqdefault.jpg)](https://youtu.be/31lsz3JNtCU)

## What it does

* **Reads** 1.10, 1.11.1, 2.0 and 2.1 files, detecting which is which.
* **Writes** all of them, from scratch — no PureRef installation, no Qt, no
  template file.
* **Converts** between them, and says what a format cannot keep instead of
  dropping it silently.
* **Round-trips exactly**: every test fixture, written by PureRef itself, comes
  back byte for byte after a load and save.
* Images (embedded or linked), positions, rotation, scale, opacity, crops,
  shared resources, notes, groups, drawings, render flags, animation state,
  stroke styles and per-item comments.
* A layout helper that packs images into a tidy rectangle, which is what this
  project was originally for.

Verified against four real PureRef releases — **1.10.4, 1.11.1, 2.0.3 and
2.1.3** — see [docs/format-v1.md](docs/format-v1.md) and
[docs/format-v2.md](docs/format-v2.md) for the formats themselves.

## Library

```python
import pureref

scene = pureref.read('board.pur')            # any version

group = scene.add_group(name='Studies', background_color='#4020a0ff')
scene.add_image('sketch.png', parent=group, x=0, y=0, rotation=15, opacity=0.8)
scene.add_image('photo.jpg', parent=group, x=300, y=0, crop=(0, 0, 400, 400))
scene.add_image('huge.png', parent=group, x=700, y=0, link=True)   # not embedded
note = scene.add_note('Ω 中', parent=group, x=0, y=-200, text_color='#eaeaea')
note.comment = 'shows up in the item tooltip'

losses = pureref.write(scene, 'board.pur', overwrite=True)   # 2.1 by default
```

`pureref.write` returns a list of what the target format could not express, and
refuses to overwrite an existing file unless you pass `overwrite=True`, because a
`.pur` is usually somebody's canvas:

```python
>>> scene.losses('1.10')
[Loss('groups', '1 group(s): 1.x has no groups, their children move to the canvas'),
 Loss('images', 'JPG image data: re-encoded as PNG, which 1.x is limited to')]
```

Each `Loss` is a string with a `.code`, so it reads fine in a message and can
still be branched on.

Every item is a `Transform` plus fields: `ImageItem`, `NoteItem`, `GroupItem`,
`DrawItem`, all with `children`. An image item's position is its **center**, and
`item.size` is what it measures on the canvas:

```python
for item in scene.images:
    item.scale_to_height(1000)               # and scale, scale_to_width, crop
    print(item.name, item.resource.size, item.size, item.grayscale)

from pureref.layout import pack_rows
pack_rows(scene.images, target_width=1000)   # rows that line up exactly
```

Anything a reader did not interpret is kept and written back, so reading and
saving a file does not degrade it. It lands on one typed carrier per generation —
`item.v1` and `scene.v1` for a 1.x file, `item.v2` and `scene.v2` for a 2.x one —
which is where the pre-crop transform, the exact 16-bit note colours, the row ids,
the envelope and any column this package has never seen live.

Reading never fails over one unfamiliar value: a serialized type this package
does not know becomes an `Unparsed` value, noted on the scene and restored byte
for byte when you save.

```python
>>> scene = pureref.read('from-a-newer-pureref.pur')
>>> scene.problems
[Problem('unparsed-value', "item 3.sort_order: Expected 'BigRational', found 'NewType'")]
```

When you want the file rather than the interpretation — a column this package has
never seen, or SQL instead of model objects — the 2.x document layer hands it
over, and the writer takes an edit hook for the same reason:

```python
from pureref.v2 import Document

with Document.read('board.pur') as document:
    document.rows('items')        # dicts, values exactly as stored
    document.database             # the inner SQLite bytes
    document.repack()             # and back to the original bytes

pureref.write_bytes(scene, edit=lambda db: db.connection.execute(...))
```

## Command line

| Command | What it does |
|---|---|
| `pureref info FILE [--json]` | describe a file: container, resources, item tree |
| `pureref new OUT IMAGES...` | build a laid-out board from images or folders |
| `pureref batch IN OUT` | one `.pur` per subfolder of images |
| `pureref convert IN OUT [--format]` | rewrite in another format |
| `pureref extract FILE DIR` | write the embedded images out |
| `pureref unpack FILE OUT.sqlite` | the inner SQLite database (2.x) |
| `pureref pack IN.sqlite OUT.pur` | wrap a database back into a `.pur` (2.x) |

`--format` takes `1.10`, `2.0` or `2.1` (the default). Exit codes: 0 success,
1 a file or format problem, 2 wrong usage.

```sh
pureref batch Artists Purs        # Artists/<name>/*.jpg  ->  Purs/<name>.pur
pureref info board.pur --json | jq .counts
```

## Install

Python 3.10 or newer; no required dependencies.

```sh
pip install .
pip install ".[thumbnails]"   # Pillow, only for previews and 1.x re-encoding
```

Pillow is needed for two things: generating a preview image, and writing
non-PNG images as 1.10, which stores PNG only.

## Tests

```sh
python -m unittest discover -s tests            # no PureRef needed
DISPLAY=:0 PUREREF_BUILDS=~/pureref python -m tests.integration_app
DISPLAY=:0 PUREREF_EXE=/usr/bin/PureRef python -m tests.integration_app
```

The unit suite covers the Qt primitives, both formats, conversions, the layout,
the CLI and the deprecated shim, against fixtures written by PureRef itself. It
also truncates and bit-flips every fixture and insists that a damaged file comes
back as either a `Scene` with `problems` or a `FormatError` — never a traceback
from inside a parser.

The layout tables in `docs/format-v1.md` are generated from the record
declarations the reader and writer use, and a test fails when they drift:

```sh
python -m tools.generate_docs            # rewrite them
python -m tools.generate_docs --check    # or just report
```

The integration suite loads the files this package writes in the real PureRef,
exports renders, saves them again and checks that every field survived. Point
`PUREREF_BUILDS` at a folder of unpacked releases — `<version>/usr/bin/PureRef`
each, which is what extracting the `.deb` downloads gives you — and every build
found is exercised: 1.x builds against 1.10 output, 2.x builds against 2.0 and
2.1 output. That is the only way to check the 1.x writer against the application
that owns the format, and it currently passes for 1.10.4, 1.11.1, 2.0.3 and
2.1.3. It uses a throwaway settings file and only synthetic images, and on Linux
it needs an X display because PureRef's AppImage ships no `offscreen` Qt plugin.

## Upgrading from the old `purformat` module

The pre-2.0 API still works and still produces identical bytes, with a
deprecation warning:

```python
import purformat                    # deprecated
pur = purformat.PurFile()
pur.read('board.pur')
pur.write('copy.pur')
```

It is now a thin shim over `pureref`, which handles 2.x as well. The original
scripts moved to [legacy/](legacy/) and still work; `pureref new` and
`pureref batch` replace them.

## About

Started after an [Artstation webscraper](https://github.com/FyorUU/Artstation-webscraper),
because collecting reference is only fun until you have to lay it out by hand.
The 2.x support came later, from the format notes in `docs/`.
