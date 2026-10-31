from typing import Any, List
import re
import os
from tools.index import Tool
from utils.pubsub import PubSub


def parse_gitignore(path: str) -> List[str]:
    gitignore_path = os.path.join(path, ".gitignore")
    if not os.path.exists(gitignore_path):
        return []

    with open(gitignore_path, "r", encoding="utf-8", errors="ignore") as f:
        patterns = [
            line.strip() for line in f if line.strip() and not line.startswith("#")
        ]
    return patterns


def run(args: Any, ps: PubSub):
    try:
        path = args.get("path")
        query = args.get("query")
        case_sensitive = args.get("case_sensitive", False)
        whole_word = args.get("whole_word", False)
        regex = args.get("regex", False)
        include_filters = args.get("include_filters", [])
        exclude_filters = args.get("exclude_filters", [])

        if not os.path.exists(path):
            return f"Error: The path '{path}' does not exist."

        # Parse .gitignore file
        gitignore_patterns = parse_gitignore(path)
        exclude_filters.extend(gitignore_patterns)

        matches = []
        for root, _, files in os.walk(path):
            for file in files:
                file_path = os.path.join(root, file)

                # Apply include and exclude filters
                if include_filters and not any(
                    re.search(f, file) for f in include_filters
                ):
                    continue
                if exclude_filters and any(
                    re.search(f, file_path) for f in exclude_filters
                ):
                    continue

                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    if regex:
                        flags = 0 if case_sensitive else re.IGNORECASE
                        pattern = re.compile(query, flags)
                    else:
                        pattern = re.escape(query)
                        if whole_word:
                            pattern = r"\b" + pattern + r"\b"
                        if not case_sensitive:
                            pattern = re.compile(pattern, re.IGNORECASE)
                        else:
                            pattern = re.compile(pattern)

                    for match in pattern.finditer(content):
                        matches.append(
                            {
                                "file": file_path,
                                "line": content.count("\n", 0, match.start()) + 1,
                                "match": match.group(),
                            }
                        )

        matches_str = "\n".join(
            [f"{m['file']}:{m['line']} - {m['match']}" for m in matches]
        )
        return matches_str
    except Exception as e:
        return f"Error searching for the query: {e}"


search_project = Tool(
    name="search_project",
    description="Performs a file search similar to 'Ctrl + Shift + F' in IDEs, with support for capitalization, matching whole words, regex, and file filters.",
    function=run,
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "The path to the project to search.",
            },
            "query": {
                "type": "string",
                "description": "The search keyword or pattern.",
            },
            "case_sensitive": {
                "type": "boolean",
                "description": "Whether the search is case sensitive.",
                "default": False,
            },
            "whole_word": {
                "type": "boolean",
                "description": "Whether to match the whole word only.",
                "default": False,
            },
            "regex": {
                "type": "boolean",
                "description": "Whether to use regex for the search.",
                "default": False,
            },
            "include_filters": {
                "type": "array",
                "items": {
                    "type": "string",
                },
                "description": "List of regex patterns to include files.",
                "default": [],
            },
            "exclude_filters": {
                "type": "array",
                "items": {
                    "type": "string",
                },
                "description": "List of regex patterns to exclude files.",
                "default": [],
            },
        },
        "required": ["query", "path"],
    },
)
