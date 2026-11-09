from abc import ABC,abstractmethod
from app.schemas import LLMResponse

#LLM-Learning Language model like Gemini,Anthropic
#Client-piece of software that communicates with an extenal service
#LLMClient repesents a client that communicates with a LLM
class LLMClient(ABC):
    @abstractmethod
    async def generate(self,system:str,message:str)->LLMResponse:
        pass

#system is the set of instructions that the llm has to follow
#message is the user's question and the context(chunks) that tell the LLM what to answr
