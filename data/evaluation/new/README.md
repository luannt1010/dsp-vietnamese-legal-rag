# Bộ benchmark ba chủ đề đã chuẩn hóa

Dùng `three_topics_pilot.development.v1.jsonl` cho các lượt benchmark tiếp theo.
Bản gốc `three_topics_pilot.draft.jsonl` và manifest gốc được giữ nguyên.

## Phạm vi và kết quả kiểm tra

| Nội dung | Bản chuẩn hóa |
| --- | --- |
| Số câu | 45, giữ nguyên toàn bộ ID và thứ tự |
| Chủ đề | Giao thông, vận tải; Khoa học, công nghệ; Giáo dục, đào tạo — mỗi chủ đề 15 câu |
| Loại câu | 12 lookup, 27 multi_clause, 3 comparison, 3 multi_document |
| Split | Toàn bộ là `development` |
| Câu có căn cứ / không đủ căn cứ | 45 / 0 |
| Câu chỉnh cách hỏi | 12; 33 câu giữ nguyên |
| Ý chuẩn trong `reference_claims` | 233 |
| Đoạn evidence | 115; tất cả ánh xạ được vào leaf chunk bằng resolver hiện có |
| Corpus | `4d70694000eb63e3` |
| Revision nguồn | `a1b6860c821b7142ffe2385178af4e4bb6f86aff` |

Đây là đánh giá nội dung trong **snapshot corpus cố định**, không phải bộ đáp án
đã xác nhận hiệu lực pháp luật tại thời điểm hiện tại. Việc rà soát pháp lý độc lập
và kiểm tra đầy đủ các nguồn đúng thay thế vẫn chưa hoàn tất. Bộ này đã được dùng
để phân tích kết quả nên được chuyển sang development; cần bộ test mới chưa dùng
để tinh chỉnh cho kết luận cuối cùng.

## Các quy tắc chuẩn hóa

- Giữ các câu chỉ ghi số hiệu. Không chèn hàng loạt tên văn bản, lĩnh vực hoặc
  số điều để kích hoạt bộ lọc của pipeline.
- Mỗi claim là một mệnh đề có thể đánh giá riêng. Định nghĩa hoặc danh sách có
  cùng một quan hệ pháp lý có thể giữ trong một claim; điều kiện và ngoại lệ đi
  cùng nội dung mà chúng giới hạn. Phần giao nhau giữa các câu tái sử dụng cùng
  cách phân tách claim, như các hình thức chuyển giao công nghệ.
- `reference_answer` được ghép từ chính các claims để hai nhãn không mâu thuẫn.
  Không yêu cầu câu trả lời của hệ thống phải giống từng chữ hoặc cùng định dạng.
- Evidence là các đoạn liên tục, nguyên văn từ evidence gốc. Chia theo khoản khi
  phù hợp; chỉ bỏ phần ngoài phạm vi hỏi hoặc tên file đính kèm. Không diễn giải
  lại nội dung trong trường `quote`.
- Giữ định danh điều của Pháp điển. Không tự suy đoán số điều của luật gốc hoặc
  phiên bản hiệu lực. Trường `clause`/`point` giữ đúng vị trí đã được đánh chỉ mục,
  không gán số khoản trong nội dung vào metadata của chunk cấp điều.
- Giữ nguyên 45 câu có căn cứ; chưa bổ sung câu unanswerable. Không coi retrieval
  tìm không ra là căn cứ để đổi `answerable` thành false.

## Những câu cần chỉnh phạm vi hoặc bổ sung đáp án

| ID | Điều chỉnh |
| --- | --- |
| GT010 | Hỏi rõ hình thức tổ chức của đơn vị kinh doanh mà đoạn nguồn nêu; không khẳng định đoạn nguồn là toàn bộ điều kiện kinh doanh. |
| GT011 | Hỏi rõ cả phạm vi và hoạt động không thuộc phạm vi áp dụng. |
| GT012 | Thay câu hỏi về ngoại lệ bằng nghĩa vụ tuân thủ bổ sung đối với phương tiện thủy nội địa/tàu biển. |
| GT015 | Giữ câu hỏi; bổ sung các nguyên tắc về trách nhiệm, quy hoạch, kết nối vận tải, quản lý và nghĩa vụ chủ đầu tư bị thiếu trong đáp án cũ. |
| KHCN003 | Hỏi rõ cả hình thức chuyển giao và yêu cầu hợp đồng/hồ sơ mà nhãn cũ đã bao gồm. |
| KHCN007 | Bỏ yêu cầu tìm ngoại lệ không được đoạn nguồn hỗ trợ; làm rõ điều kiện hoạt động tại Việt Nam. |
| KHCN012 | Chỉ hỏi đối tượng áp dụng; không suy diễn toàn văn không có ngoại lệ từ một đoạn không nêu ngoại lệ. |
| KHCN013 | Hỏi rõ danh mục, phụ lục và quy trình cập nhật; bỏ tên file đính kèm khỏi đáp án và quote. |
| KHCN014 | Giữ câu hỏi; tách đủ các nội dung phạm vi và quy định riêng về chuyển giao trong nông nghiệp. |
| KHCN015 | Hỏi rõ điều kiện góp vốn bằng công nghệ có vốn nhà nước; bổ sung thanh toán theo lợi nhuận sau thuế. Evidence thanh toán lấy khoản 1 thay vì cả điều vượt qua ranh giới leaf. |
| GD006 | Hỏi rõ cả phạm vi và đối tượng áp dụng để khớp nhãn. |
| GD011 | Hỏi rõ chính sách, đối tượng áp dụng và trường hợp loại trừ để khớp nhãn. |
| GD012 | Gọi rõ quy tắc tính tháng, công việc trong ngành giáo dục và thẩm quyền xác nhận. |
| GD014 | Giữ câu hỏi; evidence của Nghị định chỉ lấy khoản 1 về chính sách được hỏi. |
| GD015 | Hỏi đủ hoạt động bảo đảm môi trường an toàn, lành mạnh, thân thiện; bổ sung mục tiêu giáo dục bị thiếu. Không đưa yêu cầu riêng cho lớp độc lập vào câu chỉ hỏi cơ sở giáo dục. |

Các câu còn lại được tách claims, chỉnh đáp án tương ứng và chia evidence khi
cần; xem chi tiết từng ID trong `three_topics_pilot.development.v1.review.json`.
File review ghi câu hỏi trước/sau, trường thay đổi, nguồn của từng evidence,
evidence hỗ trợ từng claim và các chunk mà resolver tìm được. Manifest ghi SHA-256
của bản gốc và bản chuẩn hóa để phát hiện dữ liệu thay đổi.

Ba câu `multi_document` yêu cầu tổng hợp từ hai văn bản nhưng chưa đủ để khẳng
định đo được khả năng duyệt graph hoặc suy luận nhiều bước. Qrels hiện tại vẫn
là nhãn chunk dựa trên quote: chưa phải tập mọi chunk đúng thay thế trong corpus.

## Lệnh Windows CMD

Chạy từ thư mục project. Các lệnh dưới dùng Python trong `.venv`; nếu đang dùng
môi trường khác đã cài project, thay `.venv\Scripts\python.exe` bằng Python đó.

Kiểm tra schema, ID/câu hỏi trùng và toàn bộ evidence với corpus đã chuẩn bị:

```bat
cd /d D:\dsp-vietnamese-legal-rag
.venv\Scripts\python.exe -m scripts.benchmark validate --dataset data\evaluation\new\three_topics_pilot.development.v1.jsonl --corpus data\runtime\4d70694000eb63e3\corpus.json
```

Chạy thử một lần cho mỗi cấu hình B0–B4: 45 × 5 = 225 mẫu. Dù tên config là
`smoke.yml`, số câu được quyết định bởi file dataset truyền vào.

```bat
.venv\Scripts\python.exe -m scripts.benchmark run --dataset data\evaluation\new\three_topics_pilot.development.v1.jsonl --split development --config configs\benchmark\smoke.yml --output .runtime\benchmarks\three-topics-dev-v1-fixed-01
```

Chấm retrieval, sau đó chấm thêm context/answer và xuất report:

```bat
.venv\Scripts\python.exe -m scripts.benchmark score --output .runtime\benchmarks\three-topics-dev-v1-fixed-01 --retrieval-only
.venv\Scripts\python.exe -m scripts.benchmark score --output .runtime\benchmarks\three-topics-dev-v1-fixed-01
.venv\Scripts\python.exe -m scripts.benchmark report --output .runtime\benchmarks\three-topics-dev-v1-fixed-01
```

Lệnh score không có `--retrieval-only` gọi judge; các điểm này vẫn phụ thuộc chất
lượng và giới hạn đầu ra của judge. Bản chuẩn hóa không thay đổi pipeline hoặc
cấu hình judge. Nếu chỉ cần retrieval, bỏ lệnh score thứ hai.

Muốn lặp ba lần mỗi cấu hình, dùng `configs\benchmark\hybrid.yml` và thư mục
output mới. Luôn truyền `--split development`, vì mặc định CLI chọn `test`.
Không dùng lại thư mục run cũ: câu hỏi/nhãn mới có fingerprint khác. Không quy
chênh lệch điểm với bộ draft cũ thành cải thiện pipeline vì nhãn và 12 câu đã đổi.

Không có inference, judge hoặc tái tạo index nào được chạy khi chuẩn hóa dữ liệu.
