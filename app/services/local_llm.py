import httpx2
from google import genai
from google.genai import errors, types

from app.config import settings
from app.exceptions import LLMTimeout, LLMUnavailable
from app.schemas import LLMResponse
from app.services.base_llm import LLMClient


# Since both classes below have the same return type the application can use either without caring which one it is...
class GeminiLLM(LLMClient):
    def __init__(self, model: str = settings.llm_model):
        self.model = model
        # .aio for asynchronous client, since we are using async def generate function the sync(blocking code) for interactions has to be awaited so...
        # remember timout field in expects inputs in milliseconds so we multiplied by 10^3 and also attemps=retries+1
        # HTTP is the protocol used for communication between client and Gemini,the protocol this application uses to send requests to Gemini and receive responses too
        self.client = genai.Client(
            api_key=settings.api_key.get_secret_value(),  # Since, api_key is a pydantic SecretStr we have to use get_secret_value() to extract it's value here
            http_options=types.HttpOptions(
                timeout=settings.llm_timeout_seconds * 1000,
                retry_options=types.HttpRetryOptions(attempts=settings.llm_max_retries + 1),
            ),
        ).aio

    async def generate(self, system: str, message: str) -> LLMResponse:
        try:
            interaction = await self.client.interactions.create(
                model=self.model,
                system_instruction=system,
                input=message,
                generation_config={"max_output_tokens": settings.llm_max_tokens},
            )
            return LLMResponse(
                generated_text=interaction.output_text,
                input_token_usage=interaction.usage.total_input_tokens,
                output_token_usage=interaction.usage.total_output_tokens,
            )
        except httpx2.TimeoutException as e:
            raise LLMTimeout("LLM took too long to respond") from e
        except errors.APIError as e:  # API-level error,gemini received request but responded with an error,maybe too many requests , gemini service unavailable
            if e.code == 401 or e.code == 403:
                raise  # re-raises the original exception,unauthenticated
            raise LLMUnavailable("LLM responded with an error") from e
        except httpx2.HTTPError as e:  # HTTP transport-level error, problem while communicating over HTTP, connection error or network-related errors
            raise LLMUnavailable("HTTP transport communication error") from e


class FakeLLM(LLMClient):
    def __init__(self, generated_text: str | None = None):  # this is the constructor
        self.generated_text = generated_text

    async def generate(self, system: str, message: str) -> LLMResponse:
        return LLMResponse(
            generated_text=self.generated_text, input_token_usage=123, output_token_usage=321
        )
