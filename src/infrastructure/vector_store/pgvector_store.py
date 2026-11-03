"""Persistent pgvector search: exact, HNSW and IVFFlat over the same contract."""

import json
from collections.abc import Mapping

import numpy as np
import psycopg
from pgvector.psycopg import register_vector
from psycopg import sql
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from core.config.settings import VectorDatabaseSettings
from core.deadline import remaining_timeout
from core.exceptions import RetrievalError
from core.schemas import LegalChunk, RetrievedChunk
from src.retrieval.common import as_hit, normalize_vector, positive_integer, validate_filters, validate_vector


_METRICS = {
    "cosine": ("<=>", "vector_cosine_ops"),
    "inner_product": ("<#>", "vector_ip_ops"),
    "l2": ("<->", "vector_l2_ops"),
}


class PgVectorStore:
    def __init__(self, settings: VectorDatabaseSettings, *, dimension: int, table_name: str | None = None):
        positive_integer(dimension, "vector dimension")
        self.dimension = dimension
        self.settings = settings
        self.name = table_name or settings.table_name
        if len(self.name.encode("utf-8")) > 50:
            raise ValueError("vector table name must leave room for index suffixes")
        self.table = sql.Identifier(settings.schema_name, self.name)
        self.operator, self.opclass = _METRICS[settings.distance_metric]
        kwargs = {
            "host": settings.host, "port": settings.port, "dbname": settings.database,
            "user": settings.username, "connect_timeout": max(1, int(settings.connect_timeout_s)),
        }
        if settings.password is not None:
            kwargs["password"] = settings.password.get_secret_value()
        try:
            with psycopg.connect(**kwargs) as connection:
                connection.execute("CREATE EXTENSION IF NOT EXISTS vector")
                connection.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(settings.schema_name)))
                connection.execute(sql.SQL(
                    "CREATE TABLE IF NOT EXISTS {} (chunk_id text PRIMARY KEY, document_id text NOT NULL, "
                    "content text NOT NULL, metadata jsonb NOT NULL, embedding vector({}) NOT NULL)"
                ).format(self.table, sql.Literal(dimension)))
            self.pool = ConnectionPool(
                kwargs=kwargs, min_size=1, max_size=settings.pool_size, configure=register_vector,
                timeout=settings.connect_timeout_s, open=True,
            )
            self.pool.wait(timeout=settings.connect_timeout_s)
        except Exception as exc:
            raise RetrievalError("could not initialize pgvector; check database connection/permissions") from exc

    def upsert(self, chunks: list[LegalChunk]) -> None:
        if len({chunk.chunk_id for chunk in chunks}) != len(chunks):
            raise ValueError("vector index input chunk IDs must be unique")
        rows = []
        for chunk in chunks:
            hit = as_hit(chunk)
            vector = validate_vector(chunk.embedding, self.dimension)
            if self.settings.distance_metric == "cosine":
                vector = normalize_vector(vector)
            rows.append((hit.chunk_id, hit.document_id, hit.content, Jsonb(hit.metadata), np.asarray(vector, dtype=np.float32)))
        statement = sql.SQL(
            "INSERT INTO {} (chunk_id, document_id, content, metadata, embedding) VALUES (%s,%s,%s,%s,%s) "
            "ON CONFLICT (chunk_id) DO UPDATE SET document_id=EXCLUDED.document_id, content=EXCLUDED.content, "
            "metadata=EXCLUDED.metadata, embedding=EXCLUDED.embedding"
        ).format(self.table)
        try:
            with self.pool.connection() as connection, connection.cursor() as cursor:
                cursor.executemany(statement, rows)
                if self.settings.index_type != "exact" and rows:
                    options = (
                        sql.SQL("m = {}, ef_construction = {}").format(
                            sql.Literal(self.settings.hnsw_m), sql.Literal(self.settings.ef_construction),
                        ) if self.settings.index_type == "hnsw" else
                        sql.SQL("lists = {}").format(sql.Literal(min(self.settings.ivfflat_lists, max(1, len(rows) // 10))))
                    )
                    cursor.execute(sql.SQL("CREATE INDEX IF NOT EXISTS {} ON {} USING {} (embedding {}) WITH ({})").format(
                        sql.Identifier(self.name + "_" + self.settings.index_type), self.table,
                        sql.SQL(self.settings.index_type), sql.SQL(self.opclass), options,
                    ))
                cursor.execute(sql.SQL("ANALYZE {}").format(self.table))
        except Exception as exc:
            raise RetrievalError("pgvector indexing failed") from exc

    def search(self, vector: list[float], *, filters: dict, top_k: int) -> list[RetrievedChunk]:
        validate_filters(filters)
        positive_integer(top_k, "top_k")
        vector = validate_vector(vector, self.dimension)
        if self.settings.distance_metric == "cosine":
            vector = normalize_vector(vector)
        where, parameters = _filter_sql(filters)
        array = np.asarray(vector, dtype=np.float32)
        distance = sql.SQL("embedding {} %s::vector").format(sql.SQL(self.operator))
        score = sql.SQL("1 - ({})").format(distance) if self.settings.distance_metric == "cosine" else sql.SQL("-({})").format(distance)
        statement = sql.SQL(
            "SELECT chunk_id, document_id, content, metadata, {} AS score FROM {} WHERE {} "
            "ORDER BY {} LIMIT %s"
        ).format(score, self.table, where, distance)
        try:
            timeout = remaining_timeout(self.settings.connect_timeout_s)
            with self.pool.connection(timeout=timeout) as connection:
                connection.execute("SELECT set_config('statement_timeout', %s, true)", (str(max(1, int(timeout * 1000))),))
                if self.settings.index_type == "exact":
                    connection.execute("SET LOCAL enable_indexscan = off")
                elif self.settings.index_type == "hnsw":
                    connection.execute("SELECT set_config('hnsw.ef_search', %s, true)", (str(self.settings.ef_search),))
                    connection.execute("SET LOCAL hnsw.iterative_scan = strict_order")
                else:
                    connection.execute("SELECT set_config('ivfflat.probes', %s, true)", (str(self.settings.ivfflat_probes),))
                    connection.execute("SET LOCAL ivfflat.iterative_scan = relaxed_order")
                records = connection.execute(statement, [array, *parameters, array, top_k]).fetchall()
            hits = [RetrievedChunk(
                chunk_id=row[0], document_id=row[1], content=row[2], metadata=row[3],
                score=float(row[4]), retrieval_method="vector",
            ) for row in records]
            hits.sort(key=lambda hit: hit.score, reverse=True)
            return hits
        except Exception as exc:
            raise RetrievalError("pgvector search failed") from exc

    def count(self) -> int:
        with self.pool.connection() as connection:
            return connection.execute(sql.SQL("SELECT count(*) FROM {}").format(self.table)).fetchone()[0]

    def close(self) -> None:
        self.pool.close()

    def has_index(self) -> bool:
        if self.settings.index_type == "exact":
            return True
        with self.pool.connection() as connection:
            return connection.execute(
                "SELECT to_regclass(%s) IS NOT NULL",
                (self.settings.schema_name + "." + self.name + "_" + self.settings.index_type,),
            ).fetchone()[0]


def _filter_sql(filters: Mapping) -> tuple[sql.Composable, list]:
    """Flat JSON equality/intersection; bind both keys and values, including null."""
    clauses, parameters = [], []
    for key, expected in filters.items():
        alternatives = expected if isinstance(expected, list) else [expected]
        if not alternatives:
            clauses.append(sql.SQL("FALSE"))
            continue
        choices = []
        for value in alternatives:
            choices.append(sql.SQL(
                "(metadata ? %s AND (metadata -> %s = %s::jsonb OR "
                "(jsonb_typeof(metadata -> %s) = 'array' AND metadata -> %s @> %s::jsonb)))"
            ))
            parameters.extend((key, key, json.dumps(value, allow_nan=False), key, key, json.dumps([value], allow_nan=False)))
        clauses.append(sql.SQL("(") + sql.SQL(" OR ").join(choices) + sql.SQL(")"))
    return sql.SQL(" AND ").join(clauses) if clauses else sql.SQL("TRUE"), parameters
