"""One Rich console for coordinated status animation and conversation output."""

import asyncio
import json
from contextlib import contextmanager
from decimal import Decimal

from prompt_toolkit import HTML, PromptSession
from prompt_toolkit.validation import Validator
from rich.console import Console
from rich.markdown import Markdown
from rich.prompt import Prompt
from rich.rule import Rule
from rich.text import Text

console = Console(highlight=False)


def dollars(value: str) -> str:
    amount = Decimal(value)
    if 0 < amount < Decimal("0.0001"):
        return "<$0.0001"
    return f"${amount:,.4f}"


class Terminal:
    def __init__(self, output: Console = console):
        self.console = output
        self.tracker = None
        self._user_session = None
        self._approval_session = None
        self._user_draft = ""

    def totals(self) -> Text:
        if self.tracker is None:
            return Text("")
        summary = self.tracker.summary()
        count = summary["requests"]
        unknown = summary["unknown_requests"]
        if unknown == count and count:
            cost = "Cost unavailable"
        elif not count and not self.tracker.pricing:
            cost = "Cost unavailable"
        else:
            cost = "Session " + dollars(summary["known_cost"])
            if unknown:
                cost += " (partial)"
            elif summary.get("session_budget") is not None:
                cost += " / " + dollars(summary["session_budget"])
        parts = [cost]
        if count:
            parts.append(f"{count} request{'s' if count != 1 else ''}")
            tokens = summary.get("input_tokens", 0) + summary.get("output_tokens", 0)
            if tokens:
                parts.append(f"{tokens:,} tokens")
        return Text("  ·  ".join(parts), style="dim")

    @contextmanager
    def thinking(self):
        title = Text("Thinking…", style="bold cyan")
        totals = self.totals()
        if totals.plain:
            title.append("  ·  ")
            title.append_text(totals)
        with self.console.status(title, spinner="dots", refresh_per_second=12):
            yield

    def _prompt_header(self):
        self.console.print()
        if self.tracker and self.tracker.summary()["requests"]:
            self.console.print(Rule(self.totals(), align="right", style="dim"))

    def prompt(self, reply: bool = False) -> str:
        self._prompt_header()
        label = "Reply" if reply else "You"
        return self.console.input(f"[bold cyan]{label}[/bold cyan] [dim]›[/dim] ")

    async def prompt_async(self, reply: bool = False) -> str:
        if self._user_session is None:
            self._user_session = PromptSession()
        self._prompt_header()
        label = "Reply" if reply else "You"
        try:
            value = await self._user_session.prompt_async(
                HTML(
                    f"<b><ansicyan>{label}</ansicyan></b> <ansibrightblack>›</ansibrightblack> "
                ),
                default=self._user_draft,
            )
        except asyncio.CancelledError:
            self._user_draft = self._user_session.default_buffer.text
            raise
        self._user_draft = ""
        return value

    def _approval_header(self, tool, arguments: dict):
        self.console.print()
        self.console.print(Text(f"Approval required: {tool.name}", style="bold yellow"))
        self.console.print(Text(json.dumps(arguments, indent=2, ensure_ascii=False)))
        self.console.print(Text(tool.description, style="dim"))

    async def approve_tool_async(self, tool, arguments: dict) -> bool:
        if self._approval_session is None:
            self._approval_session = PromptSession()
        self._approval_header(tool, arguments)
        value = await self._approval_session.prompt_async(
            "Approve this invocation? [1] Approve once / [2] Deny [Enter: Deny]: ",
            default="",
            validator=Validator.from_callable(
                lambda text: text.strip() in ("", "1", "2"),
                error_message="Enter 1 to approve or 2 to deny.",
            ),
        )
        return value.strip() == "1"

    def approve_tool(self, tool, arguments: dict) -> bool:
        self._approval_header(tool, arguments)
        return (
            Prompt.ask(
                "Approve this invocation? [1] Approve once / [2] Deny",
                choices=["1", "2"],
                default="2",
                console=self.console,
            )
            == "1"
        )

    def message(self, message: str):
        self.console.print()
        self.console.print("Simon", style="bold blue")
        self.console.print(Markdown(message))


terminal = Terminal()
