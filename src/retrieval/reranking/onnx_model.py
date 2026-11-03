"""A real quantized cross-encoder backend for the existing reranker adapter."""

from pathlib import Path

import numpy as np
import onnxruntime as ort
from huggingface_hub import hf_hub_download

from src.infrastructure.tokenization import ModelTokenizer


class OnnxCrossEncoder:
    def __init__(
        self, model_name: str, *, revision: str | None = None,
        file_name: str = "onnx/model_quint8_avx2.onnx", max_length: int = 512,
        cache_dir: str | Path | None = None,
    ):
        path = hf_hub_download(model_name, file_name, revision=revision, cache_dir=cache_dir)
        self.tokenizer = ModelTokenizer(model_name, revision=revision, cache_dir=cache_dir).tokenizer
        self.tokenizer.enable_truncation(max_length=max_length, strategy="longest_first")
        self.tokenizer.enable_padding(pad_id=1, pad_token="<pad>")  # XLM-R multilingual MiniLM.
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(path, sess_options=options, providers=["CPUExecutionProvider"])
        self.input_names = {item.name for item in self.session.get_inputs()}

    def predict(self, pairs: list[tuple[str, str]], *, batch_size: int):
        scores = []
        for offset in range(0, len(pairs), batch_size):
            encoded = self.tokenizer.encode_batch(pairs[offset:offset + batch_size])
            inputs = {
                "input_ids": np.asarray([item.ids for item in encoded], dtype=np.int64),
                "attention_mask": np.asarray([item.attention_mask for item in encoded], dtype=np.int64),
                "token_type_ids": np.asarray([item.type_ids for item in encoded], dtype=np.int64),
            }
            logits = self.session.run(None, {key: value for key, value in inputs.items() if key in self.input_names})[0]
            if logits.ndim != 2 or logits.shape != (len(encoded), 1):
                raise ValueError("ONNX reranker must return one relevance logit per pair")
            scores.extend(logits[:, 0].tolist())
        return scores
