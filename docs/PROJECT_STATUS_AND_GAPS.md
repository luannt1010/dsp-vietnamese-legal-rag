# Project status, gaps, and completion plan

**Review date:** 2026-11-03
**Purpose:** Summarize the current implementation and remaining work for
technical-lead review. This is a status report, not a claim that the project is
production-ready or that benchmark quality has been established.

## Executive summary

The project has progressed from independently implemented modules to an
integrated CLI RAG pipeline. The current documented path includes legal-data
preparation and indexing, query analysis, metadata filtering, hybrid and graph
retrieval, reranking, retrieval evaluation and feedback, context construction,
answer generation, citation verification, and orchestration. The pipeline
audit reports successful smoke runs against Ollama, PostgreSQL/pgvector, and
Neo4j for the configured corpus topics.

The largest gap is now **measured answer and retrieval quality**, not the
absence of a running pipeline. There is no reviewed, labeled evaluation
dataset, and the B0-B4 benchmark protocol has not been implemented as a
reproducible runner. Existing unit and integration tests and successful smoke
runs establish software behavior and integration for tested cases; they do not
establish legal correctness, comparative retrieval quality, or production
readiness.

## Current status by area

| Area | Documented status | Remaining concern |
|---|---|---|
| Contracts and modules | Query analysis, retrieval evaluation, retrieval, generation, and orchestration implementations are present. | Confirm final product requirements and ownership where the original technical specification and later implementation reports differ. |
| Data and indexes | Data preparation, hierarchical chunking, embeddings, vector and graph stores, and topic-based corpus preparation are documented. | Freeze an exact corpus snapshot for evaluation; validate source coverage, metadata, amendments, and legal validity at the relevant date. |
| Integrated application | CLI demo wires analysis through citation verification. Recent audit documents real-service smoke tests. | The documented implementation is a CLI/demo, not a completed API or production deployment. |
| Evaluation implementation | Ranking and answer/context metric aggregators and a JSONL dataset schema/loader are present. | Metrics consume labels or judgments; they do not create verified labels or perform the required judging themselves. |
| Evaluation data | The repository has corpus fixtures and corpus snapshots. | No reviewed, labeled evaluation question set or benchmark ground truth is documented as available. Corpus chunks are not ground truth. |
| Benchmark | The B0-B4 experiment plan is documented. | No runner, frozen run manifest, complete stage artifacts, judge workflow, aggregate report, confidence intervals, or stage telemetry is documented as implemented. |
| Testing | Unit tests, database integration tests, and smoke tests are documented. | No benchmark-derived quality result; the latest test total should be confirmed by rerunning the suite on the PR branch because reports record different historical totals. |
| API and operations | The technical specification includes API/infrastructure and deployment-oriented phases. | API, packaging/deployment, production monitoring, and operational acceptance are not established by the current demo reports. |

## Evaluation dataset: responsibility and status

The technical specification explicitly assigns **Evaluation Dataset and
Benchmark** to Nguyễn Trí Anh. Therefore, creating and coordinating the
evaluation dataset is part of Trí Anh's assigned scope. It is also a
team-reviewed deliverable: Trí Anh can own the schema, collection process,
loader validation, IDs, split groups, and benchmark integration, but legal
answers and evidence must be verified by reviewers familiar with the source
documents. Dataset labels must not be inferred automatically from corpus
chunks.

Current progress:

- **Implemented:** JSONL schema and loader, validation of required fields and
  answerability/evidence consistency, duplicate-ID checks, and leakage checks
  for declared `split_group`s.
- **Not started / unavailable:** reviewed pilot questions, reference answers
  and claims, cited legal evidence, relevance labels, and assigned development
  and test groups. No benchmark quality score can yet be reported.
- **Plan target:** first pilot of 30-50 reviewed questions, then expand toward
  approximately 300, subject to team annotation capacity.
- **Required prerequisite:** choose and freeze a corpus revision and identity.
  The run must record the source revision, prepared corpus ID, and relevant
  model/prompt versions. Evidence should use stable legal document/article
  locations and verified quotations; chunk IDs can be mapped later.
- **Review:** have a second person spot-check legal evidence and answers.
  Define the annotation rubric before scoring retrieval relevance or context
  sufficiency.

Suggested division of work:

1. Trí Anh prepares JSONL templates, annotation instructions, ID/split
   conventions, validates submitted records, and coordinates the pilot.
2. The corpus/data owner confirms corpus snapshot, document identity, metadata,
   and legal source locations.
3. A second reviewer checks reference answers, claims, quotations, exceptions,
   and whether each question is answerable from that snapshot.
4. The team agrees on relevance/sufficiency rubrics and approves the pilot
   before expanding the set or tuning systems.

This division is a recommendation for review, not a claim that the named
members have accepted those tasks.

## Remaining work, ordered by dependency

### P0 — Establish trustworthy evaluation data

- Select the exact corpus snapshot and define how amendments, repeals, and
  effective dates are represented. Do not describe a text as currently
  effective unless the data supports that conclusion.
- Agree on annotation rubric, question categories, answerability policy,
  evidence granularity, and the treatment of alternate valid sources.
- Create and independently review the 30-50 question pilot, including
  unanswerable cases and multi-claim/multi-document questions.
- Assign `split_group`s based on overlapping sources or question families,
  then separate development and test groups. Keep test labels out of tuning.

### P1 — Make B0-B4 runs reproducible

- Implement benchmark presets and a runner for B0-B4, including validation
  that each configuration follows the plan.
- Record a run manifest: corpus identity/revision, index and retrieval
  settings, model and prompt digests, judge identity, software revision,
  random/repeat settings, and timestamps.
- Retain up to 20 post-fusion/rerank results for retrieval scoring while
  sending only the planned top 5 to context construction.
- Persist the exact context sent to generation and the pre-verification answer
  draft, with explicit missing/not-run states for failed or refused requests.
- Lock B4 method flags, candidate depth, context cutoff, and feedback policy;
  allow only query refinement between rounds. Store each round and the final
  result; do not select a round using test ground truth.

### P2 — Add judging and analysis

- Define/freeze judges and prompts independently of the runtime evaluator.
  Store component judgments and judge errors rather than silently dropping
  failed cases or treating judge errors as quality scores.
- Compute the planned retrieval, context, and answer metrics. Report
  answerability/refusal coverage and correct-answer yield alongside metrics
  on completed answers.
- Add per-topic/type summaries, B0 deltas, paired bootstrap 95% confidence
  intervals, and repeat-run variability where budget allows. Do not collapse
  the metrics into an arbitrary single score.
- Manually review a stratified sample, including low-scoring and
  judge-disagreement cases.

### P3 — Close operational and product gaps

- Add stage and model-call latency instrumentation, including retrieval
  sub-stages, retries, rounds, token counts, and backend timings where the
  backend provides them. Mark unavailable backend timings as N/A.
- Decide whether an API and deployment are in scope for the delivery; if so,
  implement and test the API, packaging/deployment, configuration/secrets
  handling, and operational monitoring rather than treating the CLI smoke
  test as deployment validation.
- Define production acceptance criteria for legal source traceability,
  behavior on stale/incomplete law, failure handling, and supported corpus
  coverage.

## Team status and dependencies

The documentation shows substantial implementation across all four areas:

- **Luân / integration:** retrieval, orchestration, context, citation
  verification, and the integrated CLI path are documented. Remaining
  benchmark-specific gaps include the locked B0-B4 runner policy and stage
  artifacts; API/infrastructure completion is not demonstrated in the current
  demo reports. Intent taxonomy and hard-filter semantics still need explicit
  team confirmation where they affect the evaluation protocol.
- **Đức Anh / data and graph:** data preparation, graph retrieval, and corpus
  snapshots are documented. Evaluation still depends on a frozen corpus
  identity, stable evidence references, metadata quality, and review of legal
  validity/amendment coverage.
- **Trung / generation:** answer generation and citation verification are
  integrated in the documented demo. Answer quality remains unmeasured on a
  reviewed dataset; benchmark runs must capture drafts and final verified
  answers and keep generation settings fixed across configurations.
- **Trí Anh / query understanding and evaluation:** analyzer, evaluator,
  metric aggregators, dataset contract/loader, and unit tests are documented.
  The labeled dataset, benchmark runner, and measured evaluation results
  remain outstanding.
- **Whole team:** agree on data snapshot and annotation rubric, review the
  pilot, choose API/deployment scope, and approve acceptance criteria.

The documents do not provide individual due dates or an agreed schedule.
Consequently, this report identifies outstanding deliverables but does **not**
classify any member as late or behind schedule.

## Acceptance criteria for calling the benchmark complete

- The reviewed pilot loads through the dataset validator; IDs and split groups
  are unique and free of declared train/development/test leakage.
- Every answerable record has verified claims and source evidence; unanswerable
  records follow the agreed refusal/evidence policy.
- B0-B4 runs use a frozen corpus and reproducible manifests, preserve failures
  and per-stage artifacts, and follow the planned cutoffs and feedback policy.
- Reports include the agreed metrics, sample counts, uncertainty, topic/type
  breakdowns, and latency; no unsupported aggregate score is substituted.
- The team reviews representative outputs and documents limitations before
  making quality or deployment claims.

## Sources

- [Technical specification and team work plan](vietnamese_law_rag_technical_spec.md)
- [Benchmark plan](BENCHMARK_PLAN.md)
- [Evaluation dataset contract and workflow](EVALUATION_DATASET.md)
- [Pipeline audit report](PIPELINE_AUDIT_REPORT.md)
- [Demo integration report](DEMO_IMPLEMENTATION_REPORT.md)
- [Trí Anh progress report](TriAnh_Progress.md)
