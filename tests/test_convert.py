"""Converting between the generations, and the layout helper."""
import unittest
from pathlib import Path as FilePath
from tempfile import TemporaryDirectory

import pureref
from pureref import STROKE_DASHED, CropPath, Scene, Stroke
from pureref.layout import natural_key, pack_rows

FIXTURES = FilePath(__file__).resolve().parent / 'fixtures'


class ConvertTests(unittest.TestCase):
    def test_1_x_to_2_1_keeps_everything(self):
        legacy = pureref.read(FIXTURES / 'legacy-1.10.pur')
        self.assertEqual(legacy.losses('2.1'), [])
        modern = pureref.read_bytes(pureref.write_bytes(legacy, version='2.1'))
        self.assertEqual(len(modern.images), len(legacy.images))
        self.assertEqual([item.resource.size for item in modern.images],
                         [item.resource.size for item in legacy.images])
        self.assertEqual([round(item.x, 6) for item in modern.images],
                         [round(item.x, 6) for item in legacy.images])
        self.assertEqual([item.resource.data for item in modern.images],
                         [item.resource.data for item in legacy.images])

    def test_2_x_to_1_10_names_what_it_drops(self):
        modern = pureref.read(FIXTURES / 'app-2.0.3-mixed.pur')
        losses = modern.losses('1.10')
        self.assertTrue(any('group' in loss for loss in losses))
        self.assertTrue(any('drawing' in loss for loss in losses))
        legacy = pureref.read_bytes(pureref.write_bytes(modern, version='1.10'))
        self.assertEqual(len(legacy.groups), 0)
        self.assertEqual(len(legacy.drawings), 0)
        self.assertEqual(len(legacy.images), len(modern.images))
        self.assertEqual(legacy.notes[0].text, modern.notes[0].text)

    def test_conversion_writes_files_without_clobbering(self):
        with TemporaryDirectory() as directory:
            target = FilePath(directory) / 'converted.pur'
            pureref.convert(FIXTURES / 'legacy-1.10.pur', target)
            self.assertEqual(pureref.detect(target.read_bytes()), '2.1')
            with self.assertRaises(FileExistsError):
                pureref.convert(FIXTURES / 'legacy-1.10.pur', target)
            pureref.convert(FIXTURES / 'legacy-1.10.pur', target, version='2.0',
                            overwrite=True)
            self.assertEqual(pureref.detect(target.read_bytes()), '2.0')

    def test_unknown_version_is_refused(self):
        with self.assertRaises(ValueError):
            pureref.write_bytes(Scene(), version='3.0')
        with self.assertRaises(ValueError):
            Scene().losses('3.0')

    def test_round_trip_through_1_10_keeps_note_text_and_colors(self):
        scene = Scene()
        scene.add_image(FIXTURES / 'red.png')
        scene.add_note('plain text', x=0, y=-80, text_color='#ff112233')
        legacy = pureref.read_bytes(pureref.write_bytes(scene, version='1.10'))
        self.assertEqual(legacy.notes[0].text, 'plain text')
        self.assertEqual(legacy.notes[0].text_color, '#ff112233')

    def test_drawings_survive_a_2_1_to_2_0_to_2_1_trip(self):
        scene = Scene()
        scene.add_drawing([Stroke(path=CropPath([(0, 0, 0), (1, 10, 10)]), style=STROKE_DASHED)])
        once = pureref.read_bytes(pureref.write_bytes(scene, version='2.0'))
        twice = pureref.read_bytes(pureref.write_bytes(once, version='2.1'))
        self.assertTrue(twice.drawings[0].strokes[0].dashed)


class LayoutTests(unittest.TestCase):
    def test_natural_sort(self):
        names = ['10.jpg', '2.jpg', '1.jpg', 'a10.png', 'a2.png']
        self.assertEqual(sorted(names, key=natural_key),
                         ['1.jpg', '2.jpg', '10.jpg', 'a2.png', 'a10.png'])

    def test_rows_line_up_and_fill_the_width(self):
        scene = Scene()
        for _ in range(8):
            scene.add_image(FIXTURES / 'red.png')
            scene.add_image(FIXTURES / 'blue.png')
        pack_rows(scene.images, target_width=1000.0)
        rows = {}
        for item in scene.images:
            width, height = item.size
            rows.setdefault(round(item.y - height / 2, 3), []).append(item)
        self.assertGreater(len(rows), 1)
        for row in rows.values():
            span = sum(item.size[0] for item in row)
            self.assertAlmostEqual(span, 1000.0, places=3)
            left = min(item.x - item.size[0] / 2 for item in row)
            self.assertAlmostEqual(left, 0.0, places=6)

    def test_empty_input_is_fine(self):
        pack_rows([])


if __name__ == '__main__':
    unittest.main()
