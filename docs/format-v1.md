# The PureRef 1.10 / 1.11.1 `.pur` format

Everything here was derived from files written by PureRef 1.10 and 1.11.1 and is
implemented in `pureref/v1`. PureRef 1.11.1 still writes `1.10` in the header, so
that string is a format version, not an application version.

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

| Offset | Size | Meaning |
|---:|---:|---|
| 0 | 4 | `00 00 00 08`, the byte length of the version string |
| 4 | 8 | UTF-16BE `1.10` |
| 12 | 2 | number of image items plus root note items |
| 14 | 2 | number of image items |
| 16 | 8 | offset where the reference table starts |
| 24 | 4 | `00 00 00 0c`, the byte length of the application-version string |
| 28 | 12 | UTF-16BE application version; PureRef-format leaves this zero-filled and PureRef accepts it |
| 40 | 4 | `00 00 00 40`, the byte length of the checksum string |
| 44 | 64 | UTF-16BE lowercase MD5 hex of everything from offset 108 on |
| 108 | 4 | number of item ids |
| 112 | 32 | canvas rectangle: four doubles |
| 144 | 8 | view zoom |
| 176 | 8 | view zoom again, for the vertical axis |
| 208 | 8 | zoom multiplier, always `1.0` |
| 216 | 4 | view x, int32 |
| 220 | 4 | view y, int32 |

The remaining header bytes are zero in everything observed. `pureref` keeps the
header it read and only rewrites the fields above, so unknown values survive a
load and save.

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
  source path instead. PureRef 2.x re-saves such an image as `source_type = 2`,
  its own linked-resource form.
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
uint32  0                       -- only when the image was brute-force loaded
QString source                  -- "BruteForceLoaded" for recovered images
QString name                    -- omitted for brute-force loaded images
double  1.0
6d      m11 m12 m13 m21 m22 m23 -- the linear part of the transform
2d      x y                     -- the image's center on the canvas
double  1.0
uint32  item id
double  z
6d      matrix before cropping
2d      crop offset
double  crop scale
uint32  crop point count
        per point: uint32 kind (0 for the first, 1 after), double x, double y
double  0.0
uint32  1
int8    0
int64   -1
uint32  number of note children
```

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
QString text                    -- plain text, not HTML
6d      linear part of the transform
2d      x y
double  1.0
uint32  item id
double  z
int8    color kind              -- 1 = RGB, 2 = HSV
uint16  opacity                 -- 16-bit, 0xffff is opaque
3x u16  red green blue          -- or hue saturation value when kind is 2
uint16  0
int8    background color kind
uint16  background opacity      -- PureRef's default is 5000
3x u16  background red green blue
uint16  0
uint32  number of note children
```

Colors are 16 bits per channel: `channel * 257` of an 8-bit value. HSV hue is
scaled to 35900. `pureref` normalizes HSV to RGB on read and writes the RGB form,
keeping the original 16-bit values in `extras` so unmodified files round-trip
byte for byte.

## Folder string and reference table

After the last item comes one `QString` with the folder a file was last loaded
from, and the header's offset field points just past it. From there to the end of
the file:

```text
uint32  item id
uint64  start address of that item's image data or instance slot
uint64  end address
```

One record per image item. Note items are not referenced.

## Checksum

```python
md5(file[108:]).hexdigest()
```

written as UTF-16BE at offset 44. It covers the item-id count, the canvas, the
view, and every section after the header. Getting this wrong is what made early
versions of this project produce files PureRef opened with a corruption warning.

## What 1.x does not have

Groups, drawings, per-item opacity, rich-text notes, render flags, animation and
non-PNG image data all arrived with 2.x. `Scene.losses('1.10')` lists whichever
of them a scene uses before you write it.
