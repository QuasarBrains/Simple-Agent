from roles.index import Role
from tools.libraries.fs import TOOLS as FILESYSTEM_TOOLS
from tools.libraries.python import TOOLS as PYTHON_TOOLS
from tools.libraries.search import TOOLS as SEARCH_TOOLS
from tools.libraries.web import TOOLS as WEB_TOOLS

TOOLS = [*FILESYSTEM_TOOLS, *SEARCH_TOOLS, *WEB_TOOLS, *PYTHON_TOOLS]

HELPFUL_ASSISTANT = Role(
    name="Helpful Assistant",
    identity=(
        "Help with everyday questions and tasks. Answer conversationally when no tools are needed; "
        "use files, web sources and isolated Python when they help. Switch modes freely for focused work."
    ),
    tools=TOOLS,
)
