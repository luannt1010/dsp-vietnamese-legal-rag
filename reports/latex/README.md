# English course report (LaTeX)

`Report_dsp.tex` follows the supplied `Report_dsp.docx` structure (I–IX), A4 geometry, Calibri body, dark-red chapter headings, serif cover title, original FPT logo, team roster and supervisor. It uses Methodology sample 1; the alternative RL sample is inapplicable. The original Word file is unchanged.

The report is based on **three-topics-dev-v1-fixed-01**, 45 development questions × 5 methods × 1 repeat. It deliberately distinguishes completion, chunk retrieval, packed context, model-judged quality and latency. No significant winner, held-out accuracy, current legal validity, or production readiness is claimed.

The delivered PDF has **40 A4 pages, 12 figures and 13 tables**. All pages were rendered and visually reviewed; internal destinations, caption numbering, embedded fonts, benchmark input hashes and unresolved-reference checks passed. The portable compiler used for this delivery was Tectonic 0.17.0.

## Compile without the original benchmark directory

### pdfLaTeX single-file version

For the requested pdfLaTeX workflow, upload `output/Report_dsp_pdflatex.zip` as a
new Overleaf project. Select **pdfLaTeX**, set **main.tex** as the main document,
and keep the accompanying `figures/` directory. The local editable source is
`reports/overleaf-pdflatex/main.tex`. It contains all chapter/table/bibliography
content and uses TeX Live Type 1 fonts instead of `fontspec` or Windows fonts.

This version was compiled with pdfTeX 1.40.29 / TeX Live 2026: three converged
passes in 3.42 seconds locally; 40 pages, 12 figures and 13 tables. All pages were
rendered and visually reviewed. No missing glyphs, overfull boxes or undefined
references were found. Actual Overleaf server timing has not been measured.
The preview is `output/pdf/Report_dsp_pdflatex.pdf`.

To regenerate from the flattened Unicode source:

```cmd
python reports\latex\make_pdflatex.py
```

Use `--force` only after preserving any manual edits to the existing destination.
The multi-file authoring source below remains a separate Unicode-engine variant.

All plot/table inputs are included under `data/`. Use a **Unicode LaTeX engine** (Tectonic or XeLaTeX), not pdfLaTeX. Calibri/Times New Roman are selected if installed; otherwise Carlito/TeX Gyre fallbacks are used. Font substitution changes line breaks. The supplied PDF was compiled with Calibri and Times New Roman on Windows.

Windows CMD with [Tectonic](https://tectonic-typesetting.github.io/):

```cmd
cd /d D:\dsp-vietnamese-legal-rag\reports\latex
tectonic -X compile Report_dsp.tex --keep-logs
```

Tectonic downloads TeX support files on first use; no model or database is involved. It runs BibTeX and reference passes automatically. The output is `Report_dsp.pdf` beside the source. The repository delivery copy is `output/pdf/Report_dsp.pdf`.

Alternative with TeX Live or MiKTeX:

```cmd
cd /d D:\dsp-vietnamese-legal-rag\reports\latex
xelatex -interaction=nonstopmode Report_dsp.tex
bibtex Report_dsp
xelatex -interaction=nonstopmode Report_dsp.tex
xelatex -interaction=nonstopmode Report_dsp.tex
```

For Overleaf, upload the contents of this directory, select **XeLaTeX**, and use `Report_dsp.tex` as the main file. System fonts may differ; the bundled final PDF is the verified layout. The source package contains no licensed Windows font files.

### Overleaf compile timeout

Overleaf Free currently allows 10 seconds per compile. The full source redraws
12 TikZ/PGFPlots graphics on each build and may exceed that limit. Prefer
`output/Report_dsp_overleaf_light.zip`: upload it as a **new project**, select
XeLaTeX, and use `Report_dsp.tex` as the main document. It embeds the same figures
as pre-rendered vector PDFs while keeping text, tables and captions editable.
Local compilation succeeded in about 5.5 seconds; Overleaf server timing has not
been verified. See the [official timeout advice](https://docs.overleaf.com/troubleshooting-and-support/fixing-and-preventing-compile-timeouts).

To regenerate the light package from this source (Windows CMD, repository root):

```cmd
python reports\latex\build_overleaf.py --tectonic .runtime\report-authoring\tools\tectonic\tectonic.exe
```

Or pass the path to your own Tectonic executable. The script renders figure PDFs,
builds a local verification PDF and packages the generated source. It may download
TeX support files on first use. Chart/data changes require regenerating those
figures; modifying CSV files inside the lightweight ZIP alone does not redraw them.

## Single-file editing variant

`output/Report_dsp_main.zip` contains exactly one editable LaTeX source,
`main.tex`, plus the logo/vector figures and a short README. Chapters, table rows
and the formatted bibliography are inlined; no `.bib`, `.bbl`, `chapters/` or
`data/` directory is needed to compile this variant. Upload as a new Overleaf
project, choose XeLaTeX, and set `main.tex` as the main document. Keep `figures/`.

The local editable copy is `reports/overleaf-single/main.tex`. This is a generated
report variant; edits there are not copied back to the multi-file authoring
source. To regenerate from the light package:

```cmd
python reports\latex\make_single_file.py --tectonic .runtime\report-authoring\tools\tectonic\tectonic.exe
```

The generator refuses to overwrite an existing `main.tex` unless `--force` is
explicitly passed. Preserve manual edits before regeneration.

## Regenerate tables and plots from the frozen run

From repository root, any Python 3.10+ environment works; the exporter uses only the standard library:

```cmd
conda activate free_env
python reports\latex\export_data.py --run .runtime\benchmarks\three-topics-dev-v1-fixed-01
```

This reads existing artifacts and writes report data only. It performs no inference or offline model judging. It checks the pilot's expected 225 samples/scores and records hashes and denominators in `data/provenance.json`. It exports the recorded matrix to `recorded-pilot.yml` (JSON syntax is valid YAML). `data/latency.csv` is a compact per-question timing export; `data/paired.csv` includes the report's existing paired comparisons.

The exporter is intentionally tied to this report's pilot. To report another run, review the narrative, case studies, sample counts and interpretations as well as exporting new numbers. Do not replace the frozen data with a new run while retaining the old conclusions.

## Run the benchmark again

Appendix IX.1 contains Windows CMD/Conda commands for this three-topic development set. Runtime installation details remain in `docs/BENCHMARK_QUICKSTART.md`; its national-security smoke example selects a **different corpus**, so do not carry its topic override into this run. Default `configs/demo/data_pipeline.yml` selects the three report topics.

The recorded-pilot matrix has one repeat. `configs/benchmark/hybrid.yml` has three repeats. Use a new output directory for changed inference settings. Rescoring existing answers and rerunning inference are different operations.

## Editing and evidence

- `chapters/`: front matter and sections I–VII, IX; bibliography is section VIII.
- `references.bib`: primary research papers and source/model cards.
- `figures/fpt-logo.png`: original logo extracted from the supplied Word reference.
- TikZ/PGFPlots figures are vector content in the PDF; their source lives beside the narrative.
- `AUTHORING_AUDIT.md`: template mapping, factual corrections, and remaining documentation gaps.

Member-specific work allocation, external supervisor, spending and missing hardware details were not invented. Obtain the team's actual records before adding them. The report date is November 2026; change it to the actual submission date if required.
