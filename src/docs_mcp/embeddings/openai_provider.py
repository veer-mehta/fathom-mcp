from openai import AsyncOpenAI

from docs_mcp.config import settings

_MODEL_DIMENSIONS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


class OpenAIEmbeddingProvider:
    def __init__(self) -> None:
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        self._model = settings.openai_embedding_model

    @property
    def name(self) -> str:
        return f"openai:{self._model}"

    @property
    def dimensions(self) -> int:
        return _MODEL_DIMENSIONS.get(self._model, 1536)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        response = await self._client.embeddings.create(input=texts, model=self._model)
        return [item.embedding for item in response.data]
