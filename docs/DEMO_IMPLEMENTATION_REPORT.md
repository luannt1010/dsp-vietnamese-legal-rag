# Báo cáo tích hợp pipeline demo

> Rà soát mới nhất: [PIPELINE_AUDIT_REPORT.md](PIPELINE_AUDIT_REPORT.md).
> Cập nhật corpus theo topic: xem [TOPIC_CORPUS.md](TOPIC_CORPUS.md). Mốc trước
> đã chạy toàn bộ chủ đề An ninh quốc gia với 1.896 điều/116 văn bản,
> 3.490 leaves và 144 quan hệ Neo4j. Ask/chat tự chuẩn bị index theo YAML,
> có cache embedding dùng chung giữa các lựa chọn. Hồi quy sau sửa generation:
> 292 tests, 246 subtests pass, gồm DB thật. Các bảng corpus 100 điều
> bên dưới ghi nhận mốc tích hợp ban đầu.

## Mục tiêu và kết quả

Hoàn thiện đường chạy CLI theo technical spec và sơ đồ pipeline: analysis →
filter → router → hybrid/graph retrieval → evaluation/feedback → context →
generation → citation verification. Demo mặc định dùng Ollama, pgvector và
Neo4j thật, không thay bằng mock khi dịch vụ lỗi.

Đã chạy câu hỏi “Theo nguồn đã cung cấp, phạm vi điều chỉnh của Luật An ninh
quốc gia là gì?” đến status `completed` trong một vòng. Câu trả lời trích nguyên
văn nguồn 32/2004/QH11 và qua cả kiểm tra citation lẫn LLM kiểm tra nhận định.
Đây là smoke test tích hợp, chưa phải kết quả benchmark chất lượng pháp luật.

Câu hỏi ngoài corpus về quy trình cấp phép khai thác khoáng sản năm 2026 trả
`insufficient_evidence` trong một vòng, không đi tiếp sang generation.

## Phần triển khai

| Thành phần | Vị trí | Hành vi |
| --- | --- | --- |
| Chuẩn bị corpus | `src/data_pipeline/preparation.py` | Artifact/manifest có fingerprint, tái sử dụng embedding |
| Chunking | `src/data_pipeline/chunking` | Fixed token, legal article, hierarchical điều/khoản/điểm |
| Embedding | `src/infrastructure/embedding` | Ollama BGE-M3, batch, kiểm tra dimension/finite/normalization |
| Vector storage | `src/infrastructure/vector_store` | pgvector exact/HNSW/IVFFlat; cosine/IP/L2; filter trong SQL |
| Graph | `src/knowledge_graph`, `src/infrastructure/graph_store` | Builder, Neo4j, hierarchy, evidence, BFS có giới hạn |
| Tokenizer/reranker | `src/infrastructure/tokenization.py`, `src/retrieval/reranking/onnx_model.py` | Token thật, offsets; multilingual ONNX CPU |
| Composition root | `src/runtime.py` | Tận dụng factory, retriever, RRF, filter, context và verifier có sẵn |
| CLI | `scripts/demo.py` | doctor, prepare, ask, chat; trace và debug theo request |

Ollama dùng chung HTTP client cho deadline/retry, chat API cho bốn LLM role,
structured output và kiểm tra đầy đủ response. Không dùng raw generation cho
model chat. Tắt novelty/repetition penalty để hỗ trợ trích nguyên văn.
Generation chọn số nguồn trong AnswerDraft; code dựng citation nguyên văn
từ nguồn được chọn. Confidence chưa hiệu chuẩn được giữ 0.
Evaluator không nhận raw retrieval/reranker score để suy diễn độ đủ căn cứ.

Quan hệ graph chỉ resolve khi endpoint và evidence có trong corpus. ID sai,
dẫn chiếu ngoài nguồn hoặc parent khác văn bản bị từ chối/đánh dấu unresolved;
không lấy chunk đầu văn bản khác làm chứng cứ thay thế. Trích dẫn không khớp
hoặc nhận định không được nguồn hỗ trợ vẫn bị verifier chặn.

## Kiểm chứng

Toàn bộ suite gồm DB integration: **254 tests, 245 subtests pass**. Có kiểm
tra 9 tổ hợp metric/index pgvector, ép ANN plan trong fixture nhỏ, đối chiếu
điểm với exact reference và kiểm tra filter. ANN không bị giả định luôn có
cùng top-k với exact. Neo4j được kiểm tra MERGE, PART_OF và traversal thật.
Compile và `git diff --check` không báo lỗi.

Chuẩn bị thực tế trên 100 đơn vị nguồn, 12 văn bản:

| Chunking | Leaves có embedding | Parents | Quan hệ document đã resolve |
| --- | ---: | ---: | ---: |
| Fixed | 72 | 112 | 0 |
| Legal | 126 | 100 | 3 |
| Hierarchical (default) | 168 | 162 | 3 |

Cả ba strategy ghi được vào pgvector/Neo4j; exact/HNSW/IVFFlat cũng tạo được
trên corpus thật. Hierarchical giữ 23 dẫn chiếu unresolved; fixed giữ 45 do
không có neo điều đáng tin cậy vào leaf. Các lần chạy này kiểm tra khả năng
hoạt động của phương pháp, không đo recall, latency hay so sánh chất lượng.

## Lựa chọn mặc định và giới hạn

Hierarchical 512/64, BGE-M3, BM25 word + RRF, HNSW cosine, Neo4j depth 2 và
reranker multilingual ONNX là baseline theo cấu trúc pháp luật, có thể đổi
bằng config/CLI. Generation hiện dùng Qwen3.5:4b, ba role còn lại Qwen3.5:2b;
reranker chạy CPU để phù hợp tài nguyên máy demo
16 GB RAM/GPU 6 GB; chưa kết luận đây là cấu hình tốt nhất về chất lượng.

Corpus còn nhỏ, metadata/hiệu lực/URL chưa đầy đủ; không suy diễn tình trạng
pháp lý hiện hành. Artifact JSON và BM25 hiện nạp corpus vào RAM; cần cơ chế
ingestion/sparse index theo lô khác nếu mở rộng đến corpus rất lớn. Không
triển khai API, dataset đánh giá, benchmark hay đóng gói/triển khai trong đợt này.

Lệnh chạy và cấu hình thay thế: [DEMO.md](DEMO.md).
