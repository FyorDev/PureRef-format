"""The ImHex pattern has to describe the same layouts this package parses.

`pur.hexpat` is a second implementation of both formats, written for a different
tool, so it cannot share code with the readers. What it can do is fail a test
when a field is added here and not there. The heavier check -- actually running
the pattern over every fixture -- needs a pattern-language interpreter, so it is
skipped unless `PUREREF_PLCLI` points at one:

    PUREREF_PLCLI=~/PatternLanguage/build/cli/plcli python -m unittest discover -s tests
"""
import os
import re
import shutil
import subprocess
import unittest
from pathlib import Path

from pureref.v1 import format as fmt
from pureref.v1 import records as v1
from pureref.v2 import schema

ROOT = Path(__file__).resolve().parent.parent
PATTERN = ROOT / 'pur.hexpat'
FIXTURES = ROOT / 'tests' / 'fixtures'
IMHEX_INCLUDES = Path('/usr/share/imhex/includes')

# Record field -> what the pattern calls it, where the two differ. The pattern
# reads a QString as one type, so the `_length` fields have no counterpart, and
# it splits some records into sub-structs.
ALIASES = {
    '_version': 'format_version',
    '_constant_one': 'constant_one',
    '_tail': 'tail',
    '_colour_gap': 'colour_gap',
    '_unknown_152': 'unknown_152',
    '_unknown_184': 'unknown_184',
    'bounds': 'crop_outline',
    'foreground_kind': 'foreground',
    'foreground_opacity': 'foreground',
    'foreground_rgb': 'foreground',
    'background_kind': 'background',
    'background_opacity': 'background',
    'background_rgb': 'background',
}
SKIPPED = {'_version_length', '_application_length', '_checksum_length'}


def pattern_text() -> str:
    return PATTERN.read_text()


def field_names(text: str) -> set[str]:
    """Every identifier the pattern declares, cheaply: `type name` or `name[`."""
    return set(re.findall(r'\b([a-z_][a-z0-9_]*)\s*(?:\[|;|=|\s*\[\[)', text))


class DeclarationTests(unittest.TestCase):
    def setUp(self):
        self.text = pattern_text()
        self.names = field_names(self.text)

    def test_every_1x_record_field_is_in_the_pattern(self):
        missing = []
        for record in v1.RECORDS.values():
            for entry in record.fields:
                if entry.name in SKIPPED:
                    continue
                wanted = ALIASES.get(entry.name, entry.name.lstrip('_'))
                if wanted not in self.names:
                    missing.append(f'{record.name}.{entry.name}')
        self.assertEqual(missing, [], 'pur.hexpat does not describe these fields')

    def test_the_constants_match(self):
        self.assertIn(f'HEADER_SIZE = {fmt.HEADER_SIZE}', self.text)
        self.assertEqual(v1.HEADER.size, fmt.HEADER_SIZE)
        self.assertIn(f'IMAGE_ITEM  = {fmt.IMAGE_ITEM_MARKER}', self.text)
        self.assertIn(f'TEXT_ITEM   = {fmt.TEXT_ITEM_MARKER}', self.text)
        self.assertIn(str(schema.USER_VERSION), self.text)
        self.assertIn(str(schema.APPLICATION_ID), self.text)

    def test_both_generations_are_covered(self):
        for marker in ('namespace legacy', 'namespace modern', 'SqliteHeader',
                       'scene.sqlite'):
            self.assertIn(marker, self.text)


def interpreter() -> str | None:
    return os.environ.get('PUREREF_PLCLI') or shutil.which('plcli')


@unittest.skipUnless(interpreter(), 'set PUREREF_PLCLI to a pattern-language CLI')
class InterpreterTests(unittest.TestCase):
    """Run the pattern for real, over every fixture, and demand a clean exit."""

    def run_pattern(self, path: Path) -> str:
        command = [interpreter(), 'run', '-p', str(PATTERN), '-i', str(path)]
        if IMHEX_INCLUDES.is_dir():
            command += ['-I', str(IMHEX_INCLUDES)]
        finished = subprocess.run(command, capture_output=True, timeout=300)
        return (finished.stdout + finished.stderr).decode(errors='replace')

    def test_every_fixture_parses(self):
        for path in sorted(FIXTURES.glob('*.pur')):
            with self.subTest(fixture=path.name):
                self.assertEqual(self.run_pattern(path).strip(), '')


if __name__ == '__main__':
    unittest.main()
