# transport buffers the entire response, the test client may receive the complete res only after the stream finishes
# we cant use ASGI to ptove that our events arrived at a particular time, or that cancellation works correctly
# need a diff testing approach

import json
import uuid
from unittest.mock import AsyncMock,Mock

from sqlalchemy import select

from app.deps import get_llm
from app.main import app
from app.models import Conversation, Document, Message
from app.services.local_llm import FakeLLM


async def post_question(client, workspace_id, conversation_id, question, headers):
    res = await client.post(
        f"/workspaces/{workspace_id}/conversations/{conversation_id}/stream",
        headers=headers,
        json={"question": question},
    )
    assert res.status_code == 200
    return list(parse_sse(res.text.splitlines()))  # returns (event,data) pairs


# yield makes this a generator produces events one at a time, instead of returning a complete list.
def parse_sse(lines):
    event, data = "message", []

    for line in lines:
        if line == "":  # empty line marks the send of a SSE event
            if data:  # checks whether there is data
                yield (
                    event,
                    "\n".join(data),
                )  # returns the event name and the data wo ending the generator
            event, data = "message", []  # resets both variables so the next SSE can be processed
        elif line.startswith(":"):
            continue  # lines beginning with : are normally SSE comments, so skip them using continue moving to next iteration
        elif line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data.append(line[5:].strip())


async def test_happy_path(client, upload_file, make_user, make_workspace, db_session):
    app.dependency_overrides[get_llm] = lambda: FakeLLM(
        pieces=["Knowledge hub is a RAG-based application [1]"]
    )
    owner = await make_user("owner@example.com")
    ws = await make_workspace("testws", user_headers=owner["headers"])
    workspace_id = ws["id"]
    res = await client.post(
        f"/workspaces/{workspace_id}/conversations",
        json={"title": "testconvo"},
        headers=owner["headers"],
    )
    assert res.status_code == 201
    conversation_id = res.json()["id"]
    upload_res = await upload_file(
        filename="test.txt",
        content=b"Knowledge hub is a RAG-based application ",
        workspace_id=workspace_id,
        headers=owner["headers"],
    )
    assert upload_res.status_code == 202
    doc_id = upload_res.json()["id"]
    r = await db_session.execute(
        select(Document).where(Document.id == doc_id, Document.workspace_id == workspace_id)
    )
    document = r.scalar_one()
    assert document.status == "done"
    cr = await db_session.execute(
        select(Conversation).where(
            Conversation.id == conversation_id, Conversation.workspace_id == workspace_id
        )
    )
    c = cr.scalar_one()
    assert c.title == "testconvo"
    assert c.workspace_id == uuid.UUID(workspace_id)
    assert c.id == uuid.UUID(conversation_id)

    events = await post_question(
        client=client,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        question="What is knowledge hub???",
        headers=owner["headers"],
    )

    result = await db_session.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id, Message.role == "assistant")
        .order_by(Message.created_at.desc())
    )
    assistant_mssg = result.scalars().first()
    assert assistant_mssg is not None

    streamed_text = "".join(json.loads(event[1])["text"] for event in events if event[0] == "token")
    assert streamed_text == assistant_mssg.content

    event_names = [event[0] for event in events]
    assert "done" in event_names
    assert "citations" in event_names
    assert "token" in event_names


async def test_no_chunks_no_llm_call(client, make_user, make_workspace):
    llm = FakeLLM(pieces=["Knowledge hub is a RAG-based application [1]"])
    llm.stream = AsyncMock()
    app.dependency_overrides[get_llm] = lambda: llm
    owner = await make_user("owner@example.com")
    ws = await make_workspace("testws", user_headers=owner["headers"])
    workspace_id = ws["id"]
    res = await client.post(
        f"/workspaces/{workspace_id}/conversations",
        json={"title": "testconvo"},
        headers=owner["headers"],
    )
    assert res.status_code == 201
    conversation_id = res.json()["id"]
    events = await post_question(
        client=client,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        question="What is knowledge hub???",
        headers=owner["headers"],
    )

    llm.stream.assert_not_awaited()
    streamed_text = "".join(json.loads(event[1])["text"] for event in events if event[0] == "token")
    assert streamed_text == "I don't know the answer based on the provided documents."

    event_names = [event[0] for event in events]
    assert "done" in event_names
    assert "citations" not in event_names
    assert "token" in event_names


async def test_statfullness(client,make_user,make_workspace,upload_file,db_session):
    llm= FakeLLM(
        pieces=["Knowledge hub is a RAG-based application [1]"]
    )

    app.dependency_overrides[get_llm] = lambda: llm
    owner = await make_user("owner@example.com")
    ws = await make_workspace("testws", user_headers=owner["headers"])
    workspace_id = ws["id"]
    res = await client.post(
        f"/workspaces/{workspace_id}/conversations",
        json={"title": "testconvo"},
        headers=owner["headers"],
    )
    assert res.status_code == 201
    conversation_id = res.json()["id"]
    upload_res = await upload_file(
        filename="test.txt",
        content=b"Knowledge hub is a RAG-based application ",
        workspace_id=workspace_id,
        headers=owner["headers"],
    )
    assert upload_res.status_code == 202
    doc_id = upload_res.json()["id"]
    r = await db_session.execute(
        select(Document).where(Document.id == doc_id, Document.workspace_id == workspace_id)
    )
    document = r.scalar_one()
    assert document.status == "done"
    eventsq1 = await post_question(
        client=client,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        question="What is knowledge hub???",
        headers=owner["headers"],
    )
    eventsq2 = await post_question(
        client=client,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        question="RAG-Application???",
        headers=owner["headers"],
    )
    second_prompt=llm.received_messages[1]
    assert "Knowledge hub is a RAG-based application [1]" in second_prompt
    assert "What is knowledge hub???" in second_prompt
    
    assert "RAG-Application???" in second_prompt


async def test_unauthorized_user_stream_endpoint(client,make_user,make_workspace,upload_file):
    app.dependency_overrides[get_llm] = lambda: FakeLLM(
        pieces=["Knowledge hub is a RAG-based application [1]"]
    )
    owner = await make_user("owner@example.com")
    ws = await make_workspace("testws", user_headers=owner["headers"])
    workspace_id = ws["id"]
    res = await client.post(
        f"/workspaces/{workspace_id}/conversations",
        json={"title": "testconvo"},
        headers=owner["headers"],
    )
    assert res.status_code == 201
    conversation_id = res.json()["id"]
    upload_res = await upload_file(
        filename="test.txt",
        content=b"Knowledge hub is a RAG-based application ",
        workspace_id=workspace_id,
        headers=owner["headers"],
    )
    assert upload_res.status_code == 202
    result = await client.post(
        f"/workspaces/{workspace_id}/conversations/{conversation_id}/stream",
        json={"question": "Can a unauthorized user get in?HELL NAH"},
    )
    assert result.status_code == 401
    assert "application/json" in result.headers["content-type"]  
    assert "text/event-stream" not in result.headers["content-type"]



async def test_stranger_stream_endpoint(client,make_user,make_workspace,upload_file):
    app.dependency_overrides[get_llm] = lambda: FakeLLM(
        pieces=["Knowledge hub is a RAG-based application [1]"]
    )
    owner = await make_user("owner@example.com")
    ws = await make_workspace("testws", user_headers=owner["headers"])
    workspace_id = ws["id"]
    res = await client.post(
        f"/workspaces/{workspace_id}/conversations",
        json={"title": "testconvo"},
        headers=owner["headers"],
    )
    assert res.status_code == 201
    conversation_id = res.json()["id"]
    upload_res = await upload_file(
        filename="test.txt",
        content=b"Knowledge hub is a RAG-based application ",
        workspace_id=workspace_id,
        headers=owner["headers"],
    )
    assert upload_res.status_code == 202
    stranger=await make_user("stranger@example.com")
    result = await client.post(
        f"/workspaces/{workspace_id}/conversations/{conversation_id}/stream",
        json={"question": "Can a stranger user get in?HELL NAH"},
        headers=stranger["headers"]
    )
    assert result.status_code == 404
    assert "application/json" in result.headers["content-type"]  
    assert "text/event-stream" not in result.headers["content-type"]




async def test_editor_no_access_to_owner_convo_stream_endpoint(client,make_user,make_membership,make_workspace,upload_file):
    app.dependency_overrides[get_llm] = lambda: FakeLLM(
        pieces=["Knowledge hub is a RAG-based application [1]"]
    )
    owner = await make_user("owner@example.com")
    ws = await make_workspace("testws", user_headers=owner["headers"])
    workspace_id = ws["id"]
    res = await client.post(
        f"/workspaces/{workspace_id}/conversations",
        json={"title": "testconvo"},
        headers=owner["headers"],
    )
    assert res.status_code == 201
    conversation_id = res.json()["id"]
    upload_res = await upload_file(
        filename="test.txt",
        content=b"Knowledge hub is a RAG-based application ",
        workspace_id=workspace_id,
        headers=owner["headers"],
    )
    assert upload_res.status_code == 202
    editor=await make_user("editor@example.com")
    await make_membership(workspace_id=workspace_id, role="editor", email=editor["email"], owner_headers=owner["headers"])
    result = await client.post(
        f"/workspaces/{workspace_id}/conversations/{conversation_id}/stream",
        json={"question": "Can a editor user access owners convo?HELL NAH"},
        headers=editor["headers"]
    )
    assert result.status_code == 404
    assert "application/json" in result.headers["content-type"]  
    assert "text/event-stream" not in result.headers["content-type"]



async def test_invalid_qn_stream_endpoint(client,make_user,make_workspace,upload_file):
    app.dependency_overrides[get_llm] = lambda: FakeLLM(
        pieces=["Knowledge hub is a RAG-based application [1]"]
    )
    owner = await make_user("owner@example.com")
    ws = await make_workspace("testws", user_headers=owner["headers"])
    workspace_id = ws["id"]
    res = await client.post(
        f"/workspaces/{workspace_id}/conversations",
        json={"title": "testconvo"},
        headers=owner["headers"],
    )
    assert res.status_code == 201
    conversation_id = res.json()["id"]
    upload_res = await upload_file(
        filename="test.txt",
        content=b"Knowledge hub is a RAG-based application ",
        workspace_id=workspace_id,
        headers=owner["headers"],
    )
    assert upload_res.status_code == 202
    result = await client.post(
        f"/workspaces/{workspace_id}/conversations/{conversation_id}/stream",
        json={"question": ""},
        headers=owner["headers"]
    )
    assert result.status_code == 422
    assert "application/json" in result.headers["content-type"]  
    assert "text/event-stream" not in result.headers["content-type"]


async def test_invalid_long_qn_stream_endpoint(client,make_user,make_workspace,upload_file):
    app.dependency_overrides[get_llm] = lambda: FakeLLM(
        pieces=["Knowledge hub is a RAG-based application [1]"]
    )
    owner = await make_user("owner@example.com")
    ws = await make_workspace("testws", user_headers=owner["headers"])
    workspace_id = ws["id"]
    res = await client.post(
        f"/workspaces/{workspace_id}/conversations",
        json={"title": "testconvo"},
        headers=owner["headers"],
    )
    assert res.status_code == 201
    conversation_id = res.json()["id"]
    upload_res = await upload_file(
        filename="test.txt",
        content=b"Knowledge hub is a RAG-based application ",
        workspace_id=workspace_id,
        headers=owner["headers"],
    )
    assert upload_res.status_code == 202
    result = await client.post(
        f"/workspaces/{workspace_id}/conversations/{conversation_id}/stream",
        json={"question": "RAG?"*150},
        headers=owner["headers"]
    )
    assert result.status_code == 422
    assert "application/json" in result.headers["content-type"]  
    assert "text/event-stream" not in result.headers["content-type"]



async def test_fail_after(client,make_user,make_workspace,upload_file,db_session):
    app.dependency_overrides[get_llm] = lambda: FakeLLM(
        pieces=["hello","world","!"], fail_after=2
    )
    owner = await make_user("owner@example.com")
    ws = await make_workspace("testws", user_headers=owner["headers"])
    workspace_id = ws["id"]
    res = await client.post(
        f"/workspaces/{workspace_id}/conversations",
        json={"title": "testconvo"},
        headers=owner["headers"],
    )
    assert res.status_code == 201
    conversation_id = res.json()["id"]
    upload_res = await upload_file(
        filename="test.txt",
        content=b"HELLO WORLD ",
        workspace_id=workspace_id,
        headers=owner["headers"],
    )
    assert upload_res.status_code == 202


    events = await post_question(
        client=client,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        question="hello world???",
        headers=owner["headers"],
    )


    streamed_text = "".join(json.loads(event[1])["text"] for event in events if event[0] == "token")
    assert streamed_text == "helloworld"

    event_names = [event[0] for event in events]
    assert "done" not in event_names
    assert "citations" not in event_names
    assert "token" in event_names
    assert "error" in event_names
    ar=await db_session.execute(select(Message).where(Message.conversation_id==conversation_id).order_by(Message.created_at.desc()))
    assistant_mssg= ar.scalars().first()

    assert assistant_mssg.content=="helloworld"
    assert assistant_mssg.status=="partial"


#no final result event
async def test_end_early(client,make_user,make_workspace,upload_file,db_session):
    app.dependency_overrides[get_llm] = lambda: FakeLLM(
        pieces=["hello","world","!"], end_early=True
    )
    owner = await make_user("owner@example.com")
    ws = await make_workspace("testws", user_headers=owner["headers"])
    workspace_id = ws["id"]
    res = await client.post(
        f"/workspaces/{workspace_id}/conversations",
        json={"title": "testconvo"},
        headers=owner["headers"],
    )
    assert res.status_code == 201
    conversation_id = res.json()["id"]
    upload_res = await upload_file(
        filename="test.txt",
        content=b"HELLO WORLD ",
        workspace_id=workspace_id,
        headers=owner["headers"],
    )
    assert upload_res.status_code == 202


    events = await post_question(
        client=client,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        question="hello world???",
        headers=owner["headers"],
    )


    streamed_text = "".join(json.loads(event[1])["text"] for event in events if event[0] == "token")
    assert streamed_text == "helloworld!"

    event_names = [event[0] for event in events]
    assert "done" not in event_names
    assert "citations" not in event_names
    assert "token" in event_names

    assert "error" in event_names
    ar=await db_session.execute(select(Message).where(Message.conversation_id==conversation_id).order_by(Message.created_at.desc()))
    assistant_mssg= ar.scalars().first()

    assert assistant_mssg.content=="helloworld!"
    assert assistant_mssg.status=="partial"



# final result event is passed
async def test_hit_max_tokens(client,make_user,make_workspace,upload_file,db_session):
    app.dependency_overrides[get_llm] = lambda: FakeLLM(
        pieces=["hello","world","!"], hit_max_tokens=True
    )
    owner = await make_user("owner@example.com")
    ws = await make_workspace("testws", user_headers=owner["headers"])
    workspace_id = ws["id"]
    res = await client.post(
        f"/workspaces/{workspace_id}/conversations",
        json={"title": "testconvo"},
        headers=owner["headers"],
    )
    assert res.status_code == 201
    conversation_id = res.json()["id"]
    upload_res = await upload_file(
        filename="test.txt",
        content=b"HELLO WORLD ",
        workspace_id=workspace_id,
        headers=owner["headers"],
    )
    assert upload_res.status_code == 202


    events = await post_question(
        client=client,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        question="hello world???",
        headers=owner["headers"],
    )


    streamed_text = "".join(json.loads(event[1])["text"] for event in events if event[0] == "token")
    assert streamed_text == "helloworld!"

    event_names = [event[0] for event in events]
    assert "done" in event_names
    assert "citations" not in event_names
    assert "token" in event_names

    assert "error" not in event_names
    ar=await db_session.execute(select(Message).where(Message.conversation_id==conversation_id).order_by(Message.created_at.desc()))
    assistant_mssg= ar.scalars().first()

    assert assistant_mssg.content=="helloworld!"
    assert assistant_mssg.status=="partial"




async def test_invalid_citation(client,make_user,make_workspace,upload_file,db_session):
    app.dependency_overrides[get_llm] = lambda: FakeLLM(
        pieces=["knowledge hub is a rag-based app [99]"], 
    )
    owner = await make_user("owner@example.com")
    ws = await make_workspace("testws", user_headers=owner["headers"])
    workspace_id = ws["id"]
    res = await client.post(
        f"/workspaces/{workspace_id}/conversations",
        json={"title": "testconvo"},
        headers=owner["headers"],
    )
    assert res.status_code == 201
    conversation_id = res.json()["id"]
    upload_res = await upload_file(
        filename="test.txt",
        content=b"HELLO WORLD ",
        workspace_id=workspace_id,
        headers=owner["headers"],
    )
    assert upload_res.status_code == 202


    events = await post_question(
        client=client,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        question="hello world???",
        headers=owner["headers"],
    )


    streamed_text = "".join(json.loads(event[1])["text"] for event in events if event[0] == "token")
    assert "[99]" in streamed_text

    event_names = [event[0] for event in events]
    assert "done" in event_names
    assert "citations" not in event_names
    assert "token" in event_names

    assert "error" not in event_names






 
