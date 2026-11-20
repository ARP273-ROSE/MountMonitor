#!/usr/bin/env python3
"""Checks that the installer and the application agree.

Two points that only show in use, and late:

  - `AppMutex` in installer.iss must carry exactly the name of the mutex
    created by the application. If they diverge, the installer believes
    nothing is running, fails to replace the open files, and the user ends
    up with an installation that says "finished" but a program that starts
    the old version again.
  - `[InstallDelete]` must wipe the application folder before copying.
    Inno overwrites what it brings, never what it no longer brings; yet the
    automatic update unpacks an archive into that same folder.

Static check, no dependencies.
"""

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).parent


def main():
    import json
    iss = (ROOT / 'installer.iss').read_text(encoding='utf-8', errors='replace')
    kit = json.loads((ROOT / 'kit.json').read_text(encoding='utf-8'))
    # The mutex is created by the entry point, whatever its name: kit.json
    # says which, as for the rest of the setup.
    source = (ROOT / kit['point_entree']).read_text(encoding='utf-8')
    expected = f"{kit['nom_fichier']}EnCours"
    faults = []

    found = re.search(r'^AppMutex\s*=\s*(\S+)\s*$', iss, re.MULTILINE)
    if not found:
        faults.append("installer.iss declares no AppMutex: an installation "
                      "over the running application will fail without "
                      "saying so.")
    else:
        name = found.group(1).replace('{#AppName}', kit['nom_fichier'])
        if name != expected:
            faults.append(f"AppMutex resolves to \"{name}\", expected \"{expected}\".")
        if f"'{name}'" not in source and f'"{name}"' not in source:
            faults.append(f"AppMutex is \"{name}\" in installer.iss, but "
                          f"the entry point does not create that mutex.")
        if 'CreateMutexW' not in source:
            faults.append("The entry point does not call CreateMutexW: the "
                          "named mutex does not exist, AppMutex will see nothing.")

    if '[InstallDelete]' not in iss:
        faults.append("installer.iss has no [InstallDelete] section: "
                      "the old version is not cleaned up before copying.")
    else:
        for folder in (r'{app}\app', r'{app}\python'):
            if folder not in iss:
                faults.append(f"[InstallDelete] does not wipe {folder}.")

    for fault in faults:
        print("  " + fault)
    if faults:
        print(f"\n{len(faults)} disagreement(s) between the installer and the application.")
        return 1
    print("Installer and application agree: named mutex and cleanup in place.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
