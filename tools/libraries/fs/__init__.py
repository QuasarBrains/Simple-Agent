"""Modular filesystem tools, returning tools.index.ToolResult.

All paths expand '~' and resolve relative to the process working directory.
These tools do not implement a filesystem sandbox; enforce access policy in the
caller. Read/replace/search support UTF-8 text only, not PDF or binary content.
Discovery includes hidden files and does not parse .gitignore. Enumeration order
is filesystem-dependent. Search returns matching lines, not individual matches;
Python regex uses standard re semantics (no regex execution timeout).

Successful results always include truncated, truncation_reasons, returned_chars.
Limits stop enumeration/output explicitly; skipped search files are reported as
incomplete results. max_chars counts Unicode characters, not encoded bytes.
Mutations preserve UTF-8 bytes/newlines but are not transactional or locked.
"""

from .discovery import FIND_TOOL, LIST_TOOL, SEARCH_TOOL
from .read import TOOL as READ_TOOL
from .replace import TOOL as REPLACE_TOOL
from .write import TOOL as WRITE_TOOL

TOOLS = [READ_TOOL, WRITE_TOOL, REPLACE_TOOL, LIST_TOOL, FIND_TOOL, SEARCH_TOOL]

__all__ = ["TOOLS"]
