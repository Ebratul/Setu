"""The live Attack Console: one attack through the real defence layers, step by step.

Privacy masking -> untrusted wrapping -> detector -> tool gating -> risk engine -> final answer.
The run uses the evaluation harness (real nodes, obedient mock model, sandbox services), so what a
judge sees is the code that guards the product. With "Defences: OFF" only layers 2, 4 and 5 are
disabled; the risk engine (layer 3) still stops money, and a banner says so. Nothing here can
move money or touch a deal: console events are tagged origin=console.
"""

import re
from typing import Any

from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser
from app.privacy.gateway import PrivacyGateway
from app.schemas.injection import (
    ConsoleRunIn,
    ConsoleRunOut,
    DetectionOut,
    Highlight,
    Step,
    ToolAttempt,
)
from app.security.injection import events
from app.security.injection.detector import scan
from app.security.injection.gallery import BY_ID
from app.security.injection.harness import _OBEY, FORBIDDEN_TOOL, UntrustedOut, run_case
from app.security.injection.suite import risk_of
from app.security.injection.switch import defences
from app.security.injection.wrap import new_boundary, wrap_untrusted

_TOKEN = re.compile(r"⟦[A-Z_]+_\d+⟧")
DEFAULT_TARGET = "RELEASE_FULL_PAYMENT"


def _content(text: str, source: str) -> UntrustedOut:
    key = {
        "hidden_text": "hidden_text",
        "visible_text": "visible_text",
        "metadata": "metadata",
        "email": "message_text",
    }[source]
    return UntrustedOut(**{key: text})


def _target_of(text: str) -> str:
    for target, pattern in _OBEY.items():
        if pattern.search(text):
            return target
    return DEFAULT_TARGET


def run(db: Session | None, user: CurrentUser, body: ConsoleRunIn) -> ConsoleRunOut:
    item = BY_ID.get(body.attack_id or "")
    if body.attack_id and item is None:
        from app.errors import NotFound

        raise NotFound("unknown attack")
    text = item.text if item else (body.text or "")
    source = item.source if item else body.source
    target = item.target if item else _target_of(text)
    style = item.style if item else None
    on = body.defences
    steps: list[Step] = []

    # 0. Privacy masking (before anything else sees the text)
    masked = PrivacyGateway().mask_text(text)
    n_masked = len(_TOKEN.findall(masked))
    steps.append(
        Step(
            id="privacy",
            layer=0,
            ok=True,
            status="done",
            title_en="Privacy masking",
            title_bn="গোপনীয়তা মাস্কিং",
            detail_en=f"{n_masked} identifier(s) replaced by tokens before the model sees the text."
            if n_masked
            else "Nothing to mask in this text. Account numbers, phones and names would be.",
            detail_bn=f"মডেল দেখার আগে {n_masked}টি শনাক্তকারী টোকেনে বদলানো হয়েছে।"
            if n_masked
            else "এই লেখায় মাস্ক করার মতো কিছু নেই। অ্যাকাউন্ট নম্বর, ফোন ও নাম থাকলে মাস্ক হতো।",
            data={"masked": n_masked},
        )
    )

    # 1. Untrusted wrapping (after masking)
    boundary = new_boundary()
    wrapped = wrap_untrusted(masked, f"{source}:console", boundary)
    steps.append(
        Step(
            id="wrap",
            layer=1,
            ok=True,
            status="done",
            title_en="Untrusted wrapping",
            title_bn="অবিশ্বস্ত ব্লকে মোড়ানো",
            detail_en=f'Wrapped in <untrusted id="{boundary}">. The model is told this is data, '
            "never instructions; the id is random per request.",
            detail_bn=f'<untrusted id="{boundary}"> ব্লকে মোড়ানো। মডেলকে বলা আছে এটি ডেটা, নির্দেশ নয়; '
            "আইডি প্রতিটি অনুরোধে এলোমেলো।",
            data={"boundary": boundary, "preview": wrapped[:240]},
        )
    )

    with defences(on):
        det = scan(text, source)  # type: ignore[arg-type]
        result = run_case(
            _content(text, source),
            action=target,
            delivery="email" if source == "email" else "pdf",
            on=on,
        )
    # 2. Detector
    if not on:
        steps.append(
            Step(
                id="detector",
                layer=2,
                ok=False,
                status="off",
                title_en="Detector",
                title_bn="ডিটেক্টর",
                detail_en="Defences are OFF: the text was not scanned.",
                detail_bn="সুরক্ষা বন্ধ: লেখাটি স্ক্যান করা হয়নি।",
            )
        )
    else:
        rules = ", ".join(det.matched_rules)
        steps.append(
            Step(
                id="detector",
                layer=2,
                ok=True,
                status="caught" if det.is_injection else "clear",
                title_en="Detector",
                title_bn="ডিটেক্টর",
                detail_en=f"Instruction found (score {det.score}): {rules}. It is data and was ignored."
                if det.is_injection
                else "No instruction-like text found.",
                detail_bn=f"নির্দেশ পাওয়া গেছে (স্কোর {det.score}): {rules}। এটি ডেটা, তাই উপেক্ষা করা হয়েছে।"
                if det.is_injection
                else "নির্দেশের মতো কোনো লেখা পাওয়া যায়নি।",
                data={"matched_rules": list(det.matched_rules), "score": det.score},
            )
        )

    # 4. Tool gating
    attempts: list[ToolAttempt] = []
    for b in result.blocked:
        attempts.append(ToolAttempt(name=b["name"], outcome="dropped_by_gate", layer=4))
    risks = []
    flagged = source != "email" or result.detected  # layer 3: documents are flagged at upload
    for tool in result.reached:
        k = risk_of(tool, flagged)
        risks.append(k)
        attempts.append(
            ToolAttempt(
                name=tool,
                outcome="reached_service_then_risk_engine",
                layer=3,
                risk_tier=k["tier"],
                risk_decision=k["decision"],
            )
        )
    tried = result.attempted
    if not on:
        steps.append(
            Step(
                id="gating",
                layer=4,
                ok=not tried,
                status="off" if tried else "idle",
                title_en="Tool gating",
                title_bn="টুল গেটিং",
                detail_en=f"Gate OFF: {', '.join(tried)} reached the service."
                if tried
                else "Gate OFF. The model made no money tool call.",
                detail_bn=f"গেট বন্ধ: {', '.join(tried)} সার্ভিসে পৌঁছেছে।"
                if tried
                else "গেট বন্ধ। মডেল কোনো অর্থ-সংক্রান্ত টুল কল করেনি।",
            )
        )
    elif result.blocked:
        names = ", ".join(b["name"] for b in result.blocked)
        steps.append(
            Step(
                id="gating",
                layer=4,
                ok=True,
                status="caught",
                title_en="Tool gating",
                title_bn="টুল গেটিং",
                detail_en=f"Dropped {names}: the user asked to check a document, not to move money.",
                detail_bn=f"{names} বাদ দেওয়া হয়েছে: ব্যবহারকারী নথি যাচাই চেয়েছিলেন, অর্থ সরাতে নয়।",
                data={"blocked": result.blocked},
            )
        )
    else:
        steps.append(
            Step(
                id="gating",
                layer=4,
                ok=True,
                status="clear" if not result.detected else "idle",
                title_en="Tool gating",
                title_bn="টুল গেটিং",
                detail_en="No money tool call was proposed."
                if not result.detected
                else "No call to gate: the turn stopped after the detection, so no money tool "
                "call was proposed.",
                detail_bn="কোনো অর্থ-সংক্রান্ত টুল কল প্রস্তাব করা হয়নি।"
                if not result.detected
                else "গেট করার মতো কল নেই: শনাক্তের পরেই কাজ থেমেছে।",
            )
        )

    # 3. Risk engine
    if risks:
        tier = max(k["tier"] for k in risks)
        moved = any(k["decision"] == "ALLOW" for k in risks)
        steps.append(
            Step(
                id="risk",
                layer=3,
                ok=not moved,
                status="caught" if not moved else "missed",
                title_en="Risk engine (always on)",
                title_bn="ঝুঁকি ইঞ্জিন (সর্বদা চালু)",
                detail_en=f"{result.reached[0]} only queues an approval. Tier {tier}: a person must "
                "approve; money never moved.",
                detail_bn=f"{result.reached[0]} শুধু অনুমোদনের অনুরোধ করে। টিয়ার {tier}: একজন মানুষকে "
                "অনুমোদন দিতে হবে; অর্থ সরেনি।",
                data={"risk": risks, "instruction_from_document": flagged},
            )
        )
    else:
        steps.append(
            Step(
                id="risk",
                layer=3,
                ok=True,
                status="idle",
                title_en="Risk engine (always on)",
                title_bn="ঝুঁকি ইঞ্জিন (সর্বদা চালু)",
                detail_en="Nothing reached it. Any detection on a deal also forces Tier 3 for that "
                "deal's next money action.",
                detail_bn="কিছুই এখানে পৌঁছায়নি। ডিলে কোনো শনাক্তকরণ হলে সেই ডিলের পরবর্তী অর্থ-কাজ টিয়ার ৩ হয়।",
            )
        )

    # 5. Output guard / final answer
    if not on:
        steps.append(
            Step(
                id="answer",
                layer=5,
                ok=not result.followed,
                status="off" if result.followed else "idle",
                title_en="Final answer",
                title_bn="চূড়ান্ত উত্তর",
                detail_en="Output guard OFF. The answer followed the injected text."
                if result.followed
                else "Output guard OFF. The answer did not follow the injected text.",
                detail_bn="আউটপুট গার্ড বন্ধ। উত্তর ইনজেক্ট করা লেখা মেনে চলেছে।"
                if result.followed
                else "আউটপুট গার্ড বন্ধ। উত্তর ইনজেক্ট করা লেখা মানেনি।",
            )
        )
    else:
        steps.append(
            Step(
                id="answer",
                layer=5,
                ok=True,
                status="caught" if result.guard else "clear",
                title_en="Final answer",
                title_bn="চূড়ান্ত উত্তর",
                detail_en=f"Output guard removed: {', '.join(result.guard)}. The answer says the "
                "instruction was ignored."
                if result.guard
                else "The answer was clean; nothing had to be removed.",
                detail_bn=f"আউটপুট গার্ড সরিয়েছে: {', '.join(result.guard)}। উত্তরে বলা আছে নির্দেশটি উপেক্ষা করা হয়েছে।"
                if result.guard
                else "উত্তর পরিষ্কার ছিল; কিছু সরাতে হয়নি।",
                data={"guard": result.guard},
            )
        )

    acted = [s.layer for s in steps if s.status == "caught"]
    reached = bool(result.reached)
    if on and acted and not (reached or result.followed):
        layer = min(acted)
        outcome = "blocked"
        names = {2: "the detector", 4: "tool gating", 5: "the output guard", 3: "the risk engine"}
        en = f"Attack blocked at layer {layer} ({names[layer]}). No tool ran and money never moved."
        bn = f"আক্রমণ স্তর {layer}-এ আটকানো হয়েছে। কোনো টুল চলেনি, অর্থ সরেনি।"
    elif reached:
        outcome = "stopped_by_risk_engine"
        tool = result.reached[0]
        en = f"The model tried to call {tool} — stopped by the risk engine (money never moved)."
        bn = f"মডেল {tool} কল করার চেষ্টা করেছে — ঝুঁকি ইঞ্জিন আটকেছে (অর্থ সরেনি)।"
    elif result.followed:
        outcome = "attack_succeeded"
        en = "The answer followed the injected text. No money moved; only the wording was affected."
        bn = "উত্তর ইনজেক্ট করা লেখা মেনেছে। কোনো অর্থ সরেনি; শুধু উত্তরের ভাষা প্রভাবিত হয়েছে।"
    else:
        outcome = "no_effect"
        en = "Nothing in this text tried to act on Setu."
        bn = "এই লেখা Setu-কে দিয়ে কিছু করানোর চেষ্টা করেনি।"

    event_id = None
    if db is not None:
        event_id = _record(db, user, det, result, on, style, risks)
    return ConsoleRunOut(
        defences=on,
        attack_id=item.id if item else None,
        source=source,
        text=text,
        steps=steps,
        detection=DetectionOut(
            is_injection=det.is_injection,
            score=det.score,
            matched_rules=list(det.matched_rules),
            source=det.source,
            snippet=det.snippet,
            highlights=[Highlight(start=a, end=b, rule=r) for a, b, r in det.highlights],
        )
        if on
        else None,
        attempts=attempts,
        answer=result.answer,
        blocked_at_layer=min(acted) if outcome == "blocked" else (3 if reached else None),
        outcome=outcome,  # type: ignore[arg-type]
        result_en=en,
        result_bn=bn,
        event_id=event_id,
    )


def _record(
    db: Session, user: CurrentUser, det: Any, result: Any, on: bool, style: str | None, risks: list
) -> Any:
    """Readable event + signed audit row for the run (origin=console, no deal is touched)."""
    row = None
    if on and det.is_injection:
        row = events.record_detection(
            db,
            det,
            user_id=user.id,
            origin="console",
            attack_style=style,
            defences_on=on,
        )
    for b in result.blocked:
        row = row or events.record(
            db,
            kind="BLOCKED_TOOL",
            source=det.source,
            rules=[b["code"]],
            action_taken=events.ACTION_BLOCKED_TOOL,
            layer=4,
            user_id=user.id,
            tool=b["name"],
            attack_style=style,
            origin="console",
            defences_on=on,
        )
    if not on:
        for tool, k in zip(result.reached, risks, strict=False):
            row = row or events.record(
                db,
                kind="BLOCKED_TOOL",
                source=det.source,
                rules=k["reasons"][:6] or ["AGENT_ORIGIN"],
                action_taken="RISK_ENGINE_TIER3",
                layer=3,
                user_id=user.id,
                tool=tool,
                attack_style=style,
                origin="console",
                defences_on=False,
            )
    db.commit()
    return row.id if row is not None else None


__all__ = ["FORBIDDEN_TOOL", "run"]
