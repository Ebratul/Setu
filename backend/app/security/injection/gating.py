"""Layer 4 - tool-call gating against the USER's intent.

While the model is working with untrusted blocks, each tool call it proposes is checked against
what the user asked for (the router's intent and the user's own words, never the content). A
"check my document" request may call `check_documents`; it can never lead to `propose_release_tranche`
or `propose_change_beneficiary`, whatever a document says. Disallowed calls are dropped, logged as
INJECTION_BLOCKED_TOOL and reported in the answer.
"""

import re
from dataclasses import dataclass

# Tier 0 "propose" tools: they only queue an approval for a person, but they are the money surface.
MONEY_TOOLS = frozenset(
    {
        "propose_release_tranche",
        "propose_milestones",
        "propose_confirm_milestones",
        "propose_fund_escrow",
        "propose_fx_lock",
        "propose_change_beneficiary",
    }
)

_REQUEST: dict[str, re.Pattern[str]] = {
    "propose_release_tranche": re.compile(
        r"\b(release|pay|send|disburse|payout)\b|ছাড়|পরিশোধ|পাঠা|放款|释放|支付",
        re.I,
    ),
    "propose_milestones": re.compile(
        r"\b(milestones?|schedule|split)\b|মাইলস্টোন|শিডিউল|里程碑|计划", re.I
    ),
    "propose_confirm_milestones": re.compile(
        r"\b(confirm|accept|agree)\b.{0,30}\b(milestones?|schedule)\b|নিশ্চিত|确认", re.I
    ),
    "propose_fund_escrow": re.compile(r"\b(fund|deposit|top\s*up)\b|জমা|ফান্ড|存入|注资", re.I),
    "propose_fx_lock": re.compile(r"\block\b|লক|锁定", re.I),
    "propose_change_beneficiary": re.compile(
        r"\b(change|update|new|replace)\b.{0,30}\b(account|beneficiary|bank)\b|"
        r"(অ্যাকাউন্ট|একাউন্ট|হিসাব).{0,20}(পরিবর্তন|বদল)|(更改|变更|更换).{0,6}(账户|账号)",
        re.I,
    ),
}


@dataclass(frozen=True, slots=True)
class GateDecision:
    allowed: bool
    code: str = ""
    reason: str = ""


ALLOW = GateDecision(True)


def user_requested(tool: str, user_text: str) -> bool:
    pattern = _REQUEST.get(tool)
    return bool(pattern and pattern.search(user_text or ""))


def gate_call(
    tool: str,
    *,
    intent_allowed: frozenset[str],
    user_text: str,
    untrusted_seen: bool,
    turn_flagged: bool,
) -> GateDecision:
    """Decide one proposed tool call. `intent_allowed` is the router intent's allow-list."""
    if tool in MONEY_TOOLS:
        if tool not in intent_allowed:
            return GateDecision(
                False, "NOT_FOR_THIS_REQUEST", "the user's request does not call for it"
            )
        if turn_flagged:
            return GateDecision(
                False, "FLAGGED_CONTENT_IN_TURN", "content in this turn carried an instruction"
            )
        if untrusted_seen and not user_requested(tool, user_text):
            return GateDecision(
                False, "NOT_REQUESTED_BY_USER", "the user did not ask for this money action"
            )
    elif tool not in intent_allowed and (untrusted_seen or turn_flagged):
        # An action the request never needed, proposed after untrusted content was read.
        return GateDecision(
            False, "NOT_FOR_THIS_REQUEST", "the user's request does not call for it"
        )
    return ALLOW
