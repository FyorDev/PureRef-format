"""Deprecated: kept so `generate(read_folder, write_file)` keeps working.

The same job, with either format and without Pillow:

    pureref new Purs/artist.pur Artists/artist          # 2.1, the default
    pureref new Purs/artist.pur Artists/artist --format 1.10
"""
import warnings

import pureref
from pureref.layout import natural_key, pack_rows


def generate(read_folder, write_file, version=pureref.VERSION_1):
    """Build one organised .pur file from a folder of images."""
    warnings.warn('pureref_gen.generate is deprecated; use "pureref new" or '
                  'pureref.Scene with pureref.layout.pack_rows',
                  DeprecationWarning, stacklevel=2)
    from pathlib import Path
    folder = Path(read_folder)
    paths = sorted((path for path in folder.iterdir()
                    if path.suffix.lower() in ('.png', '.jpg', '.jpeg')),
                   key=lambda path: natural_key(path.name))
    if not paths:
        print('Skipping, no valid images found in ' + str(folder))
        return None
    scene = pureref.Scene()
    for path in paths:
        print('Processing: ' + str(path))
        scene.add_image(path)
    pack_rows(scene.images)
    losses = pureref.write(scene, write_file, version=version, overwrite=True)
    for loss in losses:
        print(f'note: {version} cannot keep {loss}')
    print('Done! File created')
    return scene
