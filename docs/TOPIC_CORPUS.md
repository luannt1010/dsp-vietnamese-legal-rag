# Chọn corpus RAG bằng YAML

Chỉnh `source` và `auto_prepare` trong `configs/demo/data_pipeline.yml`; giữ
nguyên chunking và các thiết lập còn lại của file:

```yaml
data_pipeline:
  source:
    type: huggingface
    dataset: tmquan/phapdien-moj-gov-vn
    config: documents
    split: train
    revision: main
    topics:
      - An ninh quốc gia
      - Lao động
    subjects: []
    read_batch_size: 512
  auto_prepare: true
```

Ví dụ trên chọn toàn bộ hai chủ đề. Để chỉ chọn **An ninh quốc gia**, bỏ
`Lao động` khỏi `topics`. Để chọn một đề mục nhỏ hơn, dùng `topics: []` và ví dụ
`subjects: [An ninh quốc gia]`. Chủ đề và đề mục có thể trùng tên nhưng khác
phạm vi: chủ đề An ninh quốc gia có 1.898 bản ghi; đề mục cùng tên có 201.

## Tra danh mục và chạy

```powershell
.\.venv\Scripts\python.exe -m scripts.demo list-topics
.\.venv\Scripts\python.exe -m scripts.demo list-subjects
.\.venv\Scripts\python.exe -m scripts.demo chat
```

Catalog hiển thị ID, tên và số bản ghi nguồn; đề mục có thêm ID chủ đề cha.
Lấy trực tiếp từ cột phân loại của `documents` để bao gồm đủ 43 chủ đề/202
đề mục. Hai lệnh list không cần kết nối Ollama hoặc database.

Selector nhận tên tiếng Việt hoặc ID được liệt kê. Tên được chuẩn hóa Unicode
NFC, hoa/thường và khoảng trắng; không tự bỏ dấu hay fuzzy match. Tên không có
hoặc trùng nhiều mục sẽ báo lỗi và yêu cầu dùng ID. Hai danh sách kết hợp OR:
lấy mọi điều thuộc chủ đề đã chọn **hoặc** đề mục đã chọn, mỗi record một lần.
Nếu cả hai rỗng, list vẫn dùng được nhưng prepare/chat báo lỗi, không nạp toàn
bộ corpus ngầm định.

`auto_prepare: true` cho phép ask/chat chuẩn bị dữ liệu và index còn thiếu ở
lúc khởi động, trước request hỏi đáp. Có log tiến trình từng bước. Những lần
sau dùng lại corpus/index phù hợp. Nếu false, chạy `prepare` trước như cũ:

```powershell
.\.venv\Scripts\python.exe -m scripts.demo prepare
.\.venv\Scripts\python.exe -m scripts.demo chat
```

## Snapshot, cache và cập nhật

Nguồn là [dataset Pháp điển](https://huggingface.co/datasets/tmquan/phapdien-moj-gov-vn)
đã công bố, không crawl portal trực tiếp. Loader tải **các shard documents**
bằng `hf_hub_download` tại commit cụ thể, không tải bộ embeddings/reduces.
Lần đầu cần tải các shard này để có catalog đầy đủ, sau đó đọc Parquet theo
batch, lọc topic/subject trước khi chuyển thành Python rows. Chỉ điều thuộc
lựa chọn mới đi vào chunking, embedding và database.

`revision: main` được resolve thành commit một lần và lưu vào snapshot manifest.
Các lần dùng cache không gọi Hugging Face. Để chủ động lấy revision mới:

```powershell
.\.venv\Scripts\python.exe -m scripts.demo prepare --refresh-source
```

Cũng có thể ghi commit hash cụ thể vào YAML. Source và prepared manifest giữ
dataset revision, topic/subject IDs, phiên bản biến đổi, chunking và embedding
identity. Chuẩn bị một lựa chọn mới không làm thay đổi namespace của lựa chọn
cũ; runtime luôn mở đúng table/namespace của corpus đang được cấu hình.
Neo4j chỉ đánh dấu corpus sẵn sàng sau khi ghi xong hierarchy và relations;
index graph bị gián đoạn sẽ được chuẩn bị lại khi bật auto_prepare.

| Vị trí | Nội dung |
| --- | --- |
| `data/runtime/sources/hub` | Parquet cache của Hugging Face |
| `data/runtime/sources/<source_id>/snapshot.json` | Revision đã pin và các shard |
| `.../catalog-<revision>.json` | Tên, ID và số bản ghi của topic/subject |
| `.../selections/<selection_id>.json` | Source chunks/relations đã chuẩn hóa đúng lựa chọn |
| `data/runtime/embeddings.sqlite3` | Vector theo embedding identity + hash nội dung |
| `data/runtime/<corpus_id>/corpus.json` | Leaves/parents, manifest để mở đúng index |

Thêm topic hoặc đổi danh sách không tính lại embedding của nội dung đã có với
cùng model/dimension/normalization. Đổi nội dung hoặc model tạo cache key khác.
Cache commit theo batch: nếu provider lỗi, lần chạy sau tái sử dụng các batch
đã hoàn thành. Log hiển thị số text dùng lại và số text mới.

Hugging Face được đọc offline khi snapshot đã cache. Để hỏi đáp vẫn cần Ollama,
pgvector và Neo4j đang chạy. Thông tin về cache/revision dựa trên
[Hugging Face Hub download API](https://huggingface.co/docs/huggingface_hub/guides/download).

## Nguồn, định danh và graph

Loader giữ URL, dataset/revision, record ID, topic/subject ở metadata từng
nguồn/chunk. `record_id` được namespace theo dataset; không dùng mã điều hiển
thị làm khóa toàn cục vì mã này có thể lặp. Record trùng giống hệt được bỏ
trùng; cùng ID nhưng nội dung khác báo lỗi. Dòng phân cách không có nội dung
không được dùng làm căn cứ.
Fixed windows có thể cắt qua nhiều điều trong cùng văn bản; các thuộc tính
record/URL/topic/subject khác nhau không được lấy tùy tiện từ điều đầu tiên.

Graph chỉ resolve dẫn chiếu không mơ hồ trong lựa chọn. Tham chiếu ngoài phạm
vi hoặc mã điều trùng nhiều source records được giữ unresolved; không tự tải
topic liên quan vào corpus. Artifact chỉ được công bố sau khi kiểm tra hierarchy
và evidence. Các điều có danh sách đánh số lại được chia theo điều khi không
xác định chắc ranh giới khoản; không gán nhầm khoản để giữ hierarchical bằng mọi giá.

Corpus vẫn gồm các điều được pháp điển hóa, không bảo đảm đầy đủ toàn văn mọi
văn bản gốc hoặc tình trạng hiệu lực mới nhất. Việc chọn nhiều topic không
thay thế kiểm tra đủ căn cứ/citation của pipeline.

## Dùng JSON local

Đặt `source.type: json` để tiếp tục dùng `source_chunks_file` và `relations_file`
hiện có. Chế độ này không gọi Hugging Face; topics/subjects không được áp dụng
vào JSON. `auto_prepare` và các bước chunk/embed/index hoạt động như trên.

## Kết quả kiểm tra thực tế

Lượt kiểm tra trước với chủ đề An ninh quốc gia ở revision
`a1b6860c821b7142ffe2385178af4e4bb6f86aff`: 1.898 bản ghi, bỏ 2 dòng rỗng, còn
1.896 điều thuộc 116 văn bản; hierarchical tạo 3.490 leaves và 3.457 parents.
Neo4j lưu 144 quan hệ document đã resolve, 506 dẫn chiếu giữ unresolved.
Câu hỏi về phạm vi Luật An ninh quốc gia hoàn tất một vòng, citation được kiểm chứng.

Đổi sang riêng đề mục cùng tên: 201 điều/12 văn bản, 340 leaves; ask tự tạo
index từ cache với **340 text dùng lại, 0 text mới**, rồi trả `completed`.
Đây là kiểm tra tích hợp thực tế, chưa phải benchmark chất lượng.

Loader chọn đồng thời An ninh quốc gia và Lao động đã đọc được 3.303 điều có
nội dung thuộc 269 văn bản. Kiểm tra này xác nhận hợp hai chủ đề; chưa xây
vector/graph cho tổ hợp đó. Bộ hồi quy sau sửa generation: **292 tests, 246 subtests pass**,
gồm DB thật, chọn sai/trùng tên, scope cô lập, provenance, auto_prepare,
embedding cache theo model và tiếp tục sau batch lỗi.

Mốc rà soát tiếp theo trên ba topic Giao thông, vận tải; Khoa học, công nghệ;
Giáo dục, đào tạo: xem [PIPELINE_AUDIT_REPORT.md](PIPELINE_AUDIT_REPORT.md).
Số liệu trên ghi nhận các lần chạy trước; corpus hiện tại luôn theo YAML.
