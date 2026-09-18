# The PureRef 2.0 / 2.1 `.pur` format

Implemented in `pureref/v2`, verified against **PureRef 2.0.3 on Linux** and
against files written by **2.1.3 on Windows**. The envelope version is a format
version, not an application version: 2.0.3 writes `2.1` envelopes, and 2.0.3
accepts `2.0`, `2.1` and `2.2` while refusing `3.0` as "from a newer version".

An independent specification of the same format, written from 2.1.3, is
[Vacyyyy/pur-2-file-format](https://github.com/Vacyyyy/pur-2-file-format); its
`FORMAT.md` and the notes in this repository's research log cover the same ground
from two directions. This implementation is written from the format, not from
that project's code.

## Container: a SQLite database with a displaced prefix

A `.pur` is an ordinary SQLite database whose first `H` bytes were replaced by a
PureRef header and moved to the end:

```text
offset 0   header               H bytes
offset H   database[H:N]        N - H bytes
offset N   database[0:H]        H bytes
```

so `database = file[N:] + file[H:N]`. Carving from the `SQLite format 3`
signature to the end of the file recovers only the displaced prefix.

## Header

| Field | Encoding | 2.0 | 2.1 |
|---|---|:-:|:-:|
| format version | QString (`2.0` / `2.1`) | ● | ● |
| reserved | uint32, `0` | ● | ● |
| N, the database length | uint64 | ● | ● |
| application version | QString (`2.0.3`, `2.1.3`) | ● | ● |
| checksum | QString, 32 lowercase MD5 hex digits | ● | ● |
| thumbnail | QByteArray, JPEG or PNG | — | ● |

The **`2.0` layout has no thumbnail field**: its header ends at the checksum.
Adding an empty thumbnail array to a `2.0` header makes PureRef fail with
`Open failed … no such table: metadata`, because the database is then
reconstructed four bytes out of step. That layout belongs to the first 2.x
releases: 2.0.3 (September 2024) already writes `2.1` with a thumbnail, and the
changelog only adds a *setting* to stop generating thumbnails in 2.1.0.

The checksum is `md5(file[end_of_checksum_field:])`, so it covers the thumbnail,
the database body and the displaced prefix — not the reconstructed database. A
wrong checksum is a warning, not an error: PureRef still opens the file.

Previews are 256×256 RGB JPEG renders of the canvas in PureRef's own saves, and
the same bytes appear in `metadata.thumbnail`. A PNG preview is accepted too, so
`pureref` can supply one without a JPEG encoder. On Windows this is what the
shell thumbnail provider reads, which is the reason to bother writing one.

## Database

```sql
PRAGMA page_size = 4096;
PRAGMA auto_vacuum = 1;          -- FULL
PRAGMA application_id = 940753918;
PRAGMA user_version = 200101;
PRAGMA encoding = 'UTF-8';
```

`user_version` is the compatibility gate. A lower value is migrated silently and
re-saved as `200101`; a higher one makes PureRef refuse the file, quoting
`metadata.application_version` in the message. Do not advertise a version of
PureRef that does not exist yet.

PureRef reads its schema by column *name* (`PRAGMA table_info`,
`ALTER TABLE … ADD COLUMN`), which means:

* **column order is free** — 2.0.3 and 2.1.3 declare the same columns in
  different orders and open each other's files;
* **extra columns and tables** load with a warning and are dropped on the next
  save, so `pureref` exposes them on read and does not write them back;
* **missing columns are fatal** — a database without `metadata.saved` fails to
  load — so `pureref/v2/schema.py` writes the full column set, and
  `schema.missing_columns` is what `pureref pack` checks before wrapping a
  database somebody edited by hand.

| Table | Holds |
|---|---|
| `images` | image resources: bytes, format, size, checksum, source path |
| `items` | every object: parent, transform, order, z, opacity, lock, name |
| `items_images` | image instances: which resource, crop outline, flags, playback |
| `items_notes` | note HTML, colors, fixed size, style |
| `items_groups` | group background and lock mode |
| `items_drawings` | stroke lists |
| `metadata` | view, preview, application version, save bookkeeping |

Column by column, generated from `pureref/v2/schema.py`, which is the same
declaration the writer creates the database from:

<!-- generated: columns -->
### `images`

| Column | Declared | Serialized | Holds |
|---|---|---|---|
| `id` | INTEGER PRIMARY KEY | — | resource id, referenced by items_images.image |
| `source_type` | INTEGER | — | 1 embedded, 2 linked; there is no third value |
| `origin` | TEXT | — | where the image originally came from, a path or a URL |
| `source` | TEXT | — | the path a linked image is loaded from, rewritten when it is found again |
| `format` | TEXT | — | not normalised: the lowercase file extension when imported from a path, the uppercase detected format otherwise |
| `checksum` | TEXT | — | MD5 of the embedded bytes, the deduplication key; NULL when linked |
| `data` | BLOB | — | the image bytes; NULL when linked |
| `width` | INTEGER | — | pixel width, of the stored bytes -- a downscaled import stores the smaller size |
| `height` | INTEGER | — | pixel height, likewise |

### `metadata`

| Column | Declared | Serialized | Holds |
|---|---|---|---|
| `id` | INTEGER PRIMARY KEY | — | always 0: the table holds one row |
| `scene_rect` | TEXT | `QRectF` | the content rectangle, unioned with the origin |
| `application_version` | TEXT | — | the PureRef that saved the file, matching the envelope |
| `view_transform` | TEXT | `QTransform` | the view onto the scene; its scale is the zoom |
| `thumbnail` | BLOB | — | the preview image, duplicated here and in the 2.1 envelope |
| `horizontal_scroll` | INTEGER | — | the pan, in view coordinates |
| `vertical_scroll` | INTEGER | — | the pan, likewise |
| `last_save_path` | TEXT | — | the directory of the last save, which seeds the save dialog |
| `last_load_path` | TEXT | — | the path the scene is associated with; after a save, that file |
| `last_load_checksum` | TEXT | — | the header checksum of the file the scene was loaded from |
| `saved` | INTEGER | — | 0 when the scene had never been associated with a .pur before this save |

### `items`

| Column | Declared | Serialized | Holds |
|---|---|---|---|
| `parent` | INTEGER | — | the parent object id, -1 for a root |
| `id` | INTEGER PRIMARY KEY | — | object id; which subtype table holds it decides what kind of item it is |
| `name` | TEXT | — | display name, nullable |
| `transform` | BLOB | `QTransform` | the item placement, relative to its parent |
| `sort_order` | BLOB | `BigRational` | sibling order, renumbered to 1..n on every save |
| `z` | REAL | — | stacking, renumbered likewise |
| `opacity` | REAL | — | alpha multiplier |
| `locked` | INTEGER | — | lock flag |
| `comment` | INTEGER | — | the comment text, despite the INTEGER declaration; shown in the tooltip |

### `items_images`

| Column | Declared | Serialized | Holds |
|---|---|---|---|
| `image` | INTEGER | — | which images row supplies the pixels; several items can share one |
| `playback_speed` | REAL | — | playback multiplier; a float widened into a REAL |
| `id` | INTEGER PRIMARY KEY | — | the item id this row describes |
| `playback_state` | INTEGER | — | 0 still, 2 paused at playback_frame, 3 playing |
| `image_transform` | BLOB | `QTransform` | maps image pixels into item coordinates, translating by (-w/2, -h/2), which is why an image item is positioned at its centre |
| `image_bounds` | BLOB | `QPainterPath` | the visible outline in centred pixel coordinates: a closed rectangle unless cropped |
| `playback_frame` | INTEGER | — | the frame a paused animation shows |
| `flags` | INTEGER | — | bit 0x1 bilinear sampling, bit 0x2 the grayscale filter; nothing else is read |

### `items_drawings`

| Column | Declared | Serialized | Holds |
|---|---|---|---|
| `id` | INTEGER PRIMARY KEY | — | the item id this row describes |
| `strokes` | BLOB | `QList<GraphicsDrawItem::Stroke>` | the whole drawing, in one cell |

### `items_notes`

| Column | Declared | Serialized | Holds |
|---|---|---|---|
| `text_color` | TEXT | — | the default colour, used when the HTML carries none |
| `id` | INTEGER PRIMARY KEY | — | the item id this row describes |
| `fixed_size` | TEXT | `QSizeF` | (-1, -1) means the note sizes itself to its text |
| `background_color` | TEXT | — | #AARRGGBB or #RRGGBB, empty for the default |
| `text` | TEXT | — | Qt rich text, not plain text |
| `style` | INTEGER | — | 0 Comfortable, 1 Compact; other values render like Compact |

### `items_groups`

| Column | Declared | Serialized | Holds |
|---|---|---|---|
| `id` | INTEGER PRIMARY KEY | — | the item id this row describes |
| `background_color` | TEXT | — | #AARRGGBB; the geometry comes from the children |
| `lock_mode` | INTEGER | — | GraphicsGroupItem::LockMode: 0 Open, 1 Closed |
<!-- end generated -->

An item's kind comes from which subtype table holds its id. `items.parent` is
`-1` for a root. `items.z` and `items.sort_order` are renumbered to `1..n` per
parent on every save PureRef does, so small integers are all a writer needs.

## Serialized cells

`transform`, `sort_order`, `image_transform`, `image_bounds`, `fixed_size`,
`scene_rect`, `view_transform` and `strokes` are declared `BLOB` but stored with
storage class **TEXT**: each payload byte was mapped to the code point of the
same value, so `value.encode('latin1')` recovers the bytes. Image data and
thumbnails are real BLOBs; names, paths, HTML and color strings are ordinary
text.

Each payload is a QDataStream QVariant: `uint32 type_id`, `uint8 is_null`, then
for `type_id 1024` a NUL-terminated registered type name, then the value.

| Type | Payload |
|---|---|
| 20 `QRectF` | doubles x, y, width, height |
| 22 `QSizeF` | doubles width, height; `(-1,-1)` means automatic |
| 80 `QTransform` | nine doubles `m11 m12 m13 m21 m22 m23 m31 m32 m33` |
| 1024 `QPainterPath` | element count, then `int32 kind, double x, double y` each, then subpath index and fill rule |
| 1024 `BigRational` | two big integers: numerator then denominator |
| 1024 `QList<GraphicsDrawItem::Stroke>` | stroke count, then the strokes below |

`items.comment` is not a number despite its `INTEGER` declaration: it holds the
comment text an item carries (`GraphicsItem::setComment(const QString&)`), shown
in the item's tooltip. SQLite's integer affinity means a comment that looks like
a number is stored as one, so `'42'` comes back as `42`.

`QPainterPath` element kinds: 0 move-to, 1 line-to, 2 first cubic control point,
3 cubic continuation (two of them per curve).

### BigRational

Each of the two integers is:

```text
uint32 sign           1 positive, 0 zero, 0xffffffff negative
uint64 block count
uint32 blocks[]       least significant block first
```

Verified by ordering: six images given the orders `-3`, `0`, `3`, `7/2`, `5` and
`2³²` were exported by PureRef in exactly that ascending sequence.

### Strokes

The application exports its own stream operators for `GraphicsDrawItem::Stroke`,
and disassembling them gives the struct exactly:

```text
int8   version                 -- 100; a lower value means something else, below
int8   1                       -- QColor RGB
uint16 alpha, red, green, blue, 0
double width
QPainterPath                   -- no QVariant wrapper here
double point_x, point_y        -- QPointF, (0, 0) in every saved file
int32  style                   -- only present when version > 99
```

Channels are `value * 257` of an 8-bit channel.

`style` is the stroke's appearance: **0** solid with rounded ends (all PureRef
2.0.3 and 2.1.3 ever write, for freehand and straight strokes alike), **1**
dashed, **2** solid with square ends — the same three renders in both 2.x
releases. It is not the drawing tool: 2.1 registers
`DrawToolbar::Shape { Line, Ellipse, Rectangle }` and can draw those, but this
struct and the schema are unchanged from 2.0.3, so a shape has to be stored as
ordinary `QPainterPath` geometry. Style 2 also widens the item's bounding
rectangle — `GraphicsDrawItem::strokeStyleExtraBounds` returns an empty rectangle
for every other style and expands the path's end points by the stroke width for
this one. Other values draw like 0.

`version` below 100 is not a version at all: the reader seeks one byte back and
reads that byte as the start of the QColor, then skips the trailing `style`. That
is the layout from before the version byte existed, and PureRef still loads it
and rewrites it as version 100. It is also why a bogus marker produces garbage
rather than an error — a QColor spec of 200 is not RGB.

`point` is transient state the application keeps while a stroke is being drawn;
saved files always carry (0, 0) and a real coordinate there changes nothing.

## Images and instances

`images.source_type` is `1` for embedded data and `2` for a linked file
(`data` and `checksum` NULL, path in `source` and `origin`), and it has no other
values: `SceneSerializerSqlite::storeImage` binds 1 when it deduplicates by
checksum and 2 when it deduplicates by path. Web images are downloaded and
embedded, with the URL left in `origin`/`source`.

When a linked file has moved, PureRef retries the path under the `.pur`'s own
folder, dropping leading components one at a time: for `/tmp/gone/wanted.png`
beside `board.pur` it tries `<folder>/tmp/gone/wanted.png`, then
`<folder>/gone/wanted.png`, then `<folder>/wanted.png`. On a hit it rewrites
`source` and `origin` to what it found; otherwise the item renders as a
missing-image placeholder. A copy in an unrelated subfolder is not found.

`format` is not normalized: it is the lowercase file extension when the image
came from a path and the uppercase detected format otherwise. With
`AutoDownscale` enabled, imports are reduced before they are stored — a 3000×2000
PNG with a 512 limit becomes 512×342 re-encoded bytes — and nothing in the row
says so; mip levels live in PureRef's own cache directory, not in the file.

An instance's `image_transform` maps image pixels into item coordinates and
translates by `(-width/2, -height/2)`, so **an image item's position is its
center**. `image_bounds` is the visible outline in those centered pixel
coordinates: a closed five-point rectangle unless cropped. For a crop
`(left, top, width, height)` in source pixels:

```text
x0 = left - width/2        x1 = x0 + crop width
y0 = top  - height/2       y1 = y0 + crop height
```

`flags` is a render-flag bitmask: `0x1` bilinear sampling (PureRef's default;
`0` renders nearest-neighbour), `0x2` the grayscale filter. There are no other
bits: `setRenderFlags` stores the word untouched and only reacts to `0x2`, and
every other read of it masks `& 0x1` into
`QPainter::setRenderHint(SmoothPixmapTransform, …)` or `>> 1 & 0x1` into the
image cache. Higher bits survive a re-save and do nothing.

`playback_state` is `0` for stills, `2` paused at `playback_frame` — the only
state where that frame is rendered — and `3` playing, which is what PureRef
writes for an animated GIF. It is not the `Movie::State` enum the binary
registers (`NotRunning`, `Paused`, `Running` = 0, 1, 2); the stored values sit one
higher, so `0` means "not an animation" rather than "stopped".

## Notes, groups, drawings

`items_notes.text` is Qt rich text. `text_color` is the default color, used when
the HTML carries none and overridden by an inline color. `background_color`
takes `#AARRGGBB` with the alpha honored, or `''` for the default. `style` is
`0` Comfortable or `1` Compact.

`items_groups` holds only a background color and `lock_mode`. That is
`GraphicsGroupItem::LockMode`, and since the enum is registered its keys are
readable straight out of the binary's meta object: **`Open = 0`, `Closed = 1`**,
with no third mode. Closed is PureRef's default and makes a click select the
group instead of the child. Group geometry comes from the children.

`items_drawings.strokes` is the stroke list above; the item's transform places
it, and the paths are in item coordinates.

## Metadata

One row with `id = 0`. `scene_rect` is the scene's bounding rectangle including
the origin — a single 64×32 image centred at (100, 200) gives `(0, 0, 132, 216)`
— and a file converted from 1.x keeps the old 1.x canvas corner in it, which is
how converted scenes end up with `(-10000, -10000, …)`. Leaving it NULL makes
PureRef compute the framing, which is what `pureref` does for scenes that did not
come from a 2.x file: a 1.x canvas is a scrollable area, not a content rectangle.

`view_transform` carries the zoom, `horizontal_scroll` and `vertical_scroll` the
pan. The rest is save bookkeeping PureRef fills in again on its next save:
`last_save_path` is the last save's directory, `last_load_path` the path the
scene is associated with (its own, after a save), `last_load_checksum` the header
checksum of the file the scene was loaded from — so PureRef can tell whether the
file on disk changed underneath it — and `saved` is 0 when the scene had never
been associated with a `.pur` before this save.

An [ImHex](https://imhex.werwolv.net) pattern for this container is in
[pur.hexpat](../pur.hexpat): it reassembles the displaced database into a section
and hands it over as a `scene.sqlite` virtual file, so the tables can be opened
in any SQLite browser.
