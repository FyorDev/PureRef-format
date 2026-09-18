"""The Qt primitives both .pur generations are built from."""
import struct
import unittest

from pureref.qt import (Cursor, FormatError, Path, pack_big_integer, pack_bytes,
                        pack_big_rational, pack_matrix9, pack_string, pack_variant,
                        read_big_integer, read_big_rational, read_variant_header)


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


class VariantTests(unittest.TestCase):
    def test_a_custom_type_carries_its_registered_name(self):
        cursor = Cursor(pack_variant(1024, b'\x01\x02', 'BigRational'))
        self.assertEqual(read_variant_header(cursor), (1024, False, 'BigRational'))
        self.assertEqual(cursor.take(2), b'\x01\x02')

    def test_a_builtin_type_carries_none(self):
        cursor = Cursor(pack_variant(80, pack_matrix9([1, 0, 0, 0, 1, 0, 9, 8, 1])))
        self.assertEqual(read_variant_header(cursor), (80, False, None))
        self.assertEqual(list(cursor.read('9d')), [1, 0, 0, 0, 1, 0, 9, 8, 1])


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
        from fractions import Fraction
        for numerator, denominator in [(1, 1), (0, 1), (-3, 1), (7, 2), (2 ** 40, 3)]:
            value = Fraction(numerator, denominator)
            with self.subTest(value=value):
                self.assertEqual(read_big_rational(Cursor(pack_big_rational(value))), value)

    def test_one_matches_the_shape_PureRef_writes(self):
        # sign, block count, block, twice: the 1/1 PureRef stores for the first
        # sibling of a parent.
        self.assertEqual(struct.unpack('>IQIIQI', pack_big_rational(1)),
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
        self.assertEqual(Path.read(Cursor(path.pack())), path)

    def test_implausible_element_count_is_rejected(self):
        with self.assertRaises(FormatError):
            Path.read(Cursor(struct.pack('>I', 0x7FFFFFFF)))

    def test_the_constructors_agree_on_direction(self):
        self.assertEqual(Path.line(0, 0, 10, 5).points, [(0, 0), (10, 5)])
        self.assertEqual(Path.polygon([(0, 0), (1, 0)]).points,
                         [(0, 0), (1, 0), (0, 0)])


if __name__ == '__main__':
    unittest.main()
