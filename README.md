# Hướng dẫn chạy demo Vietnamese Legal RAG

Backend FastAPI nằm trong `src/api`. Sau khi chuẩn bị dữ liệu, chạy
`python -m src.api`; Swagger tại `http://127.0.0.1:8000/docs`.
Xem [hướng dẫn API và HTTP contract](docs/API.md).

Các lệnh chạy trên **Windows PowerShell**, từ thư mục gốc project.
Demo dùng Ollama, PostgreSQL/pgvector và Neo4j.

## 1. Chuẩn bị

Cài Git, Python >= 3.10 (khuyến nghị 3.12), Docker Desktop và Ollama.
Nếu chọn Conda, dùng Miniconda/Anaconda thay cho Python riêng.
Mở Docker Desktop và Ollama. Máy nên có ít nhất 16 GB RAM; lần đầu cần
Internet để tải model và dữ liệu.

```powershell
git clone https://github.com/luannt1010/dsp-vietnamese-legal-rag.git
cd dsp-vietnamese-legal-rag
```

Nếu đã clone, mở terminal tại project. Chọn **một** trong hai môi trường sau.

## 2A. Python venv

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e "."
```

Nếu PowerShell chặn script, chạy lệnh sau trong terminal hiện tại rồi kích
hoạt lại môi trường:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

## 2B. Conda

Mở Anaconda PowerShell Prompt hoặc PowerShell đã khởi tạo Conda:

```powershell
conda create -n legal-rag python=3.12 -y
conda activate legal-rag
python -m pip install --upgrade pip
python -m pip install -e "."
```

Các bước tiếp theo dùng chung. Giữ môi trường đã chọn được kích hoạt khi
chạy lệnh `python`.

## 3. Tải model và khởi động database

```powershell
ollama pull bge-m3
ollama pull qwen3.5:2b
ollama pull qwen3.5:4b
powershell -ExecutionPolicy Bypass -File .\scripts\start_demo_databases.ps1
```

Nếu Ollama chưa phục vụ kết nối, chạy `ollama serve` trong terminal riêng.
Đợi database khởi động rồi kiểm tra:

```powershell
python -m scripts.demo doctor
```

PostgreSQL dùng port `55433`, Neo4j Bolt dùng port `17687`, Neo4j Browser tại
`http://127.0.0.1:17474`. Credentials tự tạo trong `.runtime/demo.env`, CLI
tự đọc file này. Giữ file khi dùng lại database cũ. Nếu kiểm tra kết nối lỗi,
kiểm tra Docker Desktop/Ollama đang chạy rồi thử lại.

## 4. Chọn topic dữ liệu

Chỉnh `data_pipeline.source.topics` trong `configs/demo/data_pipeline.yml`.
Cấu hình hiện tại:

```yaml
topics:
  - Giao thông, vận tải
  - Khoa học, công nghệ
  - Giáo dục, đào tạo
subjects: []
```

Tra tên/ID topic và đề mục:

```powershell
python -m scripts.demo list-topics
python -m scripts.demo list-subjects
```

Để chỉ chọn đề mục, đặt `topics: []` và điền tên/ID vào `subjects`. Sau khi
đổi cấu hình, thoát chat cũ rồi chuẩn bị dữ liệu và mở chat mới.

## 5. Chuẩn bị dữ liệu và hỏi đáp

```powershell
python -m scripts.demo prepare
python -m scripts.demo chat
```

Lần đầu sẽ tải dữ liệu Hugging Face, tokenizer/reranker, tạo embedding và ghi
index vào pgvector/Neo4j nên có thể mất nhiều thời gian. Những lần sau dùng
lại cache. Với `auto_prepare: true`, `chat` cũng tự chuẩn bị index còn thiếu.

Nhập thử:

```text
Luật Giao thông đường thủy nội địa số 23/2004/QH11 điều chỉnh những hoạt động nào?
Người học có những quyền gì theo Luật Giáo dục?
```

Gõ `/exit` để thoát. Mỗi câu hỏi được xử lý độc lập. Hoặc hỏi trực tiếp:

```powershell
python -m scripts.demo ask --question "Phương tiện thủy nội địa phải đáp ứng những điều kiện gì để được hoạt động?"
```

Xem chi tiết khi có lỗi:

```powershell
python -m scripts.demo --debug ask --question "Câu hỏi của bạn"
```

## 6. Chạy lại ở lần sau

Mở terminal tại project và kích hoạt môi trường đã tạo: dùng
`.\.venv\Scripts\Activate.ps1` với venv hoặc `conda activate legal-rag` với Conda.
Mở Docker Desktop/Ollama rồi chạy:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_demo_databases.ps1
python -m scripts.demo chat
```

## 7. Benchmark

Benchmark B0–B4 đo retrieval, context, câu trả lời và inference latency bằng
cấu hình riêng. Thành viên mới bắt đầu tại
[benchmark quickstart](docs/BENCHMARK_QUICKSTART.md): cài môi trường, tải model,
chuẩn bị corpus An ninh quốc gia và chạy bộ smoke 3 câu × B0–B4 có sẵn trong repo.

Xem thêm [metric definitions và vận hành](docs/BENCHMARK.md),
[thiết kế thí nghiệm](docs/BENCHMARK_PLAN.md) và
[trạng thái dataset pilot](data/evaluation/README.md). Judge tự động hiện cần
hiệu chuẩn; chạy smoke thành công không thay thế benchmark chất lượng đã duyệt.

Bộ **development ba chủ đề, 45 câu** và lệnh Windows CMD/Conda nằm trong
[hướng dẫn bộ câu hỏi đã chuẩn hóa](data/evaluation/new/README.md). Bộ này đã dùng
để phát triển pipeline, chưa phải tập test độc lập và còn chờ rà soát pháp lý.

## 8. Báo cáo học thuật và Overleaf

Bản dùng **pdfLaTeX** gom các chương, bảng và tài liệu tham khảo vào một
[main.tex](reports/overleaf-pdflatex/main.tex). Các hình PDF vector dựng sẵn nằm
trong `figures/` đi kèm để giảm thời gian compile.

- [ZIP để upload thành project Overleaf mới](output/Report_dsp_pdflatex.zip).
- [PDF báo cáo đã biên dịch](output/pdf/Report_dsp_pdflatex.pdf).
- [Hướng dẫn pdfLaTeX](reports/overleaf-pdflatex/README.md).
- [Nguồn tác giả nhiều file, dữ liệu biểu đồ và công cụ tái tạo](reports/latex/README.md).

Trên Overleaf, chọn **Compiler: pdfLaTeX**, **Main document: main.tex**, giữ
thư mục `figures/`, rồi Recompile. Không cần chạy benchmark để biên dịch báo cáo.
Báo cáo phân biệt completion với correctness và nêu rõ giới hạn của development
pilot, nhãn evidence và judge; chưa khẳng định một cấu hình vượt trội.
