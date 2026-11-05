# One editable LaTeX source

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
