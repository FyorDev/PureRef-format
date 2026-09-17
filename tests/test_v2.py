"""The 2.0 / 2.1 format: envelope, schema and serialized values."""
import unittest
from fractions import Fraction
from pathlib import Path as FilePath

import pureref
from pureref import (LOCK_OPEN, PLAYBACK_PAUSED, PLAYBACK_PLAYING, RENDER_GRAYSCALE,
                     RENDER_SMOOTH, CropPath, Scene, Stroke)
from pureref.qt import FormatError
from pureref.v2 import envelope as env
from pureref.v2 import schema
from pureref.v2.database import Database

FIXTURES = FilePath(__file__).resolve().parent / 'fixtures'
APP_FILES = ['app-2.0.3-image', 'app-2.0.3-mixed', 'app-2.0.3-anim',
             'app-2.0.3-linked', 'app-2.0.3-dashed', 'envelope-2.0']


class EnvelopeTests(unittest.TestCase):
    def test_every_fixture_repacks_byte_for_byte(self):
        for name in APP_FILES:
            with self.subTest(name=name):
                data = (FIXTURES / f'{name}.pur').read_bytes()
                envelope, database = env.unwrap(data)
                self.assertTrue(envelope.checksum_valid)
                self.assertEqual(env.wrap(database, envelope), data)

    def test_2_0_3_writes_2_1_envelopes(self):
        envelope, _ = env.unwrap((FIXTURES / 'app-2.0.3-image.pur').read_bytes())
        self.assertEqual(envelope.format_version, '2.1')
        self.assertEqual(envelope.application_version, '2.0.3')

    def test_the_2_0_layout_has_no_thumbnail_field(self):
        data = (FIXTURES / 'envelope-2.0.pur').read_bytes()
        envelope, database = env.unwrap(data)
        self.assertEqual(envelope.format_version, '2.0')
        self.assertEqual(envelope.thumbnail, b'')
        self.assertEqual(envelope.header_size, 104)  # ends at the checksum
        with self.assertRaises(ValueError):
            env.wrap(database, env.Envelope(format_version='2.0', thumbnail=b'\xff\xd8'))

    def test_checksum_covers_everything_after_itself(self):
        data = bytearray((FIXTURES / 'app-2.0.3-image.pur').read_bytes())
        data[5000] ^= 1
        envelope, _ = env.unwrap(bytes(data))
        self.assertFalse(envelope.checksum_valid)

    def test_truncation_and_bad_sizes_are_rejected(self):
        data = (FIXTURES / 'app-2.0.3-image.pur').read_bytes()
        for broken in [b'', data[:4], data[:40], data[:-1]]:
            with self.assertRaises(FormatError):
                env.unwrap(broken)
        bad = data[:14] + (2 ** 62).to_bytes(8, 'big') + data[22:]
        with self.assertRaises(FormatError):
            env.unwrap(bad)

    def test_unknown_versions_are_named_in_the_error(self):
        from pureref.qt import pack_string
        with self.assertRaises(FormatError) as caught:
            env.unwrap(pack_string('9.9') + bytes(64))
        self.assertIn('9.9', str(caught.exception))


class SchemaTests(unittest.TestCase):
    def test_writer_output_has_every_column_PureRef_needs(self):
        _, database = env.unwrap(pureref.write_bytes(Scene()))
        with Database(database, read_only=True) as db:
            self.assertEqual(schema.missing_columns(db.connection), {})
            self.assertEqual(db.integrity(), ['ok'])
            self.assertEqual(db.pragma('user_version'), schema.USER_VERSION)
            self.assertEqual(db.pragma('application_id'), schema.APPLICATION_ID)
            self.assertEqual(db.pragma('page_size'), schema.PAGE_SIZE)

    def test_missing_columns_are_named(self):
        with Database() as db:
            db.connection.executescript('CREATE TABLE images (id INTEGER PRIMARY KEY);')
            gaps = schema.missing_columns(db.connection)
        self.assertIn('data', gaps['images'])
        self.assertIn('items', gaps)

    def test_app_files_declare_columns_in_their_own_order(self):
        _, database = env.unwrap((FIXTURES / 'app-2.0.3-image.pur').read_bytes())
        with Database(database, read_only=True) as db:
            rows = db.connection.execute('PRAGMA table_info(items)').fetchall()
            order = [row[1] for row in rows]
        self.assertNotEqual(order, list(schema.columns('items')))
        self.assertEqual(sorted(order), sorted(schema.columns('items')))


class ReadTests(unittest.TestCase):
    def test_image_position_is_its_center(self):
        scene = pureref.read(FIXTURES / 'app-2.0.3-image.pur')
        item = scene.images[0]
        self.assertEqual((item.x, item.y), (100.0, 200.0))
        self.assertEqual(item.resource.size, (64, 32))
        self.assertEqual(item.pixel_transform.dx, -32.0)
        self.assertEqual(item.order, Fraction(1))

    def test_mixed_scene_tree(self):
        scene = pureref.read(FIXTURES / 'app-2.0.3-mixed.pur')
        self.assertEqual(len(scene.groups), 1)
        group = scene.groups[0]
        self.assertEqual([child.kind() for child in group.children],
                         ['image', 'image', 'note', 'draw'])
        self.assertEqual(scene.notes[0].text, 'Generated Ω 中')
        self.assertAlmostEqual(group.children[1].opacity, 0.8)
        self.assertEqual(len(scene.drawings[0].strokes), 1)

    def test_linked_and_animated_fixtures(self):
        linked = pureref.read(FIXTURES / 'app-2.0.3-linked.pur')
        self.assertTrue(linked.resources[0].linked)
        self.assertIsNone(linked.resources[0].checksum)
        animated = pureref.read(FIXTURES / 'app-2.0.3-anim.pur')
        self.assertEqual(animated.images[0].playback.state, PLAYBACK_PLAYING)
        self.assertEqual(animated.resources[0].format, 'gif')

    def test_dashed_stroke_from_the_app(self):
        scene = pureref.read(FIXTURES / 'app-2.0.3-dashed.pur')
        dashes = sorted(stroke.dashed for drawing in scene.drawings
                        for stroke in drawing.strokes)
        self.assertEqual(dashes, [False, True])


class MalformedTests(unittest.TestCase):
    def build(self, rows):
        from pureref.qt import big_rational_cell, transform_cell
        with Database(pragmas=schema.PRAGMAS) as db:
            schema.create(db.connection)
            db.insert('metadata', id=0, application_version='2.1.3')
            for item_id, parent in rows:
                db.insert('items', id=item_id, parent=parent, name=f'item{item_id}',
                          transform=transform_cell([1, 0, 0, 0, 1, 0, 0, 0, 1]),
                          sort_order=big_rational_cell(item_id + 1), z=1.0,
                          opacity=1.0, locked=0, comment=None)
                db.insert('items_groups', id=item_id, background_color=None,
                          lock_mode=1)
            return env.wrap(db.to_bytes())

    def test_parent_cycles_do_not_hang(self):
        scene = pureref.read_bytes(self.build([(0, 1), (1, 0), (2, 2)]))
        self.assertEqual(len(list(scene.walk())), 3)
        self.assertEqual(len(scene.items), 3)
        self.assertTrue(pureref.write_bytes(scene))

    def test_items_without_a_subtype_row_are_kept(self):
        from pureref.qt import transform_cell
        with Database(pragmas=schema.PRAGMAS) as db:
            schema.create(db.connection)
            db.insert('metadata', id=0, application_version='2.1.3')
            db.insert('items', id=0, parent=-1, name='bare',
                      transform=transform_cell([1, 0, 0, 0, 1, 0, 0, 0, 1]),
                      sort_order=None, z=1.0, opacity=1.0, locked=0, comment=None)
            data = env.wrap(db.to_bytes())
        scene = pureref.read_bytes(data)
        self.assertEqual(scene.items[0].name, 'bare')
        self.assertTrue(scene.items[0].extras['v2']['orphan'])

    def test_an_image_item_without_its_resource_is_an_error(self):
        from pureref.qt import transform_cell
        with Database(pragmas=schema.PRAGMAS) as db:
            schema.create(db.connection)
            db.insert('metadata', id=0, application_version='2.1.3')
            db.insert('items', id=0, parent=-1, name='ghost',
                      transform=transform_cell([1, 0, 0, 0, 1, 0, 0, 0, 1]),
                      sort_order=None, z=1.0, opacity=1.0, locked=0, comment=None)
            db.insert('items_images', id=0, image=99, playback_speed=1.0,
                      playback_state=0, image_transform=None, image_bounds=None,
                      playback_frame=0, flags=1)
            data = env.wrap(db.to_bytes())
        with self.assertRaises(FormatError):
            pureref.read_bytes(data)


class WriteTests(unittest.TestCase):
    def build(self) -> Scene:
        scene = Scene()
        group = scene.add_group(name='Group', background_color='#4020a0ff',
                                lock_mode=LOCK_OPEN)
        scene.add_image(FIXTURES / 'red.png', parent=group, x=-100, y=0, rotation=15,
                        opacity=0.65)
        scene.add_image(FIXTURES / 'red.png', parent=group, x=100, y=0,
                        flags=RENDER_SMOOTH | RENDER_GRAYSCALE)
        scene.add_image(FIXTURES / 'blue.png', parent=group, x=250, y=0,
                        crop=(0, 0, 20, 40))
        scene.add_image(FIXTURES / 'alpha.png', parent=group, x=350, y=0, link=True)
        animated = scene.add_image(FIXTURES / 'anim.gif', parent=group, x=450, y=0)
        animated.playback.state = PLAYBACK_PAUSED
        animated.playback.frame = 1
        scene.add_note('Ω 中', parent=group, x=0, y=-150, text_color='#ff40ff',
                       background_color='#80304050', style='compact')
        scene.add_drawing([Stroke(path=CropPath([(0, 0, 0), (1, 200, 100)]),
                                  rgba=(250, 160, 50, 255), width=4, dashed=True)],
                          parent=group)
        return scene

    def test_round_trip_keeps_every_modelled_field(self):
        for version in ('2.1', '2.0'):
            with self.subTest(version=version):
                scene = self.build()
                again = pureref.read_bytes(pureref.write_bytes(scene, version=version))
                self.assertEqual(len(again.resources), 4)
                group = again.groups[0]
                self.assertEqual((group.lock_mode, group.background_color),
                                 (LOCK_OPEN, '#4020a0ff'))
                images = again.images
                self.assertAlmostEqual(images[0].opacity, 0.65)
                self.assertAlmostEqual(images[0].transform.m12, 0.2588190451, places=6)
                self.assertTrue(images[1].grayscale)
                self.assertEqual(images[2].bounds.bounding_box(),
                                 (-20.0, -40.0, 0.0, 0.0))
                self.assertTrue(images[3].resource.linked)
                self.assertEqual((images[4].playback.state, images[4].playback.frame),
                                 (PLAYBACK_PAUSED, 1))
                note = again.notes[0]
                self.assertEqual((note.text_color, note.background_color, note.style),
                                 ('#ff40ff', '#80304050', 'compact'))
                self.assertEqual(note.text, 'Ω 中')
                stroke = again.drawings[0].strokes[0]
                self.assertEqual((stroke.rgba, stroke.width, stroke.dashed),
                                 ((250, 160, 50, 255), 4.0, True))

    def test_siblings_keep_their_order(self):
        scene = self.build()
        again = pureref.read_bytes(pureref.write_bytes(scene))
        kinds = [child.kind() for child in again.groups[0].children]
        self.assertEqual(kinds, ['image'] * 5 + ['note', 'draw'])
        orders = [child.order for child in again.groups[0].children]
        self.assertEqual(orders, [Fraction(n) for n in range(1, 8)])

    def test_app_files_round_trip_through_the_model(self):
        for name in APP_FILES:
            with self.subTest(name=name):
                scene = pureref.read(FIXTURES / f'{name}.pur')
                again = pureref.read_bytes(pureref.write_bytes(scene))
                self.assertEqual(pureref.summary(again)['counts'],
                                 pureref.summary(scene)['counts'])
                self.assertEqual([item.kind() for item in again.walk()],
                                 [item.kind() for item in scene.walk()])

    def test_scene_rect_only_comes_from_2_x_scenes(self):
        from pureref.v2.database import Database as Db
        legacy = pureref.read(FIXTURES / 'legacy-1.10.pur')
        _, database = env.unwrap(pureref.write_bytes(legacy))
        with Db(database, read_only=True) as db:
            self.assertIsNone(db.rows('metadata')[0]['scene_rect'])
        modern = pureref.read(FIXTURES / 'app-2.0.3-image.pur')
        again = pureref.read_bytes(pureref.write_bytes(modern))
        self.assertEqual(again.canvas, modern.canvas)

    def test_explicit_thumbnail_is_stored_in_both_places(self):
        scene = Scene()
        scene.add_image(FIXTURES / 'red.png')
        preview = (FIXTURES / 'red.jpg').read_bytes()
        data = pureref.write_bytes(scene, thumbnail=preview)
        envelope, database = env.unwrap(data)
        self.assertEqual(envelope.thumbnail, preview)
        with Database(database, read_only=True) as db:
            self.assertEqual(db.rows('metadata')[0]['thumbnail'], preview)

    def test_thumbnail_is_refused_by_the_2_0_layout(self):
        scene = Scene()
        scene.add_image(FIXTURES / 'red.png')
        with self.assertRaises(ValueError):
            pureref.write_bytes(scene, version='2.0',
                                thumbnail=(FIXTURES / 'red.jpg').read_bytes())


if __name__ == '__main__':
    unittest.main()
