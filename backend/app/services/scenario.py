"""What-if cash-flow scenario: overrides → recomputed forecast + the alerts it would raise.
Read-only: nothing is saved."""

from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser
from app.schemas.cashflow import ScenarioOut, ScenarioRequest
from app.services.alerts import evaluate, preview
from app.services.cashflow import buffer_of, compute, forecast_out, load_book, scenario_flows
from app.services.scope import require_buyer


def run(db: Session, user: CurrentUser, req: ScenarioRequest) -> ScenarioOut:
    book = load_book(db, require_buyer(db, user, req.party_id))
    flows = scenario_flows(book.flows, req, book.currency, book.today)
    buffer = buffer_of(book, req.min_buffer)
    fc = compute(book, flows, req.days)
    drafts = evaluate(db, book, fc, buffer, flows)
    return ScenarioOut(
        forecast=forecast_out(book, fc, buffer, scenario=True),
        alerts=[preview(d) for d in drafts],
    )
