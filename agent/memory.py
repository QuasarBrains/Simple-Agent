from typing import Any, List, Optional
from functools import cached_property
from llms.llm import LLM, Message
from tools.index import Tool
from utils.pubsub import PubSub
from memory.vector_store import VectorStore
from memory.service import Memory, MemoryDraft, MemoryQuery, MemoryService
from memory.legacy import VectorStoreMemoryService
import tiktoken
from utils.terminal import console


class MemoryEngine:
    pubsub: PubSub
    vector_store: Optional[VectorStore]
    messages: List[Message]
    llm: Optional[LLM]

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
        self.messages = []

    @cached_property
    def encoding(self):
        return tiktoken.get_encoding("cl100k_base")

    def is_setup(self) -> bool:
        return self.service is not None

    def sync_messages(self, messages: List[Message]):
        self.messages = messages

    def get_memory(self) -> str:
        if not self.current_memory:
            return ""
        memory = ""
        for record in self.current_memory:
            memory += (
                f"[{record.id}] {record.title} ({record.type})\n{record.content}\n\n"
            )
        tokens = self.encoding.encode(memory, disallowed_special=())
        return self.encoding.decode(tokens[: self.token_budget])

    def evaluate_memory(self, context: str):
        self.propose_memory(context)
        self.commit_memory()

    def propose_memory(self, context: str):
        self.proposed_memory = []
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
            self.pubsub.publish("agent_error", f"Memory recall failed: {error}")

    def commit_memory(self):
        self.current_memory = self.proposed_memory

    def clear_recall(self):
        self.current_memory = []
        self.proposed_memory = []

    def delete_memories(self, memories: List[int]):
        """Legacy alias: clear working recall, without deleting persisted memories."""
        self.clear_recall()

    def add_memory(self, memory: MemoryDraft):
        if not self.service:
            return "Error: Tried to add memory when memory not initialized."
        try:
            result = self.service.add(memory)
        except Exception as error:
            self.pubsub.publish("agent_error", f"Memory write failed: {error}")
            return f"Error adding memory: {error}"
        console.print(
            f"Remembered: {memory.title}", style="medium_orchid3", markup=False
        )
        return result

    def add_memory_tool(self) -> Tool:
        def run(args: Any, pubsub: PubSub):
            if not isinstance(args, dict):
                return "Error adding memory: Expected an object."
            content = args.get("content")
            title = args.get("title")
            importance = args.get("importance")
            type = args.get("type")

            if not title:
                return "Error adding memory: No title provided."
            if not content:
                return "Error adding memory: No content provided."
            if not type:
                return "Error adding memory: No type provided."
            if not importance:
                return "Error adding memory: No importance provided."

            if type not in ["semantic", "episodic"]:
                return "Error adding memory: Invalid memory type provided. Must be either 'semantic' or 'episodic'."

            try:
                memory = MemoryDraft(
                    title=title, content=content, importance=importance, type=type
                )
            except ValueError as error:
                return f"Error adding memory: {error}"
            result = self.add_memory(memory)
            if isinstance(result, str) and result.startswith("Error"):
                return "Something went wrong." + result
            return f"Memory added: {title}"

        return Tool(
            name="add_memory",
            description="Use this tool to add a new memory.",
            function=run,
            parameters={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "The title of the memory to add.",
                    },
                    "content": {
                        "type": "string",
                        "description": "The content of the memory to add.",
                    },
                    "importance": {
                        "type": "string",
                        "pattern": "^(low|medium|high|extreme)$",
                        "description": "The initial importance of the memory. What is the likelihood of this memory being significantly useful in the future?",
                    },
                    "type": {
                        "type": "string",
                        "pattern": "^(semantic|episodic)$",
                        "description": "The type of the memory this is considered. Either semantic or episodic.",
                    },
                },
                "required": ["title", "content", "importance", "type"],
            },
        )

    def dont_add_memory_tool(self) -> Tool:
        def run(args: Any, pubsub: PubSub):
            return "No memory added."

        return Tool(
            name="dont_add_memory",
            description="Use this tool to skip adding a new memory.",
            function=run,
            parameters={},
        )
