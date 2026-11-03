"""Model tokenizers and offset-based windows; no character/token heuristics."""

from pathlib import Path

from huggingface_hub import hf_hub_download
from tokenizers import Tokenizer


class ModelTokenizer:
    def __init__(self, model: str, *, revision: str | None = None, cache_dir: str | Path | None = None):
        path = Path(model)
        if not path.is_file():
            path = Path(hf_hub_download(model, "tokenizer.json", revision=revision, cache_dir=cache_dir))
        self.tokenizer = Tokenizer.from_file(str(path))
        self.model = model
        self.revision = revision

    def count(self, text: str) -> int:
        return len(self.tokenizer.encode(text, add_special_tokens=False).ids)

    def windows(self, text: str, *, max_tokens: int, overlap_tokens: int = 0) -> list[str]:
        if max_tokens <= 0 or not 0 <= overlap_tokens < max_tokens:
            raise ValueError("require 0 <= overlap_tokens < max_tokens")
        offsets = self.tokenizer.encode(text, add_special_tokens=False).offsets
        if not offsets:
            return []
        pieces = []
        start = 0
        while start < len(offsets):
            stop = min(start + max_tokens, len(offsets))
            piece = text[offsets[start][0]:offsets[stop - 1][1]].strip()
            # Retokenization at a cut can alter boundary tokens. Check the actual
            # substring rather than assuming slice length is an exact token count.
            while self.count(piece) > max_tokens and stop > start + 1:
                stop -= 1
                piece = text[offsets[start][0]:offsets[stop - 1][1]].strip()
            if piece:
                if self.count(piece) > max_tokens:
                    raise ValueError("a tokenizer span cannot fit the configured token budget")
                pieces.append(piece)
            if stop == len(offsets):
                break
            start = max(start + 1, stop - overlap_tokens)
        return pieces
