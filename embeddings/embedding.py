"""Provider-neutral embedding contract and compatibility metadata."""

import hashlib
import json
import math
import struct
from dataclasses import asdict, dataclass
from typing import Protocol


class EmbeddingError(RuntimeError):
    pass


@dataclass(frozen=True)
class EmbeddingProfile:
    provider: str
    model: str
    dimensions: int
    revision: str | None = None
    options_json: str = "{}"
    document_task: str = "default"
    query_task: str = "default"
    input_format: str = "plain-v1"
    normalization: str = "provider"
    adapter_version: str = "1"

    def __post_init__(self):
        if (
            not self.provider
            or not self.model
            or isinstance(self.dimensions, bool)
            or not isinstance(self.dimensions, int)
            or self.dimensions <= 0
        ):
            raise ValueError(
                "Embedding profiles require provider, model and positive dimensions"
            )
        options = json.loads(self.options_json)
        if not isinstance(options, dict):
            raise ValueError("Embedding options must be a JSON object")
        object.__setattr__(
            self, "options_json", json.dumps(options, sort_keys=True, allow_nan=False)
        )

    @property
    def fingerprint(self) -> str:
        values = asdict(self)
        values.pop("adapter_version")  # Provenance, not embedding-space identity.
        return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


class EmbeddingModel(Protocol):
    profile: EmbeddingProfile

    def embed_document(self, text: str) -> list[float]: ...

    def embed_query(self, text: str) -> list[float]: ...

    def close(self) -> None: ...


def validate_vector(vector: list[float], dimensions: int) -> list[float]:
    try:
        # VSS stores float32, so validate the representation that will be indexed.
        values = [
            struct.unpack("f", struct.pack("f", float(value)))[0] for value in vector
        ]
        if (
            len(values) != dimensions
            or not all(
                math.isfinite(value) and abs(value) <= 3.4028235e38 for value in values
            )
            or not any(values)
        ):
            raise ValueError("invalid vector")
    except (TypeError, ValueError, OverflowError, struct.error) as error:
        raise EmbeddingError(
            f"Expected a finite, nonzero {dimensions}-dimensional vector"
        ) from error
    return values
