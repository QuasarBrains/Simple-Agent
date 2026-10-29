from typing import List

from utils.pubsub import PubSub

unseen_messages = []


class Environment:
    pubsub: PubSub

    unseen_messages: List[str] = []
    new_tool_messages: List[str] = []

    def __init__(self, pubsub: PubSub) -> None:
        self.pubsub = pubsub
        self.unseen_messages = []
        self.new_tool_messages = []

        self.listen_to_messages()
        self.listen_to_new_tool_messages()

    def listen_to_messages(self):
        self.pubsub.subscribe(
            "new_user_message", lambda message: self.unseen_messages.append(message)
        )

    def listen_to_new_tool_messages(self):
        def new_tool_message(message):
            self.new_tool_messages.append(message)

        self.pubsub.subscribe("new_tool_message", new_tool_message)

    def get_environment(self):
        unseen_messages = self.unseen_messages
        self.unseen_messages = []

        new_tool_messages = self.new_tool_messages
        self.new_tool_messages = []

        if len(unseen_messages) == 0 and len(new_tool_messages) == 0:
            return ""

        # Full results already live in role=tool messages. Keep their content
        # available to peek_environment/memory, without duplicating it in model input.
        tool_notice = (
            f"{len(new_tool_messages)} tool result(s) provided in conversation history."
            if new_tool_messages
            else ""
        )
        return f"""
        New Messages:
        {"".join(["- {}".format(message) for message in unseen_messages])}

        New Tool Messages:
        {tool_notice}
        """

    def peek_environment(self):
        return f"""
        Unseen Messages:
        {"".join(["- {}".format(message) for message in self.unseen_messages])}

        New Tool Messages:
        {"".join(["- {}".format(message) for message in self.new_tool_messages])}
        """

    def new_stimuli(self):
        return len(self.unseen_messages) > 0 or len(self.new_tool_messages) > 0

    def get_unseen_messages(self):
        return self.unseen_messages
