from dataclasses import asdict, dataclass, field
import json
import math
import time
from typing import Any, Callable, Protocol
from uuid import uuid4

from llms.config import LLMConfig, ProviderSettings, load_config
from llms.costs import CostTracker, Usage
from tools.index import Tool, ToolCall


class LLMError(RuntimeError):
    """A provider request, response, or continuation could not be processed."""


class OutputLimitExceeded(LLMError):
    """Provider explicitly confirmed that generation ended at its output limit."""


def response_diagnostics(response: dict, output_limit: int) -> dict:
    """Metadata only: keep failure evidence without logging arguments or reasoning blobs."""
    items = response.get("output", response.get("content", response.get("steps", [])))
    return {
        "response_status": response.get("status"),
        "stop_reason": response.get("stop_reason"),
        "incomplete_details": response.get("incomplete_details"),
        "provider_error": response.get("error"),
        "provider_errors": response.get("errors"),
        "max_output_tokens": output_limit,
        "output_items": [
            {
                key: item[key]
                for key in ("type", "id", "call_id", "name", "status")
                if key in item
            }
            | (
                {"argument_chars": len(item["arguments"])}
                if isinstance(item.get("arguments"), str)
                else {}
            )
            for item in items
        ],
    }


@dataclass
class Message:
    id: str | None
    content: str | None
    role: str
    tool_calls: list[ToolCall] | None
    tool_call_id: str | None = None
    tool_name: str | None = None
    is_error: bool = False
    provider: str | None = None
    model: str | None = None
    native: list[dict[str, Any]] | None = None
    status: str = "completed"
    provider_status: str | None = None
    request_id: str | None = None
    usage: Usage | None = None
    cost: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json(self):
        return asdict(self)


def native_content(message: Message, provider: str, model: str):
    if message.native is not None:
        if (message.provider, message.model) != (provider, model):
            raise LLMError(
                "Native continuation belongs to a different provider/model; runtime switching is not supported"
            )
        return message.native
    return None


def tool_call(id: str, name: str, arguments: Any) -> ToolCall:
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except (TypeError, ValueError) as exc:
            raise LLMError(f"Invalid JSON arguments for {name}") from exc
    if (
        not isinstance(id, str)
        or not id
        or not isinstance(name, str)
        or not name
        or not isinstance(arguments, dict)
    ):
        raise LLMError("Tool call requires an ID, name, and object arguments")
    return ToolCall(id=id, name=name, arguments=arguments)


def validate_history(messages: list[Message]):
    pending = set()
    seen = set()
    for message in messages:
        if message.role == "tool":
            if message.tool_call_id not in pending:
                raise LLMError("Tool result does not match a pending tool call")
            pending.remove(message.tool_call_id)
        else:
            if pending:
                raise LLMError(
                    "All tool results must immediately follow their assistant turn"
                )
            if message.role not in {"user", "assistant", "system"}:
                raise LLMError(f"Invalid message role: {message.role}")
            if message.tool_calls and message.role != "assistant":
                raise LLMError("Only assistant messages may contain tool calls")
            for call in message.tool_calls or []:
                if call.id in seen:
                    raise LLMError("Duplicate tool-call ID")
                tool_call(call.id, call.name, call.arguments)
                pending.add(call.id)
                seen.add(call.id)
    if pending:
        raise LLMError("Tool results are missing from conversation history")


class Provider(Protocol):
    name: str
    model: str
    settings: ProviderSettings

    def build_request(
        self,
        messages: list[Message],
        tools: list[Tool],
        system: str,
        text_only: bool,
        max_output_tokens: int | None = None,
    ) -> dict: ...
    def send(self, request: dict) -> dict: ...
    def usage(self, response: dict) -> Usage | None: ...
    def parse(self, response: dict) -> Message: ...
    def close(self) -> None: ...


class LLM:
    """Small application-facing interface with centralized admission and accounting."""

    def __init__(
        self, provider: Provider, config: LLMConfig, tracker: CostTracker | None = None
    ):
        self.provider = provider
        self.config = config
        self.tracker = tracker or CostTracker(config.cost, config.pricing)
        self.name = provider.name
        self.model_name = provider.model
        self.system_prompt = ""
        self.on_usage: Callable[[dict], None] | None = None
        self.on_event: Callable[[str, dict], None] | None = None

    def startup(self, system_prompt: str):
        self.system_prompt = system_prompt

    def close(self):
        self.provider.close()

    def get_response(
        self, messages: list[Message], tools: list[Tool], task_id: str | None = None
    ) -> Message:
        return self._request(messages, tools, self.system_prompt, False, task_id)

    def _request(self, messages, tools, system, text_only, task_id=None):
        validate_history(messages)
        generation = self.provider.settings.generation
        limit = generation.max_output_tokens
        group_id = str(uuid4())
        for attempt in range(1, generation.max_output_retries + 2):
            next_limit = min(limit * 2, generation.max_retry_output_tokens)
            retry_allowed = (
                attempt <= generation.max_output_retries and next_limit > limit
            )
            try:
                return self._attempt(
                    messages,
                    tools,
                    system,
                    text_only,
                    task_id,
                    limit,
                    group_id,
                    attempt,
                    retry_allowed,
                )
            except OutputLimitExceeded as error:
                if not retry_allowed:
                    raise LLMError(
                        f"{self.name} reached the {limit}-token output limit "
                        f"after {attempt} attempt(s); partial calls were not executed. "
                        "Increase [llm.generation].max_output_tokens or the provider-specific "
                        "generation limit. See usage.jsonl and events.jsonl for details."
                    ) from error
                if self.on_event:
                    self.on_event(
                        "llm.retry",
                        {
                            "request_group_id": group_id,
                            "attempt": attempt + 1,
                            "max_output_tokens": next_limit,
                            "reason": "output_limit",
                        },
                    )
                limit = next_limit

    def _attempt(
        self,
        messages,
        tools,
        system,
        text_only,
        task_id,
        output_limit,
        group_id,
        attempt,
        retry_allowed,
    ):
        request = self.provider.build_request(
            messages, tools, system, text_only, max_output_tokens=output_limit
        )
        # Full serialized request includes instructions, schemas and native replay data.
        byte_count = len(json.dumps(request, ensure_ascii=False).encode("utf-8"))
        estimate = (
            math.ceil(byte_count * self.config.cost.estimate_multiplier)
            + self.config.cost.estimate_overhead_tokens
        )
        generation = self.provider.settings.generation
        if (
            generation.max_estimated_input_tokens
            and estimate > generation.max_estimated_input_tokens
        ):
            raise LLMError(
                f"Estimated input ({estimate} tokens) exceeds configured context budget"
            )
        record = self.tracker.reserve(
            self.provider.name,
            self.model_name,
            estimate,
            output_limit,
            task_id or "__shared__",
        )
        record.request_group_id = group_id
        record.attempt = attempt
        response = None
        reconciled = False
        started = time.monotonic()
        try:
            if self.on_event:
                self.on_event(
                    "llm.request",
                    {
                        "id": record.id,
                        "request_group_id": group_id,
                        "attempt": attempt,
                        "provider": self.name,
                        "model": self.model_name,
                        "max_output_tokens": output_limit,
                        "message_count": len(messages),
                        "tool_count": len(tools),
                        "task_id": record.task_id,
                    },
                )
            response = self.provider.send(request)
            record.diagnostics = response_diagnostics(response, output_limit)
            record.raw_usage = response.get("usage")
            record.request_id = response.get("_request_id")
            model = response.get("model") or self.model_name
            usage = self.provider.usage(response)
            self.tracker.reconcile(record, usage, model, response.get("id"))
            reconciled = True
            message = self.provider.parse(response)
            message.provider = self.provider.name
            # Native replay is scoped to the requested configuration, not a resolved alias.
            message.model = self.model_name
            message.metadata["resolved_model"] = model
            message.request_id = response.get("_request_id")
            message.usage = usage
            message.cost = str(record.cost) if record.cost is not None else None
            if message.status in {"incomplete", "blocked", "failed"}:
                raise LLMError(
                    f"{self.name} response {message.status}: {message.provider_status}"
                )
            if not message.content and not message.tool_calls:
                raise LLMError(f"{self.name} returned no text or tool calls")
            seen_ids = {
                call.id for prior in messages for call in prior.tool_calls or []
            }
            for call in message.tool_calls or []:
                if call.id in seen_ids:
                    raise LLMError("Duplicate tool-call ID in provider response")
                seen_ids.add(call.id)
            if text_only and message.tool_calls:
                raise LLMError("Provider returned tool calls for a text-only request")
            record.outcome = "success"
            return message
        except Exception as exc:
            record.outcome = (
                "retrying"
                if isinstance(exc, OutputLimitExceeded) and retry_allowed
                else "error"
            )
            record.diagnostics["exception_type"] = type(exc).__name__
            if not reconciled:
                self.tracker.reconcile(
                    record,
                    None,
                    self.model_name,
                    response.get("id") if response else None,
                    str(exc),
                )
            else:
                record.error = str(exc)
            if isinstance(exc, LLMError):
                raise
            raise LLMError(f"{self.name} request failed: {exc}") from exc
        finally:
            record.duration_ms = round((time.monotonic() - started) * 1000)
            if self.on_usage:
                # JSON-safe events; monetary values must not be rounded through floats.
                event = json.loads(
                    json.dumps(self.tracker.record_json(record), default=str)
                )
                self.on_usage(event)

    def get_text_response(self, message: str, system_prompt: str) -> str:
        response = self._request(
            [Message(None, message, "user", None)], [], system_prompt, True
        )
        return response.content or ""

    def append_to_system_prompt(self, message: str):
        self.system_prompt += f"\n{message}"
        return self.system_prompt


def create_llm(
    provider: str, config: LLMConfig | None = None, tracker: CostTracker | None = None
) -> LLM:
    from importlib import import_module

    classes = {
        "openai": "OpenAIProvider",
        "anthropic": "AnthropicProvider",
        "google": "GoogleProvider",
    }
    if provider not in classes:
        raise ValueError(f"Unknown LLM provider: {provider}")
    config = config or load_config()
    factory = getattr(import_module(f"llms.{provider}"), classes[provider])
    return LLM(factory(config.provider(provider)), config, tracker)
