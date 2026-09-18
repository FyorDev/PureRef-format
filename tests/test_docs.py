"""The format documents are generated from the declarations, so they cannot drift."""
import unittest

from tools.generate_docs import DOCUMENTS, ROOT, rewrite


class GeneratedTableTests(unittest.TestCase):
    def test_every_document_matches_its_records(self):
        for name, sections in DOCUMENTS.items():
            with self.subTest(document=name):
                current = (ROOT / name).read_text()
                self.assertEqual(
                    current, rewrite(current, sections),
                    f'{name} is out of date; run python -m tools.generate_docs')

    def test_the_tables_are_not_empty(self):
        for name, sections in DOCUMENTS.items():
            text = (ROOT / name).read_text()
            for section in sections:
                self.assertIn(f'<!-- generated: {section} -->', text)


if __name__ == '__main__':
    unittest.main()


class SchemaNoteTests(unittest.TestCase):
    """A column without a description cannot be documented, so it is an error."""

    def test_every_column_has_a_note(self):
        from pureref.v2 import schema
        missing = [f'{table}.{column}' for table in schema.TABLES
                   for column in schema.columns(table) if not schema.note(table, column)]
        self.assertEqual(missing, [], 'add these to pureref/v2/schema.py NOTES')

    def test_no_note_describes_a_column_that_is_gone(self):
        from pureref.v2 import schema
        stale = [f'{table}.{column}' for table, notes in schema.NOTES.items()
                 for column in notes if column not in schema.columns(table)]
        self.assertEqual(stale, [])

    def test_every_serialized_column_is_a_real_column(self):
        from pureref.v2 import cells, schema
        unknown = [f'{table}.{column}' for table, entries in cells.CELLS.items()
                   for column in entries if column not in schema.columns(table)]
        self.assertEqual(unknown, [])
