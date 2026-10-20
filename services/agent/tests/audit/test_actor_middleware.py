"""AuditActorMiddleware: entries written during a signed-in request carry that user's id;
system-originated entries stay "system"."""

# ruff: noqa: F811  (pytest fixtures imported by name)

from collections.abc import Iterator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.audit.writer import current_actor_id
from app.auth.demo import COOKIE_NAME
from app.config import get_settings
from app.db.enums import ApprovalAction, ApprovalStatus
from app.db.models import ApprovalRequest, AuditLog
from app.db.session import batch_session
from app.main import create_app
from app.services import escrow
from tests.api.conftest import seeded_db  # noqa: F401  (fixture)
from tests.api.deals_support import (
    ADMIN,
    BRIGHTLINE,
    HUAXIN,
    KARIM,
    RAHIMA,
    as_user,
    confirmed,
    create,
    current_user_of,
    fund,
    give_cash,
    party_id,
    propose,
    release,
    verify_evidence,
)
from tests.api.test_approvals import big_deal_approval, reject_seeded_email_request

pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
def demo_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("ENABLE_DEV_EVIDENCE", "true")
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("COOLING_OFF_SECONDS", "600")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def last_entry(action: str) -> AuditLog:
    with batch_session() as s:
        return s.scalars(
            select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.seq.desc())
        ).first()  # type: ignore[return-value]


def test_a_buyer_creating_a_deal_is_recorded_under_their_user_id(seeded_db: str) -> None:
    rahima = as_user(RAHIMA)
    deal = create(rahima, HUAXIN)
    with batch_session() as s:
        row = s.scalars(
            select(AuditLog)
            .where(AuditLog.action == "DEAL_CREATED", AuditLog.deal_id == deal["id"])
            .order_by(AuditLog.seq.desc())
        ).first()
    assert row is not None
    assert row.actor.value == "user" and row.actor_id == str(current_user_of(RAHIMA).id)


def test_kyb_verify_by_a_buyer_and_by_an_admin_name_different_actors(seeded_db: str) -> None:
    sid = party_id(HUAXIN)
    assert as_user(RAHIMA).post(f"/kyb/verify/{sid}").status_code == 200
    mine = last_entry("KYB_CHECKED")
    assert mine.actor_id == str(current_user_of(RAHIMA).id)
    assert as_user(ADMIN).post(f"/kyb/verify/{sid}").status_code == 200
    theirs = last_entry("KYB_CHECKED")
    assert theirs.seq > mine.seq and theirs.actor_id == str(current_user_of(ADMIN).id)
    assert theirs.actor_id != mine.actor_id


def test_a_system_entry_written_inside_a_user_request_stays_system(seeded_db: str) -> None:
    give_cash("dhaka-stitch-works")
    karim, _deal_id, _ms, appr = big_deal_approval()
    with batch_session() as s:
        s.execute(
            update(ApprovalRequest)
            .where(ApprovalRequest.id == appr.id)
            .values(expires_at=escrow.utcnow() - timedelta(minutes=1))
        )
    assert (
        karim.get("/approvals?status=history").status_code == 200
    )  # the user's request expires it
    with batch_session() as s:
        row = s.scalars(
            select(AuditLog)
            .where(AuditLog.action == "APPROVAL_EXPIRED")
            .order_by(AuditLog.seq.desc())
        ).first()
        assert s.get(ApprovalRequest, appr.id).status == ApprovalStatus.EXPIRED  # type: ignore[union-attr]
    assert row is not None and (row.actor.value, row.actor_id) == ("system", "system")


def test_the_human_who_approves_is_the_recorded_actor(seeded_db: str) -> None:
    give_cash("rahima-knitwear")
    rahima = as_user(RAHIMA)
    reject_seeded_email_request(rahima)  # an open Tier 3 request freezes Huaxin money
    d = create(rahima, HUAXIN)
    propose(rahima, d["id"])
    confirmed(rahima, as_user("huaxin@demo.setu"), d["id"])
    ms = fund(rahima, d["id"])["milestones"][0]["id"]
    verify_evidence(as_user(ADMIN), ms)
    assert release(rahima, ms)[0] == 202
    with batch_session() as s:
        appr = s.scalars(
            select(ApprovalRequest).where(
                ApprovalRequest.deal_id == d["id"],
                ApprovalRequest.action == ApprovalAction.RELEASE_MILESTONE,
            )
        ).first()
    assert appr is not None
    assert rahima.post(f"/approvals/{appr.id}/approve", json={}).status_code == 200
    assert last_entry("APPROVAL_APPROVED").actor_id == str(current_user_of(RAHIMA).id)


def test_the_context_variable_is_reset_after_each_request(seeded_db: str) -> None:
    rahima = as_user(RAHIMA)
    rahima.get("/audit/public-key")
    assert current_actor_id.get() is None


def test_a_garbage_cookie_is_treated_as_anonymous_not_as_a_user(seeded_db: str) -> None:
    client = TestClient(create_app(), cookies={COOKIE_NAME: "not-a-token"})
    res = client.post(f"/kyb/verify/{party_id(HUAXIN)}")
    assert res.status_code == 401
    assert current_actor_id.get() is None


def test_big_deal_creation_by_karim_is_recorded_under_karim(seeded_db: str) -> None:
    karim = as_user(KARIM)
    d = create(karim, BRIGHTLINE)
    with batch_session() as s:
        row = s.scalars(
            select(AuditLog).where(AuditLog.action == "DEAL_CREATED", AuditLog.deal_id == d["id"])
        ).first()
    assert row is not None and row.actor_id == str(current_user_of(KARIM).id)
    assert row.actor_id != str(current_user_of(RAHIMA).id)
