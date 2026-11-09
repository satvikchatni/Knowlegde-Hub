import pytest
from app.services.prompt import llm_response_parse
from app.schemas import LLMAnswer
from app.exceptions import InvalidLLMResponse

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