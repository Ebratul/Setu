"""Read models for the transparency views: segments for highlighting, the playground dry-run and
the X-ray of a chat message or a document check. Real text comes from the caller's own data;
the model side is the stored masked payload."""

import re
from collections import Counter

from app.privacy.detectors import LABELS, Hit
from app.privacy.gateway import PrivacyGateway, Stats
from app.privacy.vault import TOKEN
from app.schemas.privacy import (
    HitOut,
    LeftBlock,
    PrivacyDryRunOut,
    RightBlock,
    Segment,
    StatsOut,
)

MAX_VIEW_CHARS = 6000


def stats_out(s: Stats) -> StatsOut:
    return StatsOut(
        masked_by_type=dict(s.masked_by_type),
        protected=s.protected,
        leaked_count=s.leaked_count,
        chars_sent=s.chars_sent,
    )


def source_segments(text: str, hits: list[Hit], tokens: list[str] | None = None) -> list[Segment]:
    out: list[Segment] = []
    pos = 0
    for i, h in enumerate(hits):
        if h.start > pos:
            out.append(Segment(text=text[pos : h.start]))
        out.append(
            Segment(text=text[h.start : h.end], type=h.type, token=tokens[i] if tokens else None)
        )
        pos = h.end
    if pos < len(text):
        out.append(Segment(text=text[pos:]))
    return out


def token_segments(masked: str) -> list[Segment]:
    """Split masked text at its tokens: what the model received, tokens typed by kind."""
    out: list[Segment] = []
    pos = 0
    for m in TOKEN.finditer(masked):
        if m.start() > pos:
            out.append(Segment(text=masked[pos : m.start()]))
        out.append(Segment(text=m.group(0), type=m.group(1), token=m.group(0)))
        pos = m.end()
    if pos < len(masked):
        out.append(Segment(text=masked[pos:]))
    return out


def count_tokens(texts: list[str]) -> Stats:
    """Distinct tokens across payloads, by type (what the headline of the X-ray counts)."""
    tokens = {m.group(0) for t in texts for m in TOKEN.finditer(t)}
    by_type: Counter[str] = Counter(t[1:-1].rsplit("_", 1)[0] for t in tokens)
    return Stats(dict(by_type))


def highlight(text: str, gw: PrivacyGateway) -> list[Segment]:
    """Real text with protected values marked (no tokens: numbering depends on the whole turn)."""
    return source_segments(text[:MAX_VIEW_CHARS], gw.hits(text[:MAX_VIEW_CHARS]))


def right_block(label: str, node: str, model: str | None, sent: bool, payload: str) -> RightBlock:
    return RightBlock(
        label=label, node=node, model=model, sent=sent, segments=token_segments(payload)
    )


def left_block(label: str, text: str, gw: PrivacyGateway) -> LeftBlock:
    return LeftBlock(label=label, segments=highlight(text, gw))


# --- playground dry-run -----------------------------------------------------------------------


def _simulated_reply(masked: str) -> str:
    """A deterministic stand-in for the model: it can only talk about the tokens it was given.
    Nothing is sent anywhere."""
    seen: dict[str, str] = {}
    for m in TOKEN.finditer(masked):
        seen.setdefault(m.group(0), m.group(1))
    if not seen:
        return "Simulated AI reply: I received your message. It contains no protected values."
    parts = ", ".join(f"{tok} ({LABELS[kind][0]})" for tok, kind in seen.items() if kind in LABELS)
    return (
        f"Simulated AI reply: I received your message and I can see {len(seen)} protected "
        f"value(s): {parts}. I will only ever refer to them by these tokens."
    )


def dry_run(text: str, gw: PrivacyGateway) -> PrivacyDryRunOut:
    hits = gw.hits(text)
    masked = gw.mask_text(text)
    tokens = [gw.token_of(h, text) for h in hits]  # same numbering mask_text used (same vault)
    masked_text, call = gw.protect_text(masked, node="playground", model=None, sent=False)
    reply = _simulated_reply(masked_text)
    restored = gw.unmask(reply)
    return PrivacyDryRunOut(
        mask_amounts=gw.mask_amounts,
        hits=[
            HitOut(
                type=h.type,
                start=h.start,
                end=h.end,
                confidence=h.confidence,
                token=tokens[i],
                obfuscated=h.obfuscated,
                label_en=LABELS[h.type][0],
                label_bn=LABELS[h.type][1],
            )
            for i, h in enumerate(hits)
        ],
        source_segments=source_segments(text, hits, tokens),
        masked_segments=token_segments(masked_text),
        masked=masked_text,
        ai_answer_masked=reply,
        ai_answer_segments=token_segments(reply),
        restored_answer=restored,
        restored_segments=highlight(restored, gw),
        stats=stats_out(call.stats),
    )


_SPACE = re.compile(r"\s+")


def clean_excerpt(text: str) -> str:
    return _SPACE.sub(" ", text).strip()
