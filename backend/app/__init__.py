from pathlib import Path

# `app.agent` and `app.rag` live in the sibling rag_agent/ folder; extending the package path keeps
# every `from app.agent...` / `from app.rag...` import working unchanged.
_RAG_AGENT_APP = Path(__file__).resolve().parent.parent.parent / "rag_agent" / "app"
if _RAG_AGENT_APP.is_dir():
    __path__.append(str(_RAG_AGENT_APP))
