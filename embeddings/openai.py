import json
import os

from embeddings.embedding import EmbeddingError, EmbeddingProfile, validate_vector


class OpenAIEmbeddingModel:
    """OpenAI adapter; client construction performs no network request."""

    def __init__(
        self,
        model: str = "text-embedding-3-small",
        dimensions: int | None = None,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
    ):
        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise EmbeddingError("Set OPENAI_API_KEY to use OpenAI memory embeddings")
        defaults = {
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
            "text-embedding-ada-002": 1536,
        }
        size = dimensions if dimensions is not None else defaults.get(model)
        if size is None:
            raise EmbeddingError(
                "Set EMBEDDING_DIMENSIONS for an unknown embedding model"
            )
        self.base_url = base_url or os.environ.get("OPENAI_BASE_URL") or None
        self.profile = EmbeddingProfile(
            provider="openai",
            model=model,
            dimensions=size,
            options_json=json.dumps({"base_url": self.base_url}),
        )
        self._api_key = key
        self._client = None
        self.request_dimensions = dimensions

    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
                api_key=self._api_key, base_url=self.base_url, timeout=30, max_retries=2
            )
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def embed_document(self, text: str) -> list[float]:
        try:
            kwargs = {"model": self.profile.model, "input": text}
            if self.request_dimensions is not None:
                kwargs["dimensions"] = self.request_dimensions
            response = self.client.embeddings.create(**kwargs)
            return validate_vector(response.data[0].embedding, self.profile.dimensions)
        except Exception as error:
            raise EmbeddingError(f"OpenAI embedding request failed: {error}") from error

    def embed_query(self, text: str) -> list[float]:
        return self.embed_document(text)
