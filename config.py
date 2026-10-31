"""Single-file application configuration, with optional environment compatibility."""

from collections.abc import Mapping
from pathlib import Path
import os
import tomllib

from dotenv import dotenv_values
from pydantic import Field, PrivateAttr, ValidationError

from llms.config import LLMConfig, Settings


class ConfigurationError(ValueError):
    pass


class AppSettings(Settings):
    log_directory: str = Field(default="simple-agent-logs", min_length=1)
    verbose: bool = False
    silence_actions: bool = False


class MemorySettings(Settings):
    backend: str = "none"
    database_path: str = "datastore/simple-agent.sqlite3"
    namespace: str = "default"
    recall_limit: int = Field(default=3, ge=1, le=100)
    context_token_budget: int = Field(default=1000, gt=0)
    embedding_provider: str = "openai"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int | None = Field(default=None, gt=0)
    simple_vector_store_url: str = ""
    simple_vector_store_directory: str = ""
    simple_vector_store_name: str = "simple-agent-memory"


class Config(Settings):
    app: AppSettings = Field(default_factory=AppSettings)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    memory: MemorySettings = Field(default_factory=MemorySettings)
    _source: Path | None = PrivateAttr(default=None)
    _legacy_settings: tuple[str, ...] = PrivateAttr(default=())

    @property
    def source(self):
        return self._source

    @property
    def legacy_settings(self):
        return self._legacy_settings

    def memory_options(self) -> dict[str, str]:
        """Adapt typed settings to the existing memory/embedding factory contract."""
        options = {
            env: str(getattr(self.memory, field))
            for env, field in MEMORY_ENV.items()
            if getattr(self.memory, field) is not None
        }
        openai = self.llm.provider("openai")
        if openai.api_key:
            options["OPENAI_API_KEY"] = openai.api_key.get_secret_value()
        if openai.base_url:
            options["OPENAI_BASE_URL"] = openai.base_url
        return options


MEMORY_ENV = {
    "MEMORY_BACKEND": "backend",
    "DATABASE_PATH": "database_path",
    "MEMORY_NAMESPACE": "namespace",
    "MEMORY_RECALL_LIMIT": "recall_limit",
    "MEMORY_CONTEXT_TOKEN_BUDGET": "context_token_budget",
    "EMBEDDING_PROVIDER": "embedding_provider",
    "EMBEDDING_MODEL": "embedding_model",
    "EMBEDDING_DIMENSIONS": "embedding_dimensions",
    "SIMPLE_VECTOR_STORE_URL": "simple_vector_store_url",
    "SIMPLE_VECTOR_STORE_DIRECTORY": "simple_vector_store_directory",
    "SIMPLE_VECTOR_STORE_NAME": "simple_vector_store_name",
}

ENV_OPTIONS = {
    "MODEL_CHOICE": ("llm", "provider"),
    "LOG_DIRECTORY": ("app", "log_directory"),
    **{env: ("memory", field) for env, field in MEMORY_ENV.items()},
    **{
        f"{prefix}_{suffix}": ("llm", "providers", provider, field)
        for prefix, provider in [
            ("OPENAI", "openai"),
            ("ANTHROPIC", "anthropic"),
            ("GEMINI", "google"),
        ]
        for suffix, field in [
            ("API_KEY", "api_key"),
            ("MODEL", "model"),
            ("BASE_URL", "base_url"),
        ]
    },
}


def _assign(data: dict, keys: tuple[str, ...], value, overwrite: bool):
    for key in keys[:-1]:
        data = data.setdefault(key, {})
    if overwrite or data.get(keys[-1]) in (None, ""):
        data[keys[-1]] = value
        return True
    return False


def load_config(
    path: str | Path | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    env_file: str | Path | None = ".env",
) -> Config:
    """Explicit environment > TOML > legacy .env > defaults. Never mutate os.environ."""
    environ = os.environ if environ is None else environ
    fallback = dotenv_values(env_file) if env_file and Path(env_file).exists() else {}
    explicit = path or environ.get("CONFIG_FILE") or fallback.get("CONFIG_FILE")
    legacy_path = environ.get("LLM_CONFIG") or fallback.get("LLM_CONFIG")
    if explicit:
        target = Path(explicit)
    elif Path("config.toml").exists():
        target = Path("config.toml")
    elif legacy_path:
        target = Path(legacy_path)
    elif Path("llm-config.toml").exists():
        target = Path("llm-config.toml")
    else:
        target = None
    notes = []
    data = {}
    if target:
        try:
            with target.open("rb") as handle:
                data = tomllib.load(handle)
        except (OSError, tomllib.TOMLDecodeError) as error:
            raise ConfigurationError(
                f"Cannot load {target}: {error}. Start with config.example.toml."
            ) from None
        if set(data) & {
            "generation",
            "cost",
            "providers",
            "pricing",
            "display_max_chars",
        }:
            data = {"llm": data}
            notes.append("llm-config.toml")
    try:
        for values, overwrite in [(fallback, False), (environ, True)]:
            for name, keys in ENV_OPTIONS.items():
                value = values.get(name)
                if value:
                    _assign(data, keys, value, overwrite)
            if values.get("VECTOR_STORE_CHOICE") and not values.get("MEMORY_BACKEND"):
                _assign(
                    data,
                    ("memory", "backend"),
                    values["VECTOR_STORE_CHOICE"],
                    overwrite,
                )
        # Deprecated limits only fill TOML gaps; process environment beats .env.
        legacy_values = dict(fallback) | dict(environ)
        for name, keys in [
            ("MAX_TOKENS", ("llm", "generation", "max_output_tokens")),
            ("MAX_MESSAGE_LENGTH", ("llm", "display_max_chars")),
        ]:
            value = legacy_values.get(name)
            if value:
                section = data
                for key in keys[:-1]:
                    section = section.setdefault(key, {})
                if keys[-1] not in section:
                    section[keys[-1]] = int(value)
                    notes.append(name)
        config = Config.model_validate(data)
    except ValidationError as error:
        # Pydantic's default error strings can include raw credential-bearing input.
        details = "; ".join(
            f"{'.'.join(map(str, e['loc']))}: {e['msg']}"
            for e in error.errors(include_input=False, include_url=False)
        )
        raise ConfigurationError(f"Invalid configuration: {details}") from None
    except (TypeError, ValueError, AttributeError):
        raise ConfigurationError(
            "Invalid configuration value or table; check config.example.toml"
        ) from None
    config._source = target
    config._legacy_settings = tuple(dict.fromkeys(notes))
    return config
