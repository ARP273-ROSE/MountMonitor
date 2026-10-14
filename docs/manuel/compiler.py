#!/usr/bin/env python3
"""Builds the three MountMonitor manuals (house PDF format): EN, FR, NL.

    python3 docs/manuel/compiler.py [en fr nl]      (from the repository root)

Sources: docs/manuel/{en,fr,nl}.tex, corps_*.tex, preambule.tex, titre.tex;
real screenshots: docs/manuel/captures/ (made by captures.py). Outputs:
docs/manual_{en,fr,nl}.pdf, shipped with the program and opened by
Help > Manual. pdflatex twice (table of contents), then the temporary
files are removed.
"""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent
RACINE = SRC.parents[1]
if os.environ.get("TEXLIVE_BIN"):
    os.environ["PATH"] = os.environ["TEXLIVE_BIN"] + os.pathsep + os.environ.get("PATH", "")


def compiler(langue: str) -> None:
    version = (RACINE / "VERSION").read_text(encoding="utf-8").strip()
    (SRC / "version.tex").write_text(f"\\def\\VERSION{{{version}}}\n", encoding="utf-8")
    try:
        for _ in range(2):
            r = subprocess.run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error",
                                f"{langue}.tex"], cwd=SRC, capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
            if r.returncode != 0:
                print(r.stdout[-3000:])
                raise SystemExit(f"{langue}.tex failed to build")
        journal = (SRC / f"{langue}.log").read_text(encoding="utf-8", errors="replace")
        if re.search(r"Overfull \\hbox \((\d{2,}|[5-9])\.", journal):
            print(f"  warning: line too long in {langue} (see the log)")
        shutil.copy2(SRC / f"{langue}.pdf", RACINE / "docs" / f"manual_{langue}.pdf")
    finally:
        for ext in (".aux", ".log", ".out", ".toc", ".pdf"):
            (SRC / f"{langue}{ext}").unlink(missing_ok=True)
        (SRC / "version.tex").unlink(missing_ok=True)
    info = subprocess.run(["pdfinfo", str(RACINE / "docs" / f"manual_{langue}.pdf")],
                          capture_output=True, text=True).stdout if shutil.which("pdfinfo") else ""
    n = re.search(r"Pages:\s+(\d+)", info)
    print(f"  docs/manual_{langue}.pdf: {n.group(1) if n else '?'} pages")


if __name__ == "__main__":
    for lg in (sys.argv[1:] or ["en", "fr", "nl"]):
        compiler(lg)
