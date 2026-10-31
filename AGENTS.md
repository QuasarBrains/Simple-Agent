## Codebase Philosophy

The overarching of Simple Agent is to be a seed repository for agentic systems, meaning that it is designed to be a minimal, lighweight, and effective core that can be tweaked and extended for specific use-cases. Therefore, our architectural goal favors modularity, extensibility, codebase maintainability, and well-defined abstractions of variable interfaces (e.g. LLMs, Embedding models). Additionally, we sacrifice raw performance capability on specific tasks for broad out-of-the-box utility, with extreme customizability toward particular domain-specific designs. The goal is that the code itself can change relatively easily for expirimentation and tailoring, but also that out-of-the-box customization isn't daunting either (e.g. tool definition, new roles, etc).

## Architecture

### Agent Anatomy

The architecture of Simple Agent follows a continuous loop where an agent percieves its environment, reasons about what it ought to do, takes an action, and sees the result of its action as a reflection of the broader environment. This perceive -> reason -> act loop drives the agent toward its goal. More specifically, the agent's perspective on the world breaks down into a few key abstracted modules:

- Perception: any relevant environmental stimuli to the task, e.g. user messages, environment information, results of previous tool calls, etc.
- Memory: a built-in memory module allows the agent to store relevant information as editable memories, which automatically resurface using RAG
- Agency: acts as the agent's innate drive toward a particular goal, for now this represents the agent's to-do list

The important note about the environmental perception building is that it is a continuous event, not something that gets triggered by a specific stimuli (like user input). Rather, a user can continuously send messages to the agent, which enter a queue through the environment module, and are pulled from the queue on the next agent iteration. This is meant to stay more true to the continuous aspect of the environment's evolution. So as the environment updates, the program keeps track of this, but the agent perceives this along with the "beat" of its own "conscious" processing.

With the perception of the model built, there are two primary stages of agent execution:

1. Reasoning: the agent uses its environmental perception, memory, and agency to determine the best course of action toward the current step
2. Action: the model's tool calls are executed with the provided parameters, and the results populate the continuous environment feed

Once action is complete, the loop restarts at building perception. This architecture is meant to be kept simple, with the key modules of building the "mind" (prompt) of the agent each being abstracted to manage their own complexity. The agent is granted tools defined for a broad set of tasks, and a meta-layer of a "Role" system also exists allowing definition of custom "Roles" the agent can adopt and switch between, which each have their own unique set of tools and system-level prompt guidance.

## Tests

The goal of agent-written tests during development is to act as deterministic guidestones for implementation-side correctness of inferred intent. However, they should act as development utilities, not long-term suite-affecting tests. Therefore, agents are instructed _not_ to leave long-lived tests unless explicitly instructed or granted permission. However, tests are permitted to be written and run during the development process, and testing recommendations may be provided after an implementation run.

- Use unit and integration tests to check unit implementation, not to act as regression tests
- After an implementation run, delete any tests added that haven't been approved for keeping
- Treat testing as a separate step from implementation, they should never coincide
- Either test cases can be defined first (red, green, refactor), or iteration on implementation can happen first with retroactive testing, in accordance w/ user preference

## Comments

The goal of comments is to make the code they represent skimable, not to explain what the code should already be explaining. Therefore, when adding comments, favor concise, readable summaries of the area of code that the comment represents (function, struct, etc.). This way, a human can glance at the comment to understand whether this area is important toward their goal or not.

- Write source-code comments as formatted block comments (`/* ... */`), with each content line prefixed by `*`.
- Keep comments short and plain. Explain what the code does or a necessary constraint in direct language.
- For functions, describe the behavior without repeating or referring to the function name; avoid self-referential phrases such as “Report ...”.
- Do not add comments that merely restate the code. Preserve required legal notices and use the native comment syntax for configuration and template files.
- When making edits to source code, ensure that associated comments are tweaked accordingly _if they need to be_

## Design

The design of simple
