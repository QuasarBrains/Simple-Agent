from collections.abc import Callable, Mapping

from memory.service import MemoryService


def local_from_config(config: Mapping[str, str]) -> MemoryService:
    from embeddings.config import create_embedding_model
    from memory.sqlite import SQLiteMemoryService
    from storage.database import Database

    return SQLiteMemoryService(
        Database.from_config(config), create_embedding_model(config)
    )


def svs_from_config(config: Mapping[str, str]) -> MemoryService:
    from memory.legacy import VectorStoreMemoryService
    from memory.simple_vector_store import (
        query_simple_vector_store,
        add_simple_vector_store_record,
        on_svs_init,
    )
    from memory.vector_store import VectorStore

    store = VectorStore(
        "simple_vector_store",
        query_simple_vector_store,
        add_simple_vector_store_record,
        on_startup=lambda: on_svs_init(config),
    )
    return VectorStoreMemoryService(store)


MEMORY_FACTORIES: dict[str, Callable[[Mapping[str, str]], MemoryService]] = {
    "local": local_from_config,
    "simple_vector_store": svs_from_config,
}


def create_memory_service(config: Mapping[str, str]) -> MemoryService | None:
    choice = config.get("MEMORY_BACKEND")
    if choice is None or not choice.strip():
        choice = config.get("VECTOR_STORE_CHOICE") or "none"
    if choice == "none":
        return None
    if choice not in MEMORY_FACTORIES:
        raise ValueError(f"Unknown MEMORY_BACKEND: {choice}")
    namespace = config.get("MEMORY_NAMESPACE") or "default"
    if namespace != "default":
        raise ValueError("Memory currently supports only MEMORY_NAMESPACE=default")
    return MEMORY_FACTORIES[choice](config)
