"""CLI Script to ingest legal data from Hugging Face tmquan/phapdien-moj-gov-vn."""

import argparse
import json
from pathlib import Path
import sys

# Ensure repo root is on python path
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from core.schemas.document import LegalDocument
from src.data_pipeline.loaders.phapdien_loader import PhapDienLoader


def group_articles_into_documents(
    doc_chunk_pairs: list[tuple[LegalDocument, object]],
) -> list[LegalDocument]:
    """Group article-level documents sharing the same document_id into unified LegalDocuments.

    Prevents upsert collisions in datastores where subsequent articles would overwrite
    earlier articles of the same legal document.
    """
    grouped: dict[str, list[LegalDocument]] = {}
    for doc, _ in doc_chunk_pairs:
        grouped.setdefault(doc.document_id, []).append(doc)

    merged_documents: list[LegalDocument] = []
    for doc_id, docs in grouped.items():
        base_metadata = docs[0].metadata
        # Combine unique article contents under the document
        combined_content = "\n\n".join(d.content for d in docs)
        merged_documents.append(
            LegalDocument(
                document_id=doc_id,
                content=combined_content,
                metadata=base_metadata,
            )
        )
    return merged_documents


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest legal data from Phap Dien MOJ dataset.")
    parser.add_argument("--limit", type=int, default=50, help="Number of articles to ingest (default: 50)")
    parser.add_argument("--offset", type=int, default=0, help="Starting offset (default: 0)")
    parser.add_argument(
        "--docs-output",
        type=str,
        default="data/processed/phapdien_documents.json",
        help="Path to save processed LegalDocuments",
    )
    parser.add_argument(
        "--chunks-output",
        type=str,
        default="data/chunks/phapdien_chunks.json",
        help="Path to save processed LegalChunks",
    )
    parser.add_argument(
        "--relations-output",
        type=str,
        default="data/processed/phapdien_relations.json",
        help="Path to save Knowledge Graph relations",
    )
    args = parser.parse_args()

    print("=== BẮT ĐẦU TRÍCH XUẤT DỮ LIỆU BỘ PHÁP ĐIỂN (MOJ) ===")
    print("Dataset: tmquan/phapdien-moj-gov-vn (Hugging Face)")
    print(f"Số lượng bản ghi yêu cầu: {args.limit} (offset: {args.offset})")

    loader = PhapDienLoader()

    print("Đang tải dữ liệu từ Hugging Face Server API...")
    rows = loader.fetch_rows_via_api(limit=args.limit, offset=args.offset)
    print(f"Đã nhận {len(rows)} bản ghi thô thành công!")

    doc_chunk_pairs = []
    chunks = []
    all_relations = []

    print("Đang chuyển đổi và chuẩn hóa sang schema dự án...")
    for row in rows:
        try:
            doc, chunk, relations = loader.transform_row(row)
            doc_chunk_pairs.append((doc, chunk))
            chunks.append(chunk.model_dump(mode="json"))
            all_relations.extend(relations)
        except Exception as e:
            print(f"Lỗi khi xử lý bản ghi {row.get('article_id')}: {e}")

    # ABORT AND PROTECT: If all conversions failed or chunks list is empty, DO NOT overwrite existing output files!
    if not chunks:
        print(
            "LỖI: Không có bản ghi nào được chuyển đổi thành công. Hủy xuất file để bảo vệ dữ liệu hiện có!",
            file=sys.stderr,
        )
        sys.exit(1)

    # Group articles into unified LegalDocuments by document_id
    merged_docs = group_articles_into_documents(doc_chunk_pairs)
    documents_json = [d.model_dump(mode="json") for d in merged_docs]

    # Ensure output directories exist
    docs_path = Path(args.docs_output)
    chunks_path = Path(args.chunks_output)
    rels_path = Path(args.relations_output)

    docs_path.parent.mkdir(parents=True, exist_ok=True)
    chunks_path.parent.mkdir(parents=True, exist_ok=True)
    rels_path.parent.mkdir(parents=True, exist_ok=True)

    with open(docs_path, "w", encoding="utf-8") as f:
        json.dump(documents_json, f, ensure_ascii=False, indent=2)

    with open(chunks_path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)

    with open(rels_path, "w", encoding="utf-8") as f:
        json.dump(all_relations, f, ensure_ascii=False, indent=2)

    print("\n=== HOÀN TẤT TỔNG HỢP DỮ LIỆU ===")
    print(f"1. LegalDocument (đã gom nhóm theo document_id): {len(documents_json)} văn bản -> {docs_path}")
    print(f"2. LegalChunk (giữ riêng từng điều luật):       {len(chunks)} chunks -> {chunks_path}")
    print(f"3. Graph Relations:                             {len(all_relations)} quan hệ -> {rels_path}")
    print("Dữ liệu đã sẵn sàng phục vụ cho Hybrid Search và Knowledge Graph!")


if __name__ == "__main__":
    main()
