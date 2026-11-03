"""Opt-in live integration checks for the three demo topics (not a benchmark)."""

import argparse
import json
import sys
from pathlib import Path
from time import monotonic

from scripts.demo import ROOT, load_demo_settings
from core.schemas import QueryRequest
from src.data_pipeline.artifacts import write_json
from src.runtime import open_runtime


CASES = [
    ("GT01", "Luật Giao thông đường thủy nội địa số 23/2004/QH11 điều chỉnh những hoạt động nào?", "completed"),
    ("GT03", "Phương tiện thủy nội địa phải đáp ứng những điều kiện gì để được hoạt động?", "completed"),
    ("GT06", "Những hành vi nào bị nghiêm cấm trong hoạt động hàng hải?", "completed"),
    ("KH01", "Luật Chuyển giao công nghệ số 07/2017/QH14 điều chỉnh những hoạt động nào?", "completed"),
    ("KH05", "Người sản xuất có những nghĩa vụ gì trong việc bảo đảm chất lượng sản phẩm, hàng hóa?", "completed"),
    ("KH07", "Tiêu chuẩn và quy chuẩn kỹ thuật khác nhau như thế nào theo các nguồn được cung cấp?", "completed"),
    ("GD01", "Luật Giáo dục số 43/2019/QH14 có phạm vi điều chỉnh như thế nào?", "completed"),
    ("GD03", "Phổ cập giáo dục và giáo dục bắt buộc được quy định như thế nào?", "completed"),
    ("GD04", "Người học có những quyền gì theo Luật Giáo dục?", "completed"),
    ("OUT01", "Số dư tài khoản ngân hàng cá nhân của tôi hôm nay là bao nhiêu? Tôi chưa cung cấp dữ liệu tài khoản hay giao dịch.", "insufficient_evidence"),
]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-dir", type=Path, default=ROOT / "configs/demo")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".runtime/demo.env")
    parser.add_argument("--output", type=Path, default=ROOT / ".runtime/pipeline-smoke")
    args = parser.parse_args()
    # Reuse the demo's exact config/env resolution and composition root.
    for name in ("chunking", "vector_index", "vector_backend", "graph_backend"):
        setattr(args, name, None)
    args.no_rerank = False
    settings = load_demo_settings(args)
    checks = []
    with open_runtime(settings) as runtime:
        topics = {chunk.metadata.topic_title for chunk in runtime.corpus.chunks}
        required = {"Giao thông, vận tải", "Khoa học, công nghệ", "Giáo dục, đào tạo"}
        if not required.issubset(topics):
            parser.error("this smoke set requires all three configured demo topics")
        for identifier, question, expected in CASES:
            started = monotonic()
            result = runtime.pipeline.run_with_trace(QueryRequest(query=question))
            write_json(args.output / f"{identifier}.json", result.model_dump(mode="json"))
            check = {"id": identifier, "query": question, "expected": expected, "status": result.status,
                     "stage": result.failure_stage, "error_type": result.error_type,
                     "rounds": len(result.rounds), "seconds": round(monotonic() - started, 2),
                     "passed": result.status == expected}
            checks.append(check)
            write_json(args.output / "summary.json", {"corpus_id": runtime.corpus.corpus_id, "checks": checks})
            print(json.dumps(check, ensure_ascii=False), flush=True)
    return 0 if all(check["passed"] for check in checks) else 2


if __name__ == "__main__":
    raise SystemExit(main())
