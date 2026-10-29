"""One Rich console for coordinated status animation and conversation output."""

from contextlib import contextmanager
from decimal import Decimal

from rich.console import Console
from rich.markdown import Markdown
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

    def prompt(self) -> str:
        self.console.print()
        if self.tracker and self.tracker.summary()["requests"]:
            self.console.print(Rule(self.totals(), align="right", style="dim"))
        return self.console.input("[bold cyan]You[/bold cyan] [dim]›[/dim] ")

    def message(self, message: str):
        self.console.print()
        self.console.print("Simmy", style="bold blue")
        self.console.print(Markdown(message))


terminal = Terminal()
