import pytest
from app.main import app
@pytest.mark.asyncio #tells pytest that this is an async test
async def test_embedder_gets_initialized():
    async with app.router.lifespan_context(app): #explicitly starts lifespan,with ASGITransport the lifespan isn't started
        assert app.state.embedder is not None #checks that the startup(everything before yield in lifespan) sucessffully created and initialized an embedder

#keep atleast one test that goes through the startup...