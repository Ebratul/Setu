"""Signed, hash-chained audit log (SR-5). See docs/audit.md."""

from app.audit.writer import current_actor_id, write_audit

__all__ = ["current_actor_id", "write_audit"]
