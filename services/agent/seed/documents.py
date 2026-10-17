"""Document metadata for SETU-2026-0001, PASSED checks for the milestone-1 evidence, placeholder
rows for the clean and FORGED bills of lading, and the hash-registry entry showing Lender A
already financed the PI.

sha256 is over the file at `data/demo/<ref>/<file>` when it exists (generated later by the
synthetic document generator); until then it is sha256 of a deterministic placeholder string, so
the registry and the document row always agree.
"""

import hashlib

from app.config import REPO_ROOT
from app.db.enums import CheckStatus, DocStatus, DocType, Severity
from app.db.models import Document, ForensicFinding, HashRegistry
from app.forensics.canonical import canonical_invoice_hash
from app.security.audit import sha256_hex
from seed.common import SEED_VERSION, Ctx, Row, Rows, sid
from seed.deals import DEALS_BY_REF, MAIN_DEAL, deal_id, milestone_id
from seed.parties import LENDER_A, PARTY_NAMES

DEMO_DIR = "data/demo"
PI_KEY = f"doc:{MAIN_DEAL}:proforma-invoice"
PI_NUMBER = "HX-PI-2026-118"
LENDER_A_LOAN_REF = "MCB-IMPLOAN-2026-0412"

# (key suffix, doc type, milestone, file, mime, status, check status, variant, uploaded offset)
DOCS: tuple[
    tuple[str, DocType, int, str, str, DocStatus, CheckStatus, str | None, int | None], ...
] = (
    (
        "proforma-invoice",
        DocType.PROFORMA_INVOICE,
        1,
        "proforma_invoice.pdf",
        "application/pdf",
        DocStatus.UPLOADED,
        CheckStatus.PASSED,
        None,
        -8,
    ),
    (
        "production-photo-1",
        DocType.PRODUCTION_PHOTO,
        1,
        "production_photo_1.jpg",
        "image/jpeg",
        DocStatus.UPLOADED,
        CheckStatus.PASSED,
        None,
        -1,
    ),
    (
        "production-photo-2",
        DocType.PRODUCTION_PHOTO,
        1,
        "production_photo_2.jpg",
        "image/jpeg",
        DocStatus.UPLOADED,
        CheckStatus.PASSED,
        None,
        -1,
    ),
    (
        "bill-of-lading-clean",
        DocType.BILL_OF_LADING,
        2,
        "bill_of_lading_clean.pdf",
        "application/pdf",
        DocStatus.PLACEHOLDER,
        CheckStatus.NOT_RUN,
        "CLEAN",
        None,
    ),
    (
        "bill-of-lading-forged",
        DocType.BILL_OF_LADING,
        2,
        "bill_of_lading_forged.pdf",
        "application/pdf",
        DocStatus.PLACEHOLDER,
        CheckStatus.NOT_RUN,
        "FORGED",
        None,
    ),
)

CHECKS: dict[DocType, tuple[tuple[str, str], ...]] = {
    DocType.PROFORMA_INVOICE: (
        ("EXTRACTION_COMPLETE", "All required fields were read"),
        ("QUANTITY_MATCH", "8,000 m matches the deal"),
        ("VALUE_MATH", "8,000 m x USD 1.20 = USD 9,600.00"),
        ("VALUE_MATCH", "Unit price and total match the deal"),
        ("NAME_MATCH", "Seller name equals the supplier licence name"),
        ("BENEFICIARY_MATCH", "Bank, holder and account equal the registered account"),
        ("DATE_LOGIC", "Invoice date is before production completion and arrival"),
        ("PORT_MATCH", "Ports and incoterm match the deal"),
        ("HS_CODE_MATCH", "HS code 6006.22 matches the deal"),
        ("PRICE_BAND", "Unit price is inside the HS band"),
        ("HIDDEN_TEXT", "No hidden or tiny text found"),
        ("INSTRUCTION_SCAN", "No instruction-like text found"),
        ("METADATA_ANOMALY", "File metadata looks unedited"),
        ("DUPLICATE_HASH", "Not seen elsewhere"),
    ),
    DocType.PRODUCTION_PHOTO: (
        ("PHOTO_MATCH", "Dyed cotton jersey visible; colour matches the ordered Navy Blue"),
        ("DUPLICATE_HASH", "Not seen elsewhere"),
    ),
}


def pi_fields() -> Row:
    spec = DEALS_BY_REF[MAIN_DEAL]
    return {
        "doc_type": DocType.PROFORMA_INVOICE.value,
        "invoice_no": PI_NUMBER,
        "seller": PARTY_NAMES[spec.supplier],
        "buyer": PARTY_NAMES[spec.buyer],
        "hs_code": spec.hs_code,
        "quantity": str(spec.quantity),
        "unit": spec.unit,
        "unit_price": str(spec.unit_price),
        "total": str(spec.goods_value.amount),
        "currency": "USD",
    }


def canonical_hash(fields: Row) -> str:
    """Invoice identity (seller, number, total, currency): a re-saved PDF keeps it."""
    return canonical_invoice_hash(
        str(fields["seller"]),
        str(fields["invoice_no"]),
        str(fields["total"]),
        str(fields["currency"]),
    )


def file_sha256(rel_path: str, key: str) -> tuple[str, int | None]:
    path = REPO_ROOT / rel_path
    if path.is_file():
        data = path.read_bytes()
        return hashlib.sha256(data).hexdigest(), len(data)
    return sha256_hex(f"setu-demo-placeholder:{key}:{SEED_VERSION}"), None


def build(ctx: Ctx) -> Rows:
    documents: list[Row] = []
    findings: list[Row] = []
    pi_sha = ""
    for suffix, doc_type, seq, file_name, mime, status, check, variant, uploaded in DOCS:
        key = f"doc:{MAIN_DEAL}:{suffix}"
        rel = f"{DEMO_DIR}/{MAIN_DEAL}/{file_name}"
        placeholder = status == DocStatus.PLACEHOLDER
        sha, size = (None, None) if placeholder else file_sha256(rel, key)
        is_pi = doc_type == DocType.PROFORMA_INVOICE
        if is_pi and sha:
            pi_sha = sha
        documents.append(
            {
                "id": sid("document", key),
                "key": key,
                "deal_id": deal_id(MAIN_DEAL),
                "milestone_id": milestone_id(MAIN_DEAL, seq),
                "doc_type": doc_type,
                "file_name": file_name,
                "storage_path": rel,
                "mime_type": mime,
                "sha256": sha,
                "canonical_hash": canonical_hash(pi_fields()) if is_pi else None,
                "size_bytes": size,
                "status": status,
                "check_status": check,
                "variant": variant,
                "extracted_json": pi_fields() if is_pi else None,
                "uploaded_at": ctx.at(uploaded, 14, 30) if uploaded is not None else None,
            }
        )
        for code, detail in CHECKS.get(doc_type, ()) if not placeholder else ():
            findings.append(
                {
                    "id": sid("finding", f"{key}:{code}"),
                    "document_id": sid("document", key),
                    "check_code": code,
                    "status": CheckStatus.PASSED,
                    "severity": Severity.INFO,
                    "detail": {"message": detail},
                    "checked_at": ctx.at(uploaded or 0, 14, 35),
                }
            )

    registry = [
        {
            "id": sid("hash_registry", f"{PI_KEY}:{LENDER_A}"),
            "sha256": pi_sha,
            "canonical_hash": canonical_hash(pi_fields()),
            "lender_party_id": sid("party", LENDER_A),
            "deal_id": deal_id(MAIN_DEAL),
            "doc_type": DocType.PROFORMA_INVOICE,
            "external_ref": LENDER_A_LOAN_REF,
            "registered_at": ctx.at(-5, 15, 20),
        }
    ]
    return [(Document, documents), (ForensicFinding, findings), (HashRegistry, registry)]
