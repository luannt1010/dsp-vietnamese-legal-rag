# Metadata Filtering

`src/preprocessing/metadata_filter.py` triển khai `BaseMetadataFilter` theo
mục 4.2 của [đặc tả](vietnamese_law_rag_technical_spec.md) và quy ước lọc trong
[INTERFACES.md](INTERFACES.md). Module kiểm tra metadata đã được Query Analyzer
trích xuất và tạo điều kiện độc lập để truyền vào router/retriever.

## Tích hợp

Trong runtime thật, Query Analyzer lấy số hiệu từ **câu hỏi gốc** bằng
`document_references.py`, rồi đối chiếu vocabulary số hiệu của corpus. Các cách
viết khác hoa/thường hoặc `ND`/`NĐ` được ánh xạ về giá trị lưu trong index.
Nhiều số hiệu dùng list OR trong field `document_number`. Khi có số hiệu rõ ràng,
không thêm điều kiện AND về loại/lĩnh vực có thể loại nhầm một phía của so sánh.
Số hiệu chưa có trong corpus vẫn được giữ; không âm thầm đổi sang văn bản khác.
Evaluator chặn generation nếu context thiếu bất kỳ văn bản được nêu rõ nào.
Có đúng văn bản chưa chứng minh đủ căn cứ: nội dung vẫn được evaluator kiểm tra.

Runtime cũng inject vocabulary điều theo từng số hiệu. Nếu tên điều được nêu
trong câu hỏi khớp tiêu đề đã index cho **mọi văn bản được hỏi**, Query Analyzer
thêm list `article` chứa các định danh đầy đủ trong corpus. Nếu chỉ một phía
khớp, giữ lọc số hiệu và không thêm lọc điều để tránh loại mất phía còn lại.
Không suy đoán mã Pháp điển từ số điều luật gốc. Một điều được gọi tên trong
dấu ngoặc kép nhưng không có trong context sẽ bị evaluator từ chối bằng guard
deterministic; các điều cùng chủ đề không được dùng thay thế.

```python
from core.schemas import MetadataFilterRequest, RetrievalRouteRequest
from src.preprocessing import MetadataFilter

# Khởi tạo một lần tại composition root; không cần config/model/database.
metadata_filter = MetadataFilter()

# analysis là QueryAnalysisResult từ QueryAnalyzer.
filter_result = metadata_filter.build_filters(MetadataFilterRequest(
    metadata=analysis.metadata,
))
strategy = router.route(RetrievalRouteRequest(
    query=analysis.rewritten_query,
    intent=analysis.intent,
    filters=filter_result.filters,
    entities=analysis.entities,
))
result = retrieval_service.retrieve(
    query=analysis.rewritten_query,
    filters=filter_result.filters,
    strategy=strategy,
    entities=analysis.entities,
)
```

Không truyền `analysis.metadata` thẳng vào retrieval. Lỗi filter phải được
truyền lên tầng điều phối để xử lý; không bắt lỗi rồi truy xuất lại bằng `{}`
vì sẽ mở rộng phạm vi tìm kiếm ngoài yêu cầu ban đầu.

## Điều kiện được hỗ trợ

Danh sách field và validation dùng chung nằm ở `core/filtering.py`;
`src/retrieval/common.py` tiếp tục export các tên cũ để giữ tương thích.
Preprocessing không import hoặc gọi implementation retrieval.

- Các field của `LegalMetadata`: định danh, số hiệu, tên, loại, cơ quan ban
  hành, ngày, status, lĩnh vực và các danh sách quan hệ văn bản.
- Các field vị trí: `chapter`, `article`, `clause`, `point`, `parent_id`.
- `source_url` nếu nguồn đã cung cấp URL.

Điều kiện là mapping phẳng, AND giữa các key; giá trị scalar so sánh bằng,
list khớp ít nhất một giá trị. Metadata nguồn có list thì khớp bằng giao
khác rỗng. Các giá trị JSON scalar giữ nguyên kiểu, không tự chuyển thành
chuỗi hoặc áp đặt enum trước khi nhóm thống nhất taxonomy.

```json
{
  "filters": {
    "legal_domain": ["labor"],
    "document_type": ["law", "decree"]
  },
  "applied_filters": ["legal_domain", "document_type"]
}
```

`applied_filters` chứa **tên field** đã đưa vào `filters`, theo thứ tự metadata
đầu vào, gồm cả điều kiện `None` hoặc list rỗng. Đây là thông tin về điều kiện
được tạo, không phải xác nhận database đã thực thi hoặc có hit thỏa mãn.

- `{}` nghĩa là không lọc.
- `[]` nghĩa là không giá trị nào được chấp nhận, không được bỏ điều kiện.
- `None` là equality với null; field vắng mặt không khớp.
- Chuỗi rỗng vẫn là equality với chuỗi rỗng, không chuyển thành `{}`/`None`.
- List giữ nguyên thứ tự và phần tử trùng; không làm thay đổi biểu diễn đầu vào.
- Không trim/casefold tên field, số hiệu, ID hoặc giá trị. Chuẩn hóa vocabulary
  cần được thống nhất giữa ingestion và Query Analyzer trước khi lọc.

## Lỗi và giới hạn trách nhiệm

Field không hỗ trợ, operator như `$or`, `gte`, `eq`, dict lồng nhau, list lồng
nhau và số không hữu hạn (`NaN`, `Infinity`) báo `ValueError`. Không âm thầm
bỏ qua phần không hiểu, kể cả giá trị của field không hỗ trợ là null/list rỗng.
Dữ liệu sai schema báo `pydantic.ValidationError`.

Ngày hiện chỉ là equality với chuỗi đầu vào; không tự tạo điều kiện khoảng
ngày hoặc suy ra hiệu lực tại một thời điểm. Không chuyển `status` thành kết
luận pháp lý. Alias như `year`, `as_of_date`, `document_numbers` chưa thuộc
contract nên bị từ chối; cần bổ sung contract và adapter trước khi hỗ trợ.
Module không xác minh metadata có đúng với ý định người dùng hay không.

Ở runtime demo, Query Analyzer chỉ tạo hard filter khi câu hỏi gốc nêu rõ
nhãn trong vocabulary corpus, không lấy hard filter do LLM suy đoán. Ví dụ
“pháp luật” không giới hạn document type về Luật. Đây là bước chọn scope trước
module này; không thay đổi semantics strict của filter, kể cả `[]` khớp rỗng.

Retriever thực thi điều kiện **trước top_k**. Với graph, `RetrievalService`
lọc graph hits/relations trước fusion vì `GraphRetrievalRequest` chưa chứa
filter. Adapter database phải dùng query parameters, không nối trực tiếp
giá trị filter thành SQL/Cypher.

## Mở rộng và kiểm thử

Builder không giữ state từng request, có thể dùng chung giữa các request đồng
thời. Input được validate lại và output không chia sẻ list/dict có thể sửa
với input hoặc kết quả request khác. Chi phí tuyến tính theo số field và giá
trị; không truy cập model/database hoặc tải cấu hình mỗi lần gọi.

Khi bổ sung field/operator, cập nhật contract dùng chung, matcher và mọi adapter
liên quan cùng test tích hợp; không chỉ thêm alias tại preprocessing. Query
Analyzer hiện chủ yếu phát sinh `legal_domain` và `document_type`, cả hai đều
được hỗ trợ sẵn.

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_metadata_filter.py tests/test_retrieval.py -q
```

Tests gồm các điều kiện rỗng/null, field/operator sai, dữ liệu bị sửa sau
validation, số không hữu hạn, isolation giữa request và tích hợp Query Analyzer,
BM25, vector, graph, router, context builder. Embedding/LLM/graph trong test dùng
fixture; thuật toán BM25/vector/filter/aggregation/context chạy implementation thật.
