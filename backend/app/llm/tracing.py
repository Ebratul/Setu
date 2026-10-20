"""LangSmith tracing, configured from settings (never from os.environ directly).

Tracing is on only when LANGSMITH_TRACING=true and LANGSMITH_API_KEY is set. Runs go to
LANGSMITH_PROJECT (default "setu"). Run metadata carries ids and roles only. Traced inputs and
outputs are what the model sees, so they become masked once the Privacy Gateway lands (P18).
"""

import uuid
from functools import lru_cache
from types import SimpleNamespace

import structlog
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.tracers import LangChainTracer
from langsmith import Client

from app.config import get_settings

log = structlog.get_logger("setu.tracing")


def tracing_enabled() -> bool:
    s = get_settings()
    key = s.langsmith_api_key
    return s.langsmith_tracing and key is not None and bool(key.get_secret_value().strip())


@lru_cache
def _client(api_key: str) -> Client:
    return Client(api_key=api_key)


def langsmith_client() -> Client | None:
    s = get_settings()
    if not tracing_enabled() or s.langsmith_api_key is None:
        return None
    return _client(s.langsmith_api_key.get_secret_value())


def callbacks() -> list[BaseCallbackHandler]:
    client = langsmith_client()
    if client is None:
        return []
    return [LangChainTracer(project_name=get_settings().langsmith_project, client=client)]


def tag_run(run_id: uuid.UUID, tags: list[str]) -> None:
    """Add tags known only after routing (intent, model) to the root run. Best effort."""
    client = langsmith_client()
    if client is None:
        return
    try:
        client.update_run(run_id, tags=tags)
    except Exception as exc:
        log.warning("langsmith_tag_failed", error=type(exc).__name__)


def run_url(run_id: uuid.UUID) -> str | None:
    client = langsmith_client()
    if client is None:
        return None
    try:
        # get_run_url only reads the run id (and builds the URL from the project).
        run = SimpleNamespace(id=run_id)
        return client.get_run_url(
            run=run,  # type: ignore[arg-type]
            project_name=get_settings().langsmith_project,
        )
    except Exception as exc:
        log.warning("langsmith_url_failed", error=type(exc).__name__)
        return None
