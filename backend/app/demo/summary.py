"""The "What you just saw" numbers, read from what the scenes actually did."""

from typing import Any

from app.demo.script import Bi
from app.schemas.demo import SummaryLink, SummaryNumber, SummaryOut


def _fact(state: dict[str, Any], scene: str, key: str) -> Any:
    return ((state.get("scenes") or {}).get(scene) or {}).get("facts", {}).get(key)


def _passed(state: dict[str, Any], scene: str) -> bool:
    return ((state.get("scenes") or {}).get(scene) or {}).get("status") == "passed"


def _money(v: Any) -> str:
    try:
        return f"USD {float(str(v).replace(',', '')):,.2f}"
    except (TypeError, ValueError):
        return "n/a"


def build(
    state: dict[str, Any], total_scenes: int, identifiers_protected: int | None
) -> SummaryOut:
    scenes = state.get("scenes") or {}
    attacks: list[Bi] = []
    if _passed(state, "8.1"):
        attacks.append(
            Bi(en="Fake payment-redirection email: blocked", bn="ভুয়া পেমেন্ট-বদলের ইমেইল: আটকানো")
        )
    if _passed(state, "9.1"):
        attacks.append(
            Bi(
                en="Forged bill of lading with a hidden instruction: failed, ignored",
                bn="লুকানো নির্দেশসহ জাল বিল অব লেডিং: ব্যর্থ, উপেক্ষিত",
            )
        )
    if _passed(state, "10.1"):
        attacks.append(
            Bi(
                en="Same invoice financed at a second lender: duplicate blocked",
                bn="একই ইনভয়েস দ্বিতীয় ঋণদাতার কাছে: ডুপ্লিকেট আটকানো",
            )
        )
    audit_n = _fact(state, "12.3", "entries_verified")
    numbers = [
        SummaryNumber(
            key="landed_cost",
            value=_money(_fact(state, "3.1", "landed_cost")),
            label=Bi(en="landed cost of the order", bn="অর্ডারের ল্যান্ডেড খরচ"),
        ),
        SummaryNumber(
            key="shortfall_solved",
            value=_money(_fact(state, "4.1", "shortfall")) if _passed(state, "4.3") else "not yet",
            label=Bi(en="cash shortfall found and solved", bn="নগদ ঘাটতি ধরা পড়ে ও সমাধান হয়েছে"),
        ),
        SummaryNumber(
            key="attacks_blocked",
            value=str(len(attacks)),
            label=Bi(en="attacks blocked", bn="আক্রমণ আটকানো"),
        ),
        SummaryNumber(
            key="identifiers_protected",
            value=str(identifiers_protected if identifiers_protected is not None else "n/a"),
            label=Bi(
                en="identifiers masked before any AI call", bn="এআই কলের আগে মাস্ক করা পরিচয় তথ্য"
            ),
        ),
        SummaryNumber(
            key="audit_verified",
            value=str(audit_n) if audit_n is not None else "n/a",
            label=Bi(en="audit entries verified", bn="অডিট এন্ট্রি যাচাইকৃত"),
        ),
    ]
    links = [
        SummaryLink(
            label=Bi(en="Risk Playground", bn="ঝুঁকি প্লেগ্রাউন্ড"), href="/demo/risk-playground"
        ),
        SummaryLink(
            label=Bi(en="Privacy Playground", bn="গোপনীয়তা প্লেগ্রাউন্ড"),
            href="/demo/privacy-playground",
        ),
        SummaryLink(label=Bi(en="Attack Console", bn="আক্রমণ কনসোল"), href="/demo/attack-console"),
        SummaryLink(label=Bi(en="Verify the audit log", bn="অডিট লগ যাচাই"), href="/verify"),
    ]
    ms = [s.get("duration_ms") or 0 for s in scenes.values()]
    return SummaryOut(
        ready=len(scenes) >= total_scenes,
        numbers=numbers,
        attacks=attacks,
        links=links,
        run_seconds=round(sum(ms) / 1000, 1) if ms else None,
    )
