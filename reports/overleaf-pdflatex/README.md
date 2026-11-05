# Single-file pdfLaTeX report

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

Verified locally: pdfTeX 1.40.29 / TeX Live 2026; 40 A4 pages, 12 figures, 13
tables, 176 valid destinations. Three passes converged in 3.42 seconds. All
40 pages rendered and visually inspected; fonts embedded, no missing glyphs,
no overfull boxes, no undefined citations/references. The report body is exactly
unchanged from the previous single-file source. Overleaf timing is untested.
