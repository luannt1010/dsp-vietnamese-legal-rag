# Dữ liệu đánh giá pilot

| File | Trạng thái |
|---|---|
| `data.json` | 31 câu gốc do nhóm chuẩn bị, nội dung JSONL, chưa kiểm duyệt hoàn chỉnh |
| `smoke.jsonl` | 3 câu dẫn xuất để kiểm tra pipeline B0–B4, không phải gold benchmark đã hiệu chuẩn |

Các câu smoke: ANQG001 (lookup), ANQG022 (lookup định nghĩa), ANQG031
(multi_document). Lấy từ `data.json`; chỉ đổi `ANQG022.evidence[0].quote` thành
đoạn định nghĩa ở khoản 1 để nằm đầy đủ trong leaf. Không đổi đáp án/claims.
Các trường tùy chọn được serialize theo schema, mặc định split=test.

Nguồn: `tmquan/phapdien-moj-gov-vn`, config documents, split train,
snapshot `a1b6860c821b7142ffe2385178af4e4bb6f86aff`, topic An ninh quốc gia.
Đã đối chiếu 32/32 quotes trong file gốc với snapshot nguồn. Với chunking
hierarchical 512 token/overlap 64, 30/31 câu gốc resolve được; smoke đã rút gọn
quote còn lại và đã chạy thành công. Các số này chỉ mô tả kiểm tra kỹ thuật,
không xác nhận độ đầy đủ hoặc hiệu lực hiện tại của nguồn pháp luật.

Cần rà lại trước khi dùng file 31 câu để kết luận chất lượng:

- ANQG009: question hỏi loại cơ quan/tổ chức; reference/claims chưa liệt kê
  đầy đủ các nhóm mà evidence nêu.
- ANQG010: reference_claims có ngoại lệ điều ước quốc tế nhưng reference_answer
  chưa có ý tương ứng.
- ANQG022: quote toàn bộ điều dài 522 token, vượt ranh giới leaf; dùng quote
  nguyên tử tương ứng với định nghĩa được hỏi như bản smoke.
- ANQG030: cần phân biệt chỉ đạo/điều hành trực tiếp của người đứng đầu với
  hướng dẫn/kiểm tra nghiệp vụ của Công an theo chính evidence đã cung cấp.

File gốc có 31 câu answerable=true, gồm 16 lookup, 14 multi_clause và 1
multi_document. Chưa có câu unanswerable; chưa đo được khả năng từ chối đúng.
Pooling thêm các nguồn đúng thay thế và kiểm tra reference claims theo người
chấm là việc còn cần làm. Điểm judge tự động hiện chưa hiệu chuẩn.

Chạy theo [benchmark quickstart](../../docs/BENCHMARK_QUICKSTART.md).
