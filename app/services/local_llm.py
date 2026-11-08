from base_llm import LLMClient
from app.schemas import LLMResponse
from google import genai
from app.config import settings
from google.genai import types

#Since both classes below have the same return type the application can use either without caring which one it is...
class GeminiLLM(LLMClient):
    def __init__(self,model:str=settings.llm_model):
        self.model=model
        #.aio for asynchronous client, since we are using async def generate function the sync(blocking code) for interactions has to be awaited so...
        #remember timout field in expects inputs in milliseconds so we multiplied by 10^3 and also attemps=retries+1
        #HTTP is the protocol used for communication between client and Gemini,the protocol this application uses to send requests to Gemini and receive responses too
        self.client=genai.Client(api_key=settings.api_key.get_secret_value(),#Since, api_key is a pydantic SecretStr we have to use get_secret_value() to extract it's value here
                                 http_options=types.HttpOptions(timeout=settings.llm_timeout_seconds*1000,
                                retry_options=types.HttpRetryOptions(attempts=settings.llm_max_retries+1))).aio 
    async def generate(self,system:str,message:str)->LLMResponse:
        interaction= await self.client.interactions.create(
            model=self.model,
            system_instruction=system,
            input=message
        )
        return LLMResponse(generated_text=interaction.output_text,input_token_usage=interaction.usage.total_input_tokens,output_token_usage=interaction.usage.total_output_tokens)


class FakeLLM(LLMClient):
    def __init__(self):
        pass
    async def generate(self,system:str,message:str)->LLMResponse:
        return LLMResponse(generated_text="This project will be the end of me",input_token_usage=123,output_token_usage=321)