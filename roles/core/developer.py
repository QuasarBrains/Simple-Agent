from roles.index import Role
from tools.libraries.fs import TOOLS as FILESYSTEM_TOOLS
from tools.libraries.python import TOOLS as PYTHON_TOOLS
from tools.libraries.search import TOOLS as SEARCH_TOOLS
from tools.libraries.shell import TOOLS as SHELL_TOOLS
from tools.libraries.web import TOOLS as WEB_TOOLS

TOOLS = [*FILESYSTEM_TOOLS, *SHELL_TOOLS, *PYTHON_TOOLS, *SEARCH_TOOLS, *WEB_TOOLS]

DEVELOPER = Role(
    name="Developer",
    identity=(
        "Develop, inspect and debug software. Discover and read the project before editing; "
        "make precise changes and verify results. Host shell commands require user approval."
    ),
    tools=TOOLS,
)
