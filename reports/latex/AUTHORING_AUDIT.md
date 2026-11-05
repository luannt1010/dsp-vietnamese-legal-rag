# Authoring and evidence audit

## Reference fidelity

Source: root `Report_dsp.docx`, SHA-256 `7b5f24bdcf6b1b4a7494c9c2783482d945bf97eed05dbd6ac0a3bd6259c887d9`.

Read using bundled python-docx and OOXML; exported read-only by native Word to a 32-page reference PDF. Cover, contents, front matter and body patterns were visually inspected. Source remains unchanged.

Preserved: A4; 25.4 mm top/bottom/left and 24.9767 mm right margins; Calibri 11 pt; 1.15 body spacing; red 16 pt chapter headings; bold 13/12 pt section/subsection hierarchy; FPT logo; ministry/university; serif cover title; Group 4 roster and IDs; supervisor Nguyen Trong Tai; main I–IX outline and its applicable subsections.

Deliberate changes: automatic contents/list of figures/list of tables and references, continuous figure/table numbers, footer page numbers, compact 4 pt paragraph spacing, filled acknowledgement/acronyms, actual group/supervisor instead of cover placeholders. The optional external-supervisor slot is omitted because no person is supplied. Methodology sample 1 is used, and sample 2's reinforcement-learning outline is omitted. Personal reflection is optional and omitted rather than fabricating personal experiences. The dated cover uses November 2026, not a claim of official submission.

## Corrections to the existing draft

| Draft assertion | Evidence-aligned report |
| --- | --- |
| Production-ready legal assistant, near-zero hallucination | Local research prototype; verification and model judging remain imperfect |
| Every claim has formal exact legal proof | Source-derived citations and answer-level support checks; no formal sentence-level proof |
| Web interface / trust badges already delivered | CLI prepare/ask/chat/doctor and benchmark commands; web delivery is future work |
| BM25Plus | BM25Okapi, k1=1.2, b=0.75 |
| Nemotron / 4096-dimensional embeddings | Ollama BGE-M3 dense vectors, 1024 dimensions |
| 1500-byte semantic chunking | Hierarchical provision-aware token chunking; target512/overlap64 fallback |
| Three graph hops | Graph depth2; B4 retrieval rounds independently bounded at3 |
| Microsoft GraphRAG | Explicit source-backed document references and chunk hierarchy; no community summaries |
| Complete national legal coverage | Three-topic snapshot:7425 articles,647 docs,14708 leaves,14333 parents |
| Verified up-to-date validity | Fixed source revision and available metadata; unknown status stays unknown |
| Unsupported historical chunk counts, recall gains and costs | Removed; current frozen 225-sample run used consistently |
| Completion or low judge score interpreted as true accuracy | Separate denominators, semantic judge counterexamples and strict-yield definition |

## Evidence used

- Implementation in `src/`, role/configuration YAML, prompts, and project docs; no production code changed for authoring.
- Source selection: pinned revision `a1b6860c821b7142ffe2385178af4e4bb6f86aff`, prepared corpus `4d70694000eb63e3`.
- Normalized dataset and its README/review/manifest:45 development questions,233 claims,115 evidence spans; independent legal review still pending.
- `.runtime/benchmarks/three-topics-dev-v1-fixed-01`:225 samples and225 scores; existing arithmetic audit and review.
- Read-only trace audit:enabled graph branches can affect ranks, but zero retained relation lists and zero `[Quan hệ văn bản]` blocks in final contexts; no inference that graph itself has zero edges.
- Regression records:366 passed/10 skipped/246 subtests; focused B3 11/11 and B0 4/4 development cases plus negative controls. Not a fresh test run caused by report authoring, nor an accuracy estimate.
- Primary papers and model/dataset sources checked online. Research performance findings are not presented as this project's results.

## Remaining gaps explicitly disclosed

No documented individual role allocation, meeting logs, spending ledger, exact hardware/RAM/GPU, LLM quantization, held-out final test, or independent legal review. Hardware notes in the recorded benchmark are an unfilled placeholder. Judge model differs in size from the generator but shares its family and the verifier model; independence is not claimed. Ten judge truncation errors are excluded for affected metrics. Some semantic judgments are demonstrably wrong; no corrected quality score is fabricated.

The dataset was used for development and question clarification. One repeat and near-ceiling cue-rich retrieval limit power and generalization. No Holm-adjusted significant difference is found; no equivalence claim is made. B0's lowest recorded mean latency supports an engineering baseline choice, not a universal quality winner.

## Reproducible document inputs

`export_data.py` reads frozen artifacts with no model calls or source mutations. It writes CSV/TeX plot inputs and SHA-256 provenance; all are included in the source package so it compiles without `.runtime`. The final PDF is built with a Unicode engine, original logo, embedded fonts and vector figures, then rasterized for page-by-page layout QA. Detailed local QA evidence is kept under `.runtime/report-authoring/`.

Final verification: 40 A4 pages; 12 numbered figures; 13 numbered tables; 176 valid internal destinations. All fonts embedded. No overfull boxes, missing glyphs, undefined references or missing citations. All 40 rendered pages visually reviewed, with full-size inspection of the architecture and statistical/latency charts. Original DOCX and frozen benchmark input hashes unchanged. Compiler: Tectonic 0.17.0. PDF SHA-256: `103315e3cef8cd6bdabd495de6d119c2662986badb84b3b61cdf166cd3baac92`.
