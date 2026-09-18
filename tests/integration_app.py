"""Load the files this package writes in the real PureRef and check them.

    DISPLAY=:0 PUREREF_BUILDS=~/pureref python -m tests.integration_app
    DISPLAY=:0 PUREREF_EXE=/usr/bin/PureRef python -m tests.integration_app

`PUREREF_BUILDS` points at a folder of unpacked releases, each holding
`<version>/usr/bin/PureRef` — the layout you get from extracting the `.deb`
downloads. Every build found there is exercised: 1.x builds against the files
this package writes as 1.10, 2.x builds against the 2.0 and 2.1 ones, which is
the only way to check the 1.x writer against the application that owns the
format. `PUREREF_EXE` runs a single build instead.

Everything runs against a throwaway settings file in a fresh temporary folder, so
the machine's PureRef configuration and open canvases are untouched. Only
synthetic images from `tests/fixtures` are used.

PureRef needs a display: its AppImage ships no `offscreen` Qt plugin, so on Linux
this has to run on an X display.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pureref
from pureref import (LOCK_OPEN, PLAYBACK_PAUSED, RENDER_GRAYSCALE, RENDER_SMOOTH,
                     STROKE_DASHED, STROKE_FLAT, Outline, Scene, Stroke)

FIXTURES = Path(__file__).resolve().parent / 'fixtures'
WINDOWS_DEFAULT = r'C:\Program Files\PureRef\PureRef.exe'
# Noise that says nothing about the file under test.
BENIGN = ('QFontDatabase: Cannot find font directory', 'Note that Qt no longer ships fonts',
          'Ignoring WAYLAND_DISPLAY')


def builds() -> list[tuple[str, str]]:
    """Every PureRef this run should test, as (version, path) pairs."""
    folder = os.environ.get('PUREREF_BUILDS')
    found = []
    if folder:
        for candidate in sorted(Path(folder).expanduser().glob('*/usr/bin/PureRef')):
            found.append((candidate.parents[2].name, str(candidate)))
    if found:
        return found
    single = os.environ.get('PUREREF_EXE') or shutil.which('PureRef') or WINDOWS_DEFAULT
    return [(version_of(single), single)] if Path(single).exists() else []


def version_of(path: str) -> str:
    finished = subprocess.run([path, '--version'], capture_output=True, timeout=120)
    text = (finished.stdout + finished.stderr).decode(errors='replace')
    for word in text.split():
        if word[:1].isdigit():
            return word
    return 'unknown'


class Session:
    """One temporary workspace plus one PureRef build's command line."""

    def __init__(self, directory: Path, version: str, executable: str):
        self.directory = directory
        self.version = version
        self.executable = executable
        # The 2.x command line only saves to a destination that already exists;
        # 1.x instead pops a confirmation dialog when one does, and hangs.
        self.saves_need_the_file_to_exist = not version.startswith('1.')
        self.settings = directory / 'settings.ini'
        self.results: dict = {}

    def run(self, *commands: str, timeout: int = 60) -> str:
        arguments = [self.executable, '-s', str(self.settings)]
        for command in commands:
            arguments += ['-c', command]
        finished = subprocess.run(arguments, capture_output=True, timeout=timeout)
        return (finished.stdout + finished.stderr).decode(errors='replace')

    def open(self, name: str, path: Path, *, width: int = 700, height: int = 400):
        """Load a file, export a render and save it again; return both paths."""
        render = self.directory / f'{name}.png'
        resaved = self.directory / f'{name}-resaved.pur'
        if self.saves_need_the_file_to_exist:
            resaved.touch()
        log = self.run(f'load;{path}', f'exportScene;{render};{width};{height};true;false',
                       f'save;{resaved}', 'exit')
        (self.directory / f'{name}.log').write_text(log)
        problems = diagnostics(log)
        assert not problems, f'{name}: PureRef complained:\n{problems}'
        assert render.exists() and render.stat().st_size > 0, f'{name}: nothing rendered'
        return render, pureref.read(resaved)


def diagnostics(log: str) -> str:
    return '\n'.join(line for line in log.splitlines()
                     if ('[Warning]' in line or '[Critical]' in line)
                     and not any(noise in line for noise in BENIGN))


def full_scene() -> Scene:
    """One scene using every field this package knows how to write."""
    scene = Scene()
    group = scene.add_group(name='Everything', background_color='#4020a0ff',
                            lock_mode=LOCK_OPEN)
    scene.add_image(FIXTURES / 'alpha.png', parent=group, x=-260, y=0,
                    scale_x=10, scale_y=10, link=True)
    scene.add_image(FIXTURES / 'tiny.png', parent=group, x=-120, y=0,
                    scale_x=20, scale_y=20, flags=0)
    scene.add_image(FIXTURES / 'tiny.png', parent=group, x=40, y=0,
                    scale_x=20, scale_y=20, flags=RENDER_SMOOTH | RENDER_GRAYSCALE)
    animated = scene.add_image(FIXTURES / 'anim.gif', parent=group, x=200, y=0,
                               scale_x=6, scale_y=6)
    animated.playback.state, animated.playback.frame = PLAYBACK_PAUSED, 1
    scene.add_image(FIXTURES / 'blue.png', parent=group, x=340, y=0,
                    scale_x=2, scale_y=2, crop=(0, 0, 20, 40))
    note = scene.add_note('Everything Ω 中', parent=group, x=-60, y=-140,
                          text_color='#ff40ff', background_color='#80304050')
    note.comment = 'a comment on a note'
    scene.add_drawing([Stroke(path=Outline([(0, -260, 120), (1, 260, 120)]),
                              rgba=(240, 200, 60, 255), width=6, style=STROKE_DASHED),
                       Stroke(path=Outline([(0, -260, 160), (1, 260, 160)]),
                              rgba=(120, 220, 255, 255), width=6, style=STROKE_FLAT)],
                      parent=group)
    return scene


def check_2_x(session: Session) -> None:
    scene = full_scene()
    renders = {}
    for version in ('2.1', '2.0'):
        path = session.directory / f'written-{version}.pur'
        pureref.write(scene, path, version=version)
        render, resaved = session.open(f'written-{version}', path)
        renders[version] = render.read_bytes()
        assert resaved.resources[0].linked, 'the linked image lost its link'
        flags = {item.flags for item in resaved.images}
        assert 0 in flags, 'the nearest-neighbour flag was not kept'
        assert RENDER_SMOOTH | RENDER_GRAYSCALE in flags, \
            'the grayscale flag was not kept'
        animated = [item for item in resaved.images
                    if item.playback.state == PLAYBACK_PAUSED]
        assert animated and animated[0].playback.frame == 1, 'playback state was lost'
        assert resaved.notes[0].text_color == '#ff40ff', 'note text color was lost'
        assert resaved.groups[0].lock_mode == LOCK_OPEN, 'group lock mode was lost'
        styles = [stroke.style for stroke in resaved.drawings[0].strokes]
        assert styles == [STROKE_DASHED, STROKE_FLAT], f'stroke styles became {styles}'
        assert resaved.notes[0].comment == 'a comment on a note', 'the comment was lost'
        session.results[f'written_{version}_loads_and_survives_a_resave'] = True
    assert renders['2.1'] == renders['2.0'], \
        'the 2.0 and 2.1 envelopes rendered differently'
    session.results['both_envelopes_render_identically'] = True


def check_1_x(session: Session) -> None:
    """The 1.10 writer, against whichever PureRef is driving this session."""
    scene = Scene()
    for index, name in enumerate(('red.png', 'blue.png', 'red.png')):
        scene.add_image(FIXTURES / name, x=index * 150, y=0, opacity=1.0 - index * 0.3)
    scene.add_image(FIXTURES / 'blue.png', x=450, y=0, crop=(0, 0, 20, 40))
    scene.add_note('written as 1.10 Ω', x=0, y=-150, text_color='#ffff8040')
    path = session.directory / 'written-1.10.pur'
    pureref.write(scene, path, version='1.10')
    _, resaved = session.open('written-1.10', path)
    assert len(resaved.images) == 4, 'an image instance went missing'
    assert len(resaved.resources) == 2, 'the shared image was not shared'
    assert resaved.notes[0].text.strip() == 'written as 1.10 Ω', 'the note was lost'
    note = resaved.notes[0]
    if session.saves_need_the_file_to_exist:
        # 2.x converts a 1.x note by moving its colour into the HTML
        assert '#ffff8040' in (note.html or ''), f'the note colour is gone: {note.html}'
    else:
        assert note.text_color == '#ffff8040', f'the note colour became {note.text_color}'
    # instances are grouped by the image they share, so compare by position
    opacities = {round(item.x): round(item.opacity, 3) for item in resaved.images}
    assert opacities == {0: 1.0, 150: 0.7, 300: 0.4, 450: 1.0}, opacities
    cropped = [item for item in resaved.images if round(item.x) == 450][0]
    crop = tuple(round(v) for v in cropped.bounds.bounding_box())
    assert crop == (-20, -40, 0, 0), f'the crop became {crop}'
    session.results['written_1_10_loads_and_survives_a_resave'] = True


def check_1_x_authentic(session: Session) -> None:
    """Read what this build saves, and hand it back unchanged."""
    path = session.directory / 'app-made.pur'
    if session.saves_need_the_file_to_exist:
        path.touch()
    log = session.run(f'load;{FIXTURES / "red.png"};100;200',
                      f'load;{FIXTURES / "blue.png"};300;0', f'save;{path}', 'exit')
    problems = diagnostics(log)
    assert not problems, f'saving a fresh scene complained:\n{problems}'
    data = path.read_bytes()
    scene = pureref.read_bytes(data)
    assert scene.source_version == '1.10', scene.source_version
    assert scene.v1.checksum_valid, 'checksum mismatch on an app-made file'
    assert scene.v1.application_version == session.version, (
        scene.v1.application_version, session.version)
    assert [item.resource.size for item in scene.images] == [(64, 32), (40, 80)]
    assert pureref.write_bytes(scene, version='1.10') == data, 'repack was not exact'
    session.results['app_made_file_repacks_byte_for_byte'] = True


def check_conversions(session: Session) -> None:
    to_modern = session.directory / 'legacy-as-2.1.pur'
    pureref.convert(FIXTURES / 'legacy-1.10.pur', to_modern)
    _, resaved = session.open('legacy-as-2.1', to_modern)
    assert len(resaved.images) == 3
    to_legacy = session.directory / 'mixed-as-1.10.pur'
    losses = pureref.convert(FIXTURES / 'app-2.0.3-mixed.pur', to_legacy, version='1.10')
    assert losses, 'converting a 2.x scene to 1.10 should report losses'
    _, resaved = session.open('mixed-as-1.10', to_legacy)
    assert len(resaved.images) == 2
    session.results['conversions_load_in_both_directions'] = True


def check_repacking() -> dict:
    """Offline, but the point of the whole exercise: exact repacking."""
    exact = 0
    for path in sorted(FIXTURES.glob('*.pur')):
        data = path.read_bytes()
        scene = pureref.read_bytes(data)
        if scene.source_version == '1.10':
            assert pureref.write_bytes(scene, version='1.10') == data, path.name
        else:
            from pureref.v2 import envelope
            wrapper, database = envelope.unwrap(data)
            assert wrapper.checksum_valid, path.name
            assert envelope.wrap(database, wrapper) == data, path.name
        exact += 1
    return {'fixtures_repacked_exactly': exact}


def main() -> int:
    found = builds()
    if not found:
        print('No PureRef found; set PUREREF_BUILDS or PUREREF_EXE', file=sys.stderr)
        return 2
    results = {'offline': check_repacking()}
    for version, executable in found:
        with tempfile.TemporaryDirectory(prefix=f'pureref-{version}-') as directory:
            session = Session(Path(directory), version, executable)
            if version.startswith('1.'):
                check_1_x_authentic(session)
                check_1_x(session)
            else:
                check_2_x(session)
                check_1_x(session)
                check_conversions(session)
            results[version] = session.results
    print(json.dumps(results, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
