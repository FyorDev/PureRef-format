"""Deprecated entry point: `python pureref_gen_script.py [input] [output]`.

It now calls the same code as `pureref batch`, which is the maintained way in:

    pureref batch Artists Purs
"""
import os
import sys

from pureref.cli import main

if __name__ == '__main__':
    source = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else 'Artists'
    destination = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else 'Purs'
    os.makedirs(source, exist_ok=True)
    print('This script is deprecated; "pureref batch" does the same thing.')
    sys.exit(main(['batch', source, destination, '--format', '1.10']))
