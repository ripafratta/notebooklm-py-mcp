# notebooklm-mcp

MCP (Model Context Protocol) server that bridges Claude Code / Claude Cowork with Google NotebookLM — enabling AI-powered research, source analysis, chat, and content generation through a structured tool interface.

> **Built on** [`notebooklm-py`](https://github.com/teng-lin/notebooklm-py) (v0.4.1) by [Teng Lin](https://github.com/teng-lin) — a community-maintained Python client and CLI for Google NotebookLM. All API interaction, authentication, and data models are powered by `notebooklm-py`. This project wraps it as an MCP server for use with Claude Code and Claude Cowork.

## Features

- **24 MCP tools** covering notebooks, sources, chat, artifacts, notes, and account management
- **Pagination** on all list tools (`limit`/`offset` with metadata)
- **Dual output format**: JSON (structured) and Markdown (human-readable) on 15 tools
- **Service prefix** (`notebooklm_*`) to prevent collisions with other MCP servers
- **Keepalive** support for long-running Claude Code sessions (token rotation every 10 min)
- **Multiple auth methods**: env var, profile-based, or inline JSON

## Prerequisites

- Python >= 3.11
- A Google account with access to [NotebookLM](https://notebooklm.google.com)
- Authentication configured via `notebooklm login` (see below)

## Installation

```bash
# Clone the repository
git clone https://github.com/ripafratta/notebooklm-py-mcp.git
cd notebooklm-py-mcp

# Install in editable mode
pip install -e .
```

This installs the `notebooklm-mcp` command along with its two core dependencies:
- [`notebooklm-py`](https://github.com/teng-lin/notebooklm-py) >= 0.4.1 — Python client/CLI for NotebookLM
- [`mcp`](https://github.com/modelcontextprotocol/python-sdk) >= 1.6.0 — Official MCP Python SDK

## Authentication

The server uses the `notebooklm-py` library's auth system. Choose one method:

### Method 1: Browser login (recommended)

```bash
# Install with cookie support
pip install 'notebooklm-py[cookies]'

# Login via browser
notebooklm login
```

This opens a Chromium browser, you sign in to Google, and the session is saved to `~/.notebooklm/profiles/default/storage_state.json`.

### Method 2: Environment variable (CI/headless)

```bash
export NOTEBOOKLM_AUTH_JSON='{"cookies":[...],"origins":[...]}'
```

The JSON format matches Playwright's `storage_state.json`. You can extract it from a logged-in browser session.

### Method 3: Multiple profiles

```bash
notebooklm profile create work
notebooklm login -p work

# Use with the server:
NOTEBOOKLM_PROFILE=work notebooklm-mcp
```

### Verify authentication

```bash
notebooklm auth check
notebooklm doctor          # Full diagnostic
```

## Quick Start

```bash
# Start the MCP server (stdio mode)
notebooklm-mcp

# Or use mcp CLI
mcp run notebooklm-mcp

# Development mode with MCP Inspector
mcp dev src/notebooklm_mcp/server.py
```

## Configure Claude Code

Add to `.claude/settings.local.json` (project-level) or `~/.claude/settings.json` (user-level):

```json
{
  "mcpServers": {
    "notebooklm": {
      "command": "notebooklm-mcp"
    }
  }
}
```

With a specific profile:

```json
{
  "mcpServers": {
    "notebooklm": {
      "command": "notebooklm-mcp",
      "env": {
        "NOTEBOOKLM_PROFILE": "work"
      }
    }
  }
}
```

Restart Claude Code or reload the window — the 20 `notebooklm_*` tools will appear in the tool list.

## Configure Claude Cowork

Claude Cowork discovers MCP servers from the same `.claude/settings.json` configuration. Once added, the tools are available in cowork sessions automatically.

You can verify the server is registered:

```bash
# List available MCP tools from within a cowork session
# Claude will see: notebooklm_list_notebooks, notebooklm_chat_ask, etc.
```

## Tools Reference

### Notebooks (5 tools)

| Tool | Description | Read‑only |
|------|-------------|:---------:|
| `notebooklm_list_notebooks` | List all notebooks with pagination and markdown table support | ✅ |
| `notebooklm_create_notebook` | Create a new notebook with a given title | ❌ |
| `notebooklm_get_notebook` | Get notebook details including all sources | ✅ |
| `notebooklm_rename_notebook` | Rename an existing notebook | ❌ |
| `notebooklm_delete_notebook` | ⚠️ Permanently delete a notebook and all contents | ❌ |

### Sources (8 tools)

| Tool | Description | Read‑only |
|------|-------------|:---------:|
| `notebooklm_list_sources` | List sources with type, status, URL, pagination | ✅ |
| `notebooklm_add_source_url` | Add a web page or YouTube video as a source | ❌ |
| `notebooklm_add_source_text` | Add pasted text as a source | ❌ |
| `notebooklm_add_source_file` | Upload a local file (PDF, Markdown, EPUB, Word, text) | ❌ |
| `notebooklm_rename_source` | Rename a source | ❌ |
| `notebooklm_get_source_content` | Get full indexed text extracted by NotebookLM | ✅ |
| `notebooklm_get_source_guide` | Get AI-generated summary and keywords for a source | ✅ |
| `notebooklm_delete_source` | ⚠️ Permanently remove a source and its content | ❌ |

### Chat (4 tools)

| Tool | Description | Read‑only |
|------|-------------|:---------:|
| `notebooklm_chat_ask` | Ask a question against notebook sources with citations | ✅ |
| `notebooklm_get_chat_history` | Get recent Q&A history with pagination | ✅ |
| `notebooklm_configure_chat` | Set chat persona, goal, and response length | ❌ |
| `notebooklm_set_chat_mode` | Quick preset: default, learning guide, concise, detailed | ❌ |

### Artifacts (4 tools)

| Tool | Description | Read‑only |
|------|-------------|:---------:|
| `notebooklm_list_artifacts` | List all AI-generated artifacts (Audio, Reports, etc.) | ✅ |
| `notebooklm_generate_audio` | Generate an Audio Overview (AI podcast) | ❌ |
| `notebooklm_generate_report` | Generate a report (Briefing Doc, Study Guide, Blog Post, Custom) | ❌ |
| `notebooklm_delete_artifact` | ⚠️ Permanently delete an artifact | ❌ |

### Notes (2 tools)

| Tool | Description | Read‑only |
|------|-------------|:---------:|
| `notebooklm_list_notes` | List user-created notes in a notebook | ✅ |
| `notebooklm_create_note` | Create a new note with title and content | ❌ |

### Account (1 tool)

| Tool | Description | Read‑only |
|------|-------------|:---------:|
| `notebooklm_get_account` | Get account tier, plan name, and limits | ✅ |

## API Coverage

The table below shows every method available in [`notebooklm-py`](https://github.com/teng-lin/notebooklm-py) and whether it's exposed as an MCP tool.

### Notebooks (5/11 covered)

| notebooklm-py method | MCP tool | Status |
|----------------------|----------|:------:|
| `list()` | `notebooklm_list_notebooks` | ✅ |
| `create(title)` | `notebooklm_create_notebook` | ✅ |
| `get(id)` | `notebooklm_get_notebook` | ✅ |
| `rename(id, title)` | `notebooklm_rename_notebook` | ✅ |
| `delete(id)` | `notebooklm_delete_notebook` | ✅ |
| `get_summary(id)` | — | ❌ |
| `get_description(id)` | — | ❌ |
| `get_metadata(id)` | — | ❌ |
| `get_raw(id)` | — | ❌ |
| `remove_from_recent(id)` | — | ❌ |
| `share(...)` | — | ❌ |

### Sources (8/14 covered)

| notebooklm-py method | MCP tool | Status |
|----------------------|----------|:------:|
| `list(nb_id)` | `notebooklm_list_sources` | ✅ |
| `add_url(nb_id, url)` | `notebooklm_add_source_url` | ✅ |
| `add_text(nb_id, title, text)` | `notebooklm_add_source_text` | ✅ |
| `add_file(nb_id, path)` | `notebooklm_add_source_file` | ✅ |
| `rename(nb_id, src_id, title)` | `notebooklm_rename_source` | ✅ |
| `get_guide(nb_id, src_id)` | `notebooklm_get_source_guide` | ✅ |
| `get_fulltext(nb_id, src_id)` | `notebooklm_get_source_content` | ✅ |
| `delete(nb_id, src_id)` | `notebooklm_delete_source` | ✅ |
| `add_drive(nb_id, file_id, ...)` | — | ❌ |
| `get(nb_id, src_id)` | — | ❌ |
| `refresh(nb_id, src_id)` | — | ❌ |
| `check_freshness(nb_id, src_id)` | — | ❌ |
| `wait_until_ready(...)` | — (used internally) | ⚪ |
| `wait_for_sources(...)` | — | ❌ |

### Chat (4/8 covered)

| notebooklm-py method | MCP tool | Status |
|----------------------|----------|:------:|
| `ask(nb_id, question, ...)` | `notebooklm_chat_ask` | ✅ |
| `get_history(nb_id, limit)` | `notebooklm_get_chat_history` | ✅ |
| `configure(nb_id, goal, ...)` | `notebooklm_configure_chat` | ✅ |
| `set_mode(nb_id, mode)` | `notebooklm_set_chat_mode` | ✅ |
| `get_conversation_turns(...)` | — | ❌ |
| `get_conversation_id(nb_id)` | — | ❌ |
| `get_cached_turns(...)` | — | ❌ |
| `clear_cache(...)` | — | ❌ |

### Artifacts (4/38 covered)

| notebooklm-py method | MCP tool | Status |
|----------------------|----------|:------:|
| `list(nb_id)` | `notebooklm_list_artifacts` | ✅ |
| `generate_audio(nb_id, ...)` | `notebooklm_generate_audio` | ✅ |
| `generate_report(nb_id, ...)` | `notebooklm_generate_report` | ✅ |
| `delete(nb_id, art_id)` | `notebooklm_delete_artifact` | ✅ |
| `generate_video(...)`, `generate_quiz(...)`, `generate_flashcards(...)`, `generate_infographic(...)`, `generate_slide_deck(...)`, `generate_mind_map(...)`, `generate_data_table(...)`, `generate_cinematic_video(...)`, `generate_study_guide(...)` | — | ❌ |
| **All `download_*`** (audio, video, report, quiz, flashcards, infographic, slide_deck, mind_map, data_table) | — | ❌ |
| **All `export_*`** (report, data_table, generic) | — | ❌ |
| `poll_status(nb_id, task_id)` | — | ❌ |
| `wait_for_completion(...)` | — | ❌ |
| `get(nb_id, art_id)`, `rename(...)`, `revise_slide(...)`, `suggest_reports(nb_id)` | — | ❌ |

### Notes (2/7 covered)

| notebooklm-py method | MCP tool | Status |
|----------------------|----------|:------:|
| `list(nb_id)` | `notebooklm_list_notes` | ✅ |
| `create(nb_id, title, text)` | `notebooklm_create_note` | ✅ |
| `get(nb_id, note_id)` | — | ❌ |
| `update(nb_id, note_id, ...)` | — | ❌ |
| `delete(nb_id, note_id)` | — | ❌ |
| `list_mind_maps(nb_id)` | — | ❌ |
| `delete_mind_map(nb_id, mm_id)` | — | ❌ |

### Research (0/3 covered)

| notebooklm-py method | MCP tool | Status |
|----------------------|----------|:------:|
| `start(nb_id, query, ...)` | — | ❌ |
| `poll(nb_id)` | — | ❌ |
| `import_sources(nb_id, task_id, ...)` | — | ❌ |

### Sharing (0/6 covered)

| notebooklm-py method | MCP tool | Status |
|----------------------|----------|:------:|
| `get_status(nb_id)` | — | ❌ |
| `set_public(nb_id, bool)` | — | ❌ |
| `set_view_level(nb_id, level)` | — | ❌ |
| `add_user(nb_id, email, ...)` | — | ❌ |
| `update_user(nb_id, email, ...)` | — | ❌ |
| `remove_user(nb_id, email)` | — | ❌ |

### Settings (1/4 covered)

| notebooklm-py method | MCP tool | Status |
|----------------------|----------|:------:|
| `get_account_limits()` | `notebooklm_get_account` | ✅ |
| `get_account_tier()` | `notebooklm_get_account` | ✅ |
| `get_output_language()` | — | ❌ |
| `set_output_language(code)` | — | ❌ |

> **Summary**: 24 MCP tools covering 24 of ~91 methods. The main gaps are artifact download/export (requires file I/O), additional generate types (video, quiz, flashcards, etc.), research (multi-step workflow), sharing, and note CRUD extensions. See [Related](#related) for using the `notebooklm-py` CLI directly for unsupported features.

## Common Workflows

### Research a topic

```
1. notebooklm_list_notebooks                        → find or create a notebook
2. notebooklm_add_source_url(nb_id, url)            → add web articles
3. notebooklm_get_source_guide(nb_id, src_id)       → read AI summaries
4. notebooklm_chat_ask(nb_id, "What are...")        → ask questions
```

### Upload and analyze local documents

```
1. notebooklm_list_notebooks
2. notebooklm_add_source_file(nb_id, "~/papers/paper.pdf")    → upload PDF
3. notebooklm_add_source_file(nb_id, "~/docs/notes.md")       → upload Markdown
4. notebooklm_list_sources(nb_id)                             → verify all ready
5. notebooklm_chat_ask(nb_id, "Summarize the papers...")      → ask questions
```

### Analyze a document set

```
1. notebooklm_list_sources(nb_id, limit=50)
2. notebooklm_get_source_content(nb_id, src_id)     → read full text
3. notebooklm_chat_ask(nb_id, "Compare...")         → cross-source analysis
4. notebooklm_generate_report(nb_id, "briefing_doc") → create executive summary
```

### Generate learning materials

```
1. notebooklm_list_notebooks
2. notebooklm_generate_report(nb_id, "study_guide") → quiz + glossary
3. notebooklm_generate_audio(nb_id, language="en")  → podcast overview
4. notebooklm_list_artifacts(nb_id)                 → check completion
```

## Response Formats

15 tools accept a `response_format` parameter:

- **`json`** (default) — Structured data with all fields. Best for programmatic use.
- **`markdown`** — Human-readable tables, headers, and formatted text. Best for reading in chat.

Example:

```
notebooklm_list_sources(nb_id, response_format="markdown", limit=10)
```

Returns:

```
| Title | Type | Status | ID |
|---|---|---|---|
| Climate Report | pdf | ready | abc123... |
| Research Paper | web_page | processing | def456... |

Showing 2 of 24 sources (offset 0)
```

## Pagination

All list tools support pagination:

| Parameter | Default | Range | Description |
|-----------|---------|-------|-------------|
| `limit` | 50 | 1–100 | Max items per page |
| `offset` | 0 | ≥0 | Items to skip |

Each response includes pagination metadata:

```json
{
  "items": [...],
  "pagination": {
    "total": 150,
    "count": 20,
    "offset": 0,
    "has_more": true,
    "next_offset": 20
  }
}
```

Use the pattern: fetch page → check `has_more` → if true, fetch with `offset = next_offset`.

## Architecture

```
src/notebooklm_mcp/
├── __init__.py      # Package metadata
├── client.py        # Singleton NotebookLMClient lifecycle + keepalive
├── models.py        # Pydantic v2 models: inputs, outputs, pagination, enums
└── server.py        # FastMCP app, lifespan, 20 @mcp.tool definitions
```

- **`client.py`** — Lazy singleton that initializes `NotebookLMClient` on first use, caches it across tool calls, and closes it on server shutdown. Keepalive rotates tokens every 10 minutes.
- **`models.py`** — 15 Pydantic v2 models with `Field(description=...)` for auto-generated JSON Schema. Includes `ResponseFormat` enum, `PaginationMeta`, and typed list result wrappers.
- **`server.py`** — `FastMCP("notebooklm_mcp")` with lifespan context manager. All 20 tools follow the same pattern: get client → call API → format response → handle errors.

### Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Transport | stdio | Local integration with Claude Code |
| Auth priority | env var → profile → default | Flexibility across local/CI/headless |
| Client lifecycle | Singleton, opened on first use | Prevents auth-at-import, enables keepalive |
| Pagination | Virtual (client-side slice) | Underlying API returns all items; dataset is small (typically <100 items) |
| Error handling | Return error strings, not exceptions | MCP best practice: "report errors within result objects" |
| Tool prefix | `notebooklm_` | Prevents collisions with other MCP servers |
| Response format | JSON default, Markdown optional | JSON for Claude's internal processing, Markdown for user display |

## Troubleshooting

### "Authentication failed"

```bash
# Re-authenticate
notebooklm login --fresh

# Or check auth status
notebooklm auth check --json
```

The server's error messages include actionable guidance — read them carefully.

### "Notebook X not found"

Use `notebooklm_list_notebooks` to get correct IDs. The library supports partial ID matching (prefix), so a short prefix may resolve to the wrong notebook.

### Tools not appearing in Claude Code

1. Verify the server starts: `notebooklm-mcp` (should hang waiting for stdio input — press Ctrl+C)
2. Check your `.claude/settings.local.json` syntax
3. Restart Claude Code completely
4. Check Claude Code logs for MCP connection errors

### Rate limiting

NotebookLM enforces rate limits. If you hit them, wait 30-60 seconds and retry. The error message will tell you when this happens.

### Empty source guides / summaries

Newly added sources need time for NotebookLM to process and generate AI guides. Use `notebooklm_list_sources` to check if the status is `ready` before calling `notebooklm_get_source_guide`.

## Development

```bash
# Install dev dependencies
pip install -e .

# Interactive testing with MCP Inspector
mcp dev src/notebooklm_mcp/server.py

# Run tests (requires auth)
python -c "
import asyncio
from notebooklm_mcp.server import notebooklm_get_account
print(asyncio.run(notebooklm_get_account()))
"
```

### Running Evaluations

The `evaluation.xml` file contains 10 complex, multi-step questions that test the MCP server end-to-end:

```bash
# Requires ANTHROPIC_API_KEY
python scripts/evaluation.py \
  -t stdio \
  -c python \
  -a -m \
  -a notebooklm_mcp.server \
  evaluation.xml
```

See `.claude/skills/mcp-builder/reference/evaluation.md` for the full evaluation workflow.

## License

MIT — see [LICENSE](LICENSE) file.

## Related

- [notebooklm-py](https://github.com/teng-lin/notebooklm-py) — Python client library for NotebookLM
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) — Official MCP SDK
- [MCP Specification](https://modelcontextprotocol.io) — Protocol documentation
- [MCP Builder Skill](./.claude/skills/mcp-builder/SKILL.md) — Skill used to design this server
