# Simple Agent

> [!warning]
> Simple agent can run commands on your machine. Be aware of the potential for it to make modifications to your system.

![Aug-16-2024 11-27-09](https://github.com/user-attachments/assets/3bb43a56-0501-4759-b3b0-ac459f53f692)

> [!note]
> Simple Agent is still a work in progress! There will likely be bugs and missing features, if you encounter them, please leave an issue!

This is an attempt to make a bare-bones, very simple agent based on LLMs and other technologies. The goal is to have a simple agent for use in various purposes:

1. Experimentation and benchmarking
2. Understanding and learning myself
3. Idk but having three points sounds more solid

## How it works

So put simply, the agent works on a constant loop, involving three main steps:

1. Perception
2. Inference
3. Action

The perception stage is characterized by a combination of 1. environmental analysis, 2. memory recall, and 3. agency or will towards a goal. The inference stage is the call to the API, where the model (right now only OpenAI models) is given the perception to reason about. The action stage is where the agent takes the output of the model, such as tool calls, and actually runs them.

## Prerequisites
To make Simple Agent work well, you'll need to meet the following prerequisites:
- Python 3.11
- Access to an LLM (Anthropic or OpenAI only by default (for now))

## How to use it

This repository is a fairly straightforward Python project. **You will need to have Python installed**, and I used Python 3.10 on MacOS, so I know that this version worked. If you use a different version, or use a platform other than MacOS and notice bugs, please let me know in an issue. You should be able to clone the repository, install dependencies (in a virtual environment if you choose), fill in the `.env` file, and run `simple-agent.py` to see it work.

1. Start by cloning the repository (or forking if you want to extend it a lot):

```bash
   git clone https://github.com/AidanTilgner/Simple-Agent.git
```

2. Then, navigate into the directory:

```bash
cd Simple-Agent
```

3a. (Optional) If you choose to use a virtual environment, you can instantiate it like so:

```bash
python -m venv venv
```

Then, activate the virtual environment:

```bash
source ./venv/bin/activate
```

3b. Install the dependencies:

```bash
pip install -r requirements.txt
```

4. Copy the `.env.example` file to `.env` and fill in the necessary information. You will need an OpenAI API key, which you can get from the [OpenAI website](https://platform.openai.com/api-keys).

(on MacOS or Linux):

```bash
cp .env.example .env
```

5. Run the program:

```bash
python simple-agent.py
```

6. To exit the program, you can use `Ctrl+C`, or type "exit".

That's it! You should see the agent start up, and you can ask it to do things using it's tools.

## Advanced Usage

You might want to extend or enhance the functionality of the tool, and if you do I'd love to hear how it goes! Or even submit a PR if you think it should be a default.

**Modifying Prompts**
You can modify prompts in the `agent.py`, `agency.py`, `memory.py`, and `environment.py` files. These files are where you'll find the actual programmatic generation logic for several aspects of the prompt. Things might change over time, so I'm not going to go into specifics here. But you might find that you can gain further behavior by modifying these files.

The `system_prompt.md` file is the source of the agent's system prompt, which can be modified as well.

**Using Different Models**
You might find that using different models is more useful. However, each provider exposes a slightly different interface for their models, making use of them a less-than-straightforward process in some cases. With that said, the `LLM` class allows for easy adaptation of the Simple Agent standard data structures to different APIs. Currently, Openai, Anthropic, and Gemini APIs are supported by default, in corresponding files in `llms/`. `MODEL_CHOICE` will allow you to set which provider you'd like to use, and then setting the corresponding `[PROVIDER]_MODEL` and `[PROVIDER]_API_KEY` environment variables in `.env` will allow you to configure the specific model.

**Adding Tools**
The `tools/` directory is where you'll find tools. Each tool must fit the `Tool` class, in order to be used by the agent. Check out `toolbox.py` to see a current list of included tools, and how they are used. If you want to add a tool, you can use the `write_file.py`, `read_file.py`, and `send_message_to_user.py` tools as a reference. More tools will be included in the future. This is another area where PRs are welcome.

## Roles
Roles are identities which can be adopted by the agent. They are are context-dependent, and each have their own set of tools which are provided to the agent. The agent can switch between roles at any time. `INCLUDED_ROLES` are defined in the `roles/config.py` file. You can learn more about roles in the [roles tutorial](/documentation/adding-a-role.md).

I'm still working on the roles system, bare with me. But you can see the beginnings of it in the `roles/` directory. Currently these roles are supported:
- `Helpful Assistant`: A helpful assistant ready to take your questions and provide answers.
- `Developer`: A dedicated developer with specialized tools for software development, testing, and debugging.
- `Researcher`: A dedicated researcher with specialized tools for web research, data analysis, and documentation.

> [!note]
> To switch between roles, just ask the agent to do it. For example, you can say "I'd like some help with research...", or more specifically "I'd like to switch to the researcher role." You'll see an "As a [ROLE]" message to confirm.

## Adding Memory
Check out [the tutorial](/documentation/adding-memory.md) to learn how to add memory to Simple Agent. This isn't necessary for the agent to work, however allows its memory to persist between sessions.

## Roadmap
I'm looking to polish this project into a really solid framework for building agents. But it's going to need to stay as a core, rather than a full-fledged agent. To make a full-fledged agent, this should be forked. In it's current state, it's usable and functional, and extensible.

## Features
**Existing Features**
- [x] Implement memory and learning through [Simple Vector Store](https://github.com/AidanTilgner/Simple-Vector-Store)
- [x] Allow selection of additional models
- [x] Get better editing
- [x] "Modes" that the agent can switch into for specialized operations, with different tool layouts

**WIP (kinda) Features**
These are things that I currently plan on doing or hope to do. If you have ideas for features or feadback, don't hesitate to open an issue so we can discuss it.
- [ ] A more robust benchmarking system through [Benchy](https://github.com/AidanTilgner/Benchy)
- [ ] A type of procedural memory
- [ ] A sort of plugin system
