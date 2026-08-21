import json
from dataclasses import dataclass

import asyncpg

SCHEMA_SQL = "CREATE EXTENSION IF NOT EXISTS vector"

TABLE_SQL = """
CREATE TABLE IF NOT EXISTS documents (
    id BIGSERIAL PRIMARY KEY,
    source_id TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT,
    content TEXT NOT NULL,
    heading_path TEXT[] NOT NULL DEFAULT '{}',
    chunk_index INT NOT NULL,
    provider TEXT NOT NULL,
    embedding vector({dim}) NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_id, url, chunk_index)
)
"""

UPSERT_SQL = """
INSERT INTO documents (source_id, url, title, content, heading_path, chunk_index, provider, embedding, metadata)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8::vector, $9::jsonb)
ON CONFLICT (source_id, url, chunk_index) DO UPDATE SET
    title = EXCLUDED.title,
    content = EXCLUDED.content,
    heading_path = EXCLUDED.heading_path,
    provider = EXCLUDED.provider,
    embedding = EXCLUDED.embedding,
    metadata = EXCLUDED.metadata,
    created_at = now()
"""


@dataclass
class SearchHit:
    url: str
    title: str | None
    heading_path: list[str]
    content: str
    similarity: float


def to_vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{v:.7f}" for v in vector) + "]"


class Database:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None

    async def pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=4)
        return self._pool

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def ensure_schema(self, dim: int) -> None:
        pool = await self.pool()
        async with pool.acquire() as conn:
            await conn.execute(SCHEMA_SQL)
            await conn.execute(TABLE_SQL.replace("{dim}", str(dim)))
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS documents_embedding_hnsw "
                "ON documents USING hnsw (embedding vector_cosine_ops)"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS documents_source_idx ON documents (source_id)"
            )
            actual = await conn.fetchval(
                "SELECT format_type(a.atttypid, a.atttypmod) FROM pg_attribute a "
                "WHERE a.attrelid = 'documents'::regclass AND a.attname = 'embedding'"
            )
            expected = f"vector({dim})"
            if actual != expected:
                raise RuntimeError(
                    f"documents.embedding column is {actual}, expected {expected}; "
                    "switch EMBEDDING_PROVIDER back or DROP TABLE documents and re-ingest"
                )

    async def upsert_chunks(self, rows: list[dict]) -> None:
        if not rows:
            return
        pool = await self.pool()
        params = [
            (
                row["source_id"],
                row["url"],
                row.get("title"),
                row["content"],
                row.get("heading_path") or [],
                row["chunk_index"],
                row["provider"],
                to_vector_literal(row["embedding"]),
                json.dumps(row.get("metadata") or {}),
            )
            for row in rows
        ]
        async with pool.acquire() as conn:
            await conn.executemany(UPSERT_SQL, params)

    async def search(
        self, query_vector: list[float], pattern: str | None = None, k: int = 5
    ) -> list[SearchHit]:
        pool = await self.pool()
        rows = await pool.fetch(
            "SELECT url, title, heading_path, content, "
            "1 - (embedding <=> $1::vector) AS similarity "
            "FROM documents WHERE ($2::text IS NULL OR source_id LIKE $2) "
            "ORDER BY embedding <=> $1::vector LIMIT $3",
            to_vector_literal(query_vector),
            pattern,
            k,
        )
        return [
            SearchHit(
                url=row["url"],
                title=row["title"],
                heading_path=list(row["heading_path"]),
                content=row["content"],
                similarity=float(row["similarity"]),
            )
            for row in rows
        ]

    async def list_sources(self) -> list[dict]:
        pool = await self.pool()
        rows = await pool.fetch(
            "SELECT source_id, count(DISTINCT url) AS pages, count(*) AS chunks, "
            "max(created_at) AS updated_at "
            "FROM documents GROUP BY source_id ORDER BY source_id"
        )
        return [dict(row) for row in rows]

    async def delete_source(self, source_id: str) -> int:
        pool = await self.pool()
        status = await pool.execute(
            "DELETE FROM documents WHERE source_id = $1", source_id
        )
        return int(status.split()[-1])
