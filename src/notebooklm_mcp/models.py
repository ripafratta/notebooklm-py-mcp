"""Pydantic models for notebooklm-mcp tool inputs and outputs.

All models use Pydantic v2 patterns with Field descriptions that
become JSON Schema for Claude's tool-use understanding.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# =========================================================================
# Shared enums
# =========================================================================


class ResponseFormat(str, Enum):
    """Output format for tool responses."""

    MARKDOWN = "markdown"
    JSON = "json"


# =========================================================================
# Pagination
# =========================================================================


class PaginationMeta(BaseModel):
    """Pagination metadata included in list responses."""

    total: int = Field(description="Total number of items available")
    count: int = Field(description="Number of items returned in this page")
    offset: int = Field(description="Current offset (0-based)")
    has_more: bool = Field(description="Whether there are more items after this page")
    next_offset: int | None = Field(
        default=None, description="Offset for the next page, or null if no more"
    )


# =========================================================================
# Notebook models
# =========================================================================


class NotebookInfo(BaseModel):
    """Summary of a NotebookLM notebook."""

    id: str = Field(description="Unique notebook identifier (UUID string)")
    title: str = Field(description="Display title of the notebook")
    sources_count: int = Field(
        default=0, description="Number of sources in the notebook"
    )
    is_owner: bool = Field(
        default=True, description="Whether the authenticated user owns this notebook"
    )
    created_at: str | None = Field(
        default=None, description="ISO-8601 creation timestamp"
    )

    @classmethod
    def from_notebook(cls, nb: Any) -> "NotebookInfo":
        """Build from a notebooklm.types.Notebook object."""
        created = None
        if nb.created_at and isinstance(nb.created_at, datetime):
            created = nb.created_at.isoformat()
        return cls(
            id=nb.id,
            title=nb.title,
            sources_count=getattr(nb, "sources_count", 0),
            is_owner=getattr(nb, "is_owner", True),
            created_at=created,
        )


class NotebookListResult(BaseModel):
    """Paginated list of notebooks."""

    notebooks: list[NotebookInfo] = Field(description="List of notebooks in this page")
    pagination: PaginationMeta


# =========================================================================
# Source models
# =========================================================================


class SourceInfo(BaseModel):
    """Summary of a source in a notebook."""

    id: str = Field(description="Unique source identifier (UUID string)")
    title: str | None = Field(
        default=None, description="Display title of the source"
    )
    type: str = Field(
        default="unknown",
        description="Source type: web_page, youtube, pdf, pasted_text, google_docs, markdown, etc.",
    )
    url: str | None = Field(
        default=None, description="Original URL (for web/YouTube sources)"
    )
    status: str = Field(
        default="unknown",
        description="Processing status: ready, processing, error, preparing",
    )
    created_at: str | None = Field(
        default=None, description="ISO-8601 creation timestamp"
    )

    @classmethod
    def from_source(cls, src: Any) -> "SourceInfo":
        """Build from a notebooklm.types.Source object."""
        created = None
        if src.created_at and isinstance(src.created_at, datetime):
            created = src.created_at.isoformat()
        kind = getattr(src, "kind", "unknown")
        status = (
            "ready"
            if getattr(src, "is_ready", False)
            else (
                "processing"
                if getattr(src, "is_processing", False)
                else "error" if getattr(src, "is_error", False) else "unknown"
            )
        )
        return cls(
            id=src.id,
            title=src.title,
            type=str(kind) if kind else "unknown",
            url=getattr(src, "url", None),
            status=status,
            created_at=created,
        )


class SourceListResult(BaseModel):
    """Paginated list of sources."""

    sources: list[SourceInfo] = Field(description="List of sources in this page")
    pagination: PaginationMeta


class SourceContent(BaseModel):
    """Full extracted text content of a source."""

    id: str = Field(description="Source identifier")
    title: str = Field(description="Source display title")
    content: str = Field(description="Full extracted/OCR text from the source")
    url: str | None = Field(default=None, description="Original source URL")
    char_count: int = Field(description="Total character count of the content")

    @classmethod
    def from_fulltext(cls, ft: Any) -> "SourceContent":
        """Build from a notebooklm.types.SourceFulltext object."""
        return cls(
            id=ft.source_id,
            title=ft.title,
            content=ft.content,
            url=getattr(ft, "url", None),
            char_count=getattr(ft, "char_count", len(ft.content)),
        )


class SourceGuide(BaseModel):
    """AI-generated summary and keywords for a source."""

    source_id: str = Field(description="Source identifier")
    summary: str = Field(description="AI-generated summary of the source")
    keywords: list[str] = Field(
        default_factory=list, description="Extracted keywords from the source"
    )


# =========================================================================
# Chat models
# =========================================================================


class CitationInfo(BaseModel):
    """A citation reference from a chat answer."""

    source_id: str = Field(description="Source ID that was cited")
    citation_number: int = Field(description="Citation number in the answer text")
    cited_text: str = Field(description="The text passage that was cited")
    start_char: int | None = Field(default=None, description="Start character offset")
    end_char: int | None = Field(default=None, description="End character offset")


class ChatAnswer(BaseModel):
    """Answer from a NotebookLM chat query."""

    answer: str = Field(description="The AI-generated answer text")
    conversation_id: str = Field(
        description="Conversation ID to use for follow-up questions via chat_ask"
    )
    turn_number: int = Field(
        default=1, description="Turn number in this conversation (1-based)"
    )
    is_follow_up: bool = Field(
        default=False, description="Whether this was a follow-up to a prior question"
    )
    citations: list[CitationInfo] = Field(
        default_factory=list,
        description="Sources cited in the answer with text excerpts",
    )

    @classmethod
    def from_ask_result(cls, result: Any) -> "ChatAnswer":
        """Build from a notebooklm.types.AskResult object."""
        citations = []
        for ref in getattr(result, "references", []) or []:
            citations.append(
                CitationInfo(
                    source_id=getattr(ref, "source_id", ""),
                    citation_number=getattr(ref, "citation_number", 0),
                    cited_text=getattr(ref, "cited_text", ""),
                    start_char=getattr(ref, "start_char", None),
                    end_char=getattr(ref, "end_char", None),
                )
            )
        return cls(
            answer=result.answer,
            conversation_id=result.conversation_id,
            turn_number=getattr(result, "turn_number", 1),
            is_follow_up=getattr(result, "is_follow_up", False),
            citations=citations,
        )


class ChatHistoryItem(BaseModel):
    """A single Q&A turn in a conversation."""

    turn_number: int = Field(description="Turn number (1-based)")
    question: str = Field(description="The user's question")
    answer: str = Field(description="The AI's answer")


class ChatHistoryResult(BaseModel):
    """Paginated chat history."""

    turns: list[ChatHistoryItem] = Field(description="Conversation turns in this page")
    pagination: PaginationMeta


# =========================================================================
# Artifact models
# =========================================================================


class ArtifactInfo(BaseModel):
    """Summary of an AI-generated artifact."""

    id: str = Field(description="Unique artifact identifier (UUID string)")
    title: str = Field(description="Artifact display title")
    type: str = Field(
        description="Artifact type: audio, video, report, quiz, flashcards, "
        "mind_map, infographic, slide_deck, data_table"
    )
    status: str = Field(
        description="Generation status: completed, processing, pending, failed"
    )
    created_at: str | None = Field(
        default=None, description="ISO-8601 creation timestamp"
    )

    @classmethod
    def from_artifact(cls, art: Any) -> "ArtifactInfo":
        """Build from a notebooklm.types.Artifact object."""
        created = None
        if art.created_at and isinstance(art.created_at, datetime):
            created = art.created_at.isoformat()
        kind = getattr(art, "kind", "unknown")
        status = (
            "completed"
            if getattr(art, "is_completed", False)
            else (
                "processing"
                if getattr(art, "is_processing", False)
                else (
                    "pending"
                    if getattr(art, "is_pending", False)
                    else "failed" if getattr(art, "is_failed", False) else "unknown"
                )
            )
        )
        return cls(
            id=art.id,
            title=art.title,
            type=str(kind) if kind else "unknown",
            status=status,
            created_at=created,
        )


class ArtifactListResult(BaseModel):
    """Paginated list of artifacts."""

    artifacts: list[ArtifactInfo] = Field(description="List of artifacts in this page")
    pagination: PaginationMeta


class GenerationStatusInfo(BaseModel):
    """Status of an artifact generation request."""

    task_id: str = Field(description="Task ID for polling completion")
    status: str = Field(
        description="Current status: pending, in_progress, completed, failed"
    )
    url: str | None = Field(
        default=None, description="URL to access the artifact when completed"
    )
    error: str | None = Field(
        default=None, description="Error message if generation failed"
    )

    @classmethod
    def from_generation_status(cls, gs: Any) -> "GenerationStatusInfo":
        """Build from a notebooklm.types.GenerationStatus object."""
        return cls(
            task_id=gs.task_id,
            status=gs.status,
            url=getattr(gs, "url", None),
            error=getattr(gs, "error", None),
        )


# =========================================================================
# Note models
# =========================================================================


class NoteInfo(BaseModel):
    """A user-created note in a notebook."""

    id: str = Field(description="Note identifier")
    title: str = Field(description="Note title")
    content: str = Field(
        description="Note content (may be truncated for long notes)"
    )
    notebook_id: str = Field(description="Parent notebook ID")
    created_at: str | None = Field(
        default=None, description="ISO-8601 creation timestamp"
    )

    @classmethod
    def from_note(cls, note: Any) -> "NoteInfo":
        """Build from a notebooklm.types.Note object."""
        created = None
        if note.created_at and isinstance(note.created_at, datetime):
            created = note.created_at.isoformat()
        content = note.content
        if len(content) > 10000:
            content = (
                content[:10000]
                + f"\n\n[... truncated, {len(note.content)} total chars]"
            )
        return cls(
            id=note.id,
            title=note.title,
            content=content,
            notebook_id=note.notebook_id,
            created_at=created,
        )


class NoteListResult(BaseModel):
    """Paginated list of notes."""

    notes: list[NoteInfo] = Field(description="List of notes in this page")
    pagination: PaginationMeta


# =========================================================================
# Account models
# =========================================================================


class AccountInfo(BaseModel):
    """Account tier and limits information."""

    tier: str | None = Field(
        default=None,
        description="Account tier label (e.g., 'standard', 'plus', 'pro', 'ultra')",
    )
    plan_name: str | None = Field(
        default=None, description="Human-readable plan name"
    )
    notebook_limit: int | None = Field(
        default=None, description="Maximum number of notebooks allowed"
    )
    source_limit: int | None = Field(
        default=None, description="Maximum sources per notebook"
    )
