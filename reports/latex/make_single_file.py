"""Flatten the light report into main.tex, including table rows and bibliography.

Pre-rendered vector figures remain separate assets so the report does not redraw
TikZ/PGFPlots on Overleaf. Uses the existing compilation helper for verification.
"""
from __future__ import annotations

import argparse
import re
import shutil
import zipfile
from pathlib import Path

from build_overleaf import ROOT, compile_tex

INPUT = re.compile(r"(?m)^\\input(?:\{([^}\r\n]+)\}|[ \t]+([^ \t\r\n]+))[ \t]*$")
GRAPHIC = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}")


def expand_inputs(text: str, source: Path, stack: tuple[Path, ...] = ()) -> str:
    def replace(match: re.Match) -> str:
        name = match.group(1) or match.group(2)
        path = source / name
        if not path.suffix:
            path = path.with_suffix(".tex")
        path = path.resolve()
        if not path.is_relative_to(source) or path in stack:
            raise ValueError(f"Unsafe or circular input: {name}")
        content = expand_inputs(path.read_text(encoding="utf-8"), source, (*stack, path))
        return f"% BEGIN {name}\n{content.rstrip()}\n% END {name}\n"

    return INPUT.sub(replace, text)


def build(engine: Path, source: Path, destination: Path, *, force: bool = False) -> None:
    main = destination / "main.tex"
    if main.exists() and not force:
        raise FileExistsError("main.tex already exists; preserve edits or use --force explicitly")
    work = ROOT / ".runtime/report-authoring/single-file"
    work.mkdir(parents=True, exist_ok=True)
    # Let the original bibliography style produce its exact author-year entries;
    # then inline those entries so the delivered project needs no .bib or BibTeX.
    compile_tex(engine, source / "Report_dsp.tex", work / "bibliography", work / "bibliography-console.log", keep_intermediates=True)
    bbl = (work / "bibliography/Report_dsp.bbl").read_text(encoding="utf-8")
    text = expand_inputs((source / "Report_dsp.tex").read_text(encoding="utf-8"), source)
    text, count = re.subn(r"\\bibliographystyle\{plainnat\}\s*\\bibliography\{references\}", lambda _: bbl, text)
    assert count == 1, "Expected exactly one bibliography"
    text = text.replace("% Compile with Tectonic or XeLaTeX + BibTeX (see README.md).", "% Single editable source: main.tex. Compile with XeLaTeX. Keep figures/ beside this file.\n% Chapters, table data and bibliography are inlined below; no BibTeX step is needed.")
    assert not re.search(r"(?m)^\s*\\(?:input|include|bibliography|bibliographystyle)\b", text)
    destination.mkdir(parents=True, exist_ok=True)
    main.write_text(text, encoding="utf-8")
    assets = sorted(set(GRAPHIC.findall(text)))
    assert len(assets) == 13, "Expected the FPT logo and twelve pre-rendered figures"
    for name in assets:
        path = (source / name).resolve()
        if not path.is_relative_to(source):
            raise ValueError(f"Graphic outside source package: {name}")
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    readme = """# One editable LaTeX source

Upload this ZIP as a new Overleaf project. Choose XeLaTeX and main.tex, then
Recompile. Edit all report content in main.tex: front matter, chapters I-IX,
tables, captions, citations and bibliography. No chapters/, data/, .bib or .bbl
files are needed. Section comments mark the original chapter boundaries.

Keep figures/ beside main.tex. It contains the logo and twelve pre-rendered
vector PDF graphics, which reduce compile work. Text remains editable; changing
plots requires replacing the relevant figure PDF. Figure and table numbers,
contents and cross-references remain automatic. Body font fallbacks may change
line/page breaks on Overleaf. Server compile time has not been verified.

The bibliography is inlined as a thebibliography environment near the end of
main.tex. Edit its bibitem entries directly and use their keys with citep/citet.
No separate BibTeX processing is required.

Generation source: reports/latex/make_single_file.py in the project repository.
It reuses the light package's figures and the original plainnat bibliography.
Changes made here are not copied back to the multi-file authoring source.
Regeneration refuses to overwrite main.tex unless --force is explicitly passed.
"""
    (destination / "README.md").write_text(readme, encoding="utf-8")
    duration = compile_tex(engine, main, work / "compiled", work / "main-console.log")
    archive = ROOT / "output/Report_dsp_main.zip"
    files = [main, destination / "README.md", *(destination / name for name in assets)]
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for path in files:
            z.write(path, path.relative_to(destination).as_posix())
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert [p for p in z.namelist() if p.endswith(".tex")] == ["main.tex"]
    print(f"Created {main}; {len(files)} packaged files; local compile {duration:.2f}s", flush=True)
    print(f"Archive: {archive}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tectonic", type=Path, required=True)
    parser.add_argument("--source", type=Path, default=ROOT / ".runtime/report-authoring/overleaf-light")
    parser.add_argument("--destination", type=Path, default=ROOT / "reports/overleaf-single")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    build(args.tectonic.resolve(), args.source.resolve(), args.destination.resolve(), force=args.force)
