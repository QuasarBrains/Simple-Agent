from typing import Any, Optional
import fitz  # PyMuPDF
from tools.index import Tool
from utils.pubsub import PubSub


def run(args: Any, ps: PubSub):
    if not args:
        return "Error running send_message_to_user: No message provided."
    try:
        file_path = args["file_path"]
        if file_path.endswith(".pdf"):
            content = read_pdf(file_path, args.get("page_range"))
        else:
            content = read_text_file(file_path, args.get("range"))
        return f"File contents:\n```\n{content}\n```"
    except Exception as e:
        return f"Error reading file: {e}"


def read_text_file(file_path: str, line_range: Optional[str] = None) -> str:
    with open(file_path, "r") as file:
        content = file.read()
        content = add_line_numbers(content)
        if line_range:
            start, end = line_range.split("-")
            lines = content.split("\n")
            start = int(start) if start else 0
            end = int(end) if end else len(lines)
            content = "\n".join(lines[start - 1 : end])
    return content


def read_pdf(file_path: str, page_range: Optional[str] = None) -> str:
    doc = fitz.open(file_path)
    content = []
    if page_range:
        start, end = page_range.split("-")
        start = int(start) if start else 1
        end = int(end) if end else doc.page_count
    else:
        start, end = 1, doc.page_count

    for page_num in range(start - 1, end):
        page = doc.load_page(page_num)
        content.append(page.get_textpage().extractText())

    return "\n".join(content)


def add_line_numbers(content: str) -> str:
    lines = content.split("\n")
    lines_with_numbers = []
    for i, line in enumerate(lines):
        lines_with_numbers.append(f"{i+1}: {line}")
    return "\n".join(lines_with_numbers)


read_file = Tool(
    name="read_file",
    description="Read a file (text or PDF)",
    function=run,
    parameters={
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "The path to the file to read.",
            },
            "range": {
                "type": "string",
                "pattern": "^\\d*-\\d*$",
                "description": "The line numbers to read for text files. Formatted as 'start-end'.",
            },
            "page_range": {
                "type": "string",
                "pattern": "^\\d*-\\d*$",
                "description": "The page numbers to read for PDF files. Formatted as 'start-end'.",
            },
        },
        "required": ["file_path"],
    },
)
