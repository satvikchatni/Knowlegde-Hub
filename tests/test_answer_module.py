import pytest
from app.services.prompt import llm_response_parse,filter_citations
from app.schemas import LLMAnswer,SearchOut
from app.exceptions import InvalidLLMResponse
import uuid

response='{"answer":"I am really hungry","cited_ids":["123","456"]}'

def test_parsing_answer():
    res=llm_response_parse(response=response)
    assert res.answer=="I am really hungry"
    assert "123" in res.cited_ids 
    assert "456" in res.cited_ids
    assert isinstance(res,LLMAnswer)

#use """ ... """ to represent multi-line strings
response_with_md_fences="""```json 
{"answer":"I am really hungry","cited_ids":["123","456"]} 
``` """

def test_parsing_answer_md_fences():
    res=llm_response_parse(response=response_with_md_fences)
    assert res.answer=="I am really hungry"
    assert "123" in res.cited_ids 
    assert "456" in res.cited_ids
    assert isinstance(res,LLMAnswer)

invalid_response='{"answer":"missing }","cited_ids":["123","345"] '


def test_parsing_invalid_ans():
    with pytest.raises(InvalidLLMResponse):
        llm_response_parse(response=invalid_response)

response_wrong_schema='{"answer":"I am really hungry","cited_ids":"123"}'

def test_parsing_ans_wrong_schema():
    with pytest.raises(InvalidLLMResponse):
        llm_response_parse(response=response_wrong_schema)


response_empty_answer='{"answer":"","cited_ids":"123"}'

def test_parsing_empty_ans():
    with pytest.raises(InvalidLLMResponse):
        llm_response_parse(response=response_empty_answer)


chunk1=SearchOut(
    chunk_id=uuid.UUID(int=101),
    document_id=uuid.UUID(int=1),
    filename="testf1.txt",
    page_number=1,
    position=1,
    text="Today is my Birthday",
    score=0.75,
)
chunk2=SearchOut(
    chunk_id=uuid.UUID(int=102), #101 isnt the uuid , 0000000-00000-0000-00065 is
    document_id=uuid.UUID(int=2),
    filename="testf2.txt",
    page_number=2,
    position=2,
    text="Happy birthday Rishabh",
    score=0.5,
)
chunk3=SearchOut(
    chunk_id=uuid.UUID(int=103),
    document_id=uuid.UUID(int=3),
    filename="testf3.txt",
    page_number=3,
    position=3,
    text="hm",
    score=0.59,
)


def test_filter_citations():
    valid_ids=filter_citations(cited_ids=[str(chunk1.chunk_id),str(chunk2.chunk_id),"999",str(chunk1.chunk_id),str(chunk2.chunk_id)],chunks=[chunk1,chunk2,chunk3])
    assert valid_ids==[str(chunk1.chunk_id),str(chunk2.chunk_id)]

def test_filter_citations_empty_cited_ids():
    valid_ids=filter_citations(cited_ids=[],chunks=[chunk1,chunk2,chunk3])
    assert valid_ids==[]