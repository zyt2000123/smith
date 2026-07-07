# CLAUDE.md

This file is the working brief for Claude or any coding agent operating in this repository.

## 1. What This Project Is

Agent-Smith is no longer positioned as a "digital employee platform".

The current product direction is:

- one self-built, local-first personal assistant Agent
- CLI-first delivery
- persistent context, memory, tools, and sessions
- execution over chat-for-chat's-sake

If you need a one-line description, use this:

> Agent-Smith is a local personal assistant Agent that runs on the user's machine, keeps context over time, and helps execute real work through tools, sessions, and memory.

## 2. Current Priority

The current priority is the Agent CLI, not the macOS app.

Unless the user explicitly asks for frontend work:

- do not expand the SwiftUI app
- do not spend time polishing macOS UI flows
- do not introduce new product language around "multiple employees"

The current intended surface is:

- one built-in default Agent
- session-based CLI interaction
- ability to inspect, resume, and continue work from CLI

## 3. Product Language

Prefer these terms in new docs and new user-facing CLI text:

- "Agent"
- "personal assistant"
- "built-in agent"
- "session"
- "memory"
- "tooling"

Avoid reintroducing these as the main product framing:

- "digital employee"
- "multiple employees as the primary story"
- "hire employees"
- "employee workbench"

Important compatibility note:

- internal code, database tables, API paths, and runtime directories still use `employee` / `employees`
- keep those internal names unless the task explicitly requires a compatibility-breaking rename
- treat that as an implementation shell, not the product truth

## 4. What To Optimize For

When making changes, optimize for:

1. a single Agent that is actually usable from CLI
2. minimal change on top of the current architecture
3. reuse of existing `server`, `engine`, and `common` logic
4. clear session continuity
5. low-risk evolution rather than broad renaming

Do not over-abstract. Do not build a parallel system if the current one can be adapted.

## 5. Architecture Boundaries

This repo uses a five-layer architecture:

```text
app/    -> frontend shell (currently not the priority)
server/ -> platform and CLI-facing orchestration
engine/ -> execution engine, task routing, ReAct loop, safety
common/ -> config, filesystem, sqlite, shared infrastructure
agents/ -> templates, built-in skills, built-in tools, safety rules
```

Dependency direction is one-way:

```text
app -> server -> engine -> common
                 ^
                 |
               agents
```

Rules:

- `engine/` should not know FastAPI or product-shell concepts
- `server/routers/` should stay thin
- `server/services/` should orchestrate, not embed storage details
- `agents/templates/` is where Agent identity lives
- new Agent behavior should prefer template and CLI changes before engine rewrites

## 6. Files That Matter Most Right Now

For the current CLI-first direction, start here:

- `server/app/cli.py`
- `server/app/services/session_service.py`
- `server/app/services/employee_service.py`
- `server/app/infrastructure/repositories/session_repo.py`
- `agents/templates/personal-assistant/`
- `README.md`
- `docs/01-产品设计与定位.md`
- `docs/02-系统架构.md`

If you are adding or changing CLI features, prefer building on top of existing session and message services instead of bypassing them.

## 7. Implementation Guidance

When editing this repo:

- inspect current code first
- prefer the existing patterns
- keep changes local
- preserve compatibility unless the user asks to break it
- write docs that reflect the actual product direction, not the old one

Good examples of the current direction:

- one built-in `personal-assistant` template
- CLI commands for ensuring the agent exists
- session listing, session inspection, and session resume

Bad examples:

- adding more "demo employees" as the main flow
- building frontend-first features while CLI remains incomplete
- renaming core storage/API internals without a migration plan

## 8. Testing And Verification

For CLI and backend work, default to these checks:

```bash
cd server && uv run --with pytest --with pytest-asyncio pytest tests/test_cli.py
cd server && uv run python -m app.cli --help
cd server && uv run python -m app.cli agent ensure
cd server && uv run python -m app.cli sessions list
cd server && uv run python -m app.cli chat --help
```

If you add a CLI command, verify:

- parser help renders correctly
- the command works against the real local database path
- the command composes with the built-in personal assistant flow

## 9. Documentation Standard

When rewriting docs in this repo:

- start from the real communication goal
- keep the language concrete
- prefer first-principles explanation over fluffy positioning
- keep it simple
- do not be vague

If a document still reflects the old "digital employee" framing, update it toward:

- single-Agent framing
- CLI-first reality
- compatibility note where old `employee` naming still exists

## 10. Default Decision Rule

If a choice is unclear, prefer the option that:

- strengthens the single-Agent CLI experience
- preserves current architecture
- avoids broad renames
- leaves the frontend untouched
- makes the system more usable today

That is the default path unless the user explicitly redirects the work.
