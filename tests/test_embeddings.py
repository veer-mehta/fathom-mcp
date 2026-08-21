import asyncio
import math

import pytest

from docs_mcp.embeddings import get_embedding_provider
from docs_mcp.embeddings.hash_provider import HashEmbeddingProvider


def test_hash_provider_deterministic_and_normalized():
    provider = HashEmbeddingProvider()
    v1, v2 = asyncio.run(provider.embed(["hello world", "hello world"]))
    v3 = asyncio.run(provider.embed(["different"]))[0]
    assert v1 == v2
    assert v1 != v3
    assert len(v1) == provider.dimensions
    norm = math.sqrt(sum(x * x for x in v1))
    assert abs(norm - 1.0) < 1e-6


def test_factory_rejects_unknown_provider(monkeypatch):
    monkeypatch.setattr("docs_mcp.config.settings.embedding_provider", "bogus")
    with pytest.raises(ValueError):
        get_embedding_provider()


def test_factory_returns_hash_provider(monkeypatch):
    monkeypatch.setattr("docs_mcp.config.settings.embedding_provider", "hash")
    provider = get_embedding_provider()
    assert isinstance(provider, HashEmbeddingProvider)
