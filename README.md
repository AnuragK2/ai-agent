# CLI AI Agent

A terminal coding agent written in Python. It streams LLM responses in a Rich TUI, can call tools (currently `read_file`), and is designed to grow into a fuller agentic CLI (edit/shell/search, slash commands, multi-turn tool loops, layered config).

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
12. [LLM client](#llm-client)
13. [Context & prompts](#context--prompts)
14. [TUI](#tui)
15. [Utilities](#utilities)
16. [Build progress / roadmap of work done](#build-progress--roadmap-of-work-done)
17. [Known limitations](#known-limitations)
18. [Extending the project](#extending-the-project)
19. [Project layout](#project-layout)

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
   ┌────┴────┬──────────────┐
   ▼         ▼              ▼
LLMClient  ContextManager  ToolRegistry
   │         │              │
   │         │              └── read_file (builtin)
   │         └── system + chat history
   └── AsyncOpenAI (stream + tools)
```

---

## Features (current)

**Working today**

- Single-shot prompts and interactive REPL
- Streaming assistant text into the terminal
- Tool calls with Rich panels (start + complete)
- Syntax-highlighted `read_file` output (Monokai, language by extension)
- OpenAI-compatible provider (OpenAI, OpenRouter, etc. via base URL)
- Layered config loading (user TOML → project TOML → `AGENT.MD`)
- Startup config validation (`API_KEY`, cwd)
- Welcome panel in interactive mode
- Token counting / truncation helpers via `tiktoken`
- Path resolution and binary-file detection for tools

**Scaffolded but not fully wired**

- Multi-turn agent loop after tools (tool results are stored; model is not called again yet)
- Passing `Config` into `Agent` / `LLMClient` (model, temperature, `max_turns`, instructions)
- Slash commands advertised in the welcome screen (`/help`, `/config`, `/approval`, `/model`, `/exit`)
- Additional tools mentioned in the system prompt (shell, edit, write, grep, memory, …)
- Tool confirmation / approval flow for mutating tools

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
| `platformdirs` | OS user config directory |

---

## Installation

```bash
cd cli-aiagent
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Create a `.env` in the project root (gitignored):

```env
# Used by LLMClient today
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1

# Optional OpenRouter (or any compatible gateway)
# OPENROUTER_API_KEY=...
# OPENROUTER_BASE_URL=https://openrouter.ai/api/v1

# Used by Config.validate() at startup
API_KEY=sk-...
# BASE_URL=https://api.openai.com/v1
```

> **Note:** Startup validation reads `API_KEY` / `BASE_URL`, while `LLMClient` reads `OPENAI_API_KEY` / `OPENAI_BASE_URL`. Until those are unified, set both (or point them at the same value).

---

## Configuration

### Models (`config/config.py`)

- **`ModelConfig`**: `name` (default `gpt-4o-mini`), `temperature` (0–2), optional `context_window`
- **`Config`**:
  - `model`, `cwd`, `max_turns` (default `100`), `max_tool_output_tokens` (default `50_000`)
  - `developer_instructions`, `user_instructions`, `debug`
  - Properties: `api_key`, `base_url`, `model_name`, `temperature`
  - `validate()` → list of error strings (missing `API_KEY`, missing cwd, etc.)

### Load order (`config/loader.py`)

`load_config(cwd)` merges layers:

1. **System TOML** — `platformdirs.user_config_dir('cli-aiagent')/config.toml`  
   (e.g. macOS: `~/Library/Application Support/cli-aiagent/config.toml`)
2. **Project TOML** — `{cwd}/.ai-agent/config.toml` (deep-merged over system)
3. **`AGENT.MD`** — if `developer_instructions` is not already set, contents of `{cwd}/AGENT.MD` are used
4. Build `Config(**config_dict)`

Invalid TOML raises `ConfigError` (or is skipped with a warning for system/project files during merge).

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

`--cwd` / `-c` affects **which config / `AGENT.MD` are loaded**. It does not currently change process `Path.cwd()` used by tools.

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
- Ctrl+C prints a hint (`Use /exit to quit`) — `/exit` itself is not implemented yet
- EOF (Ctrl+D) ends the session

**One-shot behavior**

- Runs a single agent turn
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
│ Agent                                                       │
│  ContextManager ← user / assistant / tool messages          │
│  LLMClient.chat_completion (stream + tool schemas)          │
│  ToolRegistry.invoke for each tool call                     │
└─────────────────────────────────────────────────────────────┘
```

### Design choices

| Choice | Why |
|--------|-----|
| Event-driven agent | UI stays thin; CLI maps events to Rich widgets |
| OpenAI-compatible client | One code path for OpenAI, OpenRouter, local gateways |
| Pydantic tool schemas | Validation + OpenAI function JSON schema from one model |
| Layered TOML config | User defaults + per-project overrides |
| Rich TUI | Streaming text + structured tool panels without a full TUI framework |

---

## Package guide

### `main.py`

- **`CLI`**: owns `TUI`, optional `Agent`
- **`run_single(message)`**: one agent session
- **`run_interactive()`**: welcome + input loop
- **`_process_message(message)`**: consumes `AgentEvent`s and drives the TUI
- **`_get_tool_kind(name)`**: looks up tool kind for panel styling
- **`main(prompt, cwd)`**: Click entrypoint

### `agent/`

| File | Responsibility |
|------|----------------|
| `agent.py` | `Agent` orchestration, `_agentic_loop`, async context manager |
| `events.py` | `AgentEventType`, `AgentEvent` + factory helpers |

### `client/`

| File | Responsibility |
|------|----------------|
| `llm_client.py` | `LLMClient` — AsyncOpenAI, streaming / non-streaming, retries |
| `response.py` | `StreamEvent`, `ToolCall`, `TokenUsage`, argument parsing |

### `config/`

| File | Responsibility |
|------|----------------|
| `config.py` | `ModelConfig`, `Config` |
| `loader.py` | TOML merge, `AGENT.MD`, `load_config` |

### `context/`

| File | Responsibility |
|------|----------------|
| `manager.py` | `MessageItem`, `ContextManager` (history for the model) |

### `tools/`

| File | Responsibility |
|------|----------------|
| `base.py` | `Tool`, `ToolKind`, `ToolResult`, confirmation helpers |
| `registry.py` | `ToolRegistry`, `create_default_registry()` |
| `builtin/read_file.py` | `ReadFileTool` |
| `builtin/__init__.py` | `get_all_builtin_tools()` |

### `ui/`

| File | Responsibility |
|------|----------------|
| `tui.py` | Theme, welcome, streaming, tool panels, `read_file` syntax view |

### `prompts/`

| File | Responsibility |
|------|----------------|
| `system.py` | `get_system_prompt()` — identity, security, operational guidelines |

### `utils/`

| File | Responsibility |
|------|----------------|
| `errors.py` | `AgentError`, `ConfigError` |
| `paths.py` | `resolve_path`, `display_path_rel_to_cwd`, `is_binary_file` |
| `text.py` | `count_tokens`, `truncate_text`, tokenizer helpers |

---

## Event model

`Agent` yields `AgentEvent` values. The CLI never talks to the LLM or tools directly for display — it only reacts to events.

| Type | When | Typical TUI action |
|------|------|--------------------|
| `AGENT_START` | User message accepted | (optional / unused in UI today) |
| `TEXT_DELTA` | Streamed token/chunk | `begin_assistant` once, then `stream_assistant_delta` |
| `TEXT_COMPLETE` | Full assistant text for the turn | `end_assistant` |
| `TOOL_CALL_START` | Tool about to run | Panel with args (“running…”) |
| `TOOL_CALL_COMPLETE` | Tool finished | Success/fail panel; code view for `read_file` |
| `AGENT_ERROR` | Client/tool/orchestration error | `print_error` |
| `AGENT_END` | Run finished | (final response may be `None` after tool-only turns) |

---

## Agentic loop

Current `_agentic_loop` (simplified):

```text
1. Stream one chat.completions call (with tool schemas)
2. Accumulate TEXT_DELTA → optionally TEXT_COMPLETE
3. Collect TOOL_CALL_COMPLETE events into a list
4. Persist assistant message (content + tool_calls) in ContextManager
5. For each tool call:
     emit TOOL_CALL_START
     ToolRegistry.invoke(...)
     emit TOOL_CALL_COMPLETE
     append ToolResultMessage
6. Persist tool results in ContextManager
7. Stop   ← no second LLM call yet
```

**Implication:** After `read_file`, the file content is shown in the TUI and stored in context, but the model does not automatically produce a follow-up summary until the loop is extended to continue while tool calls remain.

`Config.max_turns` exists for a future multi-step loop but is not enforced yet.

---

## Tools system

### Abstraction (`tools/base.py`)

- **`ToolKind`**: `READ`, `WRITE`, `SHELL`, `NETWORK`, `MEMORY`, `MCP`
- **`ToolInvocation`**: `params`, `cwd`
- **`ToolResult`**: `success`, `output`, `error`, `metadata`, `truncated`
- **`Tool` (ABC)**: name, description, kind, Pydantic `schema`, `execute()`, OpenAI schema export, optional confirmation for mutating tools

### Registry

```python
registry = create_default_registry()  # registers all builtin tool classes
schemas = registry.get_schemas()      # for the LLM
result  = await registry.invoke("read_file", {"path": "main.py"}, Path.cwd())
```

### Builtin: `read_file`

| | |
|---|---|
| **Name** | `read_file` |
| **Kind** | `READ` |
| **Params** | `path` (required), `offset` (1-based, optional), `limit` (optional) |
| **Limits** | ~10MB file size; output capped (~25k tokens) with truncation |
| **Behavior** | Resolves path vs cwd; rejects binaries; UTF-8 then latin-1; numbered lines; metadata (`path`, `total_lines`, `shown_start`, `shown_end`) |

### Adding a tool

1. Subclass `Tool` in `tools/builtin/`
2. Define a Pydantic params model as `schema`
3. Implement `async def execute(self, invocation) -> ToolResult`
4. Export the class from `get_all_builtin_tools()` in `tools/builtin/__init__.py`

---

## LLM client

`LLMClient` (`client/llm_client.py`):

- Lazy `AsyncOpenAI` from `OPENAI_API_KEY` / `OPENAI_BASE_URL`
- `chat_completion(messages, tools=None, stream=True)` → async generator of `StreamEvent`
- Streaming: text deltas, tool-call assembly, `MESSAGE_COMPLETE` (+ optional usage)
- Non-streaming path available
- Retries with backoff on rate-limit / connection errors
- Model name currently hardcoded to **`gpt-4o-mini`** inside the client (not yet read from `Config`)

`client/response.py` defines the normalized stream types (`TextDelta`, `ToolCall`, `StreamEventType`, etc.).

---

## Context & prompts

### `ContextManager`

Builds the message list sent to the API:

1. System message from `get_system_prompt()`
2. Conversation: user / assistant / tool messages
3. Assistant tool-call payloads when tools were requested

Token counts are stored per message (tiktoken; model name currently hardcoded for counting).

### System prompt (`prompts/system.py`)

Composed sections covering:

- Agent identity (terminal coding agent)
- Project instruction files (`AGENTS.md` / related conventions — naming may differ from loader’s `AGENT.MD`)
- Security guidelines
- Operational / coding guidelines

Several sections (environment block, injecting `developer_instructions` / `user_instructions`, memory, compression) are present as comments or stubs and not fully active yet.

---

## TUI

`ui/tui.py` provides:

- **`AGENT_THEME`** — Rich styles for roles, tools, borders
- **`get_console()`** — singleton themed console
- **`print_welcome`** — rounded welcome panel
- **Assistant streaming** — rule header + live deltas
- **`tool_call_start`** — args table, kind-colored border, short call id, “running…”
- **`tool_call_complete`** — status icon; for successful `read_file`, header (`path • lines a-b of n`) + `Syntax` highlighting
- **`print_error`**
- Relative path display via `display_path_rel_to_cwd`

---

## Utilities

| Module | Highlights |
|--------|------------|
| `utils/errors.py` | `AgentError`, `ConfigError` (optional `config_key` / `config_file`) |
| `utils/paths.py` | Resolve relative paths, display relative-to-cwd, binary sniff (`NUL` in first 8KB) |
| `utils/text.py` | Tokenizer lookup, `count_tokens`, line/char-aware `truncate_text` |

---

## Build progress / roadmap of work done

Rough chronological capability build-up reflected in the codebase:

1. **LLM client** — async OpenAI-compatible streaming + tool-call parsing + retries  
2. **Agent events** — typed event stream for UI decoupling  
3. **Context manager** — chat history + system prompt wiring  
4. **Tool framework** — ABC, kinds, registry, OpenAI schema export  
5. **First tool** — `read_file` with limits, metadata, numbered output  
6. **CLI shell** — Click one-shot + interactive loop  
7. **Rich TUI** — themes, assistant stream, tool start/complete panels, syntax for reads  
8. **Config system** — Pydantic `Config`, TOML layers, `AGENT.MD`, startup validation  
9. **Path / token helpers** — shared by tools and UI  
10. **Error types** — config vs agent errors  

**Next natural milestones**

- Continue the agentic loop after tool results (until no tools / `max_turns`)
- Thread `Config` into `Agent` and `LLMClient` (model, keys, cwd, instructions)
- Unify env var names (`API_KEY` vs `OPENAI_API_KEY`)
- Implement slash commands (at least `/exit`, `/help`, `/model`)
- Add write/edit/shell/search tools with approval gates
- Persist sessions / enforce context window
- Tests + packaging (`pyproject.toml`) + `.env.example`

---

## Known limitations

1. **Single LLM round-trip** — tool results are not followed by another model call.  
2. **Loaded `Config` is mostly unused** by the running agent/client.  
3. **Env var mismatch** — validation vs client keys.  
4. **`--cwd` does not `chdir`** — tools still use process cwd.  
5. **Only `read_file` is registered** — system prompt describes more tools than exist.  
6. **Slash commands** are advertised but not implemented.  
7. **`AGENT.MD` vs `AGENTS.md`** naming inconsistency between loader and prompt text.  
8. **No tests / packaging / `.env.example` yet.**  
9. **Assistant `tool_calls.arguments`** are stringified with `str(dict)` in one path; OpenAI expects JSON strings (`json.dumps`) for reliability.  
10. Interactive mode does not treat a missing final text reply as a hard error (by design after tool-only turns), so success is judged by TUI output rather than return value.

---

## Extending the project

### Make the agent multi-step

In `agent/agent.py`, wrap `_agentic_loop` in `while True`, break when there are no tool calls (and optionally honor `max_turns`). Ensure assistant messages include proper OpenAI `tool_calls` JSON before appending tool role messages.

### Wire config through

- Construct `Agent(config)` / `LLMClient(config)`
- Use `config.model_name`, `config.temperature`, `config.api_key` / base URL
- Inject `developer_instructions` / `user_instructions` into `get_system_prompt` or context

### Register more tools

Follow the `ReadFileTool` pattern; mark mutating tools with `ToolKind.WRITE` / `SHELL` and implement `get_confirmation()` when you add an approval UX.

---

## Project layout

```text
cli-aiagent/
├── main.py                 # Click entry + CLI ↔ TUI event bridge
├── requirements.txt
├── .env                    # local secrets (gitignored)
├── .gitignore
├── README.md
├── agent/
│   ├── agent.py            # Agent + agentic loop
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
│   └── builtin/
│       ├── __init__.py
│       └── read_file.py
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
