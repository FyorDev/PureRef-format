"""A damaged file may be refused, but it may not crash the reader.

Every fixture is truncated at many lengths and bit-flipped at many offsets, and
each result has to come back as a `Scene` -- with `problems` when something was
not understood -- or as `FormatError`. Anything else (an IndexError, a
struct.error, a sqlite3 error escaping, a MemoryError from a bogus count) is a
bug in a reader, because the input is attacker-supplied as far as this package
is concerned.
"""
import unittest
from pathlib import Path

import pureref
from pureref.model import Scene
from pureref.qt import FormatError

FIXTURES = Path(__file__).parent / 'fixtures'
PUR_FILES = sorted(FIXTURES.glob('*.pur'))


def attempt(case, data):
    """Read `data`, allowing only a Scene or a FormatError."""
    try:
        scene = pureref.read_bytes(data)
    except FormatError:
        return None
    except Exception as error:                  # noqa: BLE001 - that is the point
        raise AssertionError(
            f'{type(error).__name__} escaped instead of FormatError: {error}') from error
    case.assertIsInstance(scene, Scene)
    return scene


class TruncationTests(unittest.TestCase):
    def test_every_prefix_of_every_fixture(self):
        for path in PUR_FILES:
            data = path.read_bytes()
            lengths = sorted({0, 1, 16, 100, 108, 223, 224, len(data) // 3,
                              len(data) // 2, len(data) - 1})
            for length in lengths:
                if length >= len(data):
                    continue
                with self.subTest(file=path.name, length=length):
                    attempt(self, data[:length])


class BitFlipTests(unittest.TestCase):
    def test_flipping_a_bit_anywhere_never_crashes(self):
        for path in PUR_FILES:
            data = bytearray(path.read_bytes())
            step = 1 if len(data) <= 4096 else max(1, len(data) // 512)
            for offset in range(0, len(data), step):
                for bit in (0x01, 0x80):
                    damaged = bytearray(data)
                    damaged[offset] ^= bit
                    with self.subTest(file=path.name, offset=offset, bit=bit):
                        attempt(self, bytes(damaged))


class WriteBackTests(unittest.TestCase):
    """Whatever survives reading has to survive writing, too."""

    def test_a_damaged_but_readable_file_can_still_be_written(self):
        written = 0
        for path in PUR_FILES:
            data = bytearray(path.read_bytes())
            step = max(1, len(data) // 16)
            for offset in range(0, len(data), step):
                damaged = bytearray(data)
                damaged[offset] ^= 0x01
                scene = attempt(self, bytes(damaged))
                if scene is None:
                    continue
                with self.subTest(file=path.name, offset=offset):
                    version = scene.source_version or '2.1'
                    try:
                        pureref.write_bytes(scene, version=version)
                    except (FormatError, ValueError):
                        continue        # a refusal with a reason is acceptable
                    written += 1
        self.assertGreater(written, 0, 'nothing was readable enough to write back')


class GarbageTests(unittest.TestCase):
    def test_inputs_that_are_not_pur_files_at_all(self):
        for data in (b'', b'\0' * 8, b'SQLite format 3\0', b'not a pur file',
                     bytes(range(256)) * 4, (FIXTURES / 'red.png').read_bytes()):
            with self.subTest(head=data[:8]), self.assertRaises(FormatError):
                pureref.read_bytes(data)


if __name__ == '__main__':
    unittest.main()
