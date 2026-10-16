"""Approval binding. Phase 5.1 adds PendingApproval creation/execution on top of this."""

import uuid
from typing import Any

from app.security.audit import canonical_json, sha256_hex


def approval_binding_hash(
    *,
    action: str,
    tier: int,
    deal_id: uuid.UUID | None,
    milestone_id: uuid.UUID | None,
    bank_account_id: uuid.UUID | None,
    params: dict[str, Any],
) -> str:
    """sha256 over everything an approval authorises, so changing any column after approval
    (action, tier, target ids or params) makes the execution-time check fail."""
    return sha256_hex(
        canonical_json(
            {
                "action": action,
                "tier": tier,
                "deal_id": str(deal_id) if deal_id else None,
                "milestone_id": str(milestone_id) if milestone_id else None,
                "bank_account_id": str(bank_account_id) if bank_account_id else None,
                "params": params,
            }
        )
    )
