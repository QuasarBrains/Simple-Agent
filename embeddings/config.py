from collections.abc import Callable, Mapping

from embeddings.embedding import EmbeddingModel


def openai_from_config(config: Mapping[str, str]) -> EmbeddingModel:
    from embeddings.openai import OpenAIEmbeddingModel

    dimensions = config.get("EMBEDDING_DIMENSIONS")
    return OpenAIEmbeddingModel(
        model=config.get("EMBEDDING_MODEL") or "text-embedding-3-small",
        dimensions=int(dimensions) if dimensions else None,
        api_key=config.get("OPENAI_API_KEY"),
        base_url=config.get("OPENAI_BASE_URL"),
    )


EMBEDDING_FACTORIES: dict[str, Callable[[Mapping[str, str]], EmbeddingModel]] = {
    "openai": openai_from_config,
}


def create_embedding_model(config: Mapping[str, str]) -> EmbeddingModel:
    provider = config.get("EMBEDDING_PROVIDER") or "openai"
    if provider not in EMBEDDING_FACTORIES:
        raise ValueError(f"Unknown EMBEDDING_PROVIDER: {provider}")
    return EMBEDDING_FACTORIES[provider](config)
