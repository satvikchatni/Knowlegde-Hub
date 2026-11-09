import pytest
from app.main import app
from app.config import settings
from app.services.local_llm import FakeLLM
from app.deps import get_llm


async def test_llm_backend_fake():
    settings.llm_backend="fake"
    async with app.router.lifespan_context(app):
        assert isinstance(app.state.llm,FakeLLM)


@pytest.mark.asyncio #tells pytest that this is an async test
async def test_embedder_gets_initialized():
    async with app.router.lifespan_context(app): #explicitly starts lifespan,with ASGITransport the lifespan isn't started
        assert app.state.embedder is not None #checks that the startup(everything before yield in lifespan) sucessffully created and initialized an embedder

#keep atleast one test that goes through the startup...


