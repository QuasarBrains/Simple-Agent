"""Native Anthropic Messages adapter with lossless content-block replay."""

from copy import deepcopy
import os

from anthropic import Anthropic

from llms.config import ProviderSettings
from llms.costs import Usage
from llms.llm import LLMError, Message, OutputLimitExceeded, native_content, tool_call


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, settings: ProviderSettings, client=None):
        self.settings = settings
        self.model = (
            os.environ.get("ANTHROPIC_MODEL") or settings.model or "claude-sonnet-5-5"
        )
        self.client = client or Anthropic(
            api_key=os.environ.get("ANTHROPIC_API_KEY")
            or (settings.api_key.get_secret_value() if settings.api_key else None),
            base_url=os.environ.get("ANTHROPIC_BASE_URL") or settings.base_url,
            timeout=settings.timeout_seconds,
            max_retries=0,
        )

    def build_request(
        self, messages, tools, system, text_only=False, max_output_tokens=None
    ):
        formatted = []
        instructions = [system]
        for message in messages:
            if message.role == "system":
                instructions.append(message.content or "")
                continue
            native = native_content(message, self.name, self.model)
            if native is not None:
                blocks, role = deepcopy(native), "assistant"
            elif message.role == "tool":
                blocks = [
                    {
                        "type": "tool_result",
                        "tool_use_id": message.tool_call_id,
                        "content": message.content or "",
                        "is_error": message.is_error,
                    }
                ]
                role = "user"
            elif message.role in {"user", "assistant"}:
                role = message.role
                blocks = (
                    [{"type": "text", "text": message.content}]
                    if message.content
                    else []
                )
                blocks.extend(
                    {
                        "type": "tool_use",
                        "id": call.id,
                        "name": call.name,
                        "input": deepcopy(call.arguments),
                    }
                    for call in message.tool_calls or []
                )
                if not blocks:
                    # Anthropic rejects empty text blocks; keep the role without inventing content.
                    continue
            else:
                raise LLMError(f"Invalid message role: {message.role}")
            if formatted and formatted[-1]["role"] == role:
                formatted[-1]["content"].extend(blocks)
            else:
                formatted.append({"role": role, "content": blocks})
        generation = self.settings.generation
        request = {
            "model": self.model,
            "system": "\n".join(instructions),
            "messages": formatted,
            "max_tokens": max_output_tokens or generation.max_output_tokens,
        }
        if generation.reasoning_effort:
            request["thinking"] = {"type": "adaptive"}
            request["output_config"] = {"effort": generation.reasoning_effort}
        if tools and not text_only:
            required = generation.tool_choice == "required"
            # Current models with this restriction reject forced tools regardless of thinking.
            unsupported = self.model.startswith(
                (
                    "claude-sonnet-5-5",
                    "claude-opus-5-5",
                    "claude-fable-5-1",
                    "claude-mythos-5-1",
                )
            )
            if required and (unsupported or not self.settings.supports_required_tools):
                raise LLMError(
                    "This Claude model does not support required tool choice; configure auto"
                )
            request["tools"] = [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": deepcopy(tool.parameters),
                }
                for tool in tools
            ]
            request["tool_choice"] = {
                "type": {"required": "any"}.get(
                    generation.tool_choice, generation.tool_choice
                ),
                "disable_parallel_tool_use": not generation.parallel_tool_calls,
            }
        return request

    def send(self, request):
        response = self.client.messages.create(**request)
        return response.model_dump(mode="json", exclude_none=True) | {
            "_request_id": getattr(response, "_request_id", None)
        }

    def usage(self, response):
        raw = response.get("usage")
        if not raw or "input_tokens" not in raw or "output_tokens" not in raw:
            return None
        read = raw.get("cache_read_input_tokens") or 0
        created = raw.get("cache_creation_input_tokens") or 0
        details = raw.get("cache_creation") or {}
        hour = details.get("ephemeral_1h_input_tokens") or 0
        five = details.get("ephemeral_5m_input_tokens", created - hour) or 0
        if five + hour != created:
            return None
        return Usage(
            raw["input_tokens"] + read + created,
            raw["output_tokens"],
            cached_input_tokens=read,
            cache_write_5m_tokens=five,
            cache_write_1h_tokens=hour,
            raw=raw,
        )

    def parse(self, response):
        if response.get("stop_reason") == "max_tokens":
            raise OutputLimitExceeded(
                "Anthropic response exhausted max_tokens; partial tool calls were not executed"
            )
        blocks = response.get("content", [])
        calls = [
            tool_call(b["id"], b["name"], b["input"])
            for b in blocks
            if b["type"] == "tool_use"
        ]
        text = "".join(b["text"] for b in blocks if b["type"] == "text")
        stop = response.get("stop_reason")
        status = {
            "end_turn": "completed",
            "stop_sequence": "completed",
            "tool_use": "completed",
            "max_tokens": "incomplete",
            "model_context_window_exceeded": "incomplete",
            "refusal": "blocked",
        }.get(stop, "failed")
        return Message(
            response.get("id"),
            text or None,
            "assistant",
            calls or None,
            native=deepcopy(blocks),
            status=status,
            provider_status=stop,
        )

    def close(self):
        self.client.close()
