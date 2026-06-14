"""notebooklm-mcp: MCP server bridge for Google NotebookLM.

Exposes 24 MCP tools covering notebooks, sources, chat, artifacts, notes,
and account information. Built with FastMCP on the official MCP Python SDK.

All tools use the `notebooklm_` prefix to avoid naming collisions with
other MCP servers. Follows MCP best practices for pagination, response
format options, tool annotations, and error handling.

Usage:
    notebooklm-mcp              # Run via stdio (Claude Code default)
    mcp dev server.py           # Interactive development mode
    python -m notebooklm_mcp.server
"""

import contextlib
import json
import logging
import sys
from collections.abc import AsyncIterator
from typing import Any

from mcp.server.fastmcp import FastMCP

from notebooklm_mcp.client import close_client, get_client
from notebooklm_mcp.models import (
    AccountInfo,
    ArtifactInfo,
    ArtifactListResult,
    ChatAnswer,
    ChatHistoryItem,
    ChatHistoryResult,
    GenerationStatusInfo,
    NoteInfo,
    NoteListResult,
    NotebookInfo,
    NotebookListResult,
    PaginationMeta,
    ResponseFormat,
    SourceContent,
    SourceGuide,
    SourceInfo,
    SourceListResult,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.WARNING,  # Keep MCP stdio clean
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@contextlib.asynccontextmanager
async def notebooklm_lifespan(server: FastMCP) -> AsyncIterator[None]:
    """Manage NotebookLMClient lifecycle, tied to the MCP server."""
    try:
        await get_client()
        logger.info("NotebookLM MCP server ready")
    except Exception as e:
        logger.warning("Startup auth check failed (tools will retry): %s", e)
    try:
        yield
    finally:
        await close_client()
        logger.info("NotebookLM MCP server shut down")


# ---------------------------------------------------------------------------
# FastMCP application
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "notebooklm_mcp",
    instructions=(
        "Google NotebookLM bridge — manage notebooks, sources, chat with AI, "
        "generate artifacts (audio overviews, reports), and create notes. "
        "Requires authentication via 'notebooklm login' or NOTEBOOKLM_AUTH_JSON."
    ),
    lifespan=notebooklm_lifespan,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_error(operation: str, error: Exception) -> str:
    """Produce a user-friendly error message with actionable guidance."""
    msg = str(error).lower()

    if any(w in msg for w in ("auth", "login", "credential", "token", "expired")):
        return (
            f"Authentication failed during '{operation}': {error}\n\n"
            "To fix: run 'notebooklm login' in your terminal, or set the "
            "NOTEBOOKLM_AUTH_JSON environment variable."
        )
    if "rate limit" in msg or "too many" in msg:
        return (
            f"Rate limit hit during '{operation}': {error}\n\n"
            "Wait a moment and retry. NotebookLM enforces rate limits on API calls."
        )
    if "quota" in msg or "notebook limit" in msg:
        return (
            f"Quota exceeded during '{operation}': {error}\n\n"
            "You may need to delete unused notebooks or upgrade your account."
        )
    return f"Error in '{operation}': {error}"


def _paginate(items: list[Any], limit: int, offset: int) -> dict[str, Any]:
    """Apply virtual pagination to a full result list.

    The underlying API doesn't support server-side pagination, so we
    slice the full list.  For typical NotebookLM workloads (dozens of
    items, not thousands) this is acceptable.
    """
    total = len(items)
    page = items[offset : offset + limit]
    next_off = offset + limit if offset + limit < total else None
    return {
        "total": total,
        "count": len(page),
        "offset": offset,
        "has_more": next_off is not None,
        "next_offset": next_off,
        "items": page,
    }


def _render_json(items: list[dict[str, Any]], pagination: dict[str, Any]) -> str:
    """Render a paginated list response as JSON."""
    return json.dumps(
        {"items": items, "pagination": {k: v for k, v in pagination.items() if k != "items"}},
        indent=2,
        default=str,
    )


def _render_markdown_table(
    rows: list[dict[str, Any]], columns: list[tuple[str, str]]
) -> str:
    """Render items as a Markdown table.

    Args:
        rows: List of item dicts.
        columns: List of (key, header) pairs.
    """
    if not rows:
        return "No items found."

    # Header
    headers = [h for _, h in columns]
    keys = [k for k, _ in columns]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]

    for row in rows:
        cells = [str(row.get(k, "")) for k in keys]
        lines.append("| " + " | ".join(cells) + " |")

    return "\n".join(lines)


# =========================================================================
# NOTEBOOK TOOLS (5)
# =========================================================================


@mcp.tool(
    name="notebooklm_list_notebooks",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def notebooklm_list_notebooks(
    limit: int = 50,
    offset: int = 0,
    response_format: ResponseFormat = ResponseFormat.JSON,
) -> str:
    """List all NotebookLM notebooks you have access to.

    Returns paginated notebook metadata including title, ID, source count,
    and ownership. Use returned IDs with other tools.

    Args:
        limit: Max notebooks to return (1-100, default 50).
        offset: Number of notebooks to skip for pagination (default 0).
        response_format: "json" for structured data, "markdown" for a table.
    """
    try:
        client = await get_client()
        notebooks = await client.notebooks.list()
        items = [NotebookInfo.from_notebook(nb).model_dump() for nb in notebooks]
        pg = _paginate(items, max(1, min(limit, 100)), max(0, offset))

        if response_format == ResponseFormat.MARKDOWN:
            cols = [("title", "Title"), ("id", "ID"), ("sources_count", "Sources"), ("is_owner", "Owner")]
            table = _render_markdown_table(pg["items"], cols)
            meta = f"\n\n*Showing {pg['count']} of {pg['total']} notebooks (offset {pg['offset']})*"
            return table + meta
        return _render_json(pg["items"], pg)
    except Exception as e:
        return _format_error("notebooklm_list_notebooks", e)


@mcp.tool(
    name="notebooklm_create_notebook",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def notebooklm_create_notebook(title: str, response_format: ResponseFormat = ResponseFormat.JSON) -> str:
    """Create a new NotebookLM notebook.

    Args:
        title: Display title for the new notebook (e.g. "Research on AI safety").
        response_format: "json" for structured data, "markdown" for a summary line.
    """
    try:
        if not title.strip():
            return "Error: Notebook title cannot be empty."
        client = await get_client()
        nb = await client.notebooks.create(title.strip())
        info = NotebookInfo.from_notebook(nb).model_dump()
        if response_format == ResponseFormat.MARKDOWN:
            return f"## Notebook Created\n\n**Title**: {info['title']}\n**ID**: `{info['id']}`\n**Sources**: {info['sources_count']}"
        return json.dumps(info, indent=2, default=str)
    except Exception as e:
        return _format_error("notebooklm_create_notebook", e)


@mcp.tool(
    name="notebooklm_get_notebook",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def notebooklm_get_notebook(
    notebook_id: str, response_format: ResponseFormat = ResponseFormat.JSON
) -> str:
    """Get detailed information about a specific notebook, including its sources.

    Args:
        notebook_id: The notebook ID (UUID or partial prefix).
                     Find IDs via notebooklm_list_notebooks.
        response_format: "json" for structured data, "markdown" for formatted text.
    """
    try:
        client = await get_client()
        nb = await client.notebooks.get(notebook_id)
        info = NotebookInfo.from_notebook(nb).model_dump()

        sources_raw: list[dict[str, Any]] = []
        try:
            sources = await client.sources.list(notebook_id)
            sources_raw = [SourceInfo.from_source(s).model_dump() for s in sources]
        except Exception:
            pass
        info["sources"] = sources_raw

        if response_format == ResponseFormat.MARKDOWN:
            lines = [
                f"# {info['title']}",
                f"**ID**: `{info['id']}`  ",
                f"**Sources**: {info['sources_count']}  ",
                f"**Owner**: {'Yes' if info['is_owner'] else 'No'}  ",
            ]
            if info.get("created_at"):
                lines.append(f"**Created**: {info['created_at']}")
            if sources_raw:
                lines.append("")
                lines.append("## Sources")
                for s in sources_raw:
                    url_str = f" ({s.get('url')})" if s.get("url") else ""
                    lines.append(f"- **{s.get('title', 'Untitled')}** [{s.get('type')}] — {s.get('status')}{url_str}")
            return "\n".join(lines)
        return json.dumps(info, indent=2, default=str)
    except Exception as e:
        return _format_error("notebooklm_get_notebook", e)


@mcp.tool(
    name="notebooklm_rename_notebook",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def notebooklm_rename_notebook(
    notebook_id: str, new_title: str, response_format: ResponseFormat = ResponseFormat.JSON
) -> str:
    """Rename an existing notebook.

    Args:
        notebook_id: The notebook ID to rename.
        new_title: The new display title.
        response_format: "json" for structured data, "markdown" for a summary line.
    """
    try:
        if not new_title.strip():
            return "Error: New title cannot be empty."
        client = await get_client()
        nb = await client.notebooks.rename(notebook_id, new_title.strip())
        info = NotebookInfo.from_notebook(nb).model_dump()
        if response_format == ResponseFormat.MARKDOWN:
            return f"## Notebook Renamed\n\n**New title**: {info['title']}\n**ID**: `{info['id']}`"
        return json.dumps(info, indent=2, default=str)
    except Exception as e:
        return _format_error("notebooklm_rename_notebook", e)


@mcp.tool(
    name="notebooklm_delete_notebook",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def notebooklm_delete_notebook(notebook_id: str) -> str:
    """⚠️ DESTRUCTIVE: Permanently delete a notebook and ALL its contents.

    This action cannot be undone. All sources, notes, artifacts, and
    chat history in the notebook will be permanently lost.

    Args:
        notebook_id: The notebook ID to delete. Verify with notebooklm_list_notebooks.
    """
    try:
        client = await get_client()
        await client.notebooks.delete(notebook_id)
        return f"Notebook '{notebook_id}' deleted successfully."
    except Exception as e:
        return _format_error("notebooklm_delete_notebook", e)


# =========================================================================
# SOURCE TOOLS (8)
# =========================================================================


@mcp.tool(
    name="notebooklm_list_sources",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def notebooklm_list_sources(
    notebook_id: str,
    limit: int = 50,
    offset: int = 0,
    response_format: ResponseFormat = ResponseFormat.JSON,
) -> str:
    """List all sources in a notebook with type, status, and URL.

    Args:
        notebook_id: The notebook ID. Find IDs via notebooklm_list_notebooks.
        limit: Max sources to return (1-100, default 50).
        offset: Sources to skip (default 0).
        response_format: "json" for structured data, "markdown" for a table.
    """
    try:
        client = await get_client()
        sources = await client.sources.list(notebook_id)
        items = [SourceInfo.from_source(s).model_dump() for s in sources]
        pg = _paginate(items, max(1, min(limit, 100)), max(0, offset))

        if response_format == ResponseFormat.MARKDOWN:
            cols = [("title", "Title"), ("type", "Type"), ("status", "Status"), ("id", "ID")]
            table = _render_markdown_table(pg["items"], cols)
            meta = f"\n\n*Showing {pg['count']} of {pg['total']} sources (offset {pg['offset']})*"
            return table + meta
        return _render_json(pg["items"], pg)
    except Exception as e:
        return _format_error("notebooklm_list_sources", e)


@mcp.tool(
    name="notebooklm_add_source_url",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def notebooklm_add_source_url(
    notebook_id: str, url: str, response_format: ResponseFormat = ResponseFormat.JSON
) -> str:
    """Add a web page or YouTube video as a source to a notebook.

    NotebookLM fetches, extracts text, and indexes the content automatically.
    This waits for the source to be fully processed before returning.

    Args:
        notebook_id: Target notebook ID.
        url: URL to add (web page https://... or YouTube youtu.be/...).
        response_format: "json" for structured data, "markdown" for a summary line.
    """
    try:
        client = await get_client()
        source = await client.sources.add_url(notebook_id, url.strip())
        if not source.is_ready:
            source = await client.sources.wait_until_ready(notebook_id, source.id)
        info = SourceInfo.from_source(source).model_dump()
        if response_format == ResponseFormat.MARKDOWN:
            return f"## Source Added\n\n**Title**: {info['title']}\n**Type**: {info['type']}\n**Status**: {info['status']}\n**ID**: `{info['id']}`"
        return json.dumps(info, indent=2, default=str)
    except Exception as e:
        return _format_error("notebooklm_add_source_url", e)


@mcp.tool(
    name="notebooklm_add_source_text",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def notebooklm_add_source_text(
    notebook_id: str,
    title: str,
    content: str,
    response_format: ResponseFormat = ResponseFormat.JSON,
) -> str:
    """Add pasted text as a source. The text is indexed and searchable.

    Args:
        notebook_id: Target notebook ID.
        title: Descriptive title (e.g. "Meeting notes 2024-01-15").
        content: Full text content to index.
        response_format: "json" for structured data, "markdown" for a summary line.
    """
    try:
        client = await get_client()
        source = await client.sources.add_text(notebook_id, title.strip(), content)
        if not source.is_ready:
            source = await client.sources.wait_until_ready(notebook_id, source.id)
        info = SourceInfo.from_source(source).model_dump()
        if response_format == ResponseFormat.MARKDOWN:
            return f"## Source Added\n\n**Title**: {info['title']}\n**Type**: {info['type']}\n**Status**: {info['status']}\n**ID**: `{info['id']}`"
        return json.dumps(info, indent=2, default=str)
    except Exception as e:
        return _format_error("notebooklm_add_source_text", e)


@mcp.tool(
    name="notebooklm_add_source_file",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def notebooklm_add_source_file(
    notebook_id: str,
    file_path: str,
    response_format: ResponseFormat = ResponseFormat.JSON,
) -> str:
    """Add a local file (PDF, Markdown, EPUB, Word, text) as a source.

    Uploads the file to NotebookLM using Google's resumable upload protocol.
    Wait for processing to complete before returning.

    Supported formats: PDF (.pdf), Markdown (.md), plain text (.txt),
    EPUB (.epub), Word (.docx).

    The file must exist on the local filesystem where this MCP server runs.
    When used with Claude Code or Claude Cowork (local execution), your
    local files are accessible.

    Args:
        notebook_id: Target notebook ID. Find IDs via notebooklm_list_notebooks.
        file_path: Absolute or relative path to the file to upload.
        response_format: "json" for structured data, "markdown" for a summary line.
    """
    from pathlib import Path

    try:
        fpath = Path(file_path).resolve()
        if not fpath.exists():
            return f"Error: File not found: {fpath}"
        if not fpath.is_file():
            return f"Error: Not a regular file: {fpath}"

        client = await get_client()
        source = await client.sources.add_file(notebook_id, fpath)
        if not source.is_ready:
            source = await client.sources.wait_until_ready(notebook_id, source.id)

        info = SourceInfo.from_source(source).model_dump()
        if response_format == ResponseFormat.MARKDOWN:
            return (
                f"## File Uploaded\n\n"
                f"**Title**: {info['title']}\n"
                f"**Type**: {info['type']}\n"
                f"**Status**: {info['status']}\n"
                f"**ID**: `{info['id']}`\n"
                f"**File**: {fpath.name}"
            )
        return json.dumps(info, indent=2, default=str)
    except Exception as e:
        return _format_error("notebooklm_add_source_file", e)


@mcp.tool(
    name="notebooklm_rename_source",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def notebooklm_rename_source(
    notebook_id: str, source_id: str, new_title: str,
    response_format: ResponseFormat = ResponseFormat.JSON,
) -> str:
    """Rename a source in a notebook.

    Args:
        notebook_id: Notebook ID containing the source.
        source_id: Source ID to rename. Find IDs via notebooklm_list_sources.
        new_title: The new display title for the source.
        response_format: "json" for structured data, "markdown" for a summary line.
    """
    try:
        if not new_title.strip():
            return "Error: New title cannot be empty."
        client = await get_client()
        source = await client.sources.rename(notebook_id, source_id, new_title.strip())
        info = SourceInfo.from_source(source).model_dump()
        if response_format == ResponseFormat.MARKDOWN:
            return f"## Source Renamed\n\n**New title**: {info['title']}\n**ID**: `{info['id']}`"
        return json.dumps(info, indent=2, default=str)
    except Exception as e:
        return _format_error("notebooklm_rename_source", e)


@mcp.tool(
    name="notebooklm_get_source_content",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def notebooklm_get_source_content(
    notebook_id: str, source_id: str, response_format: ResponseFormat = ResponseFormat.JSON
) -> str:
    """Get the full indexed text of a source as extracted by NotebookLM.

    Args:
        notebook_id: Notebook ID containing the source.
        source_id: Source ID. Find IDs via notebooklm_list_sources.
        response_format: "json" for metadata + content, "markdown" for just the text.
    """
    try:
        client = await get_client()
        ft = await client.sources.get_fulltext(notebook_id, source_id)
        sc = SourceContent.from_fulltext(ft)
        if response_format == ResponseFormat.MARKDOWN:
            header = f"# {sc.title}\n\n**Source**: `{sc.id}`  \n**Chars**: {sc.char_count}\n\n---\n\n"
            return header + sc.content
        return json.dumps(sc.model_dump(), indent=2, default=str)
    except Exception as e:
        return _format_error("notebooklm_get_source_content", e)


@mcp.tool(
    name="notebooklm_get_source_guide",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def notebooklm_get_source_guide(
    notebook_id: str, source_id: str, response_format: ResponseFormat = ResponseFormat.JSON
) -> str:
    """Get AI-generated summary and keywords for a specific source.

    Args:
        notebook_id: Notebook ID containing the source.
        source_id: Source ID. Find IDs via notebooklm_list_sources.
        response_format: "json" for metadata, "markdown" for formatted text.
    """
    try:
        client = await get_client()
        guide_data = await client.sources.get_guide(notebook_id, source_id)
        result = SourceGuide(
            source_id=source_id,
            summary=guide_data.get("summary", ""),
            keywords=guide_data.get("keywords", []),
        ).model_dump()
        if response_format == ResponseFormat.MARKDOWN:
            kws = ", ".join(result["keywords"])
            return f"# Source Guide\n\n**ID**: `{result['source_id']}`\n\n## Summary\n\n{result['summary']}\n\n## Keywords\n\n{kws}"
        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        return _format_error("notebooklm_get_source_guide", e)


@mcp.tool(
    name="notebooklm_delete_source",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def notebooklm_delete_source(notebook_id: str, source_id: str) -> str:
    """⚠️ DESTRUCTIVE: Remove a source and its indexed content permanently.

    Args:
        notebook_id: Notebook ID containing the source.
        source_id: Source ID to delete. Find IDs via notebooklm_list_sources.
    """
    try:
        client = await get_client()
        await client.sources.delete(notebook_id, source_id)
        return f"Source '{source_id}' deleted from notebook '{notebook_id}'."
    except Exception as e:
        return _format_error("notebooklm_delete_source", e)


# =========================================================================
# CHAT TOOLS (4)
# =========================================================================


@mcp.tool(
    name="notebooklm_chat_ask",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def notebooklm_chat_ask(
    notebook_id: str,
    question: str,
    conversation_id: str | None = None,
    response_format: ResponseFormat = ResponseFormat.JSON,
) -> str:
    """Ask a question about sources in a notebook. Returns AI answer with citations.

    For follow-up questions, pass conversation_id from the previous answer.

    Args:
        notebook_id: Notebook ID. Find IDs via notebooklm_list_notebooks.
        question: Question to ask about the notebook's sources.
        conversation_id: Previous conversation ID for follow-up (omit for new).
        response_format: "json" for full answer + citations, "markdown" for readable answer.
    """
    try:
        client = await get_client()
        result = await client.chat.ask(
            notebook_id=notebook_id,
            question=question.strip(),
            conversation_id=conversation_id,
        )
        ca = ChatAnswer.from_ask_result(result)
        if response_format == ResponseFormat.MARKDOWN:
            lines = [f"**Answer** (turn {ca.turn_number}):\n\n{ca.answer}"]
            if ca.citations:
                lines.append("\n---\n### Citations")
                for c in ca.citations:
                    lines.append(f"- [{c.citation_number}] {c.cited_text[:120]}... (`{c.source_id}`)")
            if ca.conversation_id:
                lines.append(f"\n> *Conversation ID: `{ca.conversation_id}` — use for follow-up*")
            return "\n".join(lines)
        return json.dumps(ca.model_dump(), indent=2, default=str)
    except Exception as e:
        return _format_error("notebooklm_chat_ask", e)


@mcp.tool(
    name="notebooklm_get_chat_history",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def notebooklm_get_chat_history(
    notebook_id: str,
    limit: int = 20,
    offset: int = 0,
    response_format: ResponseFormat = ResponseFormat.JSON,
) -> str:
    """Get recent Q&A history for a notebook's latest conversation.

    Args:
        notebook_id: Notebook ID. Find IDs via notebooklm_list_notebooks.
        limit: Max turns to return (1-100, default 20).
        offset: Turns to skip (default 0).
        response_format: "json" for structured data, "markdown" for readable history.
    """
    try:
        client = await get_client()
        history = await client.chat.get_history(notebook_id, limit=100)
        items = [
            ChatHistoryItem(turn_number=i + 1, question=q, answer=a).model_dump()
            for i, (q, a) in enumerate(history)
        ]
        pg = _paginate(items, max(1, min(limit, 100)), max(0, offset))

        if response_format == ResponseFormat.MARKDOWN:
            lines = [f"# Chat History\n"]
            for turn in pg["items"]:
                lines.append(f"## Turn {turn['turn_number']}")
                lines.append(f"**Q**: {turn['question']}")
                lines.append(f"**A**: {turn['answer'][:500]}{'...' if len(turn['answer']) > 500 else ''}")
                lines.append("")
            lines.append(f"*Showing {pg['count']} of {pg['total']} turns*")
            return "\n".join(lines)
        return _render_json(pg["items"], pg)
    except Exception as e:
        return _format_error("notebooklm_get_chat_history", e)


# =========================================================================
# ARTIFACT TOOLS (4)
# =========================================================================


@mcp.tool(
    name="notebooklm_configure_chat",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def notebooklm_configure_chat(
    notebook_id: str,
    goal: str = "default",
    response_length: str = "default",
    custom_prompt: str | None = None,
) -> str:
    """Configure chat persona and response settings for a notebook.

    Adjust the AI's behavior when answering questions. Choose from preset
    goals and response lengths, or provide a custom persona prompt.

    Args:
        notebook_id: Notebook ID. Find IDs via notebooklm_list_notebooks.
        goal: Chat persona. One of:
            "default" — Standard helpful assistant
            "learning_guide" — Socratic tutor, asks follow-up questions
            "custom" — Use custom_prompt to define your own persona
        response_length: Answer verbosity. One of:
            "default" — Balanced responses
            "shorter" — Concise, to the point
            "longer" — Detailed, thorough explanations
        custom_prompt: Required when goal is "custom".
            Describe the persona (e.g. "You are a legal expert specializing in...").
    """
    try:
        from notebooklm.rpc import ChatGoal, ChatResponseLength

        goal_map = {
            "default": ChatGoal.DEFAULT,
            "learning_guide": ChatGoal.LEARNING_GUIDE,
            "custom": ChatGoal.CUSTOM,
        }
        length_map = {
            "default": ChatResponseLength.DEFAULT,
            "shorter": ChatResponseLength.SHORTER,
            "longer": ChatResponseLength.LONGER,
        }

        g = goal_map.get(goal)
        if g is None:
            valid = ", ".join(goal_map.keys())
            return f"Invalid goal '{goal}'. Choose from: {valid}"

        rl = length_map.get(response_length)
        if rl is None:
            valid = ", ".join(length_map.keys())
            return f"Invalid response_length '{response_length}'. Choose from: {valid}"

        client = await get_client()
        await client.chat.configure(
            notebook_id=notebook_id,
            goal=g,
            response_length=rl,
            custom_prompt=custom_prompt,
        )
        prompt_info = f" with custom prompt" if custom_prompt else ""
        return (
            f"Chat configured for notebook '{notebook_id}': "
            f"goal={goal}, length={response_length}{prompt_info}"
        )
    except Exception as e:
        return _format_error("notebooklm_configure_chat", e)


@mcp.tool(
    name="notebooklm_set_chat_mode",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def notebooklm_set_chat_mode(notebook_id: str, mode: str = "default") -> str:
    """Set chat mode using a predefined configuration.

    Convenience wrapper that sets goal + response_length in one call.

    Args:
        notebook_id: Notebook ID. Find IDs via notebooklm_list_notebooks.
        mode: Predefined mode. One of:
            "default" — Standard assistant, balanced responses
            "learning_guide" — Socratic tutor, longer responses
            "concise" — Short, direct answers
            "detailed" — In-depth, thorough explanations
    """
    try:
        from notebooklm.types import ChatMode

        mode_map = {
            "default": ChatMode.DEFAULT,
            "learning_guide": ChatMode.LEARNING_GUIDE,
            "concise": ChatMode.CONCISE,
            "detailed": ChatMode.DETAILED,
        }
        m = mode_map.get(mode)
        if m is None:
            valid = ", ".join(mode_map.keys())
            return f"Invalid mode '{mode}'. Choose from: {valid}"

        client = await get_client()
        await client.chat.set_mode(notebook_id=notebook_id, mode=m)
        return f"Chat mode set to '{mode}' for notebook '{notebook_id}'."
    except Exception as e:
        return _format_error("notebooklm_set_chat_mode", e)


@mcp.tool(
    name="notebooklm_list_artifacts",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def notebooklm_list_artifacts(
    notebook_id: str,
    limit: int = 50,
    offset: int = 0,
    response_format: ResponseFormat = ResponseFormat.JSON,
) -> str:
    """List all AI-generated artifacts (Audio, Reports, Quizzes, etc.) in a notebook.

    Args:
        notebook_id: Notebook ID. Find IDs via notebooklm_list_notebooks.
        limit: Max artifacts (1-100, default 50).
        offset: Artifacts to skip (default 0).
        response_format: "json" for structured data, "markdown" for a table.
    """
    try:
        client = await get_client()
        artifacts = await client.artifacts.list(notebook_id)
        items = [ArtifactInfo.from_artifact(a).model_dump() for a in artifacts]
        pg = _paginate(items, max(1, min(limit, 100)), max(0, offset))

        if response_format == ResponseFormat.MARKDOWN:
            cols = [("title", "Title"), ("type", "Type"), ("status", "Status"), ("id", "ID")]
            table = _render_markdown_table(pg["items"], cols)
            meta = f"\n\n*Showing {pg['count']} of {pg['total']} artifacts (offset {pg['offset']})*"
            return table + meta
        return _render_json(pg["items"], pg)
    except Exception as e:
        return _format_error("notebooklm_list_artifacts", e)


@mcp.tool(
    name="notebooklm_generate_audio",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def notebooklm_generate_audio(
    notebook_id: str,
    language: str = "en",
    instructions: str | None = None,
    response_format: ResponseFormat = ResponseFormat.JSON,
) -> str:
    """Generate an Audio Overview (AI podcast) from notebook sources.

    Generation takes a few minutes. Returns a task_id to track completion
    via notebooklm_list_artifacts.

    Args:
        notebook_id: Notebook ID. Find IDs via notebooklm_list_notebooks.
        language: Language code (default "en", e.g. "it", "fr", "de").
        instructions: Optional custom instructions for the hosts
                      (e.g. "Focus on technical details" or "Make it casual").
        response_format: "json" for structured data, "markdown" for a summary line.
    """
    try:
        client = await get_client()
        status = await client.artifacts.generate_audio(
            notebook_id=notebook_id,
            language=language,
            instructions=instructions,
        )
        gs = GenerationStatusInfo.from_generation_status(status)
        if response_format == ResponseFormat.MARKDOWN:
            return (
                f"## Audio Generation Started\n\n"
                f"**Task ID**: `{gs.task_id}`\n"
                f"**Status**: {gs.status}\n\n"
                f"Check completion with `notebooklm_list_artifacts`."
            )
        return json.dumps(gs.model_dump(), indent=2, default=str)
    except Exception as e:
        return _format_error("notebooklm_generate_audio", e)


@mcp.tool(
    name="notebooklm_generate_report",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def notebooklm_generate_report(
    notebook_id: str,
    report_format: str = "briefing_doc",
    custom_prompt: str | None = None,
    extra_instructions: str | None = None,
    response_format: ResponseFormat = ResponseFormat.JSON,
) -> str:
    """Generate a report from notebook sources.

    Returns a task_id; check completion via notebooklm_list_artifacts.

    Args:
        notebook_id: Notebook ID.
        report_format: "briefing_doc" (exec summary), "study_guide" (quiz + glossary),
                       "blog_post" (article), "custom" (requires custom_prompt).
        custom_prompt: Required for "custom" format. Describe the report you want.
        extra_instructions: Additional instructions appended to the template.
                            Ignored for "custom" format.
        response_format: "json" for structured data, "markdown" for a summary line.
    """
    try:
        from notebooklm.rpc.types import ReportFormat

        format_map = {
            "briefing_doc": ReportFormat.BRIEFING_DOC,
            "study_guide": ReportFormat.STUDY_GUIDE,
            "blog_post": ReportFormat.BLOG_POST,
            "custom": ReportFormat.CUSTOM,
        }
        fmt = format_map.get(report_format)
        if fmt is None:
            valid = ", ".join(format_map.keys())
            return f"Invalid report_format '{report_format}'. Choose from: {valid}"

        client = await get_client()
        status = await client.artifacts.generate_report(
            notebook_id=notebook_id,
            report_format=fmt,
            custom_prompt=custom_prompt,
            extra_instructions=extra_instructions,
        )
        gs = GenerationStatusInfo.from_generation_status(status)
        if response_format == ResponseFormat.MARKDOWN:
            return (
                f"## Report Generation Started\n\n"
                f"**Format**: {report_format}\n"
                f"**Task ID**: `{gs.task_id}`\n"
                f"**Status**: {gs.status}\n\n"
                f"Check completion with `notebooklm_list_artifacts`."
            )
        return json.dumps(gs.model_dump(), indent=2, default=str)
    except Exception as e:
        return _format_error("notebooklm_generate_report", e)


@mcp.tool(
    name="notebooklm_delete_artifact",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def notebooklm_delete_artifact(notebook_id: str, artifact_id: str) -> str:
    """⚠️ DESTRUCTIVE: Permanently delete an AI-generated artifact.

    Args:
        notebook_id: Notebook ID containing the artifact.
        artifact_id: Artifact ID to delete. Find IDs via notebooklm_list_artifacts.
    """
    try:
        client = await get_client()
        await client.artifacts.delete(notebook_id, artifact_id)
        return f"Artifact '{artifact_id}' deleted successfully."
    except Exception as e:
        return _format_error("notebooklm_delete_artifact", e)


# =========================================================================
# NOTE TOOLS (2)
# =========================================================================


@mcp.tool(
    name="notebooklm_list_notes",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def notebooklm_list_notes(
    notebook_id: str,
    limit: int = 50,
    offset: int = 0,
    response_format: ResponseFormat = ResponseFormat.JSON,
) -> str:
    """List all user-created notes in a notebook. Notes are distinct from AI artifacts.

    Args:
        notebook_id: Notebook ID. Find IDs via notebooklm_list_notebooks.
        limit: Max notes (1-100, default 50).
        offset: Notes to skip (default 0).
        response_format: "json" for structured data, "markdown" for a table.
    """
    try:
        client = await get_client()
        notes = await client.notes.list(notebook_id)
        items = [NoteInfo.from_note(n).model_dump() for n in notes]
        pg = _paginate(items, max(1, min(limit, 100)), max(0, offset))

        if response_format == ResponseFormat.MARKDOWN:
            cols = [("title", "Title"), ("id", "ID"), ("created_at", "Created")]
            table = _render_markdown_table(pg["items"], cols)
            meta = f"\n\n*Showing {pg['count']} of {pg['total']} notes*"
            return table + meta
        return _render_json(pg["items"], pg)
    except Exception as e:
        return _format_error("notebooklm_list_notes", e)


@mcp.tool(
    name="notebooklm_create_note",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def notebooklm_create_note(
    notebook_id: str,
    title: str = "New Note",
    content: str = "",
    response_format: ResponseFormat = ResponseFormat.JSON,
) -> str:
    """Create a new note in a notebook. Notes are user-created text content.

    Args:
        notebook_id: Notebook ID. Find IDs via notebooklm_list_notebooks.
        title: Note title (default "New Note").
        content: Note text content (plain text or markdown).
        response_format: "json" for structured data, "markdown" for a summary line.
    """
    try:
        client = await get_client()
        note = await client.notes.create(notebook_id, title, content)
        info = NoteInfo.from_note(note).model_dump()
        if response_format == ResponseFormat.MARKDOWN:
            preview = info["content"][:200] + ("..." if len(info["content"]) > 200 else "")
            return (
                f"## Note Created\n\n"
                f"**Title**: {info['title']}\n"
                f"**ID**: `{info['id']}`\n\n"
                f"**Preview**: {preview}"
            )
        return json.dumps(info, indent=2, default=str)
    except Exception as e:
        return _format_error("notebooklm_create_note", e)


# =========================================================================
# ACCOUNT TOOL (1)
# =========================================================================


@mcp.tool(
    name="notebooklm_get_account",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def notebooklm_get_account(
    response_format: ResponseFormat = ResponseFormat.JSON,
) -> str:
    """Get NotebookLM account tier and limits (max notebooks, sources per notebook).

    Args:
        response_format: "json" for structured data, "markdown" for a summary.
    """
    try:
        client = await get_client()
        limits = await client.settings.get_account_limits()
        tier = await client.settings.get_account_tier()
        info = AccountInfo(
            tier=getattr(tier, "tier", None),
            plan_name=getattr(tier, "plan_name", None),
            notebook_limit=getattr(limits, "notebook_limit", None),
            source_limit=getattr(limits, "source_limit", None),
        ).model_dump()
        if response_format == ResponseFormat.MARKDOWN:
            return (
                f"## Account Info\n\n"
                f"**Tier**: {info.get('tier', 'Unknown')}\n"
                f"**Plan**: {info.get('plan_name', 'Unknown')}\n"
                f"**Max Notebooks**: {info.get('notebook_limit', 'N/A')}\n"
                f"**Max Sources/Notebook**: {info.get('source_limit', 'N/A')}"
            )
        return json.dumps(info, indent=2, default=str)
    except Exception as e:
        return _format_error("notebooklm_get_account", e)


# =========================================================================
# Entry point
# =========================================================================


def main() -> None:
    """Run the MCP server via stdio transport (Claude Code default)."""
    mcp.run()


if __name__ == "__main__":
    main()
