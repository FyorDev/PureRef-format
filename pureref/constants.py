"""The values both formats store as plain numbers, and what they mean.

Every one of these was read out of PureRef itself -- the registered Qt enums in
the binary, or a probe that wrote a value and looked at what came back -- rather
than guessed; docs/format-v1.md and docs/format-v2.md say which.
"""
from __future__ import annotations

# Version tags accepted by the writers; `latest` resolves to the newest one.
VERSION_1 = '1.10'
VERSION_2_0 = '2.0'
VERSION_2_1 = '2.1'
VERSIONS = (VERSION_1, VERSION_2_0, VERSION_2_1)
LATEST = VERSION_2_1

# items_images.flags, GraphicsImageItem::RenderFlag.
RENDER_SMOOTH = 0x1
RENDER_GRAYSCALE = 0x2

# items_images.playback_state.
PLAYBACK_STATIC = 0
PLAYBACK_STOPPED = 1
PLAYBACK_PAUSED = 2
PLAYBACK_PLAYING = 3

# items_groups.lock_mode.
LOCK_OPEN = 0
LOCK_CLOSED = 1

# Stroke.style, the trailing int of a serialized stroke.
STROKE_ROUND = 0      # solid, rounded ends: what PureRef writes
STROKE_DASHED = 1
STROKE_FLAT = 2       # solid, square ends, which widens the item's bounds

# items_notes.style. Only these two exist; PureRef renders anything else like
# Compact, and this package keeps such a value on the item rather than in `style`.
NOTE_COMFORTABLE = 'comfortable'
NOTE_COMPACT = 'compact'
NOTE_STYLES = {NOTE_COMFORTABLE: 0, NOTE_COMPACT: 1}
NOTE_STYLE_NAMES = {stored: name for name, stored in NOTE_STYLES.items()}
