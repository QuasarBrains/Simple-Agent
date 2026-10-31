import os
from typing import List
import tiktoken
import json

from llms.llm import Message


def get_current_num_tokens(messages: List[Message], model: str):
    """Display-only estimate. Admission uses the complete provider request instead."""
    text = json.dumps([message.to_json() for message in messages], ensure_ascii=False)
    try:
        encoding = tiktoken.encoding_for_model(model)
        return len(encoding.encode(text))
    except KeyError:
        return len(text.encode("utf-8"))


def truncate_message(message: Message):
    """Legacy presentation helper: never mutate replayable conversation data."""
    from dataclasses import replace

    max_message_length = int(os.environ.get("MAX_MESSAGE_LENGTH", 10000))

    if message.content and len(message.content) > max_message_length:
        return replace(
            message, content=message.content[:max_message_length] + "...[TRUNCATED]"
        )

    return message
