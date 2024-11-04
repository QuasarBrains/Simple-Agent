from roles.index import Role
from tools.libraries.core.web_request import web_request
from tools.libraries.core.write_file import write_file
from tools.libraries.core.scraper import scraper

TOOLS = [web_request, write_file, scraper]

RESEARCHER = Role(
    name="Researcher",
    identity="A dedicated researcher with specialized tools for web research, data analysis, and documentation.",
    tools=TOOLS,
)
