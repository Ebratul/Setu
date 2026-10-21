import uuid

import pytest

from app.auth.deps import CurrentUser
from app.config import get_settings
from app.db.enums import MemberRole, Role, UserStatus


def admin(*, is_demo: bool, mfa: bool = False) -> CurrentUser:
    return CurrentUser(
        uuid.uuid4(), "a@x.test", "A", Role.ADMIN, "en", None, MemberRole.OWNER,
        UserStatus.ACTIVE, mfa, is_demo, False,
    )  # fmt: skip


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch):
    def set_env(**values: str) -> None:
        for key, value in values.items():
            monkeypatch.setenv(key, value)
        get_settings.cache_clear()

    yield set_env
    get_settings.cache_clear()


def test_demo_admin_needs_the_flag_in_neon_mode(env) -> None:
    env(AUTH_MODE="neon", DEMO_MODE="true", APP_ENV="dev", NEON_AUTH_BASE_URL="https://x.test/auth")
    assert not admin(is_demo=True).privileged
    env(DEMO_ADMIN_WITHOUT_MFA="true")
    assert admin(is_demo=True).privileged


def test_the_flag_never_helps_real_admins_or_prod(env) -> None:
    env(AUTH_MODE="neon", DEMO_MODE="true", APP_ENV="dev", DEMO_ADMIN_WITHOUT_MFA="true")
    assert not admin(is_demo=False).privileged
    assert admin(is_demo=False, mfa=True).privileged
    env(APP_ENV="prod")
    assert not admin(is_demo=True).privileged
    env(APP_ENV="dev", DEMO_MODE="false")
    assert not admin(is_demo=True).privileged
