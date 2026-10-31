from dataclasses import dataclass
from datetime import datetime

from agent.workspaces.workspace import Workspace, WorkspaceState
from tools.index import Tool


@dataclass
class Note:
    id: str
    content: str
    createdAt: str
    updatedAt: str
    ephemeral: bool = True


@dataclass
class Page:
    id: str
    title: str
    content: list[Note]
    updatedAt: str


@dataclass
class State(WorkspaceState):
    current_page: int | None = None


class Notepad(Workspace):
    name = "notepad"

    def __init__(self) -> None:
        super().__init__()
        self.pages: dict[int, Page] = {}
        self.notes: dict[str, Note] = {}
        self.state = State()
        self._next_note_id = 1

    def set_page(self, page_number: int) -> None:
        if page_number not in self.pages:
            raise ValueError(f"Page {page_number} not found.")
        self.state.current_page = page_number

    def next_page(self) -> None:
        if self.state.current_page is not None:
            self.set_page(self.state.current_page + 1)

    def previous_page(self) -> None:
        if self.state.current_page is not None:
            self.set_page(self.state.current_page - 1)

    def new_page(self, title: str | None = None) -> int:
        page_number = len(self.pages) + 1
        self.pages[page_number] = Page(
            id=f"page_{page_number}",
            title=title or f"Page {page_number}",
            content=[],
            updatedAt=datetime.now().isoformat(),
        )
        self.set_page(page_number)
        return page_number

    def unique_note_id(self) -> str:
        return f"note_{self._next_note_id}"

    def get_notepad_overview(self) -> str:
        entries = "\n".join(
            f"- {page.title} ({number}): {len(page.content)} note(s)"
            for number, page in self.pages.items()
        )
        return f"<notepad_overview>\n{entries or 'No pages yet.'}\n</notepad_overview>"

    def read_page(self, page_number: int) -> str:
        page = self.pages[page_number]
        notes = "\n".join(
            f'<note id="{note.id}">{note.content}</note>' for note in page.content
        )
        return f"<page_content>\n=== {page.title} ({page_number}) ===\n{notes}\n</page_content>"

    def get_current_page(self) -> str:
        if self.state.current_page is None:
            return "No page selected."
        return self.read_page(self.state.current_page)

    def build_view(self) -> str:
        overview = self.get_notepad_overview()
        content = f"\n{self.get_current_page()}" if self.is_open() else ""
        status = "open" if self.is_open() else "closed"
        return f'<notepad status="{status}">\n{overview}{content}\n</notepad>'

    def write_note(self, page_number: int, note: str) -> str:
        page = self.pages[page_number]
        timestamp = datetime.now().isoformat()
        note_id = self.unique_note_id()
        entry = Note(note_id, note, timestamp, timestamp)
        self.notes[note_id] = entry
        page.content.append(entry)
        page.updatedAt = timestamp
        self._next_note_id += 1
        return note_id

    def edit_note(self, note_id: str, new_content: str) -> None:
        note = self.notes[note_id]
        note.content = new_content
        note.updatedAt = datetime.now().isoformat()
        for page in self.pages.values():
            if note in page.content:
                page.updatedAt = note.updatedAt

    def delete_note(self, note_id: str) -> None:
        note = self.notes.pop(note_id)
        for page in self.pages.values():
            if note in page.content:
                page.content.remove(note)
                page.updatedAt = datetime.now().isoformat()

    def read_note(self, note_id: str) -> str:
        return self.notes[note_id].content

    def get_tools(self) -> list[Tool]:
        def tool(name, description, properties, required, function):
            def run(args, pubsub):
                result = function(**args)
                return "Notepad updated." if result is None else str(result)

            return Tool(
                name=f"notepad.{name}",
                description=description,
                function=run,
                parameters={
                    "type": "object",
                    "properties": properties,
                    "required": required,
                    "additionalProperties": False,
                },
            )

        page = {"type": "integer", "minimum": 1}
        text = {"type": "string"}
        return [
            self.disclosure_tool(),
            tool(
                "new_page",
                "Create and select a session notepad page; returns its number.",
                {"title": text},
                [],
                self.new_page,
            ),
            tool(
                "set_page",
                "Select the page shown in the open workspace view.",
                {"page_number": page},
                ["page_number"],
                self.set_page,
            ),
            tool(
                "read_page",
                "Read any page without changing the current page or disclosure state.",
                {"page_number": page},
                ["page_number"],
                self.read_page,
            ),
            tool(
                "write_note",
                "Append a note to a page; returns its stable note ID.",
                {"page_number": page, "note": text},
                ["page_number", "note"],
                self.write_note,
            ),
            tool(
                "edit_note",
                "Replace the content of a note using its ID.",
                {"note_id": text, "new_content": text},
                ["note_id", "new_content"],
                self.edit_note,
            ),
            tool(
                "delete_note",
                "Delete a note from its page and the session notepad.",
                {"note_id": text},
                ["note_id"],
                self.delete_note,
            ),
            tool(
                "read_note",
                "Read a note using its ID.",
                {"note_id": text},
                ["note_id"],
                self.read_note,
            ),
        ]
