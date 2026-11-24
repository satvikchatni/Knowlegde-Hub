import httpx2
import pytest
from fastapi import FastAPI

from app.middleware import RequestIDMiddleware


@pytest.mark.asyncio
async def test_req_id():
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)

    @app.get("/ping")
    async def ping():
        return {"status": "ok"}

    transport = httpx2.ASGITransport(app=app)

    async with httpx2.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/ping")
        assert res.status_code == 200
        assert "x-request-id" in res.headers  # generates req id, even tho didnt send one


@pytest.mark.asyncio
async def test_req_id_passed():
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)

    @app.get("/ping")
    async def ping():
        return {"status": "ok"}

    transport = httpx2.ASGITransport(app=app)

    async with httpx2.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/ping", headers={"X-Request-ID": "abc123"})
        assert res.status_code == 200
        assert "x-request-id" in res.headers
        assert res.headers["X-Request-ID"] == "abc123"


@pytest.mark.asyncio
async def test_logs(caplog):
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)

    @app.get("/ping")
    async def ping():
        return {"status": "ok"}

    transport = httpx2.ASGITransport(app=app)
    with caplog.at_level("INFO"):
        async with httpx2.AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get("/ping", headers={"X-Request-ID": "abc123"})
            assert res.status_code == 200
            assert "x-request-id" in res.headers
            assert res.headers["X-Request-ID"] == "abc123"

            # next() finds the first log record whose message is "request"
            log = next(record for record in caplog.records if record.message == "request")

            assert log.path == "/ping"
            assert log.status == 200
            assert log.method == "GET"
            assert log.request_id == "abc123"
