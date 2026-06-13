"""Singleton NotebookLMClient lifecycle management.

Provides lazy initialization of the NotebookLMClient with keepalive support
for long-running Claude Code sessions.

Auth priority:
1. NOTEBOOKLM_AUTH_JSON env var (inline Playwright storage state)
2. Default profile at ~/.notebooklm/profiles/<name>/
3. NOTEBOOKLM_PROFILE env var to override profile selection
"""

import logging
import os
from typing import Any

from notebooklm import NotebookLMClient
from notebooklm.auth import AuthTokens

logger = logging.getLogger(__name__)

_client: NotebookLMClient | None = None
_auth_error: str | None = None


async def get_client() -> NotebookLMClient:
    """Get or initialize the singleton NotebookLMClient.

    The client is initialized on first call and reused across all tool
    invocations during the MCP server lifetime. Keepalive is enabled to
    prevent token expiry during long human-in-the-loop sessions.

    Returns:
        NotebookLMClient: The initialized client.

    Raises:
        ValueError: If authentication fails with a clear message.
    """
    global _client, _auth_error

    if _client is not None:
        return _client

    # If we already tried and failed, report the cached error
    if _auth_error is not None:
        raise ValueError(_auth_error)

    profile = os.environ.get("NOTEBOOKLM_PROFILE")

    try:
        # Try environment variable first (inline JSON)
        auth_json = os.environ.get("NOTEBOOKLM_AUTH_JSON")
        if auth_json:
            import json

            storage_data: dict[str, Any] = json.loads(auth_json)
            auth = AuthTokens.from_storage(storage_data)
            _client = NotebookLMClient(auth=auth, keepalive=600.0)
        else:
            # Fall back to profile-based storage
            _client = await NotebookLMClient.from_storage(
                profile=profile,
                keepalive=600.0,
            )

        await _client.__aenter__()
        logger.info("NotebookLMClient initialized successfully")
        return _client

    except (ValueError, FileNotFoundError) as e:
        _auth_error = (
            f"NotebookLM authentication failed: {e}\n\n"
            "To fix this:\n"
            "  1. Run 'notebooklm login' in your terminal to authenticate via browser, or\n"
            "  2. Set the NOTEBOOKLM_AUTH_JSON environment variable with your "
            "Playwright storage state JSON."
        )
        raise ValueError(_auth_error) from e

    except Exception as e:
        _auth_error = (
            f"Unexpected error initializing NotebookLM client: {e}\n\n"
            "Ensure notebooklm-py is installed and your authentication is valid. "
            "Run 'notebooklm doctor' to diagnose issues."
        )
        raise RuntimeError(_auth_error) from e


async def close_client() -> None:
    """Close the NotebookLMClient and clean up resources.

    Called on MCP server shutdown. Safe to call multiple times.
    """
    global _client, _auth_error

    if _client is not None:
        try:
            await _client.__aexit__(None, None, None)
            logger.info("NotebookLMClient closed")
        except Exception as e:
            logger.warning("Error closing NotebookLMClient: %s", e)
        finally:
            _client = None
    _auth_error = None
