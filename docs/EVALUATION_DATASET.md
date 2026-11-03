# Evaluation dataset for the Vietnamese legal RAG benchmark

The agreed benchmark design is in [BENCHMARK_PLAN.md](BENCHMARK_PLAN.md). This
document explains the first implemented dataset contract and what still needs
human/legal-data work. A benchmark dataset is a set of **verified questions,
reference claims, and quoted legal evidence**; it is not the corpus chunk file.

## Current status

- The repository has an initial `data/chunks/phapdien_chunks.json` artifact with
  100 chunks from 12 documents, plus a separate pipeline that can prepare
  selected Pháp điển topics. These are corpus/retrieval inputs, not evaluation
  questions or ground truth.
- There is no labeled evaluation dataset yet. Do not invent reference answers,
  evidence quotes, or relevance labels from the chunks automatically.
- The target is a 30–50 question pilot followed by approximately 300 reviewed
  questions. Include lookup, multi-clause, multi-document, comparison, and
  unanswerable cases across the three benchmark topics.

## JSONL record format

Store one UTF-8 JSON object per line. `load_evaluation_dataset()` validates
records, requires unique `question_id`s, and checks answerability/evidence
invariants. For example:

```json
{
  "question_id": "GT001",
  "question": "Câu hỏi tự nhiên bằng tiếng Việt",
  "topic": "Giao thông, vận tải",
  "question_type": "multi_clause",
  "answerable": true,
  "reference_answer": "Đáp án chuẩn có đủ điều kiện và ngoại lệ.",
  "reference_claims": ["Ý chuẩn thứ nhất.", "Ý chuẩn thứ hai."],
  "evidence": [
    {
      "document_number": "01/2025/QH15",
      "document_title": "Tên văn bản pháp luật",
      "article": "Điều 1",
      "clause": "Khoản 2",
      "point": null,
      "quote": "Trích nguyên văn đoạn đủ ngữ cảnh.",
      "source_url": null
    }
  ],
  "split": "test",
  "split_group": "source-family-01"
}
```

Required fields match the agreed plan. `split` (`development` or `test`) and
`split_group` are optional for draft records, but must be supplied together when
assigning splits. Questions in one group cannot be split across development
and test. Assign groups before tuning; group questions with overlapping source
documents or belonging to the same question family together to reduce leakage.
The loader does not assign groups or choose the 20/80 split for you.

For an unanswerable case, use `question_type: "unanswerable"`,
`answerable: false`, an explanatory `reference_answer`, and empty
`reference_claims`/`evidence`. Answerable cases need at least one checkable
reference claim and one evidence quote. Keep conditions, exceptions, negative
language, document number, article/clause/point, and source URL (when verified)
with the evidence.

Load and inspect a dataset from Python:

```python
from src.evaluation import load_evaluation_dataset

questions = load_evaluation_dataset("data/evaluation/pilot.jsonl")
```

## Annotation and versioning workflow

1. Freeze the corpus source revision and prepared corpus identity for the
   benchmark. Record these in the benchmark run manifest alongside chunking,
   embedding identity, and model/prompt digests.
2. Draft questions from the selected corpus, not from memory. Confirm each
   reference answer against the exact document snapshot.
3. Break answer references into atomic `reference_claims`; retain qualifications
   and exceptions in the relevant claim.
4. Quote sufficient source text and retain document number and legal location.
   One question may have multiple evidence passages and multiple correct
   sources.
5. Mark whether the frozen corpus can fully answer the question. Do not include
   an unanswerable question in retrieval-ranking metrics that require a
   non-empty relevant set; report correct refusals separately.
6. Pool outputs from multiple retrieval configurations to identify alternate
   valid evidence, then deduplicate by legal evidence span before finalizing
   labels.
7. Group related/overlapping questions, then split groups into approximately
   20% development and 80% test. Tune only on development.
8. Have a second reviewer spot-check legal evidence and manually review a
   stratified sample, including low-score or judge-disagreement cases.

Question text, reference answers, claims, and legal quotations should be
reviewed by the team; the loader checks shape and consistency, not legal
correctness.

## Metrics already available

- Retriever ranking: Recall@k, Precision@k, Average Precision/MAP,
  Reciprocal Rank/MRR, Hit@k, and binary nDCG@k.
- Context: `context_precision_judgments()` consumes relevance judgments in
  actual context order; `context_recall_claims()` consumes one support judgment
  per reference claim. `context_precision()` / `context_recall()` also provide
  ID-based diagnostics, not the plan's semantic context scores.
- Answer: `faithfulness()` aggregates claim-support judgments;
  `factual_correctness()` aggregates reference-alignment precision/recall/F1;
  `answer_relevancy()` averages cosine similarities from an external
  question-generation/embedding step.

These are aggregation functions. They do not perform claim extraction, semantic
judgment, embeddings, or LLM evaluation. The benchmark plan still requires a
separate, frozen judge/prompt, saved component judgments, and a runner/report
that handles failed, refused, and timed-out cases without silently dropping
them.

## Still not implemented

- The labeled pilot/target dataset and source-review workflow.
- A benchmark runner for B0–B4, run manifests, and per-configuration artifacts.
- A development/test group assignment process and leakage checks for evidence
  overlap beyond the supplied `split_group` labels.
- Persisting exact context and pre-verification answer draft in `PipelineResult`.
- A separate top-20 ranking capture versus top-5 context cutoff, locked B4
  feedback policy, automatic judges, paired bootstrap confidence intervals,
  topic/type reports, and per-stage/model-call latency telemetry.
