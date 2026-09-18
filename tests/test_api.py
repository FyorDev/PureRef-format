"""The shapes of the public API: constructors, carriers and problem objects."""
import unittest

import pureref
from pureref import Outline, Scene, Stroke
from support import FIXTURES


class OutlineTests(unittest.TestCase):
    def test_a_line_is_two_elements(self):
        outline = Outline.line(0, 0, 10, 5)
        self.assertEqual(outline.points, [(0, 0), (10, 5)])
        self.assertEqual([kind for kind, _, _ in outline.elements], [0, 1])

    def test_a_polyline_stays_open_and_a_polygon_closes(self):
        points = [(0, 0), (10, 0), (10, 10)]
        self.assertEqual(Outline.polyline(points).points, points)
        self.assertEqual(Outline.polygon(points).points, points + [(0, 0)])
        self.assertEqual(Outline.polyline([]).points, [])

    def test_a_centered_rectangle_spans_the_pixels(self):
        self.assertEqual(Outline.centered_rectangle(64, 32).bounding_box(),
                         (-32.0, -16.0, 32.0, 16.0))


class StrokeTests(unittest.TestCase):
    def test_the_constructors_place_the_points(self):
        line = Stroke.line((0, 0), (100, 50), width=3.0)
        self.assertEqual(line.path.points, [(0, 0), (100, 50)])
        self.assertEqual(line.width, 3.0)
        freehand = Stroke.freehand([(0, 0), (1, 2), (3, 4)], rgba=(1, 2, 3, 4))
        self.assertEqual(freehand.path.points, [(0, 0), (1, 2), (3, 4)])
        self.assertEqual(freehand.rgba, (1, 2, 3, 4))

    def test_a_stroke_survives_a_write_and_read(self):
        scene = Scene()
        scene.add_drawing([Stroke.line((0, 0), (10, 10), width=7.0)])
        again = pureref.read_bytes(pureref.write_bytes(scene, version='2.1'))
        stroke = again.drawings[0].strokes[0]
        self.assertEqual(stroke.path.points, [(0, 0), (10, 10)])
        self.assertEqual(stroke.width, 7.0)


class CarrierTests(unittest.TestCase):
    """One typed carrier per generation, and nothing on the wrong one."""

    def test_a_1x_file_fills_only_the_1x_carriers(self):
        scene = pureref.read(FIXTURES / 'app-1.10.4.pur')
        self.assertIsNotNone(scene.v1)
        self.assertIsNone(scene.v2)
        item = scene.images[0]
        self.assertIsNotNone(item.v1)
        self.assertIsNone(item.v2)
        self.assertEqual(scene.v1.application_version, '1.10.4')

    def test_a_2x_file_fills_only_the_2x_carriers(self):
        scene = pureref.read(FIXTURES / 'app-2.0.3-mixed.pur')
        self.assertIsNone(scene.v1)
        self.assertEqual(scene.v2.integrity, ['ok'])
        self.assertEqual(scene.v2.envelope.application_version, '2.0.3')
        for item in scene.walk():
            self.assertIsNone(item.v1)
            self.assertIsNotNone(item.v2)
            self.assertIsInstance(item.v2.id, int)

    def test_unknown_columns_are_kept_rather_than_dropped(self):
        from pureref.v2 import Document
        data = (pureref.write_bytes(pureref.read(FIXTURES / 'app-2.0.3-image.pur')))
        with Document.open(data, read_only=False) as document:
            document.connection.execute('ALTER TABLE items ADD COLUMN mood TEXT')
            document.connection.execute("UPDATE items SET mood='new'")
            scene = document.to_scene()
        self.assertEqual(scene.items[0].v2.columns, {'mood': 'new'})


class MessageTests(unittest.TestCase):
    def test_a_loss_reads_as_text_and_branches_on_a_code(self):
        scene = pureref.read(FIXTURES / 'app-2.0.3-mixed.pur')
        losses = scene.losses('1.10')
        self.assertTrue(any(loss.code == 'groups' for loss in losses))
        self.assertIn('1.x has no groups', ' '.join(losses))


if __name__ == '__main__':
    unittest.main()
