"""The 1.10 / 1.11.1 binary format."""
import unittest
from pathlib import Path as FilePath

import pureref
from pureref import ImageItem, NoteItem, Resource, Scene, Transform
from pureref.qt import FormatError
from pureref.v1 import format as fmt

FIXTURES = FilePath(__file__).resolve().parent / 'fixtures'
LEGACY = FIXTURES / 'legacy-1.10.pur'


class ReadTests(unittest.TestCase):
    def setUp(self):
        self.data = LEGACY.read_bytes()
        self.scene = pureref.read_bytes(self.data)

    def test_detected_as_1_10(self):
        self.assertEqual(pureref.detect(self.data), '1.10')
        self.assertEqual(self.scene.source_version, '1.10')

    def test_images_sizes_and_positions(self):
        sizes = [item.resource.size for item in self.scene.images]
        self.assertEqual(sizes, [(200, 150), (240, 150), (280, 150)])
        first = self.scene.images[0]
        self.assertAlmostEqual(first.x, 227.2727272727, places=6)
        self.assertAlmostEqual(first.y, 170.4545454545, places=6)
        self.assertTrue(first.resource.data.startswith(fmt.PNG_HEAD))

    def test_checksum_is_checked(self):
        self.assertTrue(self.scene.v1.checksum_valid)
        broken = bytearray(self.data)
        broken[500] ^= 0xFF
        self.assertFalse(pureref.read_bytes(bytes(broken)).v1.checksum_valid)

    def test_canvas_and_view(self):
        self.assertEqual(self.scene.canvas, (-10000.0, -10000.0, 10000.0, 10000.0))
        self.assertEqual((self.scene.view.zoom, self.scene.view.x, self.scene.view.y),
                         (1.0, 0, 0))

    def test_truncated_file_is_rejected(self):
        for cut in (0, 4, 100, fmt.HEADER_SIZE - 1):
            with self.subTest(cut=cut), self.assertRaises(FormatError):
                pureref.read_bytes(self.data[:cut])

    def test_reference_offset_outside_the_file_is_rejected(self):
        broken = bytearray(self.data)
        broken[16:24] = (10 ** 9).to_bytes(8, 'big')
        with self.assertRaises(FormatError):
            pureref.read_bytes(bytes(broken))


class AuthenticAppTests(unittest.TestCase):
    """Files written by PureRef 1.10.4 and 1.11.1 themselves."""

    names = ('app-1.10.4.pur', 'app-1.11.1.pur')

    def test_both_builds_read_and_repack_byte_for_byte(self):
        for name in self.names:
            with self.subTest(name=name):
                data = (FIXTURES / name).read_bytes()
                scene = pureref.read_bytes(data)
                self.assertTrue(scene.v1.checksum_valid)
                self.assertEqual(pureref.write_bytes(scene, version='1.10'), data)

    def test_the_header_carries_the_application_version(self):
        versions = [pureref.read(FIXTURES / name).v1.application_version
                    for name in self.names]
        self.assertEqual(versions, ['1.10.4', '1.11.1'])

    def test_1_11_1_still_writes_the_1_10_format(self):
        for name in self.names:
            self.assertEqual(pureref.detect((FIXTURES / name).read_bytes()), '1.10')

    def test_the_two_builds_agree_on_everything_but_that_string(self):
        first, second = ((FIXTURES / name).read_bytes() for name in self.names)
        self.assertEqual(len(first), len(second))
        differing = [index for index, (a, b) in enumerate(zip(first, second, strict=True)) if a != b]
        # the application-version string, then the checksum that covers it
        self.assertTrue(all(28 <= index < 40 or 44 <= index < 108 for index in differing),
                        differing[:10])

    def test_scene_contents(self):
        scene = pureref.read(FIXTURES / 'app-1.11.1.pur')
        self.assertEqual([item.resource.size for item in scene.images],
                         [(64, 32), (40, 80)])
        self.assertEqual([(item.x, item.y) for item in scene.images],
                         [(100.0, 200.0), (300.0, 0.0)])
        self.assertEqual([item.name for item in scene.images], ['red', 'blue'])
        self.assertEqual([item.opacity for item in scene.images], [1.0, 1.0])
        self.assertEqual(scene.canvas, (-320.0, -216.0, 640.0, 432.0))


class OpacityTests(unittest.TestCase):
    """The double before an image item's matrix is its opacity."""

    def test_opacity_round_trips(self):
        scene = Scene()
        for index, value in enumerate((1.0, 0.5, 0.25)):
            scene.add_image(FIXTURES / 'red.png', x=index * 80, opacity=value)
        again = pureref.read_bytes(pureref.write_bytes(scene, version='1.10'))
        self.assertEqual([item.opacity for item in again.images], [1.0, 0.5, 0.25])

    def test_image_opacity_is_not_a_loss(self):
        scene = Scene()
        scene.add_image(FIXTURES / 'red.png', opacity=0.5)
        self.assertEqual(scene.losses('1.10'), [])


class RoundTripTests(unittest.TestCase):
    def test_legacy_file_is_rewritten_byte_for_byte(self):
        data = LEGACY.read_bytes()
        scene = pureref.read_bytes(data)
        self.assertEqual(pureref.write_bytes(scene, version='1.10'), data)

    def test_shared_resources_become_instance_slots(self):
        scene = Scene()
        scene.add_image(FIXTURES / 'red.png', x=0, y=0)
        scene.add_image(FIXTURES / 'red.png', x=200, y=0)
        scene.add_image(FIXTURES / 'blue.png', x=400, y=0)
        data = pureref.write_bytes(scene, version='1.10')
        again = pureref.read_bytes(data)
        self.assertEqual(len(again.images), 3)
        self.assertEqual(len(again.resources), 2)
        self.assertEqual([round(item.x) for item in again.images], [0, 200, 400])
        self.assertEqual(pureref.write_bytes(again, version='1.10'), data)

    def test_notes_and_their_children_round_trip(self):
        scene = Scene()
        image = scene.add_image(FIXTURES / 'red.png')
        scene.add(NoteItem(text='attached', transform=Transform.translate(0, 60)), image)
        note = scene.add_note('Ω 中\nsecond line', x=10, y=-20,
                              text_color='#ff00ff00')
        scene.add(NoteItem(text='child'), note)
        data = pureref.write_bytes(scene, version='1.10')
        again = pureref.read_bytes(data)
        self.assertEqual([note.text for note in again.notes],
                         ['attached', 'Ω 中\nsecond line', 'child'])
        self.assertEqual(again.notes[1].text_color, '#ff00ff00')
        self.assertEqual(again.images[0].children[0].text, 'attached')
        self.assertEqual(pureref.write_bytes(again, version='1.10'), data)

    def test_linked_image_uses_a_link_slot(self):
        scene = Scene()
        scene.add_image(FIXTURES / 'red.png', link=True)
        data = pureref.write_bytes(scene, version='1.10')
        self.assertIn(fmt.LINK_SLOT, data)
        again = pureref.read_bytes(data)
        self.assertTrue(again.resources[0].linked)
        self.assertTrue(again.resources[0].source.endswith('red.png'))

    def test_canvas_is_fitted_to_content_for_new_scenes(self):
        scene = Scene()
        scene.add_image(FIXTURES / 'red.png', x=0, y=0)
        again = pureref.read_bytes(pureref.write_bytes(scene, version='1.10'))
        self.assertEqual(again.canvas, (-232.0, -216.0, 232.0, 216.0))

    def test_crop_survives(self):
        scene = Scene()
        scene.add_image(FIXTURES / 'red.png', crop=(8, 4, 16, 8))
        again = pureref.read_bytes(pureref.write_bytes(scene, version='1.10'))
        self.assertEqual(again.images[0].bounds.bounding_box(),
                         (-24.0, -12.0, -8.0, -4.0))


class WriteRuleTests(unittest.TestCase):
    def test_non_png_data_needs_pillow(self):
        scene = Scene()
        scene.add_image(FIXTURES / 'red.jpg')
        self.assertIn('JPG image data: re-encoded as PNG, which 1.x is limited to',
                      scene.losses('1.10'))
        from pureref import transcode
        if transcode.available():
            data = pureref.write_bytes(scene, version='1.10')
            self.assertEqual(pureref.read_bytes(data).resources[0].format, 'PNG')
        else:
            with self.assertRaises(FormatError):
                pureref.write_bytes(scene, version='1.10')

    def test_groups_are_flattened_with_their_transform(self):
        scene = Scene()
        group = scene.add_group(x=100, y=50)
        scene.add_image(FIXTURES / 'red.png', parent=group, x=10, y=5)
        losses = scene.losses('1.10')
        self.assertTrue(any('group' in loss for loss in losses))
        again = pureref.read_bytes(pureref.write_bytes(scene, version='1.10'))
        self.assertEqual(len(again.groups), 0)
        self.assertEqual((again.images[0].x, again.images[0].y), (110.0, 55.0))

    def test_unknown_image_bytes_are_refused_early(self):
        with self.assertRaises(ValueError):
            Resource.from_bytes(b'not an image')

    def test_image_item_needs_a_resource(self):
        with self.assertRaises(ValueError):
            ImageItem()


if __name__ == '__main__':
    unittest.main()
