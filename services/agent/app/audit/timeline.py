"""Human-readable (EN/BN) one-liners for audit entries.

Only fields already in the signed payload are used, so the sentence can be rebuilt by anyone from
an export. Unknown actions fall back to the action name.
"""

from typing import Any

# action -> (English, Bangla). `{amt}` and `{ms}` are filled from the payload when present.
TEXT: dict[str, tuple[str, str]] = {
    "DEAL_CREATED": ("Deal created", "ডিল তৈরি হয়েছে"),
    "DEAL_COMPLETED": ("Deal completed", "ডিল সম্পন্ন হয়েছে"),
    "MILESTONES_PROPOSED": ("Milestone schedule proposed", "মাইলস্টোন সূচি প্রস্তাব করা হয়েছে"),
    "MILESTONES_CONFIRMED": ("Milestone schedule confirmed", "মাইলস্টোন সূচি নিশ্চিত হয়েছে"),
    "ESCROW_FUNDED": ("Escrow funded{amt} (simulated)", "এসক্রোতে অর্থ জমা{amt} (সিমুলেটেড)"),
    "ESCROW_FROZEN": ("Escrow frozen", "এসক্রো স্থগিত"),
    "ESCROW_REFUNDED": ("Escrow refunded{amt} (simulated)", "এসক্রো ফেরত{amt} (সিমুলেটেড)"),
    "EVIDENCE_STATUS_SET": ("Milestone{ms} evidence status set", "মাইলস্টোন{ms} প্রমাণের অবস্থা"),
    "TRANCHE_RELEASED": ("Tranche{ms} released{amt} (simulated)", "কিস্তি{ms} ছাড়{amt} (সিমুলেটেড)"),
    "MILESTONE_RELEASED": (
        "Tranche{ms} released{amt} (simulated)",
        "কিস্তি{ms} ছাড়{amt} (সিমুলেটেড)",
    ),
    "TRANCHE_RELEASE_REFUSED": ("Release{ms} refused", "ছাড়{ms} প্রত্যাখ্যাত"),
    "RELEASE_APPROVAL_REQUESTED": (
        "Release{ms} sent for human approval",
        "ছাড়{ms} মানুষের অনুমোদনের জন্য পাঠানো হয়েছে",
    ),
    "RISK_DECISION": ("Risk engine decision", "ঝুঁকি ইঞ্জিনের সিদ্ধান্ত"),
    "APPROVAL_REQUESTED": ("Approval requested", "অনুমোদনের অনুরোধ"),
    "APPROVAL_GRANTED": ("Approval granted", "অনুমোদন দেওয়া হয়েছে"),
    "APPROVAL_APPROVED": ("Approved by a human", "মানুষ অনুমোদন করেছেন"),
    "APPROVAL_REJECTED": ("Rejected by a human", "মানুষ প্রত্যাখ্যান করেছেন"),
    "APPROVAL_CANCELLED": ("Approval cancelled", "অনুমোদন বাতিল"),
    "APPROVAL_EXPIRED": ("Approval expired", "অনুমোদনের সময় শেষ"),
    "APPROVAL_LOCKED": ("Approval locked after failed codes", "ভুল কোডের পরে অনুমোদন লক"),
    "APPROVAL_EXECUTED": ("Approved action executed", "অনুমোদিত কাজ সম্পন্ন"),
    "APPROVAL_OTP_SENT": ("One-time code sent (simulated SMS)", "ওটিপি পাঠানো (সিমুলেটেড এসএমএস)"),
    "APPROVAL_OTP_FAILED": ("Wrong one-time code entered", "ভুল ওটিপি দেওয়া হয়েছে"),
    "APPROVAL_TOO_EARLY": ("Tried to execute during cooling-off", "কুলিং-অফ চলাকালে চালানোর চেষ্টা"),
    "APPROVAL_REESCALATED": ("Approval escalated to a higher tier", "উচ্চতর স্তরে উন্নীত"),
    "FX_LOCKED": ("FX rate locked", "বিনিময় হার লক"),
    "BENEFICIARY_CHANGE_REQUESTED": (
        "Beneficiary account change requested",
        "প্রাপকের অ্যাকাউন্ট পরিবর্তনের অনুরোধ",
    ),
    "BENEFICIARY_CHANGED": ("Beneficiary account changed", "প্রাপকের অ্যাকাউন্ট পরিবর্তিত"),
    "EMAIL_BENEFICIARY_CHANGE_BLOCKED": (
        "Emailed bank-detail change blocked",
        "ইমেইলে ব্যাংক তথ্য পরিবর্তনের অনুরোধ ঠেকানো হয়েছে",
    ),
    "KYB_CHECKED": ("Supplier KYB check", "সরবরাহকারীর কেওয়াইবি যাচাই"),
    "DOC_UPLOADED": ("Document uploaded", "নথি আপলোড"),
    "DOCUMENT_CHECKED": ("Document checked", "নথি যাচাই"),
    "DOC_CHECK_FAILED": ("Document check found problems", "নথি যাচাইয়ে সমস্যা পাওয়া গেছে"),
    "DOC_INSTRUCTION_DETECTED": (
        "Instruction-like text found in a document",
        "নথিতে নির্দেশের মতো লেখা পাওয়া গেছে",
    ),
    "DOC_ALERT_RESOLVED": ("Document alert resolved", "নথির সতর্কতা নিষ্পত্তি"),
    "DOC_DOWNLOADED": ("Document downloaded", "নথি ডাউনলোড"),
    "REGISTRY_REGISTERED": ("Document hash registered", "নথির হ্যাশ নিবন্ধিত"),
    "REGISTRY_DUPLICATE_HIT": ("Duplicate document hash found", "একই নথির হ্যাশ পাওয়া গেছে"),
    "REGISTRY_RELEASED": ("Document hash released", "নথির হ্যাশ মুক্ত"),
    "REGISTRY_LENDER_CHECK": ("Lender checked the registry", "ঋণদাতা রেজিস্ট্রি যাচাই করেছেন"),
    "INJECTION_DETECTED": ("Prompt-injection attempt detected", "প্রম্পট ইনজেকশনের চেষ্টা শনাক্ত"),
    "INJECTION_BLOCKED_TOOL": ("Injected tool call blocked", "ইনজেক্ট করা টুল কল ঠেকানো হয়েছে"),
    "INJECTION_RESOLVED": ("Injection flag resolved", "ইনজেকশন সতর্কতা নিষ্পত্তি"),
    "PRIVACY_LEAK_ALERT": ("Privacy leak alert", "গোপনীয়তা ফাঁসের সতর্কতা"),
    "DEMO_RESET": ("Demo data reset", "ডেমো ডেটা রিসেট"),
    "DISPUTE_OPENED": ("Dispute opened", "বিরোধ শুরু"),
    "CREDIT_RECORD_ISSUED": ("Signed credit record issued", "স্বাক্ষরিত ক্রেডিট রেকর্ড ইস্যু"),
}


def _amount(payload: dict[str, Any]) -> str:
    amount = payload.get("amount")
    if amount in (None, ""):
        return ""
    return f" {amount} {payload.get('currency', '')}".rstrip()


def _milestone(payload: dict[str, Any]) -> str:
    seq = payload.get("milestone_seq")
    return f" #{seq}" if seq not in (None, "") else ""


def describe_entry(action: str, payload: dict[str, Any], decision: str) -> dict[str, str]:
    """{'en': ..., 'bn': ...} for one entry."""
    if action.startswith("TOOL:"):
        name = action[5:]
        return {
            "en": f"Assistant used tool {name} ({decision})",
            "bn": f"সহকারী {name} টুল ব্যবহার করেছে ({decision})",
        }
    en, bn = TEXT.get(action, (action.replace("_", " ").capitalize(), action.replace("_", " ")))
    fill = {"amt": _amount(payload), "ms": _milestone(payload)}
    return {"en": en.format(**fill), "bn": bn.format(**fill)}
