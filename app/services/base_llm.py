from abc import ABC,abstractmethod


#LLM-Learning Language model like Gemini,Anthropic
#Client-piece of software that communicates with an extenal service
#LLMClient repesents a client that communicates with a LLM
class LLMClient(ABC):
    @abstractmethod
    async def generate(system:str,message:str):
        pass

#system is the set of instructions that the llm has to follow
#message is what action the llm should perform ,the user's question and the context(chunks)
