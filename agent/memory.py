import json
from functools import cached_property
from typing import List, Optional

import tiktoken

from llms.llm import LLM, Message
from memory.legacy import VectorStoreMemoryService
from memory.service import (
    EditableMemoryService,
    Memory,
    MemoryDraft,
    MemoryQuery,
    MemoryService,
    MemoryServiceError,
    MemoryUpdate,
    RemovableMemoryService,
)
from memory.vector_store import VectorStore
from tools.index import ExecutionPolicy, Tool, ToolResult
from utils.pubsub import PubSub
from utils.terminal import console


class MemoryEngine:
    def __init__(
        self,
        pubsub: PubSub,
        vector_store: Optional[VectorStore] = None,
        llm: Optional[LLM] = None,
        *,
        service: Optional[MemoryService] = None,
        recall_limit: int = 3,
        token_budget: int = 1000,
    ) -> None:
        self.pubsub = pubsub
        self.vector_store = vector_store
        self.llm = llm
        self.service = service
        if service is None and vector_store is not None:
            self.service = VectorStoreMemoryService(vector_store)
            self.service.startup()
        if not 1 <= recall_limit <= 100 or token_budget <= 0:
            raise ValueError(
                "Memory recall limit must be 1..100 and token budget must be positive"
            )
        self.recall_limit = recall_limit
        self.token_budget = token_budget
        self.current_memory: List[Memory] = []
        self.proposed_memory: List[Memory] = []
        self.messages: List[Message] = []
        self.recall_failed = False

    @cached_property
    def encoding(self):
        return tiktoken.get_encoding("cl100k_base")

    def is_setup(self) -> bool:
        return self.service is not None

    def can_update(self) -> bool:
        return isinstance(self.service, EditableMemoryService)

    def can_remove(self) -> bool:
        return isinstance(self.service, RemovableMemoryService)

    def get_tools(self) -> List[Tool]:
        if not self.is_setup():
            return []
        tools = [self.add_memory_tool()]
        if self.can_update():
            tools.append(self.update_memory_tool())
        if self.can_remove():
            tools.append(self.remove_memory_tool())
        return tools

    def sync_messages(self, messages: List[Message]):
        self.messages = messages

    def get_memory(self) -> str:
        if not self.service:
            return (
                "Persistent memory is DISABLED for this session. No memory tools are available. "
                "Use task notes for temporary context; do not claim information was saved to long-term memory."
            )
        status = (
            "Persistent memory is ENABLED. Relevant memories are recalled automatically before reasoning; "
            "no retrieval tool call is needed. Use memory.add for NEW durable information. "
        )
        if self.can_update():
            status += (
                "Use memory.update with the exact memory_id below or from successful memory-tool result metadata "
                "to correct/refresh an existing memory. Omitted fields are preserved. "
            )
        else:
            status += "This backend cannot edit existing memories; memory.update is unavailable. "
        if self.can_remove():
            status += (
                "Use memory.remove with an exact memory_id and a reason to retire a memory from recall. "
                "Removal requires user approval and retains a recoverable record; use memory.update for corrections. "
            )
        else:
            status += (
                "This backend cannot remove memories; memory.remove is unavailable. "
            )
        status += "The latest Memory section supersedes older recalled copies in conversation history.\n\n"
        if self.recall_failed:
            return (
                status
                + "Automatic recall failed this turn; earlier recalled entries have been cleared."
            )
        if not self.current_memory:
            return (
                status
                + "No relevant memories recalled this turn; this does not mean the store is empty."
            )
        memory = ""
        for record in self.current_memory:
            memory += (
                f"### memory_id: {json.dumps(str(record.id))}\n"
                f"Title: {record.title}\nType: {record.type}\nImportance: {record.importance}\n"
                f"Updated: {record.updated_at or 'unknown'}\nContent:\n{record.content}\n\n"
            )
        tokens = self.encoding.encode(memory, disallowed_special=())
        text = self.encoding.decode(tokens[: self.token_budget])
        if len(tokens) > self.token_budget:
            text += "\n[Recall text truncated; do not assume this is the complete memory content.]"
        return status + text

    def evaluate_memory(self, context: str):
        self.propose_memory(context)
        self.commit_memory()

    def propose_memory(self, context: str):
        self.proposed_memory = []
        self.recall_failed = False
        if not self.service or not context.strip():
            return
        try:
            tokens = self.encoding.encode(context, disallowed_special=())
            query = self.encoding.decode(tokens[:2000])
            self.proposed_memory = [
                result.memory
                for result in self.service.search(MemoryQuery(query, self.recall_limit))
            ]
        except Exception as error:
            self.recall_failed = True
            self.pubsub.publish("agent_error", f"Memory recall failed: {error}")

    def commit_memory(self):
        self.current_memory = self.proposed_memory

    def clear_recall(self):
        self.current_memory = []
        self.proposed_memory = []
        self.recall_failed = False

    def delete_memories(self, memories: List[int]):
        """Legacy alias: clear working recall, without deleting persisted memories."""
        self.clear_recall()

    def add_memory(self, memory: MemoryDraft) -> Memory:
        if not self.service:
            raise MemoryServiceError("Persistent memory is disabled")
        try:
            result = self.service.add(memory)
        except Exception as error:
            self.pubsub.publish("agent_error", f"Memory write failed: {error}")
            raise
        console.print(
            f"Remembered: {result.title}", style="medium_orchid3", markup=False
        )
        return result

    def update_memory(self, memory_id: int | str, changes: MemoryUpdate) -> Memory:
        if not isinstance(self.service, EditableMemoryService):
            raise MemoryServiceError("This memory backend does not support updates")
        try:
            result = self.service.update(memory_id, changes)
        except Exception as error:
            self.pubsub.publish("agent_error", f"Memory update failed: {error}")
            raise
        for name in ("current_memory", "proposed_memory"):
            setattr(
                self,
                name,
                [
                    result if str(m.id) == str(result.id) else m
                    for m in getattr(self, name)
                ],
            )
        return result

    def remove_memory(self, memory_id: int | str) -> Memory:
        if not isinstance(self.service, RemovableMemoryService):
            raise MemoryServiceError("This memory backend does not support removal")
        try:
            result = self.service.remove(memory_id)
        except Exception as error:
            self.pubsub.publish("agent_error", f"Memory removal failed: {error}")
            raise
        for name in ("current_memory", "proposed_memory"):
            setattr(
                self,
                name,
                [m for m in getattr(self, name) if str(m.id) != str(result.id)],
            )
        return result

    @staticmethod
    def _tool_fields() -> dict:
        return {
            "title": {
                "type": "string",
                "minLength": 1,
                "description": "A short, descriptive title for this long-term memory.",
            },
            "content": {
                "type": "string",
                "minLength": 1,
                "description": "The durable information to remember, including relevant context and scope.",
            },
            "type": {
                "type": "string",
                "enum": ["semantic", "episodic"],
                "description": "semantic for facts/preferences; episodic for a specific event or experience.",
            },
            "importance": {
                "type": "string",
                "enum": ["low", "medium", "high", "extreme"],
                "description": "Expected future usefulness; reserve extreme for essential enduring information.",
            },
        }

    def add_memory_tool(self) -> Tool:
        def run(arguments, pubsub):
            result = self.add_memory(
                MemoryDraft(
                    title=arguments["title"],
                    content=arguments["content"],
                    type=arguments.get("type", "semantic"),
                    importance=arguments.get("importance", "medium"),
                )
            )
            return ToolResult(
                content=f"Memory added: {result.title}",
                metadata={"memory_id": str(result.id)},
            )

        fields = self._tool_fields()
        fields["type"]["default"] = "semantic"
        fields["importance"]["default"] = "medium"
        return Tool(
            name="memory.add",
            description=(
                "Save NEW information to persistent long-term memory for future sessions: durable facts, "
                "user preferences, lessons, or significant experiences. Recall is automatic. "
                "Use task notes for temporary work. If a recalled memory already covers the information, "
                "use memory.update when available instead of creating a duplicate. "
                "Returns memory_id in result metadata. Defaults: type=semantic, importance=medium."
            ),
            function=run,
            parameters={
                "type": "object",
                "properties": fields,
                "required": ["title", "content"],
                "additionalProperties": False,
            },
        )

    def update_memory_tool(self) -> Tool:
        def run(arguments, pubsub):
            changes = MemoryUpdate(
                **{key: value for key, value in arguments.items() if key != "memory_id"}
            )
            result = self.update_memory(arguments["memory_id"], changes)
            return ToolResult(
                content=f"Memory updated: {result.title}\nCurrent content: {result.content}",
                metadata={"memory_id": str(result.id)},
            )

        fields = self._tool_fields()
        fields["content"]["description"] = (
            "Full replacement content, not a diff. Preserve still-correct information and describe "
            "the scope of corrections or exceptions. Omit to keep the current content."
        )
        return Tool(
            name="memory.update",
            description=(
                "Correct, refresh, or refine an EXISTING persistent memory by memory_id from the Memory "
                "section or a prior memory-tool result's metadata. Supply at least one changed field; "
                "omitted fields stay unchanged. Content is a full replacement. Preserve valid information "
                "and scope case-specific exceptions rather than turning them into universal facts. "
                "Keeps the same ID and refreshes retrieval embeddings when title/content changes."
            ),
            function=run,
            parameters={
                "type": "object",
                "properties": {
                    "memory_id": {
                        "type": "string",
                        "minLength": 1,
                        "description": "Exact memory_id from automatic recall or successful memory-tool result metadata. Do not guess.",
                    },
                    **fields,
                },
                "required": ["memory_id"],
                "additionalProperties": False,
            },
        )

    def remove_memory_tool(self) -> Tool:
        def run(arguments, pubsub):
            result = self.remove_memory(arguments["memory_id"])
            return ToolResult(
                content=f"Memory removed from automatic recall: {result.title}. Its record is retained for recovery.",
                metadata={"memory_id": str(result.id), "removed_at": result.removed_at},
            )

        return Tool(
            name="memory.remove",
            description=(
                "Retire an EXISTING memory from automatic recall by its exact memory_id. "
                "Requires user approval for each invocation; denial makes no changes. "
                "This is a soft removal: the record and content remain stored for recovery, not permanently erased. "
                "Give a clear reason for the approval request. Use memory.update for corrections instead."
            ),
            function=run,
            parameters={
                "type": "object",
                "properties": {
                    "memory_id": {
                        "type": "string",
                        "minLength": 1,
                        "pattern": r"\S",
                        "description": "Exact memory_id from recall or successful memory-tool result metadata. Do not guess.",
                    },
                    "reason": {
                        "type": "string",
                        "minLength": 1,
                        "pattern": r"\S",
                        "description": "Explain which memory is being retired and why. Shown to the user for approval.",
                    },
                },
                "required": ["memory_id", "reason"],
                "additionalProperties": False,
            },
            policy=ExecutionPolicy(requires_approval=True),
        )
