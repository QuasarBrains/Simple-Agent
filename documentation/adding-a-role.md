# Adding a role

Roles focus the agent's objectives and working practices. They are not permission
boundaries: the agent can switch modes freely with `set_role` while retaining its
conversation, tasks, and memory. Each role selects a working set of tools from
reusable capability libraries.

## Define and register a role

```python
from roles.index import Role
from tools.libraries.fs import TOOLS as FILESYSTEM_TOOLS
from tools.libraries.search import TOOLS as SEARCH_TOOLS
from tools.libraries.web import TOOLS as WEB_TOOLS

REVIEWER = Role(
    name="Reviewer",
    identity="Review local artifacts against sources and explain discrepancies with citations.",
    tools=[*FILESYSTEM_TOOLS, *SEARCH_TOOLS, *WEB_TOOLS],
)
```

Add the instance to `ROLES_INCLUDED` in `roles/config.py`. Set `DEFAULT_ROLE` to
choose the startup mode (currently `HELPFUL_ASSISTANT`). Keep tool names unique
within each role; reuse the same exported tool instances across roles.

The three bundled modes are Helpful Assistant, Researcher, and Developer.
All include filesystem, search, readable web retrieval, and isolated Python.
Developer additionally includes approval-gated host shell execution.
Their identities prescribe different working practices, even where their tool
sets overlap. See [the tooling inventory](tooling.md).

## Runtime behavior

The system prompt includes every role's identity and canonical tool inventory.
The active identity is also supplied on every perception iteration. Provider
schemas expose only the active role's tools plus shared harness operations:
user messaging, task management, role switching, and configured memory tools.

Switching unregisters the previous role's tools and registers the next set,
leaving shared operations intact. Registration failure restores the old toolbox.
Changes take effect immediately, including for later calls in the same sequential
batch. Prefer switching first and requesting the newly available tools on the
next inference, once their schemas are visible.

See [Adding a tool](adding-a-tool.md) for the callable, schema, result, and
execution-policy contracts.
