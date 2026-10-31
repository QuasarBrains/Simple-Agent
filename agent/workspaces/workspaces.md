# Workspaces

Workspaces are session-local tool classes that expose working state through the agent's environment on every reasoning iteration. They are ephemeral by default; durable information belongs in memory. A workspace can wrap another application if it exposes the same interface.

## Standard interface

Implement `Workspace` from `agent/workspaces/workspace.py`:

- `name`: a unique workspace identifier.
- `state`: workspace-owned state, including an `open` disclosure flag. Extend `WorkspaceState` for additional view state.
- `build_view() -> str`: the current environment view. Open workspaces show working details; closed workspaces show a minimized overview, not an empty or deleted workspace.
- `get_tools() -> list[Tool]`: tools that manipulate or read workspace state. Include `self.disclosure_tool()` to expose `workspace.<name>.set_open(open)`.
- `has_pending_work() -> bool`: optional lifecycle hook, false by default. Pending work keeps the loop active unless the agent explicitly waits.
- `active_task_ids() -> list[str]`: optional cost-attribution hook, empty by default. A single active task receives inference costs; otherwise costs are shared.

`open()`, `close()`, and `is_open()` manage disclosure only. Closing a workspace does not delete its state, disable tools, complete tasks, or pause the agent.

## Lifecycle integration

`Agent.workspaces` holds the session's workspace instances. Default initialization registers each workspace's tools independently of roles. On every prompt build, the agent appends current workspace views to the `Environment` section. The loop consults workspace hooks for pending work and inference cost attribution; it does not need workspace-specific logic.

To add a workspace, implement the interface and add an instance to `Agent.workspaces` during construction. No environment subscriptions, custom prompt sections, or agent-loop branches are required.

## Built-in workspaces

### Tasks

Replaces the former standalone agency module. Open views show incomplete tasks with requirements and notes, plus a compact completed-task summary. Closed views show counts. Existing task tool names (`create_task`, `complete_task`, `modify_task_notes`, `modify_task_requirements`) and task events are preserved. Incomplete tasks sustain active work but never override an explicit wait.

### Notepad

Stores session-local pages and notes. The open view shows a table of contents and the selected page; the closed view shows only the table of contents. Creating a page selects it. `notepad.set_page` changes the visible page; `notepad.read_page` reads another page without changing selection or disclosure. Notes expose stable IDs for reading, editing, and deletion. Merely retaining notes does not keep the agent awake.

Tools: `notepad.new_page`, `notepad.set_page`, `notepad.read_page`, `notepad.write_note`, `notepad.read_note`, `notepad.edit_note`, and `notepad.delete_note`.

## Migration

`agent/agency.py`, `Agency`, and `Agent.agency` are replaced by `agent/workspaces/tasks.py`, `Tasks`, and `Agent.workspaces`. There is no separate `Agency` prompt section. Notepad no longer accepts unused PubSub or LLM constructor arguments. Its `get_current_page()` reads the selected page without an argument.
