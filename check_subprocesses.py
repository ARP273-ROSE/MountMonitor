#!/usr/bin/env python3
"""Looks for subprocesses that will flash a console.

A Windows GUI application runs under `pythonw.exe`, without a console. Each
`subprocess` then briefly launches a black window, which appears and
disappears — unless `creationflags=CREATE_NO_WINDOW` is passed.

It is not just a matter of elegance. MusicOtheque's CD drive watcher polls
the hardware every four seconds: that made a window flash on the desktop
constantly, all day long. The user reported it as: "a sort of console window
that lights up for a second and closes, all the time". MountMonitor had the
same defect at startup, with four calls to `wmic`.

The flag only exists on Windows; elsewhere it is zero and does no harm:
    _NO_CONSOLE = getattr(subprocess, 'CREATE_NO_WINDOW', 0)

This check is static and deliberately simple: it reads the call and looks
for `creationflags` in it.

    python check_subprocesses.py            # the whole folder
    python check_subprocesses.py file.py
"""

import ast
import pathlib
import sys

LAUNCHERS = {'run', 'Popen', 'call', 'check_call', 'check_output'}

# Programs that never open a console: reporting them would be noise.
CONSOLELESS_BY_NATURE = {'explorer', 'open', 'xdg-open'}

# Files that are not part of the GUI application. A build script runs in a
# console, on the CI machine: asking it to hide a window that does not exist
# would make no sense.
# The pattern covers build_package.py, build_unix.py and their kin: they are
# CI tools, not the application.
OUTSIDE_APP = ('build_',)


def _first_text_argument(node):
    """The program called, when it can be read directly in the code."""
    if not node.args:
        return ''
    first = node.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value
    if isinstance(first, (ast.List, ast.Tuple)) and first.elts:
        head = first.elts[0]
        if isinstance(head, ast.Constant) and isinstance(head.value, str):
            return head.value
    return ''


def suspects(path: pathlib.Path):
    try:
        tree = ast.parse(path.read_text(encoding='utf-8'))
    except (OSError, SyntaxError):
        return []

    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        if not (isinstance(target, ast.Attribute) and target.attr in LAUNCHERS):
            continue
        if getattr(target.value, 'id', '') != 'subprocess':
            continue
        if any(m.arg == 'creationflags' for m in node.keywords):
            continue
        program = _first_text_argument(node).lower()
        if program.rsplit('\\', 1)[-1].replace('.exe', '') in CONSOLELESS_BY_NATURE:
            continue
        found.append((node.lineno, target.attr, program or '?'))
    return found


def main(argv):
    targets = [pathlib.Path(a) for a in argv[1:]] or sorted(
        pathlib.Path.cwd().glob('*.py'))
    total = 0
    for path in targets:
        if path.name == pathlib.Path(__file__).name:
            continue
        if path.name.startswith(
                OUTSIDE_APP + ('_', 'fix_', 'test_', 'check_')):
            continue
        for line, launcher, program in suspects(path):
            print(f"{path.name}:{line}: subprocess.{launcher}({program}) "
                  f"without creationflags — a console will flash")
            total += 1
    if total:
        print(f"\n{total} subprocess(es) without CREATE_NO_WINDOW.")
        return 1
    print(f"{len(targets)} file(s) checked: no stray console.")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
