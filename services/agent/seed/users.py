"""One demo user per role. No passwords: demo mode uses a 'login as' switch (added with auth)."""

import uuid

from app.db.enums import Language, Role
from app.db.models import User
from seed.common import Ctx, Rows, sid
from seed.parties import HUAXIN, KARIM, RAHIMA

USERS: tuple[tuple[str, str, Role, Language, str | None], ...] = (
    ("rahima@demo.setu", "Rahima Akter", Role.BUYER, Language.BN, RAHIMA),
    ("karim@demo.setu", "Karim Hossain", Role.BUYER, Language.EN, KARIM),
    ("huaxin@demo.setu", "Wang Lei", Role.SUPPLIER, Language.ZH, HUAXIN),
    ("admin@demo.setu", "Setu Admin", Role.ADMIN, Language.EN, None),
    ("judge@demo.setu", "Demo Judge", Role.JUDGE, Language.EN, None),
)


def user_id(email: str) -> uuid.UUID:
    return sid("user", email)


def build(ctx: Ctx) -> Rows:
    rows = [
        {
            "id": user_id(email),
            "email": email,
            "display_name": name,
            "role": role,
            "language": lang,
            "party_id": sid("party", party) if party else None,
            "is_demo": True,
        }
        for email, name, role, lang, party in USERS
    ]
    return [(User, rows)]
