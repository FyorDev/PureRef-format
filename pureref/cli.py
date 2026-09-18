"""The `pureref` command line tool.

    pureref info board.pur
    pureref new board.pur images/*.png
    pureref batch Artists Purs
    pureref convert board.pur board-1.10.pur --format 1.10
    pureref extract board.pur images/
    pureref unpack board.pur board.sqlite
    pureref pack board.sqlite board.pur

Exit codes: 0 success, 1 a file or format problem, 2 wrong usage.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import LATEST, VERSION_1, VERSIONS, FormatError, Scene, convert, read, write
from .layout import natural_key, pack_rows
from .report import summary, text_report
from .v2 import envelope as envelope_module
from .v2.database import Database

IMAGE_SUFFIXES = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.tif', '.tiff')


def main(argv=None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        return args.run(args)
    except FormatError as error:
        print(f'pureref: {error}', file=sys.stderr)
        return 1
    except FileExistsError as error:
        print(f'pureref: {error.filename} exists; pass --overwrite to replace it',
              file=sys.stderr)
        return 1
    except (OSError, ValueError) as error:
        print(f'pureref: {error}', file=sys.stderr)
        return 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='pureref', description=__doc__.splitlines()[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)

    info = commands.add_parser('info', help='describe a .pur file')
    info.add_argument('file')
    info.add_argument('--json', action='store_true', help='machine-readable output')
    info.set_defaults(run=_info)

    new = commands.add_parser('new', help='build a .pur from images')
    new.add_argument('output')
    new.add_argument('images', nargs='+')
    _add_write_options(new)
    new.add_argument('--link', action='store_true',
                     help='reference the files instead of embedding them (2.x only)')
    new.add_argument('--width', type=float, default=1000.0,
                     help='row width used by the layout (default 1000)')
    new.set_defaults(run=_new)

    batch = commands.add_parser('batch', help='turn every folder of images into a .pur')
    batch.add_argument('input')
    batch.add_argument('output')
    _add_write_options(batch)
    batch.set_defaults(run=_batch)

    convert_command = commands.add_parser('convert', help='rewrite a .pur in another format')
    convert_command.add_argument('input')
    convert_command.add_argument('output')
    _add_write_options(convert_command)
    convert_command.set_defaults(run=_convert)

    extract = commands.add_parser('extract', help='write the embedded images to a folder')
    extract.add_argument('file')
    extract.add_argument('directory')
    extract.set_defaults(run=_extract)

    unpack = commands.add_parser('unpack', help='write the inner SQLite database (2.x)')
    unpack.add_argument('file')
    unpack.add_argument('output')
    unpack.set_defaults(run=_unpack)

    pack = commands.add_parser('pack', help='wrap a SQLite database as a .pur (2.x)')
    pack.add_argument('database')
    pack.add_argument('output')
    pack.add_argument('--format', choices=['2.0', '2.1'], default='2.1')
    pack.add_argument('--application-version', default='2.1.3')
    pack.add_argument('--overwrite', action='store_true')
    pack.set_defaults(run=_pack)
    return parser


def _add_write_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('--format', choices=list(VERSIONS), default=LATEST,
                        dest='version', help=f'output format (default {LATEST})')
    parser.add_argument('--overwrite', action='store_true',
                        help='replace the output file if it exists')


def _info(args) -> int:
    scene = read(args.file)
    print(json.dumps(summary(scene), indent=2, default=str) if args.json
          else text_report(scene))
    for problem in scene.problems:
        print(f'note: {problem}', file=sys.stderr)
    return 0


def _new(args) -> int:
    paths = _image_paths(args.images)
    if not paths:
        print('pureref: no images to add', file=sys.stderr)
        return 1
    if args.link and args.version == VERSION_1:
        print('pureref: 1.10 always embeds images; drop --link', file=sys.stderr)
        return 2
    scene = _scene_from(paths, link=args.link, width=args.width)
    return _save(scene, args.output, args)


def _batch(args) -> int:
    source, destination = Path(args.input), Path(args.output)
    if not source.is_dir():
        print(f'pureref: {source} is not a folder', file=sys.stderr)
        return 1
    destination.mkdir(parents=True, exist_ok=True)
    folders = sorted((child for child in source.iterdir() if child.is_dir()),
                     key=lambda path: natural_key(path.name))
    folders = folders or [source]
    written = 0
    for folder in folders:
        target = destination / f'{folder.name}.pur'
        if target.exists() and not args.overwrite:
            print(f'skipping {target.name}, it already exists')
            continue
        paths = _image_paths([folder])
        if not paths:
            print(f'skipping {folder.name}, no images found')
            continue
        scene = _scene_from(paths, link=False, width=1000.0)
        _save(scene, target, args)
        written += 1
    print(f'{written} file(s) written to {destination}')
    return 0


def _convert(args) -> int:
    losses = convert(args.input, args.output, version=args.version,
                     overwrite=args.overwrite)
    _report_losses(losses, args.version)
    return 0


def _extract(args) -> int:
    scene = read(args.file)
    directory = Path(args.directory)
    directory.mkdir(parents=True, exist_ok=True)
    written = 0
    for index, resource in enumerate(scene.resources):
        if resource.linked:
            print(f'image {index} is linked to {resource.source}, nothing to extract')
            continue
        suffix = resource.format.lower()
        target = directory / f'image-{index}.{suffix if suffix.isalnum() else "bin"}'
        target.write_bytes(resource.data or b'')
        written += 1
    print(f'{written} image(s) written to {directory}')
    return 0


def _unpack(args) -> int:
    data = Path(args.file).read_bytes()
    _, database = envelope_module.unwrap(data)
    _write_file(Path(args.output), database, overwrite=False)
    print(f'{len(database)} bytes of SQLite written to {args.output}')
    return 0


def _pack(args) -> int:
    database = Path(args.database).read_bytes()
    with Database(database, read_only=True) as db:
        missing = _missing_columns(db)
    if missing:
        print(f'pureref: this database is missing columns PureRef needs: {missing}',
              file=sys.stderr)
        return 1
    wrapped = envelope_module.wrap(database, envelope_module.Envelope(
        format_version=args.format, application_version=args.application_version))
    _write_file(Path(args.output), wrapped, overwrite=args.overwrite)
    print(f'wrote {args.output} as a {args.format} file')
    return 0


def _missing_columns(db: Database) -> dict:
    from .v2 import schema
    return schema.missing_columns(db.connection)


def _scene_from(paths, *, link: bool, width: float) -> Scene:
    scene = Scene()
    for path in paths:
        scene.add_image(path, link=link)
    pack_rows(scene.images, target_width=width)
    return scene


def _image_paths(arguments) -> list[Path]:
    paths: list[Path] = []
    for argument in arguments:
        path = Path(argument)
        if path.is_dir():
            paths.extend(child for child in path.iterdir()
                         if child.suffix.lower() in IMAGE_SUFFIXES)
        elif path.suffix.lower() in IMAGE_SUFFIXES:
            paths.append(path)
        else:
            print(f'skipping {path}, not a supported image', file=sys.stderr)
    return sorted(paths, key=lambda path: natural_key(path.name))


def _save(scene: Scene, output, args) -> int:
    losses = write(scene, output, version=args.version, overwrite=args.overwrite)
    _report_losses(losses, args.version)
    print(f'wrote {output}')
    return 0


def _report_losses(losses, version: str) -> None:
    for loss in losses:
        print(f'note: {version} cannot keep {loss}', file=sys.stderr)


def _write_file(path: Path, data: bytes, *, overwrite: bool) -> None:
    if overwrite:
        path.write_bytes(data)
        return
    with path.open('xb') as stream:
        stream.write(data)


if __name__ == '__main__':
    sys.exit(main())
