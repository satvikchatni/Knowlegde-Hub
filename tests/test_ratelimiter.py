from unittest.mock import AsyncMock, MagicMock

import pytest

from app.exceptions import RateLimited
from app.services.rate_limiter import RateLimiter


@pytest.mark.asyncio
async def test_rl():
    redis = MagicMock()

    redis.eval = AsyncMock(return_value=[0, "2"])

    request = MagicMock()

    request.app.state.redis_pool = redis

    user = MagicMock()
    user.id = "abc123"

    limiter = RateLimiter(name="llm", limit=10, window=60, current_user=None)

    with pytest.raises(RateLimited):
        await limiter.dependency()(request, user)
