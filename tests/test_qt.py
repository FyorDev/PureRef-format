"""The Qt primitives both formats are built from."""
import struct
import unittest
from fractions import Fraction

from pureref.qt import (Cursor, FormatError, Path, big_rational_cell, bytes_to_cell,
                        cell_to_bytes, pack_big_integer, pack_bytes, pack_string,
                        read_big_integer, read_big_rational, read_variant_header,
                        transform_cell)


class StringTests(unittest.TestCase):
    def test_strings_count_bytes_not_characters(self):
        packed = pack_string('Ω中')
        self.assertEqual(struct.unpack('>I', packed[:4])[0], 4)
        self.assertEqual(Cursor(packed).read_string(), 'Ω中')

    def test_null_and_empty_are_different(self):
        self.assertIsNone(Cursor(pack_string(None)).read_string())
        self.assertEqual(Cursor(pack_string('')).read_string(), '')
        self.assertIsNone(Cursor(pack_bytes(None)).read_bytes())
        self.assertEqual(Cursor(pack_bytes(b'')).read_bytes(), b'')

    def test_truncation_is_reported(self):
        packed = pack_string('hello')
        with self.assertRaises(FormatError):
            Cursor(packed[:-2]).read_string()

    def test_odd_length_is_not_utf16(self):
        with self.assertRaises(FormatError):
            Cursor(struct.pack('>I', 3) + b'abc').read_string()


class CellTests(unittest.TestCase):
    def test_payload_survives_the_latin1_round_trip(self):
        payload = bytes(range(256)) + b'\0\0trailing'
        self.assertEqual(cell_to_bytes(bytes_to_cell(payload)), payload)

    def test_blob_cells_pass_through(self):
        self.assertEqual(cell_to_bytes(b'\x89PNG'), b'\x89PNG')
        self.assertEqual(cell_to_bytes(None), b'')


class BigRationalTests(unittest.TestCase):
    values = [0, 1, -1, 3, -3, 2 ** 32, -(2 ** 32) - 5, 2 ** 96 + 7]

    def test_big_integers_round_trip(self):
        for value in self.values:
            with self.subTest(value=value):
                self.assertEqual(read_big_integer(Cursor(pack_big_integer(value))), value)

    def test_blocks_are_least_significant_first(self):
        packed = pack_big_integer(2 ** 32)
        self.assertEqual(struct.unpack('>IQ2I', packed), (1, 2, 0, 1))

    def test_rationals_round_trip(self):
        for numerator, denominator in [(1, 1), (0, 1), (-3, 1), (7, 2), (2 ** 40, 3)]:
            with self.subTest(value=(numerator, denominator)):
                cursor = Cursor(cell_to_bytes(big_rational_cell(
                    Fraction(numerator, denominator))))
                read_variant_header(cursor)
                self.assertEqual(read_big_rational(cursor),
                                 Fraction(numerator, denominator))

    def test_one_matches_the_shape_PureRef_writes(self):
        cursor = Cursor(cell_to_bytes(big_rational_cell(1)))
        type_id, is_null, name = read_variant_header(cursor)
        self.assertEqual((type_id, is_null, name), (1024, False, 'BigRational'))
        # sign, block count, block, twice: the 1/1 that PureRef stores for the
        # first sibling of a parent.
        self.assertEqual(struct.unpack('>IQIIQI', cursor.take(32)),
                         (1, 1, 1, 1, 1, 1))


class PathTests(unittest.TestCase):
    def test_rectangle_is_closed(self):
        path = Path.centered_rectangle(64, 32)
        self.assertEqual(path.elements[0], (0, -32.0, -16.0))
        self.assertEqual(path.elements[0][1:], path.elements[-1][1:])
        self.assertEqual(path.bounding_box(), (-32.0, -16.0, 32.0, 16.0))

    def test_round_trip(self):
        path = Path([(0, 1.0, 2.0), (2, 3.0, 4.0), (3, 5.0, 6.0), (3, 7.0, 8.0)],
                    subpath_start=0, fill_rule=1)
        cursor = Cursor(cell_to_bytes(path.cell()))
        read_variant_header(cursor)
        again = Path.read(cursor)
        self.assertEqual(again, path)

    def test_implausible_element_count_is_rejected(self):
        cursor = Cursor(struct.pack('>I', 0x7FFFFFFF))
        with self.assertRaises(FormatError):
            Path.read(cursor)


class TransformTests(unittest.TestCase):
    def test_transform_cell_holds_nine_doubles(self):
        cursor = Cursor(cell_to_bytes(transform_cell([1, 0, 0, 0, 1, 0, 100, 200, 1])))
        type_id, _, _ = read_variant_header(cursor)
        self.assertEqual(type_id, 80)
        self.assertEqual(list(cursor.read('9d')), [1, 0, 0, 0, 1, 0, 100, 200, 1])


if __name__ == '__main__':
    unittest.main()
