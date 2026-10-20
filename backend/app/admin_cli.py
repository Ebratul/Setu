"""Admin bootstrap: `python -m app.admin_cli create-admin --email X --name Y`.

Creates an ADMIN account (ACTIVE, not demo, no party). The person then signs up in Neon Auth with
that email; the first verified sign-in links the account, then they turn on TOTP
(POST /auth/mfa/totp/setup + enable): admin screens need it. Prints no secrets."""

import argparse
import sys
import uuid

from sqlalchemy import select

from app.audit.writer import write_audit
from app.config import get_settings
from app.db.enums import Language, Role, UserStatus
from app.db.models import User
from app.db.session import batch_session


def create_admin(email: str, name: str, *, force: bool = False) -> uuid.UUID:
    if get_settings().auth_mode == "demo" and not force:
        raise SystemExit("AUTH_MODE=demo: admins are created for neon mode only (use --force)")
    email = email.strip().lower()
    if "@" not in email or not name.strip():
        raise SystemExit("a valid --email and a non-empty --name are required")
    with batch_session() as db:
        if db.scalar(select(User.id).where(User.email.ilike(email))) is not None:
            raise SystemExit("an account with this email already exists")
        user = User(
            id=uuid.uuid4(),
            email=email,
            display_name=name.strip(),
            role=Role.ADMIN,
            language=Language.EN,
            party_id=None,
            is_demo=False,
            status=UserStatus.ACTIVE,
        )
        db.add(user)
        db.flush()
        write_audit(
            db,
            actor="system",
            action="admin.created",
            tier=3,
            params={"user_id": str(user.id)},
            result="ok",
        )
        return user.id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.admin_cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("create-admin", help="create an ADMIN account")
    p.add_argument("--email", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--force", action="store_true", help="allow when AUTH_MODE=demo")
    args = parser.parse_args(argv)
    uid = create_admin(args.email, args.name, force=args.force)
    print(f"created admin {uid}; sign up with that email, then turn on two-factor authentication")
    return 0


if __name__ == "__main__":
    sys.exit(main())
