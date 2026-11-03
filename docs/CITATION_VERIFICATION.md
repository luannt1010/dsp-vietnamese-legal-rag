# Citation Verification

`src/generation/citation_verifier.py` triển khai
`BaseCitationVerifier.verify(answer, context) -> LegalAnswer` theo mục 4.9 và
12.6 của [đặc tả](vietnamese_law_rag_technical_spec.md), cùng yêu cầu kiểm tra
nguồn hỗ trợ nhận định trong [INTERFACES.md](INTERFACES.md).

## Tích hợp

```python
from src.generation import CitationVerifier

# llm là adapter BaseLLM được khởi tạo tại composition root.
verifier = CitationVerifier(llm=llm)
verified_answer = verifier.verify(answer, context)
```

`context` đến từ `LegalContextBuilder`; `answer` là output của answer generator.
LLM adapter được inject để đánh giá nhận định, dùng timeout/model/provider đã
cấu hình ở ngoài module. Prompt riêng nằm tại `prompts/citation_verifier/v1.txt`.
Không có chế độ bỏ qua đánh giá nhận định hoặc tự chấp nhận khi model lỗi.

## Luồng kiểm tra

1. Validate lại input và tạo snapshot độc lập để không sửa answer/context gốc.
2. Kiểm tra context có nguồn, không trùng chunk ID, document ID nhất quán;
   nội dung các chunk phải có trong `context_text`, `cited_document_ids` phải
   đúng danh sách văn bản duy nhất theo thứ tự nguồn.
3. Với từng citation, tìm chunk cùng `document_id`, khớp `document_number`,
   các field vị trí/URL được cung cấp và nguyên văn `quoted_text`.
4. Khi tất cả citation đều khớp, gọi LLM **một lần** để đánh giá mọi nhận định
   trong answer và disclaimer dựa trên các nguồn được trích dẫn.
5. Chỉ trả snapshot answer khi verdict hợp lệ và `is_supported=True`.

Các field của cùng citation phải khớp **cùng một chunk**; không ghép số hiệu
từ chunk này với trích dẫn từ chunk khác. `article`, `clause`, `point` và
`source_url` có thể là `None`; nếu cung cấp thì phải khác rỗng và khớp chính
xác metadata. Thiếu số hiệu ở nguồn thì không được tự điền số hiệu từ LLM.

Quotation được so sánh substring nguyên văn; không fuzzy match, bỏ dấu, sửa
khoảng trắng hoặc ghép các đoạn không liên tục. Generator cần giữ nguyên câu
trích dẫn từ chunk. Verifier không sửa citation, loại citation sai khỏi answer
hoặc thay đổi confidence.

## Kiểm tra nhận định

LLM chỉ nhận câu hỏi, answer/disclaimer, citations và các chunk đã khớp citation.
Không đưa chunk không được trích dẫn vào để bù căn cứ thiếu. Giữ đầy đủ nội dung
chunk để model xét ngữ cảnh, phủ định, điều kiện và ngoại lệ quanh quotation;
không gửi retrieval score hoặc answer confidence để làm căn cứ phán đoán.

Prompt yêu cầu kiểm tra toàn bộ nhận định thực chất, không suy ra hiệu lực từ
status/ngày đơn lẻ, không dùng kiến thức ngoài nguồn và từ chối khi chưa xác
định được căn cứ. Các giá trị đầu vào được truyền dưới dạng JSON và được coi
là dữ liệu, không phải chỉ dẫn. Verdict phải có đúng hai field:

```json
{"is_supported": true, "reason": "Lý do ngắn gọn"}
```

`is_supported` phải là boolean thật; chuỗi `"true"` hoặc số `1` bị từ chối.
Đây là đánh giá bằng model, không phải chứng minh tính đúng pháp lý; cần kiểm
tra chất lượng với model/provider và bộ câu hỏi thật khi tích hợp. Unit test
hiện dùng verdict giả lập để kiểm tra luồng và cách xử lý lỗi.

## Lỗi và trách nhiệm tầng điều phối

Không có citations, nguồn/quotation không khớp, context không nhất quán,
verdict phủ định/không hợp lệ hoặc provider lỗi đều báo
`CitationVerificationError`. Lỗi phụ thuộc được giữ qua `raise ... from exc`.
Input sai schema báo `pydantic.ValidationError`.

Orchestrator sở hữu retry/deadline, sửa câu trả lời bằng generation lại hoặc
trả thông báo thiếu căn cứ. Câu trả lời fallback không có citations cần đi
theo nhánh fallback riêng; không đưa qua verifier như một answer đã có căn cứ.
LLM adapter phải kiểm tra giới hạn token của prompt verification thực tế và
dùng ngân sách thời gian còn lại; verifier không tự tải model hay retry.

Module không lưu state của request. Có thể dùng chung instance khi LLM adapter
được inject cũng hỗ trợ cách sử dụng đồng thời đó.

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_citation_verifier.py -q
```

Tests gồm nguồn/số hiệu/vị trí/URL sai, quotation sửa hoặc ghép, một citation
sai giữa nhiều citation đúng, nguồn đã bị context budget loại bỏ, verdict sai
kiểu/phủ định, lỗi provider và tích hợp BM25 → context builder → verifier.
