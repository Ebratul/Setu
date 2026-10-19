"""Deterministic risk-tier engine (SR-1, SR-2). Pure: no DB, no clock, no LLM, no I/O.

`evaluate(RiskContext) -> RiskDecision`. The context is built by code from DB rows (see
`context.py`), never from model text or request fields. Every rule is a function of the context and
the thresholds in `config/risk.yaml`; the highest matching tier wins and BLOCK beats every tier.

Which rule applies to which action is the `APPLIES` table below, so the behaviour of each action
is visible in one place:
- BLOCK rules: every money action.
- Release-only: amount, advance held, documents, first deal, KYB account warning, FX lock.
- FUND_ESCROW moves the buyer's own cash into escrow, not out to a third party, so only the BLOCK
  rules and the agent-origin rule apply; the supplier-bound rules apply at release.
"""

import hashlib
from decimal import Decimal
from enum import StrEnum
from typing import Literal, NamedTuple

from pydantic import BaseModel, ConfigDict, Field

from app.security.audit import canonical_json
from app.security.policy import RiskPolicy, load_policy
from app.security.risk_hook import RiskDecision as Verdict


class Action(StrEnum):
    RELEASE_TRANCHE = "RELEASE_TRANCHE"
    LOCK_FX = "LOCK_FX"
    CONFIRM_MILESTONES = "CONFIRM_MILESTONES"
    PROPOSE_MILESTONES = "PROPOSE_MILESTONES"
    CHANGE_BENEFICIARY = "CHANGE_BENEFICIARY"
    FUND_ESCROW = "FUND_ESCROW"
    ANALYSIS = "ANALYSIS"  # non-money: analysis and checks (Tier 0)


class Origin(StrEnum):
    USER_UI = "USER_UI"
    AGENT = "AGENT"
    SYSTEM = "SYSTEM"


MONEY_ACTIONS = frozenset(a for a in Action if a != Action.ANALYSIS)
ALL_MONEY = MONEY_ACTIONS
RELEASE = frozenset({Action.RELEASE_TRANCHE})
BENEFICIARY = frozenset({Action.RELEASE_TRANCHE, Action.CHANGE_BENEFICIARY})


class RiskContext(BaseModel):
    """Facts only. Built from the database by code; `extra="forbid"` so a stray client field such
    as `tier` or `approved` cannot ride along."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    action: Action
    origin: Origin = Origin.USER_UI
    amount: Decimal = Decimal("0")
    currency: str = "USD"
    amount_usd: Decimal = Decimal("0")  # unrounded: never round a limit away
    buyer_id: str = ""
    supplier_id: str = ""
    is_first_deal_with_supplier: bool = False
    beneficiary_changed_recently: bool = False
    beneficiary_status: str = "ACTIVE"  # ACTIVE | PENDING_CHANGE | RETIRED | BLOCKED
    beneficiary_verified: bool = True
    kyb_status: str = "VERIFIED"  # VERIFIED | WARNING | BLOCKED
    kyb_account_warning: bool = False  # WARNING caused by an account-related check
    max_document_fraud_score: int = Field(default=0, ge=0, le=100)
    any_document_warning: bool = False
    any_document_failed: bool = False
    duplicate_hash: bool = False
    instruction_from_document: bool = False
    sanctions_hit: bool = False
    advance_over_limit: bool = False  # total held in escrow above the Tier 1 limit
    fx_lock_missing: bool = False  # settlement needs a currency conversion with no active lock
    deal_ref: str = ""
    milestone_seq: int | None = None


class Reason(NamedTuple):
    code: str
    tier: int  # 3 for BLOCK reasons; `blocking` is what matters
    blocking: bool
    en: str
    bn: str


class RiskDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    decision: Verdict
    tier: int = Field(ge=0, le=3)
    reason_codes: list[str]
    explanation_en: str
    explanation_bn: str
    context_hash: str
    decided_by: list[str] = Field(default_factory=list)  # rules that set the final tier
    trace: "list[TraceItem]" = Field(default_factory=list)
    hints: "list[Hint]" = Field(default_factory=list)


# code -> (English, Bangla). Wording is fixed text: the explanation is as deterministic as the tier.
TEXT: dict[str, tuple[str, str]] = {
    "SANCTIONS_HIT": ("A party matched the sanctions list.", "একটি পক্ষ নিষেধাজ্ঞা তালিকার সাথে মিলেছে।"),
    "KYB_BLOCKED": ("The supplier is blocked by KYB.", "সরবরাহকারী কেওয়াইবিতে ব্লক করা আছে।"),
    "BENEFICIARY_BLOCKED": (
        "The receiving account is blocked.",
        "প্রাপক অ্যাকাউন্টটি ব্লক করা আছে।",
    ),
    "DOCUMENT_FAILED": (
        "A document for this tranche failed the forensic checks.",
        "এই কিস্তির একটি ডকুমেন্ট যাচাইয়ে ব্যর্থ হয়েছে।",
    ),
    "AMOUNT_OVER_LIMIT": (
        "The amount is above the USD 20,000 automatic limit.",
        "পরিমাণ USD 20,000 স্বয়ংক্রিয় সীমার উপরে।",
    ),
    "ADVANCE_OVER_LIMIT": (
        "The advance held in escrow is above the USD 20,000 limit.",
        "এসক্রোতে রাখা অগ্রিম USD 20,000 সীমার উপরে।",
    ),
    "BENEFICIARY_CHANGE": (
        "This changes the receiving account.",
        "এতে প্রাপক অ্যাকাউন্ট পরিবর্তন হচ্ছে।",
    ),
    "BENEFICIARY_PENDING_CHANGE": (
        "The receiving account has a change waiting for review.",
        "প্রাপক অ্যাকাউন্টের একটি পরিবর্তন যাচাইয়ের অপেক্ষায় আছে।",
    ),
    "BENEFICIARY_CHANGED_RECENTLY": (
        "The receiving account was changed or opened recently.",
        "প্রাপক অ্যাকাউন্ট সম্প্রতি পরিবর্তিত বা খোলা হয়েছে।",
    ),
    "FRAUD_SCORE_HIGH": (
        "A document has a high fraud score.",
        "একটি ডকুমেন্টের জালিয়াতি স্কোর বেশি।",
    ),
    "DUPLICATE_HASH": (
        "A document was already used as evidence or collateral.",
        "একটি ডকুমেন্ট আগেই প্রমাণ বা জামানত হিসেবে ব্যবহৃত হয়েছে।",
    ),
    "DOC_INSTRUCTION": (
        "A document contained instruction-like text, which was ignored.",
        "একটি ডকুমেন্টে নির্দেশের মতো লেখা ছিল, যা উপেক্ষা করা হয়েছে।",
    ),
    "KYB_ACCOUNT_WARNING": (
        "The supplier's KYB warning concerns the receiving account.",
        "সরবরাহকারীর কেওয়াইবি সতর্কতা প্রাপক অ্যাকাউন্ট নিয়ে।",
    ),
    "FIRST_DEAL": ("First deal with this supplier.", "এই সরবরাহকারীর সাথে প্রথম চুক্তি।"),
    "DOCUMENT_WARNING": (
        "A document has a forensic warning.",
        "একটি ডকুমেন্টে যাচাইয়ের সতর্কতা আছে।",
    ),
    "LOCK_FX": ("Locking an FX rate needs a person's approval.", "বিনিময় হার লক করতে অনুমোদন লাগবে।"),
    "CONFIRM_MILESTONES": (
        "Confirming the milestone schedule needs a person's approval.",
        "কিস্তির সূচি নিশ্চিত করতে অনুমোদন লাগবে।",
    ),
    "PROPOSE_MILESTONES": (
        "Creating or changing the milestone schedule needs a person's approval.",
        "কিস্তির সূচি তৈরি বা পরিবর্তনে অনুমোদন লাগবে।",
    ),
    "AGENT_ORIGIN": (
        "The assistant can only propose this; a person must confirm.",
        "সহকারী শুধু প্রস্তাব দিতে পারে; একজন ব্যক্তিকে নিশ্চিত করতে হবে।",
    ),
    "FX_RATE_NOT_LOCKED": (
        "The payment converts currency and no rate is locked.",
        "পেমেন্টে মুদ্রা রূপান্তর হচ্ছে কিন্তু কোনো হার লক করা নেই।",
    ),
    "NOT_FULLY_VERIFIED": (
        "The supplier or receiving account is not fully verified.",
        "সরবরাহকারী বা প্রাপক অ্যাকাউন্ট পুরোপুরি যাচাই করা নয়।",
    ),
    "AUTO_OK": (
        "Everything is verified and within the automatic limit.",
        "সবকিছু যাচাই করা এবং স্বয়ংক্রিয় সীমার মধ্যে।",
    ),
}


def _reason(tier: int, code: str, blocking: bool = False) -> Reason:
    en, bn = TEXT[code]
    return Reason(code, tier, blocking, en, bn)


class TraceItem(BaseModel):
    """One rule as evaluated for this decision: did it fire, on what value, and was it the one
    that set the final tier. `value_*` is a fixed template filled with context numbers."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    kind: Literal["BLOCK", "TIER3", "TIER2"]
    fired: bool
    deciding: bool = False
    label_en: str
    label_bn: str
    value_en: str
    value_bn: str


class Hint(BaseModel):
    """A deterministic counterfactual: what would clear a fired rule."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    to_tier: int | None
    text_en: str
    text_bn: str


HINTS: dict[str, tuple[int | None, str, str]] = {
    "FIRST_DEAL": (
        1,
        "Tier 2 → Tier 1 after one completed deal with this supplier.",
        "এই সরবরাহকারীর সাথে একটি চুক্তি সম্পন্ন হলে টিয়ার ২ থেকে টিয়ার ১ হবে।",
    ),
    "DOCUMENT_WARNING": (
        1,
        "Upload a corrected or missing document to clear the warning.",
        "সতর্কতা দূর করতে সংশোধিত বা অনুপস্থিত ডকুমেন্ট আপলোড করুন।",
    ),
    "AMOUNT_OVER_LIMIT": (
        1,
        "Split the payment into tranches of at most the automatic limit.",
        "পেমেন্টকে স্বয়ংক্রিয় সীমার মধ্যে কিস্তিতে ভাগ করুন।",
    ),
    "ADVANCE_OVER_LIMIT": (
        1,
        "Deposit tranche by tranche so escrow never holds more than the limit.",
        "কিস্তি অনুযায়ী জমা দিন, যাতে এসক্রোতে সীমার বেশি না থাকে।",
    ),
    "BENEFICIARY_CHANGED_RECENTLY": (
        1,
        "Becomes Tier 1 once the receiving account is older than the minimum age.",
        "প্রাপক অ্যাকাউন্ট নির্ধারিত বয়স পার করলে টিয়ার ১ হবে।",
    ),
    "BENEFICIARY_PENDING_CHANGE": (
        None,
        "Approve or reject the pending account change first.",
        "আগে অপেক্ষমাণ অ্যাকাউন্ট পরিবর্তন অনুমোদন বা বাতিল করুন।",
    ),
    "BENEFICIARY_CHANGE": (
        None,
        "A change of receiving account always needs the strictest approval.",
        "প্রাপক অ্যাকাউন্ট পরিবর্তনে সবসময় কঠোরতম অনুমোদন লাগে।",
    ),
    "FRAUD_SCORE_HIGH": (
        None,
        "Ask the supplier for a clean original document and re-run the checks.",
        "সরবরাহকারীর কাছ থেকে নির্ভুল মূল ডকুমেন্ট নিয়ে যাচাই আবার চালান।",
    ),
    "DUPLICATE_HASH": (
        None,
        "Use a document that has not been used as evidence or collateral elsewhere.",
        "অন্যত্র প্রমাণ বা জামানত হিসেবে ব্যবহার হয়নি এমন ডকুমেন্ট ব্যবহার করুন।",
    ),
    "DOC_INSTRUCTION": (
        None,
        "Replace the document; a person must review the hidden text.",
        "ডকুমেন্ট বদলান; লুকানো লেখা একজন ব্যক্তিকে দেখতে হবে।",
    ),
    "KYB_ACCOUNT_WARNING": (
        None,
        "Resolve the account mismatch in the supplier's KYB, then re-verify.",
        "সরবরাহকারীর কেওয়াইবিতে অ্যাকাউন্টের অমিল মিটিয়ে আবার যাচাই করুন।",
    ),
    "NOT_FULLY_VERIFIED": (
        1,
        "Re-run supplier verification until the supplier and account are verified.",
        "সরবরাহকারী ও অ্যাকাউন্ট যাচাই না হওয়া পর্যন্ত যাচাই আবার চালান।",
    ),
    "FX_RATE_NOT_LOCKED": (
        1,
        "Lock the FX rate (one tap) before releasing.",
        "ছাড়ের আগে বিনিময় হার লক করুন (এক ট্যাপ)।",
    ),
    "AGENT_ORIGIN": (
        1,
        "Do it yourself in the app: a person's own request is not limited by this rule.",
        "অ্যাপে নিজে করুন: ব্যক্তির নিজের অনুরোধে এই নিয়ম প্রযোজ্য নয়।",
    ),
    "LOCK_FX": (
        None,
        "Lock the rate yourself in the app (one tap).",
        "অ্যাপে নিজে হার লক করুন (এক ট্যাপ)।",
    ),
    "CONFIRM_MILESTONES": (
        None,
        "Confirm the schedule yourself in the app (one tap).",
        "অ্যাপে নিজে সূচি নিশ্চিত করুন (এক ট্যাপ)।",
    ),
    "PROPOSE_MILESTONES": (
        None,
        "Create the schedule yourself in the app (one tap).",
        "অ্যাপে নিজে সূচি তৈরি করুন (এক ট্যাপ)।",
    ),
}
BLOCK_HINT = (
    "This cannot be lowered here: it is blocked until the underlying problem is resolved.",
    "এটি এখানে কমানো যাবে না: মূল সমস্যা না মেটা পর্যন্ত আটকানো থাকবে।",
)


class _Eval(NamedTuple):
    code: str
    tier: int
    blocking: bool
    applies: frozenset[Action]
    fired: bool
    value: tuple[str, str]


def _usd(v: Decimal) -> str:
    text = f"{v:,.2f}"
    return text[:-3] if text.endswith(".00") else text


def _yn(flag: bool) -> tuple[str, str]:
    return ("yes", "হ্যাঁ") if flag else ("no", "না")


def _eval(ctx: RiskContext, p: RiskPolicy) -> list[_Eval]:
    """Every rule, whether or not it applies to the action, with the value it looked at."""
    limit = _usd(p.tier1_max_usd)
    amount = _usd(ctx.amount_usd)
    out: list[_Eval] = []

    def rule(
        code: str,
        tier: int,
        applies: frozenset[Action],
        fired: bool,
        value: tuple[str, str],
        *,
        block: bool = False,
    ) -> None:
        out.append(_Eval(code, tier, block, applies, fired, value))

    def flag(v: bool) -> tuple[str, str]:
        return _yn(v)

    rule("SANCTIONS_HIT", 3, ALL_MONEY, ctx.sanctions_hit, flag(ctx.sanctions_hit), block=True)
    rule(
        "KYB_BLOCKED",
        3,
        ALL_MONEY,
        ctx.kyb_status == "BLOCKED",
        (f"KYB status {ctx.kyb_status}", f"কেওয়াইবি অবস্থা {ctx.kyb_status}"),
        block=True,
    )
    rule(
        "BENEFICIARY_BLOCKED",
        3,
        BENEFICIARY,
        ctx.beneficiary_status in ("BLOCKED", "RETIRED"),
        (f"Account {ctx.beneficiary_status}", f"অ্যাকাউন্ট {ctx.beneficiary_status}"),
        block=True,
    )
    rule(
        "DOCUMENT_FAILED",
        3,
        RELEASE,
        ctx.any_document_failed,
        flag(ctx.any_document_failed),
        block=True,
    )
    rule(
        "AMOUNT_OVER_LIMIT",
        3,
        RELEASE,
        ctx.amount_usd > p.tier1_max_usd,
        (f"Amount USD {amount} vs limit USD {limit}", f"পরিমাণ USD {amount}, সীমা USD {limit}"),
    )
    rule(
        "ADVANCE_OVER_LIMIT",
        3,
        RELEASE,
        ctx.advance_over_limit,
        (
            f"Escrow held above USD {limit}: " + flag(ctx.advance_over_limit)[0],
            f"এসক্রো USD {limit}-এর উপরে: " + flag(ctx.advance_over_limit)[1],
        ),
    )
    rule(
        "BENEFICIARY_CHANGE",
        3,
        frozenset({Action.CHANGE_BENEFICIARY}),
        True,
        ("Account change requested", "অ্যাকাউন্ট পরিবর্তনের অনুরোধ"),
    )
    rule(
        "BENEFICIARY_PENDING_CHANGE",
        3,
        BENEFICIARY,
        ctx.beneficiary_status == "PENDING_CHANGE",
        (f"Account {ctx.beneficiary_status}", f"অ্যাকাউন্ট {ctx.beneficiary_status}"),
    )
    rule(
        "BENEFICIARY_CHANGED_RECENTLY",
        3,
        BENEFICIARY,
        ctx.beneficiary_changed_recently,
        (
            f"Account newer than {p.new_beneficiary_days} days: "
            + flag(ctx.beneficiary_changed_recently)[0],
            f"অ্যাকাউন্ট {p.new_beneficiary_days} দিনের কম পুরনো: "
            + flag(ctx.beneficiary_changed_recently)[1],
        ),
    )
    rule(
        "FRAUD_SCORE_HIGH",
        3,
        RELEASE,
        ctx.max_document_fraud_score > p.fraud_score_tier3_above,
        (
            f"Fraud score {ctx.max_document_fraud_score} vs limit {p.fraud_score_tier3_above}",
            f"জালিয়াতি স্কোর {ctx.max_document_fraud_score}, সীমা {p.fraud_score_tier3_above}",
        ),
    )
    rule("DUPLICATE_HASH", 3, RELEASE, ctx.duplicate_hash, flag(ctx.duplicate_hash))
    rule(
        "DOC_INSTRUCTION",
        3,
        ALL_MONEY,
        ctx.instruction_from_document,
        flag(ctx.instruction_from_document),
    )
    acct_warn = ctx.kyb_status == "WARNING" and ctx.kyb_account_warning
    rule(
        "KYB_ACCOUNT_WARNING",
        3,
        RELEASE,
        acct_warn,
        (
            f"KYB {ctx.kyb_status}, account reason: " + flag(ctx.kyb_account_warning)[0],
            f"কেওয়াইবি {ctx.kyb_status}, অ্যাকাউন্ট কারণ: " + flag(ctx.kyb_account_warning)[1],
        ),
    )
    rule("FIRST_DEAL", 2, RELEASE, ctx.is_first_deal_with_supplier,
         flag(ctx.is_first_deal_with_supplier))  # fmt: skip
    rule("DOCUMENT_WARNING", 2, RELEASE, ctx.any_document_warning, flag(ctx.any_document_warning))
    rule("LOCK_FX", 2, frozenset({Action.LOCK_FX}), True, ("FX lock requested", "হার লকের অনুরোধ"))
    rule(
        "CONFIRM_MILESTONES",
        2,
        frozenset({Action.CONFIRM_MILESTONES}),
        True,
        ("Schedule confirmation requested", "সূচি নিশ্চিতকরণের অনুরোধ"),
    )
    rule(
        "PROPOSE_MILESTONES",
        2,
        frozenset({Action.PROPOSE_MILESTONES}),
        True,
        ("Schedule change requested", "সূচি পরিবর্তনের অনুরোধ"),
    )
    rule(
        "AGENT_ORIGIN",
        2,
        ALL_MONEY,
        ctx.origin == Origin.AGENT,
        (f"Requested by {ctx.origin.value}", f"অনুরোধকারী {ctx.origin.value}"),
    )
    rule("FX_RATE_NOT_LOCKED", 2, RELEASE, ctx.fx_lock_missing, flag(ctx.fx_lock_missing))
    unverified = ctx.kyb_status != "VERIFIED" or not ctx.beneficiary_verified
    rule(
        "NOT_FULLY_VERIFIED",
        2,
        RELEASE,
        unverified,
        (
            f"KYB {ctx.kyb_status}, account verified: " + flag(ctx.beneficiary_verified)[0],
            f"কেওয়াইবি {ctx.kyb_status}, অ্যাকাউন্ট যাচাই: " + flag(ctx.beneficiary_verified)[1],
        ),
    )
    return out


def _rules(ctx: RiskContext, p: RiskPolicy) -> list[Reason]:
    return [
        _reason(e.tier, e.code, e.blocking)
        for e in _eval(ctx, p)
        if e.fired and ctx.action in e.applies
    ]


def context_hash(ctx: RiskContext) -> str:
    return hashlib.sha256(canonical_json(ctx.model_dump(mode="json")).encode()).hexdigest()


def _trace(ctx: RiskContext, p: RiskPolicy, deciding: set[str]) -> list[TraceItem]:
    items: list[TraceItem] = []
    for e in _eval(ctx, p):
        if ctx.action not in e.applies:
            continue
        en, bn = TEXT[e.code]
        items.append(
            TraceItem(
                code=e.code,
                kind="BLOCK" if e.blocking else ("TIER3" if e.tier == 3 else "TIER2"),
                fired=e.fired,
                deciding=e.fired and e.code in deciding,
                label_en=en,
                label_bn=bn,
                value_en=e.value[0],
                value_bn=e.value[1],
            )
        )
    return items


def _hints(fired: list[Reason]) -> list[Hint]:
    out: list[Hint] = []
    for r in sorted(fired, key=lambda r: (not r.blocking, -r.tier, r.code)):
        if r.blocking:
            out.append(
                Hint(code=r.code, to_tier=None, text_en=BLOCK_HINT[0], text_bn=BLOCK_HINT[1])
            )
        elif r.code in HINTS:
            to_tier, en, bn = HINTS[r.code]
            out.append(Hint(code=r.code, to_tier=to_tier, text_en=en, text_bn=bn))
    return out


def evaluate(ctx: RiskContext, policy: RiskPolicy | None = None) -> RiskDecision:
    p = policy or load_policy()
    digest = context_hash(ctx)
    if ctx.action not in MONEY_ACTIONS:
        return RiskDecision(
            decision=Verdict.ALLOW,
            tier=0,
            reason_codes=[],
            explanation_en="Analysis only; nothing moves.",
            explanation_bn="শুধু বিশ্লেষণ; কোনো অর্থ সরানো হচ্ছে না।",
            context_hash=digest,
        )
    hits = _rules(ctx, p)
    blocks = [h for h in hits if h.blocking]
    if blocks:
        chosen, decision, tier = blocks, Verdict.BLOCK, 3
        deciding = {h.code for h in blocks}
    elif hits:
        tier = max(h.tier for h in hits)
        chosen = sorted((h for h in hits if h.tier == tier), key=lambda h: h.code)
        deciding = {h.code for h in chosen}
        chosen += sorted((h for h in hits if h.tier < tier), key=lambda h: (-h.tier, h.code))
        decision = Verdict.REQUIRE_APPROVAL
    else:
        chosen, decision, tier = [_reason(1, "AUTO_OK")], Verdict.ALLOW, 1
        deciding = set()
    head_en = {
        Verdict.BLOCK: "Blocked",
        Verdict.REQUIRE_APPROVAL: f"Needs Tier {tier} approval",
        Verdict.ALLOW: "Allowed (Tier 1, with notice)",
    }[decision]
    head_bn = {
        Verdict.BLOCK: "আটকানো হয়েছে",
        Verdict.REQUIRE_APPROVAL: f"টিয়ার {tier} অনুমোদন লাগবে",
        Verdict.ALLOW: "অনুমোদিত (টিয়ার ১, বিজ্ঞপ্তিসহ)",
    }[decision]
    return RiskDecision(
        decision=decision,
        tier=tier,
        reason_codes=[] if decision == Verdict.ALLOW else [h.code for h in chosen],
        explanation_en=f"{head_en}: " + " ".join(h.en for h in chosen),
        explanation_bn=f"{head_bn}: " + " ".join(h.bn for h in chosen),
        context_hash=digest,
        decided_by=sorted(deciding),
        trace=_trace(ctx, p, deciding),
        hints=_hints(hits),
    )


RiskDecision.model_rebuild()


# --- policy-as-code: the rules table rendered from the same code that decides -------------------


class RuleRow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    kind: Literal["BLOCK", "TIER3", "TIER2"]
    applies_to: list[str]
    label_en: str
    label_bn: str
    condition_en: str
    condition_bn: str


def _conditions(p: RiskPolicy) -> dict[str, tuple[str, str]]:
    limit = _usd(p.tier1_max_usd)
    d = p.new_beneficiary_days
    return {
        "SANCTIONS_HIT": ("A party matches the sanctions list", "কোনো পক্ষ নিষেধাজ্ঞা তালিকায় আছে"),
        "KYB_BLOCKED": ("Supplier KYB status is BLOCKED", "সরবরাহকারীর কেওয়াইবি BLOCKED"),
        "BENEFICIARY_BLOCKED": (
            "Receiving account is blocked or retired",
            "প্রাপক অ্যাকাউন্ট ব্লক বা বাতিল",
        ),
        "DOCUMENT_FAILED": (
            "A document of the tranche has a FAILED verdict",
            "কিস্তির কোনো ডকুমেন্ট FAILED",
        ),
        "AMOUNT_OVER_LIMIT": (f"Amount in USD is above {limit}", f"USD পরিমাণ {limit}-এর বেশি"),
        "ADVANCE_OVER_LIMIT": (
            f"Escrow holds more than USD {limit}",
            f"এসক্রোতে USD {limit}-এর বেশি",
        ),
        "BENEFICIARY_CHANGE": ("The receiving account is being changed", "প্রাপক অ্যাকাউন্ট বদলানো হচ্ছে"),
        "BENEFICIARY_PENDING_CHANGE": (
            "The account has a change pending review",
            "অ্যাকাউন্টের পরিবর্তন অপেক্ষমাণ",
        ),
        "BENEFICIARY_CHANGED_RECENTLY": (
            f"Account first seen less than {d} days ago",
            f"অ্যাকাউন্ট {d} দিনের কম পুরনো",
        ),
        "FRAUD_SCORE_HIGH": (
            f"Document fraud score is above {p.fraud_score_tier3_above}",
            f"জালিয়াতি স্কোর {p.fraud_score_tier3_above}-এর বেশি",
        ),
        "DUPLICATE_HASH": (
            "A document is a duplicate in the shared registry",
            "ডকুমেন্টটি রেজিস্ট্রিতে ডুপ্লিকেট",
        ),
        "DOC_INSTRUCTION": (
            "A document contains instruction-like text",
            "ডকুমেন্টে নির্দেশের মতো লেখা আছে",
        ),
        "KYB_ACCOUNT_WARNING": (
            "KYB is WARNING because of the receiving account",
            "কেওয়াইবি WARNING, কারণ প্রাপক অ্যাকাউন্ট",
        ),
        "FIRST_DEAL": (
            "No earlier funded deal with this supplier",
            "এই সরবরাহকারীর সাথে আগের কোনো চুক্তি নেই",
        ),
        "DOCUMENT_WARNING": (
            "A document of the tranche has a WARNING verdict",
            "কিস্তির কোনো ডকুমেন্টে WARNING",
        ),
        "LOCK_FX": ("The action is an FX rate lock", "কাজটি বিনিময় হার লক"),
        "CONFIRM_MILESTONES": (
            "The action is a milestone confirmation",
            "কাজটি কিস্তির সূচি নিশ্চিত করা",
        ),
        "PROPOSE_MILESTONES": (
            "The action creates or changes the schedule",
            "কাজটি সূচি তৈরি বা পরিবর্তন",
        ),
        "AGENT_ORIGIN": (
            "The request comes from the assistant, not a person",
            "অনুরোধ সহকারীর কাছ থেকে, ব্যক্তির নয়",
        ),
        "FX_RATE_NOT_LOCKED": (
            "Payment converts currency and no rate is locked",
            "মুদ্রা রূপান্তর হচ্ছে কিন্তু হার লক নেই",
        ),
        "NOT_FULLY_VERIFIED": (
            "Supplier KYB or receiving account is not verified",
            "সরবরাহকারী বা অ্যাকাউন্ট যাচাই হয়নি",
        ),
    }


def rules_table(policy: RiskPolicy | None = None) -> list[RuleRow]:
    p = policy or load_policy()
    cond = _conditions(p)
    probe = {a: _eval(RiskContext(action=a), p) for a in MONEY_ACTIONS}
    rows: list[RuleRow] = []
    seen: set[str] = set()
    for e in (
        probe[Action.RELEASE_TRANCHE]
        + [x for x in probe[Action.CHANGE_BENEFICIARY] if x.code == "BENEFICIARY_CHANGE"]
        + [x for x in probe[Action.LOCK_FX] if x.code in ("LOCK_FX",)]
        + [x for x in probe[Action.CONFIRM_MILESTONES] if x.code == "CONFIRM_MILESTONES"]
        + [x for x in probe[Action.PROPOSE_MILESTONES] if x.code == "PROPOSE_MILESTONES"]
    ):
        if e.code in seen:
            continue
        seen.add(e.code)
        en, bn = TEXT[e.code]
        rows.append(
            RuleRow(
                code=e.code,
                kind="BLOCK" if e.blocking else ("TIER3" if e.tier == 3 else "TIER2"),
                applies_to=sorted(a.value for a in MONEY_ACTIONS if a in e.applies),
                label_en=en,
                label_bn=bn,
                condition_en=cond[e.code][0],
                condition_bn=cond[e.code][1],
            )
        )
    order = {"BLOCK": 0, "TIER3": 1, "TIER2": 2}
    return sorted(rows, key=lambda r: (order[r.kind], r.code))
