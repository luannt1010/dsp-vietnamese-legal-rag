"""Create the single-file pdfLaTeX variant without changing report content.

The flattened XeLaTeX source is preserved. Only the font/encoding setup and
instructions change; figure PDFs are copied from the verified light package.
"""
from __future__ import annotations

import argparse
import re
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FONTS = r"""% pdfLaTeX fonts: Carlito has Calibri-compatible metrics.
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage[sfdefault]{carlito}
\usepackage{tgtermes}
\usepackage[scaled=0.95]{inconsolata}
\newcommand{\coverfont}{\fontfamily{qtm}\selectfont}"""


def build(source: Path, destination: Path, *, force: bool = False) -> None:
    if (destination / "main.tex").exists() and not force:
        raise FileExistsError("Destination main.tex exists; preserve edits or explicitly pass --force")
    original = (source / "main.tex").read_text(encoding="utf-8")
    lines = original.splitlines()
    assert lines.count(r"\usepackage{fontspec}") == 1
    assert sum(line.startswith(r"\IfFontExistsTF") for line in lines) == 3
    text = "\n".join(
        FONTS if line == r"\usepackage{fontspec}" else line
        for line in lines if not line.startswith(r"\IfFontExistsTF")
    ) + "\n"
    text = text.replace("Compile with XeLaTeX.", "Compile with pdfLaTeX.")
    # Protect the report body from accidental changes during a font conversion.
    assert text.split(r"\begin{document}",1)[1] == original.split(r"\begin{document}",1)[1]
    assert not re.search(r"\\(?:setmainfont|setmonofont|newfontfamily|IfFontExistsTF)\b", text)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "main.tex").write_text(text, encoding="utf-8")
    graphics = sorted(set(re.findall(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", text)))
    for name in graphics:
        origin = (source / name).resolve()
        if not origin.is_relative_to(source):
            raise ValueError(f"Graphic outside source: {name}")
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origin, target)
    readme = """# Single-file pdfLaTeX report

Upload this ZIP as a new Overleaf project. Select pdfLaTeX as the compiler and
main.tex as the main document. Keep figures/ beside main.tex, then Recompile.
All chapters, tables, citations and bibliography are in main.tex; no .bib file
or BibTeX step is needed. Text and tables remain editable.

This version removes fontspec and system-font detection. It uses T1/UTF-8 input,
Carlito (Calibri-compatible body metrics), TeX Gyre Termes for the cover title,
and Inconsolata for code. These are TeX Live fonts, not Windows font files.
Diagrams stay pre-rendered vector PDFs, so TikZ/PGFPlots are not compiled.
Font substitution may change line/page breaks from the earlier Calibri PDF.

Local command (TeX Live or MiKTeX): run pdflatex main.tex repeatedly until the
cross-reference and contents warnings disappear, or use latexmk -pdf main.tex.
No paid Overleaf feature is used by this source. Actual server compilation
time has not been measured; Overleaf's plan timeout still applies.

The original XeLaTeX version is preserved separately. Regeneration source:
reports/latex/make_pdflatex.py. It copies only the required graphic assets and
changes only the preamble; the report body is checked for exact equality.
"""
    (destination / "README.md").write_text(readme, encoding="utf-8")
    archive = ROOT / "output/Report_dsp_pdflatex.zip"
    files = [destination / "main.tex", destination / "README.md", *(destination / name for name in graphics)]
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for path in files:
            z.write(path, path.relative_to(destination).as_posix())
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert [name for name in z.namelist() if name.endswith(".tex")] == ["main.tex"]
    print(f"Created pdfLaTeX source: {destination / 'main.tex'}", flush=True)
    print(f"ZIP: {archive}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "reports/overleaf-single")
    parser.add_argument("--destination", type=Path, default=ROOT / "reports/overleaf-pdflatex")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    build(args.source.resolve(), args.destination.resolve(), force=args.force)
