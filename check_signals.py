#!/usr/bin/env python3
"""Looks for Qt signals declared with an expensive type.

A signal declared `pyqtSignal(list)` or `pyqtSignal(dict)` is not a mere
reference hand-off: PyQt converts the value to a Qt type on emission, then
converts it back on arrival, element by element.

Measured on this application: 341 ms to pass the seventy-one thousand tracks
of the library as `list`, against zero as `object`. It was the biggest freeze
at startup, and it showed up in no function's profile — the time was spent
inside Qt, between emission and reception.

`object` passes the Python object as is. It is fine as long as nobody tries
to connect from C++, which is always the case here.

A `list` declaration remains legitimate when the payload is short and known:
a few file paths dropped onto the window, for example. This check therefore
reports suspects, not faults: the list of accepted exceptions is at the
bottom of the file.

    python check_signals.py            # the whole folder
    python check_signals.py file.py
"""

import ast
import pathlib
import sys

COSTLY_TYPES = {'list', 'dict'}

# Signals whose payload is short by construction, and which are not worth
# rewriting. Format: (file, signal name).
# Measurement made to decide: passing a thirty-two-field track costs 67 us as
# `dict` against 48 us as `object`. The conversion only costs per element; a
# single record weighs nothing, and changing the type would also change how
# the object is shared between sender and receiver. They are left as is.
TOLERATED = {
    ('poller.py', 'mount_info_ready'),         # a session record
    ('main_window.py', 'files_dropped'),       # paths from a drag and drop
    ('main_window.py', 'tracks_dropped'),      # identifiers of a selection
    ('library_watcher.py', 'scan_requested'),  # a few folders
    ('player.py', 'track_changed'),            # one track
    ('player.py', 'radio_changed'),            # one station
    ('player.py', 'audio_info_changed'),       # one audio format
    ('player.py', '_stream_url_resolved'),     # an address and its headers
    ('first_run.py', 'finished'),              # a first-launch summary
    ('first_run.py', 'analyse_terminee'),      # an analysis summary
    ('harmonizer.py', 'finished'),             # a harmonisation summary
    ('migration.py', 'finished'),              # a migration summary
}


def suspects(path: pathlib.Path):
    try:
        tree = ast.parse(path.read_text(encoding='utf-8'))
    except (OSError, SyntaxError):
        return []

    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        call = node.value
        if not (isinstance(call, ast.Call)
                and getattr(call.func, 'id', getattr(call.func, 'attr', '')) == 'pyqtSignal'):
            continue
        types = [a.id for a in call.args if isinstance(a, ast.Name)]
        if not any(t in COSTLY_TYPES for t in types):
            continue
        for target in node.targets:
            name = getattr(target, 'id', None)
            if name and (path.name, name) not in TOLERATED:
                found.append((node.lineno, name, ', '.join(types)))
    return found


# Folders not to walk: nothing useful, and a lot of noise.
EXCLUDED = {'__pycache__', '.git', 'dist', 'build', 'installer_out',
            '.venv', 'venv', 'node_modules', '.build_cache'}


def python_files(root: pathlib.Path):
    """All the code in the repository, subfolders included.

    Walking only the root let through the projects whose code lives in a
    package — that is, most of them. The check reported "no defect" without
    having read anything.
    """
    for path in sorted(root.rglob('*.py')):
        if EXCLUDED.isdisjoint(path.parts):
            yield path


def main(argv):
    targets = ([pathlib.Path(a) for a in argv[1:]]
               or list(python_files(pathlib.Path(__file__).parent)))
    total = 0
    for path in targets:
        if path.name == pathlib.Path(__file__).name:
            continue
        for line, name, types in suspects(path):
            print(f"{path.name}:{line}: {name} = pyqtSignal({types}) — "
                  f"`object` passes it without converting")
            total += 1
    if total:
        print(f"\n{total} signal(s) to check. If the payload is short and "
              f"will stay so, add them to TOLERATED with the reason.")
        return 1
    print(f"{len(targets)} file(s) checked: no expensive signal.")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
