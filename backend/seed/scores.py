"""Six monthly supplier-scorecard snapshots per supplier (network-wide, simulated).

score = 60*on_time_rate + 30*max(0, 1 - 5*defect_rate) + 10 - 3*doc_mismatch_count
        - 5*dispute_count, clipped to [0, 100] and rounded to 2 dp.
"""

from decimal import Decimal

from app.db.models import SupplierScore
from app.domain.money import q2
from seed.common import Ctx, Rows, rng, sid
from seed.parties import BRIGHTLINE, HUAMENG, HUAXIN

MONTHS = 6
BP = Decimal("0.0001")

# supplier: (deals per month, on-time bp, on-time jitter bp, defect bp, defect jitter bp,
#            doc mismatches per month, disputes per month)
PROFILES: dict[
    str, tuple[tuple[int, ...], int, int, int, int, tuple[int, ...], tuple[int, ...]]
] = {
    HUAXIN: ((2, 3, 2, 3, 2, 3), 9850, 150, 120, 60, (0, 0, 0, 0, 0, 0), (0, 0, 0, 0, 0, 0)),
    BRIGHTLINE: ((3, 2, 4, 3, 3, 2), 9150, 300, 300, 100, (0, 1, 0, 0, 1, 0), (0, 0, 0, 1, 0, 0)),
    HUAMENG: ((1, 2, 1, 2, 1, 2), 6600, 500, 900, 200, (2, 3, 2, 3, 2, 3), (1, 0, 1, 0, 1, 0)),
}


def score(on_time: Decimal, defect: Decimal, mismatches: int, disputes: int) -> Decimal:
    raw = (
        Decimal(60) * on_time
        + Decimal(30) * max(Decimal(0), 1 - 5 * defect)
        + Decimal(10)
        - Decimal(3 * mismatches)
        - Decimal(5 * disputes)
    )
    return q2(min(Decimal(100), max(Decimal(0), raw)))


def build(ctx: Ctx) -> Rows:
    rows = []
    for supplier, (deals, on_bp, on_j, def_bp, def_j, mism, disp) in PROFILES.items():
        r = rng(f"scores:{supplier}")
        for i in range(MONTHS):
            months_back = MONTHS - i
            on_time = min(Decimal(1), Decimal(on_bp + r.randint(-on_j, on_j)) * BP)
            defect = max(Decimal(0), Decimal(def_bp + r.randint(-def_j, def_j)) * BP)
            month = ctx.month_start(months_back)
            rows.append(
                {
                    "id": sid("score", f"{supplier}:m-{months_back}"),
                    "supplier_id": sid("party", supplier),
                    "month": month,
                    "deals_count": deals[i],
                    "on_time_rate": on_time,
                    "defect_rate": defect,
                    "doc_mismatch_count": mism[i],
                    "dispute_count": disp[i],
                    "score": score(on_time, defect, mism[i], disp[i]),
                }
            )
    return [(SupplierScore, rows)]
