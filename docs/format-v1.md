# The PureRef 1.10 / 1.11.1 `.pur` format

Everything here was derived from files written by PureRef 1.10.4 and 1.11.1, and
checked by loading this package's output back into both of them; it is
implemented in `pureref/v1`. PureRef 1.11.1 still writes `1.10` in the header, so
that string is a format version, not an application version — the application's
own version sits twelve bytes later.

For the same scene, 1.10.4 and 1.11.1 produce byte-identical files apart from
that application-version string and the checksum that covers it.

All integers are big-endian; reals are IEEE-754 binary64. Strings are Qt
`QString`s: a `uint32` **byte** count followed by UTF-16BE code units, where
`0xffffffff` means null.

The file is five sections, in order:

```text
header          224 bytes, fixed offsets
image section   embedded PNGs, each followed by one slot per extra instance
items           image items and note items, nested children after their parent
folder string   the last folder a file was loaded from
references      one 20-byte record per image item
```

## Header

<!-- generated: header -->
| Offset | Size | Field | Encoding | Meaning |
|---:|---:|---|---|---|
| 0 | 4 | `_version_length` | uint32 | byte length of the version string |
| 4 | 8 | `_version` | 8 bytes | UTF-16BE "1.10" — the format version, which 1.11.1 still writes |
| 12 | 2 | `item_count` | uint16 | image items plus root note items |
| 14 | 2 | `image_count` | uint16 | image items |
| 16 | 8 | `reference_offset` | uint64 | where the reference table starts |
| 24 | 4 | `_application_length` | uint32 | byte length of the application-version string |
| 28 | 12 | `application_version` | 12 bytes | UTF-16BE "1.10.4" or "1.11.1"; PureRef accepts it zero-filled |
| 40 | 4 | `_checksum_length` | uint32 | byte length of the checksum string |
| 44 | 64 | `checksum` | 64 bytes | UTF-16BE MD5 hex of everything from offset 108 |
| 108 | 4 | `id_count` | uint32 | number of item ids |
| 112 | 32 | `canvas` | four doubles | canvas rectangle |
| 144 | 8 | `zoom` | double | view zoom |
| 152 | 24 | `_unknown_152` | 24 bytes | zero in every observed file; preserved |
| 176 | 8 | `zoom_y` | double | view zoom again, vertically |
| 184 | 24 | `_unknown_184` | 24 bytes | zero in every observed file; preserved |
| 208 | 8 | `zoom_multiplier` | double | always 1.0 |
| 216 | 4 | `view_x` | int32 | view x |
| 220 | 4 | `view_y` | int32 | view y |

Total: 224 bytes.
<!-- end generated -->

The application version is `1.10.4` or `1.11.1`, six characters exactly; this
package writes back whatever it read and zero-fills it for new files, which
PureRef accepts.

The remaining header bytes are zero in everything observed, and PureRef preserves
whatever is there: a file written with `0xAA` through bytes 152-175 and `0xBB`
through 184-207 comes back with both runs intact. `pureref` keeps the header it
read and only rewrites the fields above, so unknown values survive a load and
save.

This layout is the same idea as the 2.x envelope — version string, counts, an
offset, an application-version string, an MD5 checksum string — which makes the
2.x header look like a direct descendant. See [format-v2.md](format-v2.md).

## Image section

Image data is **PNG only**: the reader finds images by scanning for the PNG
signature `89 50 4E 47 0D 0A 1A 0A` and reads through the `IEND` chunk. Writing
a JPEG or GIF here produces a file PureRef cannot open, so `pureref` re-encodes
other formats (Pillow) or refuses.

Between the PNGs sit four-byte slots:

* `FF FF FF FF` — a **linked** image: no data in the file, loaded from the item's
  source path instead. PureRef 1.x resolves the path on load and **embeds the
  file on its next save**, so the link does not survive a 1.x round trip; PureRef
  2.x instead keeps it as `source_type = 2`, its own linked-resource form.
* any other value — another **instance** of the image that owns the preceding
  PNG, holding the id of the item that owns it.

Both kinds of slot are addressable, which is what the reference table points at.

**Ordering matters.** PureRef pairs the image section with the reference table in
address order: if an item's id goes backwards relative to its address, the file
is rejected with "Corrupt image data sections encountered". `pureref` therefore
groups every instance under the image it shares and assigns ids in that order,
the same order PureRef writes.

## Items

Each item block starts with a `uint64` holding the absolute offset just past its
own fields, followed by a `uint32` byte length and the class name. The length is
how items are recognized: `34` for `GraphicsImageItem`, `32` for
`GraphicsTextItem`. Children are written after the parent's block, and the
parent's field count says how many to expect.

### Image item

```text
uint64  end offset
uint32  34
34      UTF-16BE "GraphicsImageItem"
```

then, in order:

<!-- generated: image-item -->
| Field | Encoding | Meaning |
|---|---|---|
| `brute_force` | uint32 0, only when present | four zero bytes, present for an image recovered by brute force |
| `source` | QString or -1 for none | "BruteForceLoaded" for recovered images |
| `name` | QString or -1 for none | omitted entirely for brute-force loaded images |
| `opacity` | double | 1.0 when opaque; PureRef stores it as a float |
| `linear` | six doubles: m11 m12 m13 m21 m22 m23 | the linear part of the transform; m13 and m23 are rewritten as 0 |
| `position` | two doubles: x, y | the image centre on the canvas |
| `_constant_one` | double | rewritten as 1.0 whatever it held |
| `id` | uint32 | item id |
| `z` | double | stacking |
| `before_crop` | six doubles: m11 m12 m13 m21 m22 m23 | the transform before cropping, for "reset cropping" |
| `crop_offset` | two doubles: x, y | crop offset |
| `crop_scale` | double | crop scale |
| `bounds` | uint32 count, then uint32 kind and two doubles each | the crop outline, closed, in centred pixel coordinates |
| `_tail` | 21 bytes | PureRef writes 0.0, 1, 0, 2000, 2000; kept, no observed effect |
| `children` | uint32 | number of note children |
<!-- end generated -->

**`opacity` was long read as a constant.** Writing 1.0, 0.5 and 0.15
renders the three images at full, half and near-transparent, and PureRef writes
the value back — as single precision, so 0.15 returns as
`0.15000000596046448`. Every file PureRef itself writes has 1.0 there, which is
why it reads like a constant. The double *after* the position is a constant: any
other value is rewritten as 1.0.

`m13` and `m23` are stored but not kept: values of 0.5 and 0.75 come back as 0,
so the transform is affine in practice.

The `_tail` block is stored state PureRef hands back unchanged (it rewrote only
the `int8`, normalising 3 to 1). PureRef writes `2000, 2000` where this
package's predecessor wrote `-1` as an `int64`, and both load; varying any of it
changes nothing on screen, including the render of a large image, so it is not a
resolution limit that affects drawing.

The crop points are a closed outline in centered pixel coordinates: an uncropped
64×32 image spans `(-32,-16)` to `(32,16)`, which is also how 2.x stores
`image_bounds`. The scale in the transform maps those pixels onto the canvas, so
the on-canvas size is the outline's span times the transform.

The crop outline is the only record of an image's pixel size in 1.x; `pureref`
prefers the size in the embedded PNG header and falls back to the outline.

### Note item

```text
uint64  end offset
uint32  32
32      UTF-16BE "GraphicsTextItem"
```

then, in order:

<!-- generated: note-item -->
| Field | Encoding | Meaning |
|---|---|---|
| `text` | QString | plain text, not HTML |
| `linear` | six doubles: m11 m12 m13 m21 m22 m23 | the linear part of the transform |
| `position` | two doubles: x, y | position on the canvas |
| `_constant_one` | double | rewritten as 1.0 whatever it held |
| `id` | uint32 | item id |
| `z` | double | stacking |
| `foreground_kind` | int8 | 1 = RGB, 2 = HSV |
| `foreground_opacity` | uint16 | 16-bit alpha |
| `foreground_rgb` | three uint16 channels | red green blue, or hue saturation value when the kind is 2 |
| `_colour_gap` | 2 bytes | zero in every observed file |
| `background_kind` | int8 | 1 = RGB, 2 = HSV |
| `background_opacity` | uint16 | 16-bit alpha; PureRef defaults to 5000 |
| `background_rgb` | three uint16 channels | background channels |
| `_tail` | 2 bytes | zero in every observed file, and it belongs before the count |
| `children` | uint32 | number of note children |
<!-- end generated -->

Colors are 16 bits per channel: `channel * 257` of an 8-bit value. HSV hue is
scaled to 35900. `pureref` normalizes HSV to RGB on read and writes the RGB form,
keeping the original 16-bit values on `item.v1` so unmodified files round-trip
byte for byte.

## Folder string and reference table

After the last item comes one `QString` with the folder a file was last loaded
from, and the header's offset field points just past it. From there to the end of
the file:

<!-- generated: reference -->
| Offset | Size | Field | Encoding | Meaning |
|---:|---:|---|---|---|
| 0 | 4 | `id` | uint32 | image item id |
| 4 | 8 | `start` | uint64 | start of its image data or instance slot |
| 12 | 8 | `end` | uint64 | end of the same |

Total: 20 bytes.
<!-- end generated -->

One record per image item. Note items are not referenced.

## Checksum

```python
md5(file[108:]).hexdigest()
```

written as UTF-16BE at offset 44. It covers the item-id count, the canvas, the
view, and every section after the header. Getting this wrong is what made early
versions of this project produce files PureRef opened with a corruption warning.

## Version history

PureRef 2.x still contains the whole legacy loader family, and its symbol names
lay the history out: `load12`, `load13`, `load14`, `load15` and `load110`, plus
per-item readers `loadSingleItemMetadata16`, `17`, `18` and a current one. The
item record's layout is chosen by the version string in the header —
`1.7` selects reader 16, `1.8` selects 17, `1.9` selects 18, and anything from
`1.9` up uses the current one. A `1.10` file therefore uses the newest item
layout, which is the one described above and the only one this package
implements. 2.x can also still *write* this format (`savePurBinary`), which is
what the "overwrite old format" prompt is about.

## Where these answers come from

1.x is a 2 MB binary against shared Qt 5.12 that exports none of its internals
and registers no `Q_ENUM`s, so unlike the 2.x notes, none of the field meanings
above could be read out of the code: each was settled by writing a value, loading
the file in 1.10.4 and 1.11.1, looking at what they render, and reading back what
they save.

Its meta objects are not completely empty, though — the 150 slots and signals in
1.11.1 carry their declared types, which is how `ImageLoader::load(QStringList
urls, float x, float y, LoadJob*)` shows that load coordinates are floats, and
that `setAutoDownscale`, `setAutoDownscaleMaxWidth` and `setDefaultNoteColor`
already existed in 1.x.

## The clipboard carries this format too

PureRef copies items to the clipboard under the mime type `pureref/binary`, in
every release from 1.10.4 to 2.1.3. The payload is a `QDataStream` holding the
sending instance's key, an item count, a `QRectF` of the selection, and then item
records written by the same `writeItemMetadata` the 1.x file writer uses — so a
reader for the item blocks above is most of a paste parser. Image pixels are not
in the payload: the receiving instance asks the sender for them over a local
socket, which is why pasting between different PureRef versions is refused.

## What 1.x does not have

Groups, drawings, rich-text notes, render flags, animation, item comments and
non-PNG image data all arrived with 2.x. Image opacity did not: it is the field
above. `Scene.losses('1.10')` lists whichever of the missing ones a scene uses
before you write it.
