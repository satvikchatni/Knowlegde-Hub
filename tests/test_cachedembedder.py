from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.cached_embedder import CachedEmbedder


@pytest.mark.asyncio
async def test_single_flight_cached_embedder():
    inner = MagicMock()

    inner.embed_documents = AsyncMock(return_value=[[0.1, 0.2, 0.3]])

    redis = MagicMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()

    embedder = CachedEmbedder(inner=inner, redis=redis, ttl=3600)

    res = await embedder.embed_documents(texts=["omg", "omg"], is_query=True)

    assert res == [[0.1, 0.2, 0.3], [0.1, 0.2, 0.3]]

    inner.embed_documents.assert_awaited_once()
