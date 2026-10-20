from pathlib import Path

# `app.agent` and `app.rag` live in the sibling rag_agent/ folder; extending the package path keeps
# every `from app.agent...` / `from app.rag...` import working unchanged. A Vercel bundle stages
# rag_agent/ inside backend/ (the function root), so that location is tried second.
_BACKEND = Path(__file__).resolve().parent.parent
for _candidate in (_BACKEND.parent / "rag_agent" / "app", _BACKEND / "rag_agent" / "app"):
    if _candidate.is_dir():
        __path__.append(str(_candidate))
        break
