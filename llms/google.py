"""Native Google Interactions adapter using application-owned transcript replay."""

from copy import deepcopy
import os

from google import genai
from google.genai import types

from llms.config import ProviderSettings
from llms.costs import Usage
from llms.llm import LLMError, Message, native_content, tool_call


class GoogleProvider:
    name = "google"

    def __init__(self, settings: ProviderSettings, client=None):
        self.settings = settings
        self.model = (
            os.environ.get("GEMINI_MODEL") or settings.model or "gemini-3.8-flash"
        )
        self.client = client or genai.Client(
            api_key=os.environ.get("GEMINI_API_KEY")
            or (settings.api_key.get_secret_value() if settings.api_key else None),
            http_options=types.HttpOptions(
                base_url=os.environ.get("GEMINI_BASE_URL") or settings.base_url,
                timeout=int(settings.timeout_seconds * 1000),
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )
        self.interactions = self.client.interactions
        # google-genai 2.33 clamps HttpRetryOptions.attempts to >= 1, then
        # Interactions interprets it as an *additional* retry count. Disable
        # retries on the resource configuration too; covered by a transport test.
        self.interactions.sdk_configuration.retry_config.strategy = "none"

    def build_request(
        self, messages, tools, system, text_only=False, max_output_tokens=None
    ):
        steps = []
        instructions = [system]
        call_names = {}
        for message in messages:
            for call in message.tool_calls or []:
                call_names[call.id] = call.name
            native = native_content(message, self.name, self.model)
            if native is not None:
                steps.extend(deepcopy(native))
            elif message.role == "system":
                instructions.append(message.content or "")
            elif message.role == "tool":
                steps.append(
                    {
                        "type": "function_result",
                        "call_id": message.tool_call_id,
                        "name": message.tool_name
                        or call_names.get(message.tool_call_id),
                        "result": message.content or "",
                        "is_error": message.is_error,
                    }
                )
            elif message.role in {"user", "assistant"}:
                if message.content is not None:
                    steps.append(
                        {
                            "type": "user_input"
                            if message.role == "user"
                            else "model_output",
                            "content": [{"type": "text", "text": message.content}],
                        }
                    )
                steps.extend(
                    {
                        "type": "function_call",
                        "id": call.id,
                        "name": call.name,
                        "arguments": deepcopy(call.arguments),
                    }
                    for call in message.tool_calls or []
                )
            else:
                raise LLMError(f"Invalid message role: {message.role}")
        generation = self.settings.generation
        config = {
            "max_output_tokens": max_output_tokens or generation.max_output_tokens
        }
        if generation.reasoning_effort:
            config["thinking_level"] = generation.reasoning_effort
        request = {
            "model": self.model,
            "input": steps,
            "system_instruction": "\n".join(instructions),
            "generation_config": config,
            "store": False,
        }
        if tools and not text_only:
            if not generation.parallel_tool_calls:
                raise LLMError(
                    "Google Interactions does not expose a single-call switch; enable parallel_tool_calls (execution remains sequential)"
                )
            if (
                generation.tool_choice == "required"
                and not self.settings.supports_required_tools
            ):
                raise LLMError(
                    "This model does not support required tool choice; configure auto"
                )
            config["tool_choice"] = {"required": "any"}.get(
                generation.tool_choice, generation.tool_choice
            )
            request["tools"] = [
                {
                    "type": "function",
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": deepcopy(tool.parameters),
                }
                for tool in tools
            ]
        return request

    def send(self, request):
        response = self.interactions.create(**request)
        return response.model_dump(mode="json", exclude_none=True)

    def usage(self, response):
        raw = response.get("usage")
        if (
            not raw
            or raw.get("total_input_tokens") is None
            or raw.get("total_output_tokens") is None
        ):
            return None
        input_tokens = raw["total_input_tokens"]
        output = raw["total_output_tokens"]
        thoughts = raw.get("total_thought_tokens") or 0
        total = raw.get("total_tokens")
        # Interactions reports thought tokens separately. Accept inclusive output too
        # when the total explicitly confirms it, rather than charging reasoning twice.
        if total == input_tokens + output and thoughts <= output:
            billed_output = output
        else:
            billed_output = output + thoughts
        if total is not None and total != input_tokens + billed_output:
            return None
        # Hosted tools are not enabled by this adapter; do not underprice unexpected use.
        if raw.get("total_tool_use_tokens") or raw.get("grounding_tool_count"):
            return None
        return Usage(
            input_tokens,
            billed_output,
            cached_input_tokens=raw.get("total_cached_tokens") or 0,
            reasoning_tokens=thoughts,
            raw=raw,
        )

    def parse(self, response):
        steps = response.get("steps", [])
        text, calls = [], []
        for step in steps:
            if step["type"] == "function_call":
                calls.append(tool_call(step["id"], step["name"], step["arguments"]))
            elif step["type"] == "model_output":
                for content in step.get("content", []):
                    if content["type"] != "text":
                        raise LLMError("Only text output is supported by this adapter")
                    text.append(content["text"])
            elif step["type"] != "thought":
                raise LLMError(f"Unsupported Google step: {step['type']}")
        stop = response.get("status", "failed")
        status = {
            "completed": "completed",
            "requires_action": "completed",
            "incomplete": "incomplete",
        }.get(stop, "failed")
        return Message(
            response.get("id"),
            "".join(text) or None,
            "assistant",
            calls or None,
            native=deepcopy(steps),
            status=status,
            provider_status=stop,
            metadata={"errors": response.get("errors", [])},
        )

    def close(self):
        self.client.close()
