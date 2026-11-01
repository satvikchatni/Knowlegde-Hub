from app.main import app
import pytest
from httpx import AsyncClient,ASGITransport
from app.exceptions import TooLarge,UnsupportedType,NotFound,Conflict,UnAuthenticatedClient,UnAuthorizedClient

async def woah():
    raise RuntimeError("db pwd is omg")#Starlette's exception handler takes care of this error.

app.add_api_route("/woah",woah)

async def test_unexpected_error_is_hidden_but_logged(caplog):
    transport=ASGITransport(app=app,raise_app_exceptions=False)#ASGITransport completely bypasses the internet network layer, takes the req directly from AsyncClient to your app (Python code)
    async with AsyncClient(transport=transport,base_url="http://t") as c:#AsyncClient acts like a tool you would use to make API requests like Postman.
        r=await c.get("/woah")#URL becomes "http://t/woah"
    assert r.status_code==500
    assert r.json()=={"error_code":"internal_error",
            "message":"Something went wrong"}
    assert "omg" in caplog.text
    assert "omg" not in r.text


errors={
    401:UnAuthenticatedClient("Login first."),
    403:UnAuthorizedClient("Can't perform this action."),
    404:NotFound("Doesn't exist."),
    409:Conflict("Conflict"),
    413:TooLarge("File too large"),
    415:UnsupportedType("Only PDF/TXT files allowed.")
}

@app.get("/tests/{status_code}")
def function_for_test(status_code:int):
    if status_code in errors:
        raise errors[status_code]
    return {"good":"morning"}


@pytest.mark.parametrize(
    "expected_status_code,error_code",
    [
        (401,"unauthenticated_client_error"),(403,"unauthorized_client_error"),(404,"not_found"),(409,"conflict_error"),(413,"content_too_large"),(415,"unsupported_media_type")
    ]
)
async def test_app_error_matrix(expected_status_code,error_code):
    transport=ASGITransport(app=app,raise_app_exceptions=False)
    async with AsyncClient(transport=transport,base_url="http://t") as c:
        r=await c.get(f"/tests/{expected_status_code}")
    assert r.json()["error_code"]==error_code
    assert r.status_code==expected_status_code
    assert "detail" not in r.json()
    assert "input" not in r.json()
    
        
#405 Method Not allowed Starlette's exception
#To trigger a 405, we send a POST req insead of a GET route, FastAPI will intercept it immediately and route it to StarletteHTTPException handler
async def test_405():
    transport=ASGITransport(app=app,raise_app_exceptions=False)
    async with AsyncClient(transport=transport,base_url="http://t") as c:
        r=await c.post(f"/tests/404")
    assert r.json()["error_code"]=="http_405"
    assert r.status_code==405
    assert "detail" not in r.json()
    assert "input" not in r.json()


async def test_validation_error_handler(client):
    res=await client.post("/auth/login",data={})
    assert res.status_code==422
    assert res.json()["error_code"]=="validation_error"
    assert res.json()["message"]=="The request is invalid."
    assert "field" in res.json()["details"][0]
    assert "message" in res.json()["details"][0]
