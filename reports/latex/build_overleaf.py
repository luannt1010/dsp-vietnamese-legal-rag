"""Build an Overleaf package with pre-rendered vector figures.

The academic source under reports/latex remains the source of truth. Generated
chapters stay editable; only TikZ pictures become PDF graphics. This script
requires Tectonic and downloads TeX packages on its first invocation if needed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import time
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PICTURE = re.compile(r"\\begin\{tikzpicture\}.*?\\end\{tikzpicture\}", re.DOTALL)


def compile_tex(engine: Path, source: Path, output: Path, log: Path, *, keep_intermediates: bool = False) -> float:
    output.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    command = [str(engine), "-X", "compile", str(source), "--outdir", str(output), "--keep-logs"]
    if keep_intermediates:
        command.append("--keep-intermediates")
    with log.open("w", encoding="utf-8") as stream:
        subprocess.run(
            command,
            stdout=stream, stderr=subprocess.STDOUT, check=True,
        )
    return time.perf_counter() - start


def build(engine: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    work = ROOT / ".runtime/report-authoring/overleaf-figures"
    work.mkdir(parents=True, exist_ok=True)
    master = (HERE / "Report_dsp.tex").read_text(encoding="utf-8")
    preamble = master.split(r"\begin{document}", 1)[0]
    # Preview crops each picture to its natural bounding box. The original
    # geometry and font sizes preserve \textwidth-relative chart dimensions.
    preview = (
        r"\usepackage[active,tightpage]{preview}" "\n"
        r"\PreviewEnvironment{tikzpicture}" "\n"
        r"\setlength{\PreviewBorder}{0pt}" "\n"
    )
    shutil.copytree(HERE / "data", work / "data", dirs_exist_ok=True)
    shutil.copytree(HERE / "data", destination / "data", dirs_exist_ok=True)
    data_hash = hashlib.sha256()
    for path in sorted((HERE / "data").rglob("*")):
        if path.is_file():
            data_hash.update(path.relative_to(HERE).as_posix().encode())
            data_hash.update(path.read_bytes())
    shutil.copytree(HERE / "figures", destination / "figures", dirs_exist_ok=True)
    chapters = destination / "chapters"
    chapters.mkdir(exist_ok=True)
    rendered = destination / "figures/rendered"
    rendered.mkdir(exist_ok=True)
    inventory = []
    # Follow the main document order so the graphic index matches figure order.
    for chapter in re.findall(r"\\input\{(chapters/[^}]+)\}", master):
        original = (HERE / (chapter + ".tex")).read_text(encoding="utf-8")

        def replace(match: re.Match) -> str:
            name = f"figure-{len(inventory)+1:02}"
            picture = match.group()
            source = work / f"{name}.tex"
            source.write_text(preamble + preview + "\n\\begin{document}\n" + picture + "\n\\end{document}\n", encoding="utf-8")
            pdf = work / f"{name}.pdf"
            stamp = work / f"{name}.sha256"
            # A picture can \input a plot program or read CSV data. Include
            # those dependencies so changed benchmark data cannot reuse a stale PDF.
            digest = hashlib.sha256(source.read_bytes() + data_hash.digest()).hexdigest()
            if not pdf.exists() or not stamp.exists() or stamp.read_text() != digest:
                duration = compile_tex(engine, source, work, work / f"{name}-console.log")
                stamp.write_text(digest)
                print(f"Rendered {name}: {duration:.2f}s", flush=True)
            shutil.copy2(pdf, rendered / pdf.name)
            inventory.append({"graphic": name, "chapter": chapter, "source_sha256": digest})
            return rf"\includegraphics{{figures/rendered/{name}.pdf}}"

        (destination / (chapter + ".tex")).write_text(PICTURE.sub(replace, original), encoding="utf-8")
    assert len(inventory) == 12, "Review the package build when the figure inventory changes"
    light = master.replace(r"\usepackage{graphicx,tikz,pgfplots}", r"\usepackage{graphicx}")
    light = "\n".join(line for line in light.splitlines() if not line.startswith((r"\usetikzlibrary", r"\pgfplotsset", r"\tikzset"))) + "\n"
    (destination / "Report_dsp.tex").write_text(light, encoding="utf-8")
    shutil.copy2(HERE / "references.bib", destination / "references.bib")
    shutil.copy2(HERE / "AUTHORING_AUDIT.md", destination / "AUTHORING_AUDIT.md")
    readme = """# Overleaf package with pre-rendered figures

Upload this ZIP as a NEW Overleaf project. Select XeLaTeX as the compiler and
Report_dsp.tex as the main document, then click Recompile. The report text,
tables, captions, references and cross-references remain editable.

The 12 diagrams/plots are embedded vector PDF files under figures/rendered/.
TikZ/PGFPlots are not loaded during report compilation. This reduces repeated
work; it does not change Overleaf's plan limits. The package has been compiled
locally; successful compilation inside a particular Overleaf account is not
guaranteed, and no paid-account features are used by this source.

Edit chapter text under chapters/. To change chart values or diagram designs,
edit the original reports/latex source in the repository, then regenerate this
package with build_overleaf.py. Changing CSV files here alone does not redraw
the already rendered figures. The original full-source ZIP remains available.

All figure fonts are embedded. Body fonts use the original automatic fallbacks;
Overleaf may substitute Carlito/TeX Gyre fonts, changing line/page breaks.
The first compile may need extra passes for references. If a compile times out,
check the first actual error with Stop on first error before retrying.
"""
    (destination / "README.md").write_text(readme, encoding="utf-8")
    # Remove unused PGF plot programs from this generated package, retaining
    # numeric evidence and the TeX table rows that the report still reads.
    for name in ("ci-plot.tex", "ecdf-plot.tex"):
        (destination / "data" / name).unlink(missing_ok=True)
    (destination / "figure-manifest.json").write_text(json.dumps(inventory, indent=2)+"\n", encoding="utf-8")
    duration = compile_tex(engine, destination / "Report_dsp.tex", work / "report", work / "report-console.log")
    print(f"Light report compiled: {duration:.2f}s (local Tectonic, not Overleaf)", flush=True)
    archive = ROOT / "output/Report_dsp_overleaf_light.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(destination.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(destination).as_posix())
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
    (work / "build-result.json").write_text(json.dumps({"local_compile_seconds":duration,"figures":len(inventory),"archive":str(archive)},indent=2)+"\n",encoding="utf-8")
    print(f"Package ready: {archive}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tectonic", type=Path, required=True)
    parser.add_argument("--destination", type=Path, default=ROOT / ".runtime/report-authoring/overleaf-light")
    args = parser.parse_args()
    build(args.tectonic.resolve(), args.destination.resolve())
