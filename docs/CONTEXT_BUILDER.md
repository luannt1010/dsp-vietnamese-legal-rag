# Legal Context Builder

`src/generation/context_builder.py` triển khai `BaseLegalContextBuilder` theo
mục 4.8 và 12.6 của [đặc tả](vietnamese_law_rag_technical_spec.md),
[contract](INTERFACES.md), [ngân sách token](CONFIGURATION.md) và
[quy tắc graph sau retrieval](RETRIEVAL.md).

## Tích hợp

Khởi tạo ở composition root, sau khi chọn answer model. Inject callable
`token_counter(text: str) -> int` dùng **đúng tokenizer của answer model**,
không thêm special token cho mỗi lần đếm. Builder không tải model, gọi LLM,
kết nối database hay đọc cấu hình từ đĩa.

```python
from collections.abc import Callable

from core.config import Settings
from core.schemas import ContextBuilderRequest, LegalContext, RetrievalResult
from src.generation import LegalContextBuilder


def build_context(
    settings: Settings,
    count_answer_tokens: Callable[[str], int],
    result: RetrievalResult,
    original_query: str,
) -> LegalContext:
    builder = LegalContextBuilder(
        settings=settings.context,
        token_counter=count_answer_tokens,
    )
    return builder.build(ContextBuilderRequest(
        retrieval_result=result,
        original_query=original_query,
    ))
```

Ứng dụng có thể khởi tạo builder một lần rồi dùng chung cho các request.
Builder không lưu trạng thái từng request; tokenizer được inject cũng cần
an toàn khi gọi đồng thời nếu dùng theo cách này.

## Ngân sách và lựa chọn nguồn

- `max_context_tokens` giới hạn **toàn bộ `context_text`**: nhãn nguồn,
  metadata, nội dung, dấu phân cách và quan hệ graph.
- `prompt_reserve_tokens` là ngân sách riêng cho câu hỏi/chỉ dẫn/overhead;
  không trừ lần nữa khỏi `max_context_tokens`. Theo `Settings.check_budgets`,
  tổng context + prompt reserve + output phải nằm trong cửa sổ answer model.
  Answer generator vẫn phải kiểm tra token của prompt thực tế, kể cả chat
  template và câu hỏi dài vượt mức dự phòng, trước khi gọi model.
- Giữ thứ tự `RetrievalResult.results`; nếu câu hỏi chỉ rõ nhiều số hiệu,
  ưu tiên tiêu đề điều được nêu rõ trong câu hỏi, rồi chia lượt giữa các văn bản.
  Các hit còn lại giữ thứ hạng trong từng văn bản. Cùng policy được áp dụng trước giới hạn số nguồn cho
  context, nên một văn bản không chiếm hết top-k context. Ranking retrieval
  được lưu/chấm giữ nguyên. Không sắp xếp bằng score khác thang đo. Giữ trọn chunk,
  không sửa hoặc cắt nội dung quy định pháp luật.

Tên điều chỉ là tín hiệu chọn context, không phải bằng chứng rằng nội dung đã đủ.
Evaluator vẫn kiểm tra toàn bộ yêu cầu trên context thực tế. Policy dùng câu hỏi
và metadata nguồn, không đọc reference answer, claims hoặc qrels của benchmark.
Ở bước ưu tiên context, tên điều có thể khớp sau khi bỏ từ đệm câu hỏi như
"gì", "nào", "những", "để". Cách khớp này chỉ sắp ưu tiên nguồn, không làm
rộng điều kiện lọc cứng `article` của Query Analyzer.
- Bỏ qua chunk không vừa và tiếp tục thử chunk nhỏ hơn phía sau. Không có
  chunk nào vừa thì báo `InsufficientEvidenceError`.
- Đếm chuỗi context hoàn chỉnh mỗi lần thử thêm block. Không cộng số token
  từng block vì tokenization ở ranh giới có thể làm tổng khác đi.
- `len` trong unit test chỉ là bộ đếm giả lập xác định, không dùng để đo
  token model trong production. Counter phải trả số nguyên dương cho chuỗi
  khác rỗng; giá trị sai báo `ValueError`, lỗi tokenizer được truyền nguyên.

Việc bớt chunk theo ngân sách có thể làm mất căn cứ cần thiết cho một phần
câu hỏi. Builder không thay evaluator hoặc chứng minh tính đầy đủ pháp lý;
orchestrator gọi evaluator trên chính các nguồn còn lại sau khi đóng gói,
trước khi cho phép generation.

Khi có `parent_lookup`, builder giữ các leaf vừa ngân sách trước, sau đó mới
thử nâng lên khoản/điều cùng văn bản bằng phần ngân sách còn lại. Một lần mở rộng
chỉ được nhận nếu không làm mất nguồn khác đã giữ. Các hit có chung ancestor
có thể gộp thành một nguồn nguyên vẹn. Điều quá lớn thì giữ khoản/leaf; không
cắt nội dung. Hierarchy có vòng lặp báo lỗi; parent thiếu hoặc khác văn bản
không được dùng để mở rộng. Telemetry `context_selection` ghi ID đầu vào và
ID/số hiệu nguồn được giữ để đối chiếu với retrieval ranking.

## Truy nguyên và quan hệ graph

Mỗi nguồn có nhãn `[Nguồn N]`, metadata JSON và nội dung nguyên văn. Header
luôn có `document_id`, `chunk_id`; đưa thêm số hiệu, tên văn bản, vị trí,
URL và dữ liệu hiệu lực khi đầu vào cung cấp. Không tự sinh số hiệu, URL
hoặc suy ra hiệu lực từ `status`. JSON escape xuống dòng trong metadata.
Metadata mở rộng vẫn được giữ nguyên trong `chunks` dù không hiện trong header.

`LegalContext.query` giữ câu hỏi gốc. `chunks` chỉ chứa nguồn thực sự có trong
`context_text`; `cited_document_ids` là ID văn bản duy nhất theo thứ tự xuất
hiện. Output được tách khỏi list/dict đầu vào, không chia sẻ metadata có thể sửa.

Chunk trùng ID và cùng document/content/metadata chỉ xuất hiện một lần;
score hoặc retrieval method khác nhau không làm đổi nguồn đầu tiên. Trùng
ID nhưng khác nguồn/metadata hoặc `metadata.document_id` mâu thuẫn với
`chunk.document_id` báo `ValueError`, không âm thầm chọn nguồn.

Quan hệ graph có ưu tiên sau toàn bộ chunk. Chỉ đưa bốn field baseline
`source_document_id`, `target_document_id`, `relation_type`,
`evidence_chunk_ids` vào context khi:

- Hai văn bản đều còn trong các chunk đã giữ.
- Có loại quan hệ khác rỗng và ít nhất một evidence chunk ID.
- **Toàn bộ** evidence chunk còn trong context; không bỏ bớt evidence để
  làm quan hệ có vẻ hợp lệ.
- Block quan hệ còn vừa ngân sách.

Quan hệ sai cấu trúc, không đủ evidence hoặc không vừa bị bỏ qua; quan hệ
trùng baseline được loại trùng. Quan hệ được thể hiện như dữ liệu nguồn,
không phải kết luận về hiệu lực. Citation verifier tiếp tục đối chiếu với
`LegalContext.chunks`; contract `LegalContext` không thêm field mới.

## Chi phí và kiểm thử

Lập map loại trùng và set tra nguồn theo số chunk/quan hệ đầu vào, không
gọi retriever hoặc LLM lại. Mỗi lần đóng gói chỉ tokenize context đang giữ
cộng block đang xét; context đang giữ bị giới hạn bởi ngân sách. Không cache
nội dung/token toàn cục hoặc chia sẻ state giữa các request. Chi phí tokenizer
phụ thuộc kích thước nguồn đầu vào và ngân sách context; chunk rất lớn vẫn
cần được tokenizer xử lý để xác định có vừa hay không.

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_context_builder.py -q
```

Tests bao gồm boundary token và dấu phân cách, chunk quá dài, quotation nguyên
văn, source identity, dữ liệu bị sửa sau validation, quan hệ bị loại bởi ngân
sách, request đồng thời và tích hợp BM25 với mock corpus/config thật của repo.
