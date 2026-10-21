"""`python -m app.audit.keygen`: create a dev signing key if missing (never overwrites) and write
the matching public key to docs/submission/audit-public-key.pem when that file is absent."""

import sys

from app.audit.keys import (
    PUBLIC_KEY_PATH,
    create_dev_key_file,
    fingerprint,
    load_signing_key,
    public_pem,
)
from app.config import get_settings


def main() -> int:
    settings = get_settings()
    created = False
    if settings.audit_signing_key is None:
        created = create_dev_key_file(settings.audit_dev_key_path)
    public = load_signing_key().public_key()
    fp = fingerprint(public)
    pem = public_pem(public)
    if created:
        print(f"created dev signing key {settings.audit_dev_key_path} (git-ignored)")
    if not PUBLIC_KEY_PATH.exists():
        PUBLIC_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
        PUBLIC_KEY_PATH.write_text(pem)
        print(f"wrote {PUBLIC_KEY_PATH}")
    elif PUBLIC_KEY_PATH.read_text() != pem:
        print(
            f"WARNING: {PUBLIC_KEY_PATH} does not match the signing key in use; "
            "exports will not verify against the committed key",
            file=sys.stderr,
        )
        print(f"fingerprint (signing key): {fp}")
        return 1
    print(f"fingerprint: {fp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
