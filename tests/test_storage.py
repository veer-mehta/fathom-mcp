import math

import pytest

from docs_mcp.storage.db import Database

pytestmark = pytest.mark.integration

DSN = "postgresql://docs_mcp:docs_mcp@localhost:5432/docs_mcp"


class FakeProvider:
    name = "fake:test"
    dimensions = 1536

    async def embed(self, texts: list[str]) -> list[list[float]]:
        results = []
        for text in texts:
            seed = sum(ord(char) for char in text)
            values = [math.sin(seed + i) for i in range(self.dimensions)]
            norm = math.sqrt(sum(v * v for v in values)) or 1.0
            results.append([v / norm for v in values])
        return results


@pytest.fixture()
async def db():
    database = Database(DSN)
    yield database
    await database.close()


@pytest.fixture()
async def clean_source(db):
    yield None
    await db.delete_source("fake-fw@1.0")


async def test_upsert_and_search_roundtrip(db, clean_source):
    provider = FakeProvider()
    await db.ensure_schema(provider.dimensions)

    rows = [
        {
            "source_id": "fake-fw@1.0",
            "url": "https://fake.dev/docs/guide",
            "title": "Guide",
            "content": f"chunk {i} about routing",
            "heading_path": ["Guide", f"S{i}"],
            "chunk_index": i,
            "provider": provider.name,
            "metadata": {},
        }
        for i in range(3)
    ]
    vectors = await provider.embed([row["content"] for row in rows])
    for row, vector in zip(rows, vectors):
        row["embedding"] = vector
    await db.upsert_chunks(rows)

    hits = await db.search((await provider.embed(["chunk 1 about routing"]))[0], k=3)
    assert hits, "expected at least one hit"
    assert hits[0].url == "https://fake.dev/docs/guide"
    assert hits[0].heading_path == ["Guide", "S1"]
    assert 0.99 < hits[0].similarity <= 1.0001

    sources = {s["source_id"]: s for s in await db.list_sources()}
    assert sources["fake-fw@1.0"]["chunks"] == 3
    assert sources["fake-fw@1.0"]["pages"] == 1


async def test_upsert_is_idempotent(db, clean_source):
    provider = FakeProvider()
    await db.ensure_schema(provider.dimensions)

    row = {
        "source_id": "fake-fw@1.0",
        "url": "https://fake.dev/docs/api",
        "title": "API",
        "content": "stable content",
        "heading_path": ["API"],
        "chunk_index": 0,
        "provider": provider.name,
        "embedding": (await provider.embed(["stable content"]))[0],
        "metadata": {},
    }
    await db.upsert_chunks([row])
    row["title"] = "API v2"
    await db.upsert_chunks([row])

    sources = {s["source_id"]: s for s in await db.list_sources()}
    assert sources["fake-fw@1.0"]["chunks"] == 1


async def test_search_respects_source_filter(db, clean_source):
    provider = FakeProvider()
    await db.ensure_schema(provider.dimensions)
    row = {
        "source_id": "fake-fw@1.0",
        "url": "https://fake.dev/docs/only",
        "title": None,
        "content": "unique filterable text",
        "heading_path": [],
        "chunk_index": 0,
        "provider": provider.name,
        "embedding": (await provider.embed(["unique filterable text"]))[0],
        "metadata": {},
    }
    await db.upsert_chunks([row])

    hits = await db.search(row["embedding"], pattern="fake-fw@%", k=5)
    assert any(hit.url == "https://fake.dev/docs/only" for hit in hits)

    hits = await db.search(row["embedding"], pattern="no-such-source@%", k=5)
    assert hits == []

    deleted = await db.delete_source("fake-fw@1.0")
    assert deleted >= 1
