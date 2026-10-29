"""Typed LLM policy embedded in the general application configuration."""

from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

Money = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class Generation(Settings):
    max_output_tokens: int = Field(default=4096, gt=0, strict=True)
    max_output_retries: int = Field(default=1, ge=0, le=3, strict=True)
    max_retry_output_tokens: int = Field(default=16384, gt=0, strict=True)
    max_estimated_input_tokens: int | None = Field(default=None, gt=0, strict=True)
    tool_choice: Literal["auto", "required", "none"] = "auto"
    parallel_tool_calls: bool = True
    reasoning_effort: str | None = None


class ProviderSettings(Settings):
    api_key: SecretStr | None = None
    model: str | None = Field(default=None, min_length=1)
    base_url: str | None = None
    timeout_seconds: float = Field(default=120, gt=0, allow_inf_nan=False)
    # Override when using a model/setting that rejects forced tool choice.
    supports_required_tools: bool = True
    supports_parallel_tools: bool = True
    generation: Generation = Field(default_factory=Generation)


class CostPolicy(Settings):
    currency: Literal["USD"] = "USD"
    request_budget: Money | None = None
    session_budget: Money | None = None
    task_budget: Money | None = None
    # A byte-based estimate is intentionally conservative, but not a billing guarantee.
    estimate_multiplier: float = Field(default=1.25, ge=1, allow_inf_nan=False)
    estimate_overhead_tokens: int = Field(default=1024, ge=0, strict=True)

    @property
    def enforced(self):
        return any(
            x is not None
            for x in (self.request_budget, self.session_budget, self.task_budget)
        )


class Price(Settings):
    provider: Literal["openai", "anthropic", "google"]
    model: str = Field(min_length=1)
    input_per_million: Money
    output_per_million: Money
    cached_input_per_million: Money | None = None
    cache_write_5m_per_million: Money | None = None
    cache_write_1h_per_million: Money | None = None
    source: str = Field(min_length=1)
    effective_date: str = Field(min_length=1)


class LLMConfig(Settings):
    provider_name: Literal["openai", "anthropic", "google"] = Field(
        default="openai", alias="provider"
    )
    generation: Generation = Field(default_factory=Generation)
    cost: CostPolicy = Field(default_factory=CostPolicy)
    providers: dict[str, ProviderSettings] = Field(default_factory=dict)
    pricing: list[Price] = Field(default_factory=list)
    display_max_chars: int | None = Field(default=None, gt=0, strict=True)

    @model_validator(mode="after")
    def unique_models(self):
        keys = [(p.provider, p.model) for p in self.pricing]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate provider/model pricing entries")
        if set(self.providers) - {"openai", "anthropic", "google"}:
            raise ValueError("Unknown provider in configuration")
        return self

    def provider(self, name: str) -> ProviderSettings:
        settings = self.providers.get(name)
        if settings is None:
            return ProviderSettings(generation=self.generation)
        generation = Generation.model_validate(
            self.generation.model_dump()
            | settings.generation.model_dump(exclude_unset=True)
        )
        return settings.model_copy(update={"generation": generation})


def load_config(path: str | Path | None = None) -> LLMConfig:
    """Compatibility entry point; application configuration now lives in config.py."""
    from config import load_config as load_app_config

    return load_app_config(path).llm
