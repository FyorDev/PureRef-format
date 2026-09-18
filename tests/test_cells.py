"""How 2.x stores a serialized value, and the column map over those encodings."""
import unittest
from fractions import Fraction

from pureref.qt import Cursor, Path, read_big_rational, read_variant_header
from pureref.v2 import cells
from pureref.v2.values import (big_rational_cell, bytes_to_cell, cell_to_bytes,
                               path_cell, rect_cell, size_cell, transform_cell)


class StorageTests(unittest.TestCase):
    def test_payload_survives_the_latin1_round_trip(self):
        payload = bytes(range(256)) + b'\0\0trailing'
        self.assertEqual(cell_to_bytes(bytes_to_cell(payload)), payload)

    def test_blob_cells_pass_through(self):
        self.assertEqual(cell_to_bytes(b'\x89PNG'), b'\x89PNG')
        self.assertEqual(cell_to_bytes(None), b'')

    def test_a_cell_is_text_so_sqlite_stores_it_as_text(self):
        cell = transform_cell([1, 0, 0, 0, 1, 0, 0, 0, 1])
        self.assertIsInstance(cell, str)
        self.assertTrue(all(ord(character) <= 0xFF for character in cell))


class EncodingTests(unittest.TestCase):
    def payload(self, cell):
        cursor = Cursor(cell_to_bytes(cell))
        return read_variant_header(cursor), cursor

    def test_transform_holds_nine_doubles(self):
        (type_id, _, _), cursor = self.payload(
            transform_cell([1, 0, 0, 0, 1, 0, 100, 200, 1]))
        self.assertEqual(type_id, 80)
        self.assertEqual(list(cursor.read('9d')), [1, 0, 0, 0, 1, 0, 100, 200, 1])

    def test_rect_and_size_are_plain_doubles(self):
        (type_id, _, _), cursor = self.payload(rect_cell(1, 2, 3, 4))
        self.assertEqual((type_id, list(cursor.read('4d'))), (20, [1, 2, 3, 4]))
        (type_id, _, _), cursor = self.payload(size_cell(-1, -1))
        self.assertEqual((type_id, list(cursor.read('2d'))), (22, [-1, -1]))

    def test_named_types_carry_their_name(self):
        for cell, name in ((big_rational_cell(3), 'BigRational'),
                           (path_cell(Path.centered_rectangle(4, 2)), 'QPainterPath')):
            with self.subTest(name=name):
                (type_id, _, stored), _ = self.payload(cell)
                self.assertEqual((type_id, stored), (1024, name))

    def test_rationals_round_trip_through_a_cell(self):
        for value in (Fraction(1), Fraction(-3), Fraction(7, 2), Fraction(2 ** 40, 3)):
            with self.subTest(value=value):
                _, cursor = self.payload(big_rational_cell(value))
                self.assertEqual(read_big_rational(cursor), value)

    def test_a_path_round_trips_through_a_cell(self):
        path = Path([(0, 1.0, 2.0), (1, 3.0, 4.0)], subpath_start=0, fill_rule=1)
        _, cursor = self.payload(path_cell(path))
        self.assertEqual(Path.read(cursor), path)


class ColumnMapTests(unittest.TestCase):
    def test_every_entry_reads_what_it_writes(self):
        samples = {
            ('items', 'transform'): __import__('pureref').Transform(dx=5, dy=6),
            ('items', 'sort_order'): Fraction(3, 2),
            ('items_images', 'image_bounds'): Path.centered_rectangle(8, 4),
            ('items_notes', 'fixed_size'): (-1.0, -1.0),
            ('metadata', 'scene_rect'): (0.0, 1.0, 2.0, 3.0),
        }
        for (table, column), value in samples.items():
            with self.subTest(column=f'{table}.{column}'):
                again = cells.reader_for(table, column)(cells.encode(table, column, value))
                self.assertEqual(again, value)

    def test_a_column_that_is_not_serialized_is_a_mistake(self):
        with self.assertRaises(KeyError):
            cells.cell_for('items', 'name')
        with self.assertRaises(KeyError):
            cells.cell_for('nowhere', 'name')

    def test_every_entry_names_its_type_for_the_documentation(self):
        for table, columns in cells.CELLS.items():
            for column, cell in columns.items():
                with self.subTest(column=f'{table}.{column}'):
                    self.assertTrue(cell.doc)


if __name__ == '__main__':
    unittest.main()
