from app.services.base_embedder import BaseEmbedder

class FailingEmbedder(BaseEmbedder):  # for tests
    async def embed_documents(self, texts: list[str], is_query: bool = False):
        raise RuntimeError(
            "OOPS"
        )  # this will mimic and embedder failure and should give "error" with no chunks


class WrongDimEmbedder(BaseEmbedder):  # for tests again
    async def embed_documents(self, texts: list[str], is_query: bool = False):
        return [[0.1] * 381 for _ in texts]
