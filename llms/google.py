import json
import os
from typing import List

from dotenv import load_dotenv
from openai import NOT_GIVEN, OpenAI
from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessageParam,
    ChatCompletionMessageToolCall,
    ChatCompletionSystemMessageParam,
    ChatCompletionToolMessageParam,
    ChatCompletionToolParam,
    ChatCompletionUserMessageParam,
)
from openai.types.chat.chat_completion_message_tool_call_param import (
    ChatCompletionMessageToolCallParam,
    Function,
)
from openai.types.shared_params import FunctionDefinition

from llms.llm import LLM, Message
from tools.index import Tool, ToolCall

load_dotenv()

openai_client: OpenAI
openai_model: str = "gpt-4o-mini"


def tool_to_openai_tool_call(tool: Tool) -> ChatCompletionToolParam:
    return ChatCompletionToolParam(
        type="function",
        function=FunctionDefinition(
            name=tool.name,
            description=tool.description,
            parameters=tool.parameters,
        ),
    )


def openai_tool_call_to_tool_call(tool_call: ChatCompletionMessageToolCall) -> ToolCall:
    parsed_arguments = json.loads(tool_call.function.arguments)
    return ToolCall(
        name=tool_call.function.name, arguments=parsed_arguments, id=tool_call.id
    )


def tool_call_to_openai_tool_call(
    tool_call: ToolCall,
) -> ChatCompletionMessageToolCallParam:
    return ChatCompletionMessageToolCallParam(
        id=tool_call.id,
        function=Function(
            name=tool_call.name, arguments=json.dumps(tool_call.arguments)
        ),
        type="function",
    )


def message_to_openai_message(message: Message) -> ChatCompletionMessageParam:
    if not message.content:
        return ChatCompletionAssistantMessageParam(
            content="",
            role="assistant",
            tool_calls=[tool_call_to_openai_tool_call(tc) for tc in message.tool_calls]
            if message.tool_calls
            else [],
        )
    if message.role == "tool" and message.tool_call_id is not None:
        return ChatCompletionToolMessageParam(
            content=message.content,
            role="tool",
            tool_call_id=message.tool_call_id,
        )
    if message.role == "user":
        return ChatCompletionUserMessageParam(
            content=message.content,
            role="user",
        )
    if message.role == "assistant":
        return ChatCompletionAssistantMessageParam(
            content=message.content,
            role="assistant",
        )
    if message.role == "system":
        return ChatCompletionSystemMessageParam(
            content=message.content,
            role="system",
        )
    raise ValueError(f"Invalid message role: {message.role}")


def get_openai_model_response(
    messages: List[Message], tools: List[Tool], system_prompt: str
) -> Message:
    if not openai_client:
        raise ValueError("OpenAI client not initialized")

    tool_list = [tool_to_openai_tool_call(tool) for tool in tools]

    response = openai_client.chat.completions.create(
        model=openai_model,
        max_tokens=int(os.environ.get("MAX_TOKENS", 1024)),
        messages=[
            message_to_openai_message(
                Message(
                    id=None,
                    role="system",
                    content=system_prompt,
                    tool_calls=None,
                    tool_call_id=None,
                )
            )
        ]
        + [message_to_openai_message(message) for message in messages],
        tools=tool_list if len(tool_list) > 0 else NOT_GIVEN,
        parallel_tool_calls=False,
        tool_choice="required",
    )

    message = response.choices[0].message

    if message.tool_calls is None:
        return Message(
            id=None,
            content=message.content,
            role=message.role,
            tool_calls=None,
            tool_call_id=None,
        )

    return Message(
        id=None,
        content=None,
        role=message.role,
        tool_calls=[openai_tool_call_to_tool_call(tc) for tc in message.tool_calls],
        tool_call_id=None,
    )


def init_openai_llm():
    global openai_client
    global openai_model

    openai_client = OpenAI(
        api_key=os.environ.get("GEMINI_API_KEY"),
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    )

    env_model = os.environ.get("GEMINI_MODEL")
    if env_model != "" and env_model is not None:
        openai_model = env_model
    if not openai_model:
        openai_model = "models/gemini-2.0-flash"


GoogleLLM = LLM(
    name="Google",
    model_name=openai_model,
    get_model_response=get_openai_model_response,
    on_startup=init_openai_llm,
)
