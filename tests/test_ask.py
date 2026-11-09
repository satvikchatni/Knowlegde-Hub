import uuid
from unittest.mock import AsyncMock, patch

from google.genai import errors

from app.deps import get_llm
from app.exceptions import LLMTimeout, LLMUnavailable
from app.main import app
from app.schemas import Ask, SearchOut
from app.services.local_llm import FakeLLM
from app.services.workspaces import ask


async def test_ask_empty_question(client,make_user,make_workspace):
    owner=await make_user("owner@example.com")
    ws=await make_workspace(workspace_name="testws",user_headers=owner["headers"])
    workspace_id=ws["id"]
    res=await client.post(f"/workspaces/{workspace_id}/ask",json={"question":""},headers=owner["headers"])
    assert res.status_code==422

async def test_ask_long_question(client,make_user,make_workspace):
    owner=await make_user("owner@example.com")
    ws=await make_workspace(workspace_name="testws",user_headers=owner["headers"])
    workspace_id=ws["id"]
    #James Bond
    res=await client.post(f"/workspaces/{workspace_id}/ask",json={"question":"a"*1007},headers=owner["headers"])
    assert res.status_code==422


chunk1 = SearchOut(
    chunk_id=uuid.UUID(int=101),
    document_id=uuid.UUID(int=1),
    filename="testf1.txt",
    page_number=1,
    position=1,
    text="Today is my Birthday",
    score=0.75,
)
chunk2=SearchOut(
    chunk_id=uuid.UUID(int=102),
    document_id=uuid.UUID(int=2),
    filename="testf2.txt",
    page_number=2,
    position=2,
    text="Happy birthday Rishabh",
    score=0.5,
)

ask_params=Ask(question="When is my bday")

#called happy path cause everything goes right
async def test_happy_path():
    workspace_id=uuid.uuid4() #dummy ws id, won't be querying thr db
    llm=FakeLLM(f'{{"answer":"Rishabh bday is today","cited_ids":["{chunk1.chunk_id}","{chunk2.chunk_id}"]}}')
    with patch("app.services.workspaces.retrieve",return_value=[chunk1,chunk2]) as mock_retrieve:
        result=await ask(db=None,workspace_id=workspace_id,ask_params=ask_params,llm=llm,embedder=None)
        print(result["citations"])
        assert result["answer"]=="Rishabh bday is today"
        assert len(result["citations"])==2
        assert result["citations"][0]['chunk_id']==chunk1.chunk_id
        assert result["citations"][1]['chunk_id']==chunk2.chunk_id
    mock_retrieve.assert_called_once() #to check retrieve was only called once


async def test_ask_no_chunks():
    workspace_id=uuid.uuid4() #dummy ws id, won't be querying thr db
    llm=FakeLLM(f'{{"answer":"llm wont be called","cited_ids":["{chunk1.chunk_id}"]}}') #creates fake llm
    llm.generate=AsyncMock() # replaces it's generate method with a mock so we can check whether it has been awaited or not
    with patch("app.services.workspaces.retrieve",return_value=[]) as mock_retrieve:
        result=await ask(db=None,workspace_id=workspace_id,ask_params=ask_params,llm=llm,embedder=None)
        assert result["citations"]==[]
        assert result["answer"]=="I don't know the answer based on the provided documents"
    llm.generate.assert_not_awaited() #since retrieve() returns [] we don't waste api calls and the async generate() function is never awaited/used.the llm is never called
    mock_retrieve.assert_called_once() #to check retrieve was only called once


async def test_ask_llm_timeout(client,make_user,make_workspace):
    owner=await make_user("owner@example.com")
    ws=await make_workspace("testws",user_headers=owner["headers"])
    workspace_id=ws["id"]
    llm=FakeLLM(f'{{"answer":"llm is taking too long","cited_ids":["{chunk1.chunk_id}"]}}')
    llm.generate=AsyncMock(side_effect=LLMTimeout("Gemini took too long to respond")) #side_effect tells the mock what to do when it gets called
    app.dependency_overrides[get_llm]=lambda:llm #client fixtures already overrides get_llm with FakeLLM, but here we need to override it with the mock we just created
    with patch("app.services.workspaces.retrieve",return_value=[chunk1]): #if we don't use this retrieve returns [] and it never get's to generate()
        res=await client.post(f"/workspaces/{workspace_id}/ask",headers=owner["headers"],json={"question":"When is my bday?"})
        llm.generate.assert_awaited_once()
        assert res.status_code==504
        assert res.json()["error_code"]=="llm_timeout"


async def test_ask_llm_unavailable(client,make_user,make_workspace):
    owner=await make_user("owner@example.com")
    ws=await make_workspace("testws",user_headers=owner["headers"])
    workspace_id=ws["id"]
    llm=FakeLLM(f'{{"answer":"llm wont answer the call","cited_ids":["{chunk1.chunk_id}"]}}')
    llm.generate=AsyncMock(side_effect=LLMUnavailable("Gemini is busy elsewhere"))
    app.dependency_overrides[get_llm]=lambda:llm
    with patch("app.services.workspaces.retrieve",return_value=[chunk1]):
        res=await client.post(f"/workspaces/{workspace_id}/ask",headers=owner["headers"],json={"question":"When is my bday?"})
        llm.generate.assert_awaited_once()
        assert res.status_code==503
        assert res.json()["error_code"]=="llm_unavailable"


async def test_ask_llm_invalid_res(client,make_user,make_workspace):
    owner=await make_user("owner@example.com")
    ws=await make_workspace("testws",user_headers=owner["headers"])
    workspace_id=ws["id"]
    llm=FakeLLM(generated_text='{"answer":"this is gonna reply with 502","cited_ids":]}')
    app.dependency_overrides[get_llm]=lambda:llm
    with patch("app.services.workspaces.retrieve",return_value=[chunk1]):
        res=await client.post(f"/workspaces/{workspace_id}/ask",headers=owner["headers"],json={"question":"When is my bday?"})
        assert res.status_code==502
        assert res.json()["error_code"]=="invalid_llm_response"

# from google.genai import errors
# import inspect
# print(inspect.signature(errors.ClientError))

# gemini reteurning 403
auth_error = errors.ClientError(
    code=403,
    response_json={
        "error": {"message": "api key doesn't have permission", "status": "PERMISSION_DENIED"}
    },
)


# ASGITransport:raise_app_exception=False, if an exception escapes, don't re-raise it, let me inspect the http response.
async def test_ask_llm_auth_error(client, make_user, make_workspace, caplog):
    owner = await make_user("owner@example.com")
    ws = await make_workspace("testws", user_headers=owner["headers"])
    workspace_id = ws["id"]
    llm = FakeLLM(f'{{"answer":"auth error loading","cited_ids":["{chunk1.chunk_id}"]}}')
    llm.generate = AsyncMock(side_effect=auth_error)
    app.dependency_overrides[get_llm] = lambda: llm
    with patch("app.services.workspaces.retrieve", return_value=[chunk1]):
        res = await client.post(
            f"/workspaces/{workspace_id}/ask",
            headers=owner["headers"],
            json={"question": "When is my bday?"},
        )
        # what user sees
        assert res.status_code == 500
        assert res.json()["error_code"] == "internal_error"
        assert res.json()["message"] == "Something went wrong"
        # what server(we) see
        assert "Unhandled error on POST" in caplog.text
        assert "/workspaces/" in caplog.text
        assert "403 PERMISSION_DENIED" in caplog.text
