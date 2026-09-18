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
