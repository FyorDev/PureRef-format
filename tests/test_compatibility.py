"""The deprecated `purformat` shim keeps the pre-2.0 surface working."""
import unittest
import warnings
from pathlib import Path as FilePath
from tempfile import TemporaryDirectory

FIXTURES = FilePath(__file__).resolve().parent / 'fixtures'


def load():
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', DeprecationWarning)
        import purformat
        return purformat


class ShimTests(unittest.TestCase):
    def setUp(self):
        self.purformat = load()
        self.directory = TemporaryDirectory()
        self.path = FilePath(self.directory.name)
        self.addCleanup(self.directory.cleanup)

    def test_reading_fills_the_old_object_graph(self):
        pur = self.purformat.PurFile()
        pur.read(str(FIXTURES / 'legacy-1.10.pur'))
        self.assertEqual(len(pur.images), 3)
        self.assertEqual(pur.text, [])
        self.assertEqual(pur.zoom, 1.0)
        self.assertEqual(pur.canvas, [-10000.0, -10000.0, 10000.0, 10000.0])
        transform = pur.images[0].transforms[0]
        self.assertEqual(transform.pointCount, 5)
        self.assertAlmostEqual(transform.width, 454.5454545454, places=6)
        self.assertTrue(pur.images[0].pngBinary.startswith(b'\x89PNG'))

    def test_writing_reproduces_the_original_bytes(self):
        original = (FIXTURES / 'legacy-1.10.pur').read_bytes()
        pur = self.purformat.PurFile()
        pur.read(str(FIXTURES / 'legacy-1.10.pur'))
        target = self.path / 'again.pur'
        pur.write(str(target))
        self.assertEqual(target.read_bytes(), original)

    def test_building_a_file_from_scratch_the_old_way(self):
        items = self.purformat.items
        pur = self.purformat.PurFile()
        image = items.PurImage()
        image.pngBinary = (FIXTURES / 'red.png').read_bytes()
        transform = items.PurGraphicsImageItem()
        transform.reset_crop(64, 32)
        transform.source = str(FIXTURES / 'red.png')
        transform.name = 'red'
        transform.scale_to_height(320)
        image.transforms = [transform]
        pur.images = [image]
        note = items.PurGraphicsTextItem()
        note.text = 'from the old API'
        note.y = -200.0
        pur.text = [note]
        target = self.path / 'old-api.pur'
        pur.write(str(target))

        import pureref
        scene = pureref.read(target)
        self.assertEqual(len(scene.images), 1)
        self.assertEqual(scene.images[0].resource.size, (64, 32))
        self.assertAlmostEqual(scene.images[0].size[1], 320.0, places=6)
        self.assertEqual(scene.notes[0].text, 'from the old API')

    def test_duplicate_instances_still_share_one_image(self):
        items = self.purformat.items
        pur = self.purformat.PurFile()
        image = items.PurImage()
        image.pngBinary = (FIXTURES / 'red.png').read_bytes()
        first = items.PurGraphicsImageItem()
        first.reset_crop(64, 32)
        second = items.PurGraphicsImageItem()
        second.reset_crop(64, 32)
        second.x = 300.0
        image.transforms = [first, second]
        pur.images = [image]
        target = self.path / 'duplicate.pur'
        pur.write(str(target))
        again = self.purformat.PurFile()
        again.read(str(target))
        self.assertEqual(len(again.images), 1)
        self.assertEqual(len(again.images[0].transforms), 2)

    def test_deprecation_is_announced(self):
        import importlib
        import purformat
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            importlib.reload(purformat)
        self.assertTrue(any(issubclass(entry.category, DeprecationWarning)
                            for entry in caught))


if __name__ == '__main__':
    unittest.main()
