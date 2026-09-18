"""The record declarations, and the codecs they are built from."""
import unittest

from pureref.qt import Cursor, FormatError, Path
from pureref.records import (F64, U16, U32, Field, Matrix6, NullableUtf16String,
                             PointF, Raw, Record, Utf16String, ZeroMarker)
from pureref.v1 import records as v1


class CodecTests(unittest.TestCase):
    def round_trip(self, codec, value):
        buffer = bytearray()
        codec.write(buffer, value)
        return codec.read(Cursor(bytes(buffer))), bytes(buffer)

    def test_scalars_and_tuples(self):
        self.assertEqual(self.round_trip(U32, 4294967295)[0], 4294967295)
        self.assertEqual(self.round_trip(F64, -0.5)[0], -0.5)
        self.assertEqual(self.round_trip(PointF, (1.5, -2.5))[0], (1.5, -2.5))
        self.assertEqual(len(self.round_trip(Matrix6, (1, 2, 3, 4, 5, 6))[1]), 48)

    def test_raw_keeps_and_pads(self):
        value, written = self.round_trip(Raw(4), b'\x01\x02')
        self.assertEqual(written, b'\x01\x02\x00\x00')
        self.assertEqual(value, b'\x01\x02\x00\x00')
        with self.assertRaises(ValueError):
            Raw(2).write(bytearray(), b'\x01\x02\x03')

    def test_strings(self):
        self.assertEqual(self.round_trip(Utf16String(), 'Ω 中')[0], 'Ω 中')
        self.assertIsNone(self.round_trip(NullableUtf16String(), None)[0])
        self.assertEqual(self.round_trip(NullableUtf16String(), '')[0], '')

    def test_the_zero_marker_is_there_or_not(self):
        present, written = self.round_trip(ZeroMarker(), True)
        self.assertEqual(written, b'\x00\x00\x00\x00')
        self.assertTrue(present)
        buffer = bytearray()
        ZeroMarker().write(buffer, False)
        self.assertEqual(bytes(buffer), b'')

    def test_a_truncated_field_says_which_one(self):
        record = Record('probe', [Field('first', U32), Field('second', U32)])
        with self.assertRaises(FormatError) as caught:
            record.read(Cursor(b'\x00\x00\x00\x01'))
        self.assertIn('probe.second', str(caught.exception))


class RecordTests(unittest.TestCase):
    def test_conditional_fields_are_skipped_but_still_present(self):
        record = Record('probe', [
            Field('flag', ZeroMarker(), default=False),
            Field('value', U16, default=7, when=lambda values: not values['flag']),
        ])
        # the flag is set, so the value is not in the bytes at all
        written = record.to_bytes({'flag': True, 'value': 9})
        self.assertEqual(written, b'\x00\x00\x00\x00')
        values = record.read(Cursor(written))
        self.assertEqual((values['flag'], values['value']), (True, 7))

    def test_defaults_fill_in_what_a_caller_omits(self):
        record = Record('probe', [Field('value', U32, default=42)])
        self.assertEqual(record.read(Cursor(record.to_bytes({})))['value'], 42)

    def test_describe_is_the_documentation_source(self):
        rows = v1.IMAGE_ITEM.describe()
        names = [name for name, _, _ in rows]
        self.assertIn('opacity', names)
        self.assertIn('_tail', names)
        self.assertTrue(all(isinstance(note, str) for _, _, note in rows))


class LayoutTests(unittest.TestCase):
    """The declarations have to match the format, and they are the only copy."""

    def test_the_header_is_exactly_224_bytes(self):
        self.assertEqual(v1.HEADER.size, 224)

    def test_a_reference_record_is_20_bytes(self):
        self.assertEqual(v1.REFERENCE.size, 20)

    def test_the_note_gap_precedes_the_child_count(self):
        names = [name for name, _, _ in v1.NOTE_ITEM.describe()]
        self.assertEqual(names[-2:], ['_tail', 'children'])
        self.assertLess(names.index('_colour_gap'), names.index('background_kind'))

    def test_the_image_record_round_trips_through_itself(self):
        values = {'source': '/tmp/x.png', 'name': 'x', 'opacity': 0.25, 'id': 3,
                  'z': 2.0, 'bounds': Path.centered_rectangle(64, 32),
                  '_tail': bytes(range(21)), 'children': 0}
        written = v1.IMAGE_ITEM.to_bytes(values)
        again = v1.IMAGE_ITEM.read(Cursor(written))
        for name in ('source', 'name', 'opacity', 'id', 'z', '_tail', 'children'):
            self.assertEqual(again[name], values[name], name)
        self.assertEqual(again['bounds'].elements, values['bounds'].elements)
        self.assertEqual(v1.IMAGE_ITEM.to_bytes(again), written)

    def test_the_outline_rejects_an_implausible_count(self):
        import struct
        with self.assertRaises(FormatError):
            v1.CropOutline().read(Cursor(struct.pack('>I', 0x7FFFFFFF)))


if __name__ == '__main__':
    unittest.main()
