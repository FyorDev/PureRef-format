# Fixtures

Every `.pur` here was written by PureRef itself unless the entry says otherwise,
which is what makes the byte-exact round-trip tests meaningful: the target is the
application's own output, not this package's. Re-recording one means saving the
described scene in that release and copying the file in — and then the round-trip
tests say whether anything was lost.

| File | Format | Written by | Contents |
|---|---|---|---|
| `legacy-1.10.pur` | 1.10 | PureRef 1.10 (the original fixture this project started from) | three images, no application-version string |
| `app-1.10.4.pur` | 1.10 | PureRef 1.10.4 | two images, one at 0.5 opacity |
| `app-1.11.1.pur` | 1.10 | PureRef 1.11.1 | the same scene, to show 1.11.1 differs only in the version string and checksum |
| `envelope-2.0.pur` | 2.0 | PureRef 2.0.0 | one image; the only fixture in the 2.0 envelope, which has no thumbnail field |
| `app-2.0.3-image.pur` | 2.1 | PureRef 2.0.3 | one embedded image |
| `app-2.0.3-linked.pur` | 2.1 | PureRef 2.0.3 | one linked image: `source_type = 2`, no data |
| `app-2.0.3-anim.pur` | 2.1 | PureRef 2.0.3 | an animated GIF, with playback state |
| `app-2.0.3-comment.pur` | 2.1 | PureRef 2.0.3 | three images, one carrying a comment |
| `app-2.0.3-dashed.pur` | 2.1 | PureRef 2.0.3 | two drawings, one dashed and one square-capped, for the stroke styles |
| `app-2.0.3-mixed.pur` | 2.1 | PureRef 2.0.3 | two images, a note, a group and a drawing: the widest scene |
| `legacy-stroke.pur` | 2.1 | this package | a stroke in the pre-version layout, where the first byte is the QColor rather than a version |

PureRef 2.0.3 already writes the `2.1` envelope; `2.0` is the earlier layout, so
the file names say which release saved a file and the Format column says which
envelope it is in.

## Images

Synthetic and tiny, so they can live in git: `red.png`, `blue.png`, `tiny.png`,
`alpha.png` (with an alpha channel), `red.jpg` (for the 1.x PNG-only path) and
`anim.gif` (two frames, for playback).
