from app.main import app,CHECKS
import httpx2
import pytest

@pytest.mark.asyncio
async def test_readiness(monkeypatch):
    async def healthy():
        return None
    monkeypatch.setattr("app.main.CHECKS",{"db":healthy,"redis":healthy})
    transport=httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport,base_url="http://test") as client:
        res=await client.get("/ready")

        assert res.status_code==200
        assert res.json()["status"]=="ready"
        assert res.json()["failing"]==[]