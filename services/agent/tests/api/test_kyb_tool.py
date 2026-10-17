"""The Tier 0 `verify_party` agent tool: card shape, buyer isolation, read-only, chat routing."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.agent import persistence
from app.agent.registry import INTENT_TOOLS, ToolContext, ToolOutcome, default_registry
from app.auth.deps import to_current
from app.config import get_settings
from app.db.models import User
from app.db.session import get_engine
from app.security.tiers import Tier
from tests.api.conftest import login

pytestmark = pytest.mark.db

RAHIMA, KARIM, ADMIN = "rahima@demo.setu", "karim@demo.setu", "admin@demo.setu"
DEAL = "SETU-2026-0001"


@pytest.fixture(autouse=True)
def mock_llm(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("AGENT_MOCK_MODE", "true")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    get_settings.cache_clear()
    yield
    persistence.close_checkpointers()
    get_settings.cache_clear()


@pytest.fixture
def db(seeded_db: str) -> Iterator[Session]:
    with Session(get_engine()) as s:
        yield s


def run(db: Session, email: str, args: dict[str, Any], **ctx: Any) -> ToolOutcome:
    user = to_current(db.query(User).filter(User.email == email).one())
    c = ToolContext(caller="llm", user=user, db=db, thread_id="t", **ctx)
    return default_registry().guard("verify_party", args, c)


def test_tool_is_registered_tier0_and_allow_listed() -> None:
    spec = default_registry().get("verify_party")
    assert spec is not None and spec.max_tier == Tier.T0
    assert (
        "verify_party" in INTENT_TOOLS["analysis"] and "verify_party" in INTENT_TOOLS["deal_status"]
    )
    assert default_registry().llm_tools(frozenset({"verify_party"})) == ["verify_party"]
    assert spec.definition()["input_schema"]["properties"].keys() == {"supplier_id", "deal_id"}


def test_card_for_a_verified_supplier_with_a_pending_change(db: Session) -> None:
    out = run(db, RAHIMA, {"deal_id": DEAL})
    assert out.ok, out.error
    assert out.injection == [], "our own explanation text must not look like an instruction"
    assert out.data["card_type"] == "kyb" and out.data["simulated"] is True
    d = out.data["data"]
    assert d["status"] == "VERIFIED" and d["score"] == 100 and d["deal_ref"] == DEAL
    assert d["supplier_code"] == "shaoxing-huaxin" and d["reasons"] == []
    assert d["has_pending_change"] is True and d["pending_status"] == "WARNING"
    assert d["supplier_route"] == f"/app/suppliers/{d['supplier_id']}"
    assert d["checks_passed"] == d["checks_total"] == 7
    assert "PENDING_BENEFICIARY_CHANGE" in out.data["explanation_codes"]
    assert out.data["explanation_en"] and out.data["explanation_bn"]


def test_card_for_huameng_lists_the_top_three_reasons(db: Session) -> None:
    out = run(db, KARIM, {"supplier_id": "guangzhou-huameng"})
    assert out.ok and out.injection == []
    d = out.data["data"]
    assert d["status"] == "WARNING" and d["score"] == 40
    assert [r["code"] for r in d["reasons"]] == [
        "LICENSE_VS_ACCOUNT_HOLDER",
        "ACCOUNT_TYPE",
        "ACCOUNT_AGE",
    ]
    assert all(r["status"] == "FAIL" and r["detail_bn"] for r in d["reasons"])
    by_id = run(db, KARIM, {"supplier_id": d["supplier_id"]})
    assert by_id.ok and by_id.data["data"]["score"] == 40


def test_buyer_isolation_and_bad_input(db: Session) -> None:
    gone = {"code": "not_found", "message": "supplier or deal not found"}
    assert run(db, RAHIMA, {"supplier_id": "guangzhou-huameng"}).error == gone
    assert run(db, KARIM, {"deal_id": DEAL}).error == gone  # Rahima's deal
    assert run(db, KARIM, {"supplier_id": "guangzhou-huameng", "deal_id": DEAL}).error == gone
    assert run(db, KARIM, {}, deal_ref=DEAL).error == gone  # chat scope is isolated too
    assert run(db, KARIM, {"supplier_id": "no-such-supplier"}).error == gone
    assert run(db, RAHIMA, {"supplier_id": "rahima-knitwear"}).error == gone  # not a supplier
    assert run(db, RAHIMA, {}).error["code"] == "needs_supplier"  # type: ignore[index]
    assert run(db, RAHIMA, {"supplier_id": "x'; DROP TABLE parties;--"}).error["code"] == (  # type: ignore[index]
        "invalid_args"
    )
    assert run(db, RAHIMA, {"deal_id": DEAL, "extra": 1}).error["code"] == "invalid_args"  # type: ignore[index]
    assert run(db, RAHIMA, {}, deal_ref=DEAL).ok  # chat deal scope supplies the supplier
    assert run(db, ADMIN, {"supplier_id": "guangzhou-huameng"}).ok


def test_verify_party_writes_nothing(db: Session) -> None:
    tables = ["kyb_runs", "kyb_checks", "audit_log", "alerts", "bank_accounts", "documents"]

    def state() -> tuple[dict[str, int], list[tuple[str, str]]]:
        counts = {t: db.scalar(text(f"SELECT count(*) FROM {t}")) for t in tables}
        statuses = [
            tuple(r) for r in db.execute(text("SELECT code, kyb_status FROM parties ORDER BY code"))
        ]
        return counts, statuses  # type: ignore[return-value]

    before = state()
    for email, args in [
        (RAHIMA, {"deal_id": DEAL}),
        (KARIM, {"supplier_id": "guangzhou-huameng"}),
        (ADMIN, {"supplier_id": "ningbo-brightline"}),
    ]:
        assert run(db, email, args).ok
    assert not db.new and not db.dirty
    assert state() == before  # no rollback: nothing was even flushed


def test_chat_routes_kyb_questions_to_the_tool(client: TestClient) -> None:
    login(client, KARIM)
    out = client.post("/chat", json={"message": "Is Huameng safe to pay? Run a KYB check"}).json()
    [card] = out["cards"]
    assert card["card_type"] == "kyb" and card["data"]["status"] == "WARNING"
    assert "WARNING" in out["answer"]
    bn = client.post("/chat", json={"message": "Huameng সাপ্লায়ারকে যাচাই করো"}).json()
    assert bn["cards"][0]["card_type"] == "kyb"


def test_model_input_has_role_labels_not_holder_or_sanctions_names(db: Session) -> None:
    out = run(db, KARIM, {"supplier_id": "guangzhou-huameng"})
    assert out.ok
    for body in (out.model_payload(), out.payload()):
        assert "Chen Wei" not in body, "a natural person's name must not reach the model or card"
    assert "personal account" in out.model_payload()
    assert out.data["data"]["supplier_name"] == "Guangzhou Huameng Trading Co., Ltd."


def test_chat_answer_does_not_leak_the_holder_name(client: TestClient) -> None:
    login(client, KARIM)
    out = client.post("/chat", json={"message": "Is Huameng safe to pay? Run a KYB check"}).json()
    assert "Chen Wei" not in str(out)
