"""Content/model-addressed embedding cache shared across topic selections."""

import hashlib
import json
import sqlite3
from pathlib import Path

from src.retrieval.common import validate_vector


class EmbeddingCache:
    def __init__(self, path: Path, *, namespace: str, dimension: int):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.namespace, self.dimension = namespace, dimension
        self.hits = self.misses = 0
        self.connection = sqlite3.connect(path)
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS embeddings (namespace TEXT, content_hash TEXT, vector TEXT NOT NULL, "
            "PRIMARY KEY (namespace, content_hash))"
        )

    def get(self, text: str) -> list[float] | None:
        key = hashlib.sha256(text.encode()).hexdigest()
        row = self.connection.execute("SELECT vector FROM embeddings WHERE namespace=? AND content_hash=?", (self.namespace, key)).fetchone()
        if row:
            self.hits += 1
            return validate_vector(json.loads(row[0]), self.dimension)
        self.misses += 1
        return None

    def put_many(self, texts: list[str], vectors: list[list[float]]) -> None:
        if len(texts) != len(vectors):
            raise ValueError("embedding cache inputs differ in length")
        rows = []
        for text, vector in zip(texts, vectors):
            key = hashlib.sha256(text.encode()).hexdigest()
            value = json.dumps(validate_vector(vector, self.dimension), allow_nan=False)
            rows.append((self.namespace, key, value))
        with self.connection:
            self.connection.executemany("INSERT OR REPLACE INTO embeddings VALUES (?, ?, ?)", rows)

    def close(self) -> None:
        self.connection.close()
