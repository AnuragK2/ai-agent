# CLI AI Agent

A terminal coding agent written in Python. It streams LLM responses in a Rich TUI, runs a multi-turn tool loop, and ships a full builtin toolset (files, search, shell, web, memory, todos), specialized sub-agents, and project/user tool discovery.

This document describes the project **as it exists today**: what is built, how the pieces connect, how to run it, and what is still incomplete.

---

## Table of contents

1. [Overview](#overview)
2. [Features (current)](#features-current)
3. [Requirements](#requirements)
4. [Installation](#installation)
5. [Configuration](#configuration)
6. [Usage](#usage)
7. [Architecture](#architecture)
8. [Package guide](#package-guide)
9. [Event model](#event-model)
10. [Agentic loop](#agentic-loop)
11. [Tools system](#tools-system)
12. [Custom tool discovery](#custom-tool-discovery)
13. [Sub-agents](#sub-agents)
14. [LLM client](#llm-client)
15. [Context & prompts](#context--prompts)
16. [TUI](#tui)
17. [Utilities](#utilities)
18. [Build progress / roadmap](#build-progress--roadmap)
19. [Known limitations](#known-limitations)
20. [Extending the project](#extending-the-project)
21. [Project layout](#project-layout)

---

## Overview

| | |
|---|---|
| **Type** | CLI coding agent |
| **Language** | Python 3.14+ |
| **CLI** | [Click](https://click.palletsprojects.com/) |
| **UI** | [Rich](https://rich.readthedocs.io/) |
| **LLM API** | OpenAI-compatible Chat Completions (`openai` SDK) |
| **Config** | Pydantic models + layered TOML + `AGENT.MD` |
| **Entry point** | `main.py` |

High-level flow:

```text
User (prompt or interactive REPL)
        │
        ▼
   main.py / CLI
        │  load_config → validate
        │  map AgentEvent → TUI
        ▼
      Agent
        │
      Session
   ┌────┴────┬──────────────┐
   ▼         ▼              ▼
LLMClient  ContextManager  ToolRegistry
   │         │              │
   │         │              ├── builtins (read/write/edit/shell/…)
   │         │              ├── subagents (investigator, reviewer)
   │         │              └── discovered tools ({cwd}/.ai-agent/tools, user config/tools)
   │         └── system + chat history + memory
   └── AsyncOpenAI (stream + tools)
```

---

## Features (current)

**Working today**

- Single-shot prompts and interactive REPL
- Multi-turn agentic loop (continues after tool results until no tools / `max_turns`)
- Streaming assistant text into the terminal
- Tool calls with Rich panels (start + complete), including diffs, shell output, search summaries
- Full builtin toolset: files, search, shell, web, todos, memory
- Sub-agents: `codebase_investigator`, `code_reviewer` (isolated Agent runs with restricted tools)
- Custom tool discovery from `{cwd}/.ai-agent/tools/*.py` and the user config `tools/` directory
- OpenAI-compatible provider via `Config` (`api_key`, `base_url`, model name)
- Layered config loading (user TOML → project TOML → `AGENT.MD`)
- Startup config validation (`OPENAI_API_KEY` / `API_KEY`, cwd)
- Persistent user memory (`user_memory.json` under the OS data dir)
- System prompt with environment, tool guidelines, security, and optional developer/user instructions
- Token counting / truncation helpers via `tiktoken`
- Path resolution and binary-file detection for tools

**Scaffolded / advertised but not fully wired**

- Slash commands advertised in the welcome screen (`/help`, `/config`, `/approval`, `/model`, `/exit`)
- Tool confirmation / approval UX for mutating tools (`get_confirmation` exists; CLI does not prompt yet)

---

## Requirements

- Python **3.14+** (developed against 3.14.x)
- An OpenAI-compatible API key
- Dependencies listed in `requirements.txt`

Main libraries:

| Package | Role |
|---------|------|
| `openai` | Chat Completions (async) |
| `click` | CLI parsing |
| `rich` | Themed console, panels, syntax |
| `pydantic` | Config + tool parameter schemas |
| `tiktoken` | Token counting / truncation |
| `python-dotenv` | Load `.env` |
| `platformdirs` | OS user config / data directories |
| `httpx` | `web_fetch` |
| `ddgs` / `duckduckgo-search` | `web_search` |

---

## Installation

```bash
cd cli-aiagent
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Create a `.env` in the project root (gitignored), or copy `.env.example`:

```env
OPENAI_API_KEY=sk-...
# Optional — Config.base_url currently reads BASE_URL
BASE_URL=https://api.openai.com/v1

# Also supported as an alternate key name for validation / client:
# API_KEY=sk-...

# Optional OpenRouter (or any compatible gateway)
# OPENROUTER_API_KEY=...
# Set BASE_URL=https://openrouter.ai/api/v1 when using OpenRouter
```

> **Note:** `Config.api_key` accepts `OPENAI_API_KEY` or `API_KEY`. `Config.base_url` reads `BASE_URL` only (not `OPENAI_BASE_URL`).

---

## Configuration

### Models (`config/config.py`)

- **`ModelConfig`**: `name` (default `gpt-4o-mini`), `temperature` (0–2), optional `context_window`
- **`ShellEnvironmentPolicy`**: env scrubbing for shell (`exclude_patterns`, `set_vars`, …)
- **`Config`**:
  - `model`, `cwd`, `shell_environment`
  - `max_turns` (default `100`), `max_tool_output_tokens` (default `50_000`)
  - `allowed_tools` — if set, registry exposes only those tool names (used by sub-agents)
  - `developer_instructions`, `user_instructions`, `debug`
  - Properties: `api_key`, `base_url`, `model_name`, `temperature`
  - `validate()` → list of error strings (missing API key, missing cwd)
  - `to_dict()` → JSON-mode dump (used when spawning sub-agent configs)

### Load order (`config/loader.py`)

`load_config(cwd)` merges layers:

1. **System TOML** — `platformdirs.user_config_dir('.ai-agent')/config.toml`
2. **Project TOML** — `{cwd}/.ai-agent/config.toml` (deep-merged over system)
3. **`cwd`** — set from the CLI `--cwd` / process cwd if not already in TOML
4. **`AGENT.MD`** — if `developer_instructions` is not already set, contents of `{cwd}/AGENT.MD` are used
5. Build `Config(**config_dict)`

Invalid TOML raises `ConfigError` (or is skipped with a warning for system/project files during merge).

User data (e.g. memory) lives under `platformdirs.user_data_dir('cli-aiagent')`.

### Example project config

`.ai-agent/config.toml`:

```toml
debug = true
max_turns = 50

[model]
name = "gpt-4o-mini"
temperature = 0.7
```

### CLI option

`--cwd` / `-c` sets which project root is used for config / `AGENT.MD` / `{cwd}/.ai-agent/tools` and becomes `Config.cwd` (tools resolve paths against it).

---

## Usage

```bash
# Interactive REPL (welcome panel + prompt loop)
python main.py

# One-shot prompt
python main.py "read main.py file for me"

# Load config relative to another project root
python main.py --cwd /path/to/project
python main.py -c /path/to/project "summarize this repo"
```

**Interactive behavior**

- Prints a welcome panel (model, cwd, advertised commands)
- Prompt: `You:`
- Empty input is ignored
- Ctrl+C prints a hint (`Use /exit to quit`) — slash commands are not implemented yet; use Ctrl+D / EOF to leave
- EOF (Ctrl+D) ends the session

**One-shot behavior**

- Runs a single agent session (may include many tool turns)
- Exits with code `1` if there is no final text response

---

## Architecture

### Runtime pipeline

```text
┌─────────────────────────────────────────────────────────────┐
│ main.py                                                     │
│  load_dotenv → load_config → Config.validate                │
│  CLI.run_single / run_interactive                           │
│  for event in Agent.run(...):  dispatch → TUI               │
└───────────────────────────┬─────────────────────────────────┘
                            │ AgentEvent stream
┌───────────────────────────▼─────────────────────────────────┐
│ Agent(config)                                               │
│  Session: registry → discover_all → ContextManager          │
│  _agentic_loop: chat → tools → chat … until done/max_turns  │
└─────────────────────────────────────────────────────────────┘
```

### Design choices

| Choice | Why |
|--------|-----|
| Event-driven agent | UI stays thin; CLI maps events to Rich widgets |
| Session owns clients/tools/context | One place for per-run wiring and lifecycle |
| Filesystem tool discovery | Drop a `Tool` subclass into `.ai-agent/tools/` without editing the registry |
| OpenAI-compatible client | One code path for OpenAI, OpenRouter, local gateways |
| Pydantic tool schemas | Validation + OpenAI function JSON schema from one model |
| `allowed_tools` on Config | Sub-agents get a restricted tool surface without a separate registry type |
| Layered TOML config | User defaults + per-project overrides |
| Rich TUI | Streaming text + structured tool panels without a full TUI framework |

---

## Package guide

### `main.py`

- **`CLI`**: owns `TUI`, optional `Agent`, `Config`
- **`run_single(message)`**: one agent session
- **`run_interactive()`**: welcome + input loop (session persists across turns)
- **`_process_message(message)`**: consumes `AgentEvent`s and drives the TUI
- **`_get_tool_kind(name)`**: looks up tool kind for panel styling
- **`main(prompt, cwd)`**: Click entrypoint

### `agent/`

| File | Responsibility |
|------|----------------|
| `agent.py` | `Agent` orchestration, multi-turn `_agentic_loop`, async context manager |
| `session.py` | `Session` — LLM client, registry, discovery, context, turn counter, memory load |
| `events.py` | `AgentEventType`, `AgentEvent` + factory helpers |

### `client/`

| File | Responsibility |
|------|----------------|
| `llm_client.py` | `LLMClient(config)` — AsyncOpenAI, streaming / non-streaming, retries |
| `response.py` | `StreamEvent`, `ToolCall`, `TokenUsage`, argument parsing |

### `config/`

| File | Responsibility |
|------|----------------|
| `config.py` | `ModelConfig`, `ShellEnvironmentPolicy`, `Config` |
| `loader.py` | TOML merge, `AGENT.MD`, `load_config`, `get_data_dir` |

### `context/`

| File | Responsibility |
|------|----------------|
| `manager.py` | `MessageItem`, `ContextManager` (history for the model) |

### `tools/`

| File | Responsibility |
|------|----------------|
| `base.py` | `Tool`, `ToolKind`, `ToolResult`, `FileDiff`, confirmation helpers |
| `registry.py` | `ToolRegistry`, `create_default_registry()` (builtins + subagents) |
| `subagents.py` | `SubagentTool`, definitions, `get_default_subagents_definitions()` |
| `discovery.py` | `ToolDiscoveryManager` — load `Tool` subclasses from project/user tool dirs |
| `builtin/*` | Individual tools (see [Tools system](#tools-system)) |

### `ui/`

| File | Responsibility |
|------|----------------|
| `tui.py` | Theme, welcome, streaming, tool panels (read/shell/grep/diff/…) |

### `prompts/`

| File | Responsibility |
|------|----------------|
| `system.py` | `get_system_prompt(config, user_memory, tools)` |

### `utils/`

| File | Responsibility |
|------|----------------|
| `errors.py` | `AgentError`, `ConfigError` |
| `paths.py` | `resolve_path`, `display_path_rel_to_cwd`, `is_binary_file`, … |
| `text.py` | `count_tokens`, `truncate_text`, tokenizer helpers |

---

## Event model

`Agent` yields `AgentEvent` values. The CLI never talks to the LLM or tools directly for display — it only reacts to events.

| Type | When | Typical TUI action |
|------|------|--------------------|
| `AGENT_START` | User message accepted | (unused in UI today) |
| `TEXT_DELTA` | Streamed token/chunk | `begin_assistant` once, then `stream_assistant_delta` |
| `TEXT_COMPLETE` | Full assistant text for the turn | `end_assistant` |
| `TOOL_CALL_START` | Tool about to run | Panel with args (“running…”) |
| `TOOL_CALL_COMPLETE` | Tool finished | Success/fail panel; specialized views per tool |
| `AGENT_ERROR` | Client/tool/orchestration error (incl. max turns) | `print_error` |
| `AGENT_END` | Run finished | (emitted; UI does not special-case it yet) |

---

## Agentic loop

Current `_agentic_loop` (simplified):

```text
for turn in range(max_turns):
  1. Stream chat.completions (with tool schemas from registry)
  2. Accumulate TEXT_DELTA → TEXT_COMPLETE when text present
  3. Collect tool calls; persist assistant message (content + tool_calls as JSON)
  4. If no tool calls → return (done)
  5. For each tool call:
       emit TOOL_CALL_START
       ToolRegistry.invoke(..., cwd=config.cwd)
       emit TOOL_CALL_COMPLETE
       append tool role message
  6. Continue loop with updated context
else:
  emit AGENT_ERROR (max turns exceeded)
```

`Config.max_turns` is enforced. Interactive mode keeps one `Agent`/`Session` across user messages, so conversation history accumulates.

---

## Tools system

### Abstraction (`tools/base.py`)

- **`ToolKind`**: `READ`, `WRITE`, `SHELL`, `NETWORK`, `MEMORY`, `MCP`
- **`ToolInvocation`**: `params`, `cwd`
- **`ToolResult`**: `success`, `output`, `error`, `metadata`, `truncated`, optional `diff` / `exit_code`
- **`Tool` (ABC)**: name, description, kind, Pydantic `schema`, `execute()`, OpenAI schema export, optional confirmation for mutating tools

### Registry

```python
registry = create_default_registry(config)  # builtins + default subagents
# Session then runs ToolDiscoveryManager.discover_all() before building context
schemas = registry.get_schemas()            # filtered by config.allowed_tools if set
result  = await registry.invoke("read_file", {"path": "main.py"}, config.cwd)
```

### Builtin tools

| Tool | Kind | Purpose |
|------|------|---------|
| `read_file` | READ | Read file with optional offset/limit; numbered lines; size/token caps |
| `write_file` | WRITE | Create/overwrite files |
| `edit` | WRITE | Surgical search/replace edits (`old_string` / `new_string`) |
| `list_dir` | READ | List directory entries |
| `grep` | READ | Regex search across files |
| `glob` | READ | Find files by glob pattern |
| `shell` | SHELL | Run shell commands (blocked dangerous patterns, timeout, env policy) |
| `web_search` | NETWORK | DuckDuckGo search via `ddgs` |
| `web_fetch` | NETWORK | HTTP fetch URL content via `httpx` |
| `todos` | MEMORY | In-session task list (add/complete/list/…) |
| `memory` | MEMORY | Persistent key/value preferences in user data dir |

### Adding a builtin tool

1. Subclass `Tool` in `tools/builtin/`
2. Define a Pydantic params model as `schema`
3. Implement `async def execute(self, invocation) -> ToolResult`
4. Export the class from `get_all_builtin_tools()` in `tools/builtin/__init__.py`

For project-local tools that should not live in the repo package, use [custom tool discovery](#custom-tool-discovery) instead.

---

## Custom tool discovery

`ToolDiscoveryManager` (`tools/discovery.py`) loads extra tools at session start, **after** builtins/sub-agents are registered and **before** `ContextManager` is built (so discovered tools appear in both the OpenAI tool schemas and the system prompt).

### Search paths

1. **Project** — `{cwd}/.ai-agent/tools/*.py`
2. **User** — `{platformdirs.user_config_dir('.ai-agent')}/tools/*.py`  
   (macOS: `~/Library/Application Support/.ai-agent/tools/`)

Files whose names start with `__` are skipped. Each `.py` file is imported dynamically; every `Tool` subclass defined in that module is instantiated with `Config` and registered via `register_tool`. Load failures are logged and skipped so a broken custom tool does not crash the session.

### Writing a discovered tool

Drop a file such as `.ai-agent/tools/test_tool.py`:

```python
from pydantic import BaseModel, Field
from tools.base import Tool, ToolInvocation, ToolResult, ToolKind

class TestToolParams(BaseModel):
    message: str = Field(..., description="The message to echo back")

class TestTool(Tool):
    name = "test_tool"
    description = "A test tool that echoes back the message provided."
    kind = ToolKind.READ
    schema = TestToolParams

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = TestToolParams(**invocation.params)
        return ToolResult.success_result(params.message)
```

Requirements:

- Subclass `Tool` (not `Tool` itself), with `name`, `description`, `kind`, and `schema`
- Constructor must accept `config: Config` (the base `Tool.__init__` already does)
- `execute` must return a `ToolResult` (`success_result` / `error_result`)
- The class must be defined in the discovered file (`obj.__module__` must match the loaded module)

This repo includes `.ai-agent/tools/test_tool.py` as an example echo tool.

---

## Sub-agents

Sub-agents are registered as normal tools named `subagent_<name>`. Invoking one spins up a nested `Agent` with a cloned config (often with a lower `max_turns` and a restricted `allowed_tools` list), runs until completion/timeout/error, and returns a summary string to the parent.

| Definition | Tool name | Default tools | Notes |
|------------|-----------|---------------|-------|
| `CODEBASE_INVESTIGATOR` | `subagent_codebase_investigator` | `read_file`, `grep`, `glob`, `list_dir` | Explore structure/patterns; max 20 turns; 600s timeout |
| `CODE_REVIEWER` | `subagent_code_reviewer` | `read_file`, `grep`, `list_dir`, `glob` | Review quality/bugs; max 10 turns; 300s timeout |

Params: `{ "goal": "..." }`.

The system prompt lists sub-agents separately and advises using them for broad exploration/review, not for simple one-shot greps.

---

## LLM client

`LLMClient` (`client/llm_client.py`):

- Constructed with `Config`; lazy `AsyncOpenAI` from `config.api_key` / `config.base_url`
- `chat_completion(messages, tools=None, stream=True)` → async generator of `StreamEvent`
- Uses `config.model.name` for the API `model` field
- Streaming: text deltas, tool-call assembly, `MESSAGE_COMPLETE` (+ optional usage)
- Non-streaming path available
- Retries with backoff on rate-limit / connection errors

`client/response.py` defines the normalized stream types (`TextDelta`, `ToolCall`, `StreamEventType`, etc.).

---

## Context & prompts

### `ContextManager`

Builds the message list sent to the API:

1. System message from `get_system_prompt(config, user_memory, tools)`
2. Conversation: user / assistant / tool messages
3. Assistant tool-call payloads when tools were requested (`arguments` as JSON strings)

Token counts are stored per message via tiktoken using `config.model.name`.

### System prompt (`prompts/system.py`)

Composed sections covering:

- Agent identity
- Environment (date, OS, cwd, shell)
- Tool usage guidelines (including sub-agents and any discovered tools when present)
- `AGENTS.md` conventions (prompt guidance; loader still uses `AGENT.MD` for developer instructions)
- Security guidelines
- Optional remembered context from persistent memory
- `developer_instructions` / `user_instructions` when set
- Operational / coding guidelines

### Session memory

On session start, `Session` loads `user_memory.json` from the data dir (if present) and injects a summary into the system prompt. The `memory` tool reads/writes the same store.

---

## TUI

`ui/tui.py` provides:

- **`AGENT_THEME`** — Rich styles for roles, tools, borders
- **`print_welcome`** — rounded welcome panel
- **Assistant streaming** — rule header + live deltas
- **`tool_call_start`** — args table, kind-colored border, short call id, “running…”
- **`tool_call_complete`** — specialized rendering for:
  - `read_file` — syntax-highlighted code
  - `shell` — command + exit code + output
  - `list_dir` / `grep` / `glob` / `web_*` — summary metadata + body
  - `write_file` / `edit` — unified diffs when available
- **`print_error`**
- Relative path display via `display_path_rel_to_cwd`

---

## Utilities

| Module | Highlights |
|--------|------------|
| `utils/errors.py` | `AgentError`, `ConfigError` (optional `config_key` / `config_file`) |
| `utils/paths.py` | Resolve relative paths, display relative-to-cwd, binary sniff, parent ensure |
| `utils/text.py` | Tokenizer lookup, `count_tokens`, line/char-aware `truncate_text` |

---

## Build progress / roadmap

Rough chronological capability build-up reflected in the codebase:

1. **LLM client** — async OpenAI-compatible streaming + tool-call parsing + retries
2. **Agent events** — typed event stream for UI decoupling
3. **Context manager** — chat history + system prompt wiring
4. **Tool framework** — ABC, kinds, registry, OpenAI schema export
5. **File / search / shell / web tools** — full builtin set with TUI views
6. **Multi-turn agentic loop** — continue after tools; honor `max_turns`
7. **Session** — config-aware client, registry, context, memory load
8. **Config system** — Pydantic `Config`, TOML layers, `AGENT.MD`, startup validation
9. **Sub-agents** — nested Agent runs with restricted tools
10. **Persistent memory + todos**
11. **Path / token helpers** — shared by tools and UI
12. **Custom tool discovery** — load `Tool` subclasses from `.ai-agent/tools/` and the user config tools dir

**Next natural milestones**

- Implement slash commands (at least `/exit`, `/help`, `/model`)
- Wire tool confirmation / approval for mutating tools
- Pass `temperature` (and related sampling params) through to the API
- Unify base URL env vars (`BASE_URL` vs `OPENAI_BASE_URL`)
- Context window enforcement / session persistence across process restarts
- Tests + packaging (`pyproject.toml`)

---

## Known limitations

1. **Slash commands** are advertised but not implemented (EOF to quit interactive mode).
2. **No approval UX** — mutating tools can run without an interactive confirm step.
3. **`temperature` is not sent** to the chat completions API yet (config field exists).
4. **`BASE_URL` vs `OPENAI_BASE_URL`** — client uses `Config.base_url` → `BASE_URL` only.
5. **`AGENT.MD` vs `AGENTS.md`** naming inconsistency between loader and prompt text.
6. **No tests / packaging** yet (`.env.example` exists).
7. Interactive mode does not treat a missing final text reply as a hard error (by design after tool-only turns).
8. Discovered tools that fail to import are skipped (logged); there is no TUI warning.

---

## Extending the project

### Add another sub-agent

1. Define a `SubAgentDefinition` in `tools/subagents.py`
2. Append it to `get_default_subagents_definitions()`
3. Restrict `allowed_tools` / `max_turns` / `timeout_seconds` as needed

### Register more tools

- **Builtin:** follow existing tools under `tools/builtin/` and export from `get_all_builtin_tools()`.
- **Project/user:** add a `Tool` subclass under `.ai-agent/tools/` (see [custom tool discovery](#custom-tool-discovery)). Restart the CLI so `Session` rediscovers files.

Mark mutating tools with `ToolKind.WRITE` / `SHELL` / `NETWORK` and implement `get_confirmation()` when you add an approval UX.

### Wire slash commands

Handle `/exit`, `/help`, etc. in `CLI.run_interactive` before calling `_process_message`.

---

## Project layout

```text
cli-aiagent/
├── main.py                 # Click entry + CLI ↔ TUI event bridge
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
├── .ai-agent/
│   ├── config.toml         # project config
│   └── tools/
│       └── test_tool.py    # example discovered tool
├── agent/
│   ├── agent.py            # Agent + multi-turn agentic loop
│   ├── session.py          # Session (client, registry, discovery, context)
│   └── events.py           # AgentEvent types
├── client/
│   ├── llm_client.py       # AsyncOpenAI wrapper
│   └── response.py         # Stream / tool DTOs
├── config/
│   ├── config.py           # Pydantic settings
│   └── loader.py           # TOML + AGENT.MD merge
├── context/
│   └── manager.py          # Conversation state
├── prompts/
│   └── system.py           # System prompt
├── tools/
│   ├── base.py             # Tool ABC
│   ├── registry.py         # Registry + defaults
│   ├── discovery.py        # Load Tool subclasses from disk
│   ├── subagents.py        # SubagentTool + definitions
│   └── builtin/
│       ├── __init__.py
│       ├── read_file.py
│       ├── write_file.py
│       ├── edit_file.py
│       ├── list_dir.py
│       ├── grep.py
│       ├── glob.py
│       ├── shell.py
│       ├── web_search.py
│       ├── web_fetch.py
│       ├── todo.py
│       └── memory.py
├── ui/
│   └── tui.py              # Rich UI
└── utils/
    ├── errors.py
    ├── paths.py
    └── text.py
```

---

## License

Not specified yet. Add a license file when you publish or share the repo.
