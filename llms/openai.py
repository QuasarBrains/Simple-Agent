"""Native OpenAI Responses adapter. Tool execution stays in the agent."""

import json
import os
from copy import deepcopy

from openai import OpenAI

from llms.config import ProviderSettings
from llms.costs import Usage
from llms.llm import LLMError, Message, OutputLimitExceeded, native_content, tool_call
from tools.names import decode_tool_name, encode_tool_name


class OpenAIProvider:
    name = "openai"

    def __init__(self, settings: ProviderSettings, client=None):
        self.settings = settings
        self.model = os.environ.get("OPENAI_MODEL") or settings.model or "gpt-4o-mini"
        self.client = client or OpenAI(
            api_key=os.environ.get("OPENAI_API_KEY")
            or (settings.api_key.get_secret_value() if settings.api_key else None),
            base_url=os.environ.get("OPENAI_BASE_URL") or settings.base_url,
            timeout=settings.timeout_seconds,
            max_retries=0,
        )

    def build_request(
        self, messages, tools, system, text_only=False, max_output_tokens=None
    ):
        items = []
        for message in messages:
            native = native_content(message, self.name, self.model)
            if native is not None:
                items.extend(deepcopy(native))
            elif message.role == "tool":
                items.append(
                    {
                        "type": "function_call_output",
                        "call_id": message.tool_call_id,
                        "output": message.content or "",
                    }
                )
            elif message.role in {"user", "assistant", "system"}:
                if message.content is not None:
                    items.append({"role": message.role, "content": message.content})
                for call in message.tool_calls or []:
                    items.append(
                        {
                            "type": "function_call",
                            "call_id": call.id,
                            "name": encode_tool_name(call.name),
                            "arguments": json.dumps(call.arguments),
                        }
                    )
            else:
                raise LLMError(f"Invalid message role: {message.role}")
        generation = self.settings.generation
        request = {
            "model": self.model,
            "instructions": system,
            "input": items,
            "max_output_tokens": max_output_tokens or generation.max_output_tokens,
            "store": False,
            "include": ["reasoning.encrypted_content"],
        }
        if generation.reasoning_effort:
            request["reasoning"] = {"effort": generation.reasoning_effort}
        if tools and not text_only:
            if (
                generation.tool_choice == "required"
                and not self.settings.supports_required_tools
            ):
                raise LLMError(
                    "This model does not support required tool choice; configure auto"
                )
            if (
                not generation.parallel_tool_calls
                and not self.settings.supports_parallel_tools
            ):
                raise LLMError("This model cannot enforce single-call generation")
            request["tools"] = [
                {
                    "type": "function",
                    "name": encode_tool_name(tool.name),
                    "description": tool.description,
                    "parameters": deepcopy(tool.parameters),
                    "strict": False,
                }
                for tool in tools
            ]
            request["tool_choice"] = generation.tool_choice
            if self.settings.supports_parallel_tools:
                request["parallel_tool_calls"] = generation.parallel_tool_calls
        return request

    def send(self, request):
        response = self.client.responses.create(**request)
        return response.model_dump(mode="json", exclude_none=True) | {
            "_request_id": getattr(response, "_request_id", None)
        }

    def usage(self, response):
        raw = response.get("usage")
        if not raw or "input_tokens" not in raw or "output_tokens" not in raw:
            return None
        return Usage(
            raw["input_tokens"],
            raw["output_tokens"],
            cached_input_tokens=raw.get("input_tokens_details", {}).get(
                "cached_tokens", 0
            ),
            reasoning_tokens=raw.get("output_tokens_details", {}).get(
                "reasoning_tokens", 0
            ),
            raw=raw,
        )

    def parse(self, response):
        status = response.get("status", "failed")
        if status == "incomplete":
            reason = (response.get("incomplete_details") or {}).get(
                "reason", "unspecified"
            )
            if reason == "max_output_tokens":
                raise OutputLimitExceeded(
                    "OpenAI response exhausted max_output_tokens; partial tool calls were not executed"
                )
            raise LLMError(
                f"OpenAI response incomplete (reason={reason}); partial tool calls were not executed"
            )
        if status != "completed":
            raise LLMError(f"OpenAI response ended with status={status}")
        output = response.get("output", [])
        text, calls, refusals = [], [], []
        for item in output:
            if item["type"] == "function_call":
                if item.get("status") not in {None, "completed"}:
                    raise LLMError(
                        f"OpenAI function call {item.get('name', '<unnamed>')} "
                        f"(call_id={item.get('call_id')}) has status={item.get('status')} "
                        f"in response {response.get('id')} (response status={status}); not executed"
                    )
                calls.append(
                    tool_call(
                        item["call_id"],
                        decode_tool_name(item["name"]),
                        item["arguments"],
                    )
                )
            elif item["type"] == "message":
                for block in item.get("content", []):
                    if block["type"] == "output_text":
                        text.append(block["text"])
                    elif block["type"] == "refusal":
                        refusals.append(block.get("refusal", "Refused"))
            elif item["type"] != "reasoning":
                raise LLMError(f"Unsupported OpenAI output item: {item['type']}")
        status = response.get("status", "failed")
        normalized = (
            "blocked"
            if refusals
            else {"completed": "completed", "incomplete": "incomplete"}.get(
                status, "failed"
            )
        )
        return Message(
            response.get("id"),
            "".join(text) or None,
            "assistant",
            calls or None,
            native=deepcopy(output),
            status=normalized,
            provider_status=status,
            metadata={
                "refusals": refusals,
                "incomplete_details": response.get("incomplete_details"),
            },
        )

    def close(self):
        self.client.close()
