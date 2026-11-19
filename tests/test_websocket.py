import pytest
from arq import create_pool
from arq.connections import RedisSettings
from httpx2 import AsyncClient
from httpx2.websockets import ASGIWebSocketTransport, WebSocketDisconnect

from app.config import settings
from app.main import app


async def test_ws_bad_token(make_user, make_workspace):
    owner = await make_user("owner@example.com")
    ws = await make_workspace(workspace_name="testws", user_headers=owner["headers"])
    workspace_id = ws["id"]
    async with AsyncClient(
        transport=ASGIWebSocketTransport(app), base_url="http://test"
    ) as ws_client:
        async with ws_client.websocket(f"/ws/workspaces/{workspace_id}/progress") as ws:
            await ws.send_text("invalid token")

            with pytest.raises(WebSocketDisconnect) as exc:
                await ws.receive_text()

            assert exc.value.code == 1008


async def test_ws_no_token(make_user, make_workspace):
    owner = await make_user("owner@example.com")
    ws = await make_workspace(workspace_name="testws", user_headers=owner["headers"])
    workspace_id = ws["id"]
    async with AsyncClient(
        transport=ASGIWebSocketTransport(app), base_url="http://test"
    ) as ws_client:
        async with ws_client.websocket(f"/ws/workspaces/{workspace_id}/progress") as ws:
            with pytest.raises(WebSocketDisconnect) as exc:
                await ws.receive_text()

            assert exc.value.code == 1008


async def test_ws_token_nonmember(make_user, make_workspace):
    owner = await make_user("owner@example.com")
    ws = await make_workspace(workspace_name="testws", user_headers=owner["headers"])
    workspace_id = ws["id"]
    nm = await make_user("nm@example.com")
    async with AsyncClient(
        transport=ASGIWebSocketTransport(app), base_url="http://test"
    ) as ws_client:
        async with ws_client.websocket(f"/ws/workspaces/{workspace_id}/progress") as ws:
            await ws.send_text(f"{nm['access_token']}")

            with pytest.raises(WebSocketDisconnect) as exc:
                await ws.receive_text()

            assert exc.value.code == 1008


async def test_ws_token_member(make_user, make_workspace, monkeypatch):
    owner = await make_user("owner@example.com")
    ws = await make_workspace(workspace_name="testws", user_headers=owner["headers"])
    workspace_id = ws["id"]
    redis_pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    monkeypatch.setattr(app.state, "redis_pool", redis_pool, raising=False)

    try:
        async with AsyncClient(
            transport=ASGIWebSocketTransport(app), base_url="http://test"
        ) as ws_client:
            async with ws_client.websocket(f"/ws/workspaces/{workspace_id}/progress") as ws:
                await ws.send_text(f"{owner['access_token']}")

                snapshot = await ws.receive_json()

                assert snapshot["event"] == "snapshot"
                assert snapshot["documents"] == []  # cause no doc uploads
    finally:
        await redis_pool.aclose()
