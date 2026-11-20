#!/usr/bin/env python3
"""Looks for what can freeze the window.

A slow operation called from an event handler blocks the Qt loop, hence the
whole display. This spots the expensive calls — database, network, file
system, subprocesses — that are not already in a background thread.

The check is static: it reads the code, it does not run it. It reports
suspects, not certainties, and it has two known blind spots, both paid for:

  - it only sees functions whose name announces an event. The podcast
    episode census, which tested two thousand three hundred files on the GUI
    thread, was called `_telecharger_tous_les_manquants` and so slipped
    through;
  - it only sees Python code. The biggest startup freeze happened *inside
    Qt*, between emitting a signal and receiving it — see check_signals.py.

For the rest, measurement wins: a heartbeat in the event loop and a probe
sampling the GUI thread's stack tell what no reading of the code will.

    python audit_blocking.py            # the whole folder
    python audit_blocking.py file.py
"""
import ast
import pathlib
import sys

# What is expensive, by family.
# "get" and "join" are left out: dict.get and str.join share their names with
# requests.get and Thread.join, and drowned the real suspects under hundreds
# of false ones.
COSTLY = {
    'database': {'execute', 'fetchall', 'fetchone', 'commit', 'checkpoint',
                 'executemany', 'backup_database'},
    'network': {'urlopen', 'post', 'urlretrieve'},
    'files': {'isfile', 'exists', 'getsize', 'listdir', 'walk', 'glob',
              'rglob', 'copy2', 'copy', 'move', 'rmtree', 'disk_usage',
              'getmtime'},
    'process': {'run', 'check_output', 'call', 'Popen'},
    'waiting': {'sleep'},
}
ALL = {name: family for family, names in COSTLY.items() for name in names}

# A function whose name starts like this answers an event: it runs on the
# GUI thread.
EVENT_PREFIXES = ('_on_', 'on_', 'paint', 'mouse', 'key', 'close',
                  'show', 'drag', 'drop', 'resize', 'event')


def analyse(path: pathlib.Path):
    try:
        source = path.read_text(encoding='utf-8')
        tree = ast.parse(source)
    except (OSError, SyntaxError):
        return []

    suspects = []
    for function in ast.walk(tree):
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not function.name.startswith(EVENT_PREFIXES):
            continue

        # Nested function bodies are left out: putting the expensive work
        # there, then launching them in a thread, is precisely the right way
        # to do it.
        inner_ids = set()
        for inner in ast.walk(function):
            if (isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and inner is not function):
                inner_ids.update(id(n) for n in ast.walk(inner))

        for node in ast.walk(function):
            if id(node) in inner_ids or not isinstance(node, ast.Call):
                continue
            target = node.func
            callee = (target.attr if isinstance(target, ast.Attribute)
                      else target.id if isinstance(target, ast.Name) else '')
            if callee in ALL:
                suspects.append((node.lineno, function.name, callee, ALL[callee]))
    return suspects


def main(argv):
    targets = [pathlib.Path(a) for a in argv[1:]] or sorted(
        pathlib.Path(__file__).parent.glob('*.py'))
    total = 0
    for path in targets:
        if path.name == pathlib.Path(__file__).name:
            continue
        suspects = analyse(path)
        if not suspects:
            continue
        print(f"\n=== {path.name} ===")
        for line, function, call, family in sorted(suspects):
            print(f"  {path.name}:{line:5d}  {function:34s} {call:16s} ({family})")
            total += 1
    print(f"\n{total} expensive call(s) on the GUI thread — to judge one by one.")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
