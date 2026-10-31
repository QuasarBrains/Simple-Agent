from roles.index import Role
from tools.libraries.fs import TOOLS as FILESYSTEM_TOOLS
from tools.libraries.python import TOOLS as PYTHON_TOOLS
from tools.libraries.search import TOOLS as SEARCH_TOOLS
from tools.libraries.web import TOOLS as WEB_TOOLS

TOOLS = [*SEARCH_TOOLS, *WEB_TOOLS, *FILESYSTEM_TOOLS, *PYTHON_TOOLS]

RESEARCHER = Role(
    name="Researcher",
    identity=(
        "Research questions through source discovery, readable retrieval and comparison. "
        "Cite source URLs, distinguish evidence from inference, and save useful artifacts. "
        "Use isolated Python to check calculations when appropriate."
    ),
    tools=TOOLS,
)
