import asyncio

from docs_mcp.config import settings


class LocalEmbeddingProvider:
    def __init__(self) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(settings.local_embedding_model)

    @property
    def name(self) -> str:
        return f"local:{settings.local_embedding_model}"

    @property
    def dimensions(self) -> int:
        return int(self._model.get_sentence_embedding_dimension())

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return await asyncio.to_thread(
            lambda: self._model.encode(
                texts, normalize_embeddings=True, show_progress_bar=False
            ).tolist()
        )
