from abc import ABC, abstractmethod

from app.schemas import LLMResponse,LLMStreamResult
from typing import AsyncIterator



# LLM-Learning Language model like Gemini,Anthropic
# Client-piece of software that communicates with an extenal service
# LLMClient repesents a client that communicates with a LLM
class LLMClient(ABC):
    @abstractmethod
    async def generate(self, system: str, message: str) -> LLMResponse:
        pass

    @abstractmethod
    async def stream(self,system:str,message:str)->AsyncIterator[str|LLMStreamResult]: #here, AsyncIterator[str] means the function asynchronously yields strings, one at a time
        pass


# system is the set of instructions that the llm has to follow
# message is the user's question and the context(chunks) that tell the LLM what to answr
