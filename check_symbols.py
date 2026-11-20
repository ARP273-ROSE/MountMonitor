#!/usr/bin/env python3
"""Looks for names that are used but never imported.

Python only notices when the faulty line runs. A class defined deep inside a
rarely called method can thus stay silent for months, then bring the
application down the day that method becomes automatic.

That is exactly what happened: `RefreshWorker(QObject)` lived in a function
triggered by a menu click, and `QObject` had never been imported. The day the
feed refresh moved to startup, the program crashed on every launch — on
someone else's machine.

This check is static and dependency-free: it reads the files, it does not
run them.

    python check_symbols.py            # the whole folder
    python check_symbols.py file.py
"""

import ast
import pathlib
import re
import sys

# What Python provides without importing anything.
BUILTINS = set(dir(__builtins__)) | {
    '__file__', '__name__', '__doc__', 'self', 'cls',
}

# A class name: capital initial, and at least one lowercase letter — which
# rules out constants in capitals.
#
# A first draft required an inner capital, in the style of "MainWindow".
# That missed "QObject", precisely the name that was missing: a check that
# does not see the defect it is meant to catch is useless.
CLASS_PATTERN = re.compile(r'^[A-Z][A-Za-z0-9_]*$')


def _looks_like_a_class(name: str) -> bool:
    return bool(CLASS_PATTERN.match(name)) and any(c.islower() for c in name)


def defined_names(tree: ast.AST) -> set[str]:
    """Everything the file defines or imports, wherever it is."""
    known = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                known.add(alias.asname or alias.name.split('.')[0])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            known.add(node.name)
            for arg in getattr(node, 'args', ast.arguments(
                    posonlyargs=[], args=[], kwonlyargs=[], kw_defaults=[], defaults=[])).args:
                known.add(arg.arg)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            known.add(node.id)
        elif isinstance(node, ast.arg):
            known.add(node.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            known.add(node.name)
        elif isinstance(node, ast.Global):
            known.update(node.names)
    return known


def check(path: pathlib.Path) -> list[tuple[int, str]]:
    """Returns [(line, name)] of the classes used without ever being defined."""
    try:
        source = path.read_text(encoding='utf-8')
        tree = ast.parse(source)
    except (OSError, SyntaxError):
        return []

    known = defined_names(tree) | BUILTINS
    missing = {}
    for node in ast.walk(tree):
        if (isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
                and _looks_like_a_class(node.id) and node.id not in known):
            missing.setdefault(node.id, node.lineno)
    return sorted((line, name) for name, line in missing.items())


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
    faults = 0
    for path in targets:
        if path.name == pathlib.Path(__file__).name:
            continue
        for line, name in check(path):
            print(f"{path.name}:{line}: {name} is used but never imported")
            faults += 1
    if faults:
        print(f"\n{faults} missing name(s): the application will crash on reaching them.")
        return 1
    print(f"{len(targets)} file(s) checked: no missing name.")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
