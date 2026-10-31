import threading

from utils.pubsub import PubSub


class Environment:
    def __init__(self, pubsub: PubSub) -> None:
        self.pubsub = pubsub
        self.unseen_messages: list[str] = []
        self.new_tool_messages: list[str] = []
        self.external_stimuli: list[str] = []
        self.lock = threading.Lock()
        self.listen_to_messages()
        self.listen_to_new_tool_messages()
        self.pubsub.subscribe("new_environment_stimulus", self.add_external_stimulus)

    def listen_to_messages(self):
        self.pubsub.subscribe("new_user_message", self.add_user_message)

    def listen_to_new_tool_messages(self):
        self.pubsub.subscribe("new_tool_message", self.add_tool_message)

    def add_user_message(self, message):
        with self.lock:
            self.unseen_messages.append(str(message))

    def add_tool_message(self, message):
        with self.lock:
            self.new_tool_messages.append(str(message))

    def add_external_stimulus(self, stimulus):
        with self.lock:
            self.external_stimuli.append(str(stimulus))

    def get_environment(self):
        with self.lock:
            unseen, self.unseen_messages = self.unseen_messages, []
            tools, self.new_tool_messages = self.new_tool_messages, []
            external, self.external_stimuli = self.external_stimuli, []
        if not unseen and not tools and not external:
            return ""
        sections = []
        if unseen:
            sections.append(
                "New Messages:\n" + "\n".join(f"- {message}" for message in unseen)
            )
        if external:
            sections.append(
                "External Stimuli:\n" + "\n".join(f"- {event}" for event in external)
            )
        if tools:
            sections.append(
                f"{len(tools)} tool result(s) provided in conversation history."
            )
        return "\n\n".join(sections)

    def peek_environment(self):
        with self.lock:
            return (
                "Unseen Messages:\n"
                + "\n".join(self.unseen_messages)
                + "\nExternal Stimuli:\n"
                + "\n".join(self.external_stimuli)
                + "\nNew Tool Messages:\n"
                + "\n".join(self.new_tool_messages)
            )

    def has_user_messages(self):
        with self.lock:
            return bool(self.unseen_messages)

    def has_external_stimuli(self):
        with self.lock:
            return bool(self.unseen_messages or self.external_stimuli)

    def new_stimuli(self):
        with self.lock:
            return bool(
                self.unseen_messages or self.external_stimuli or self.new_tool_messages
            )

    def get_unseen_messages(self):
        with self.lock:
            return self.unseen_messages.copy()
