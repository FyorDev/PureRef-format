"""The command line tool."""
import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path as FilePath
from tempfile import TemporaryDirectory

import pureref
from pureref.cli import main
from support import FIXTURES


def run(*argv) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.path = FilePath(self.directory.name)
        self.addCleanup(self.directory.cleanup)

    def test_info_text_and_json(self):
        code, out, _ = run('info', str(FIXTURES / 'app-2.0.3-mixed.pur'))
        self.assertEqual(code, 0)
        self.assertIn('PureRef 2.1 file', out)
        self.assertIn('group at', out)
        code, out, _ = run('info', '--json', str(FIXTURES / 'legacy-1.10.pur'))
        self.assertEqual(code, 0)
        report = json.loads(out)
        self.assertEqual(report['version'], '1.10')
        self.assertEqual(report['counts']['images'], 3)

    def test_new_builds_a_laid_out_file(self):
        target = self.path / 'new.pur'
        code, out, _ = run('new', str(target), str(FIXTURES / 'red.png'),
                           str(FIXTURES / 'blue.png'))
        self.assertEqual(code, 0)
        scene = pureref.read(target)
        self.assertEqual(len(scene.images), 2)
        self.assertAlmostEqual(sum(item.size[0] for item in scene.images), 1000.0,
                               places=3)

    def test_new_refuses_to_clobber_and_accepts_overwrite(self):
        target = self.path / 'new.pur'
        run('new', str(target), str(FIXTURES / 'red.png'))
        code, _, err = run('new', str(target), str(FIXTURES / 'red.png'))
        self.assertEqual(code, 1)
        self.assertIn('exists', err)
        code, _, _ = run('new', str(target), str(FIXTURES / 'red.png'), '--overwrite')
        self.assertEqual(code, 0)

    def test_new_with_link_is_refused_for_1_10(self):
        code, _, err = run('new', str(self.path / 'x.pur'), str(FIXTURES / 'red.png'),
                           '--format', '1.10', '--link')
        self.assertEqual(code, 2)
        self.assertIn('embeds', err)

    def test_batch_walks_folders(self):
        images = self.path / 'Artists'
        for artist in ('a', 'b'):
            folder = images / artist
            folder.mkdir(parents=True)
            (folder / 'red.png').write_bytes((FIXTURES / 'red.png').read_bytes())
        output = self.path / 'Purs'
        code, out, _ = run('batch', str(images), str(output))
        self.assertEqual(code, 0)
        self.assertEqual(sorted(path.name for path in output.iterdir()),
                         ['a.pur', 'b.pur'])
        code, out, _ = run('batch', str(images), str(output))
        self.assertIn('already exists', out)

    def test_convert_reports_losses_on_stderr(self):
        target = self.path / 'legacy.pur'
        code, _, err = run('convert', str(FIXTURES / 'app-2.0.3-mixed.pur'), str(target),
                           '--format', '1.10')
        self.assertEqual(code, 0)
        self.assertIn('cannot keep', err)
        self.assertEqual(pureref.detect(target.read_bytes()), '1.10')

    def test_extract_writes_embedded_images(self):
        target = self.path / 'images'
        code, out, _ = run('extract', str(FIXTURES / 'app-2.0.3-mixed.pur'), str(target))
        self.assertEqual(code, 0)
        self.assertEqual(sorted(path.name for path in target.iterdir()),
                         ['image-0.png', 'image-1.png'])

    def test_extract_says_when_an_image_is_only_linked(self):
        code, out, _ = run('extract', str(FIXTURES / 'app-2.0.3-linked.pur'),
                           str(self.path / 'linked'))
        self.assertEqual(code, 0)
        self.assertIn('is linked to', out)

    def test_unpack_then_pack(self):
        database = self.path / 'scene.sqlite'
        code, _, _ = run('unpack', str(FIXTURES / 'app-2.0.3-image.pur'), str(database))
        self.assertEqual(code, 0)
        self.assertTrue(database.read_bytes().startswith(b'SQLite format 3\0'))
        target = self.path / 'packed.pur'
        code, _, _ = run('pack', str(database), str(target), '--format', '2.0')
        self.assertEqual(code, 0)
        self.assertEqual(pureref.detect(target.read_bytes()), '2.0')
        self.assertEqual(len(pureref.read(target).images), 1)

    def test_pack_refuses_a_database_missing_columns(self):
        import sqlite3
        database = self.path / 'thin.sqlite'
        connection = sqlite3.connect(database)
        connection.execute('CREATE TABLE images (id INTEGER PRIMARY KEY)')
        connection.commit()
        connection.close()
        code, _, err = run('pack', str(database), str(self.path / 'thin.pur'))
        self.assertEqual(code, 1)
        self.assertIn('missing columns', err)

    def test_a_file_that_is_not_a_pur_fails_cleanly(self):
        broken = self.path / 'broken.pur'
        broken.write_bytes(b'not a pureref file at all')
        code, _, err = run('info', str(broken))
        self.assertEqual(code, 1)
        self.assertIn('pureref:', err)


if __name__ == '__main__':
    unittest.main()
