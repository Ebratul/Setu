"""The demo script (data/demo/demo_steps.yaml): typed, validated, with a tiny expression language.

Paths read results: `chat.body.answer`, `alerts.body.alerts[type=SHORTFALL][status=OPEN][0].amount`
(`[k=v]` keeps list items whose field equals v, `[k~=v]` whose field contains v, `[n]` indexes).
Templates `{deal.ref}` / `{release.approval_id}` read variables. Missing data is None, never an
exception, so a check can say `falsy`."""

import re
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.config import get_settings

# Names the runner provides to every scene (app/demo/runner.py `static_vars`).
RESERVED = frozenset({"deal", "buyer", "m1", "m2", "m3", "huaxin", "huameng", "pi", "photo1"})
Tag = Literal["TASK", "SECURITY", "INNOVATION"]
View = Literal["buyer", "supplier", "admin", "split"]


class Bi(BaseModel):
    model_config = ConfigDict(extra="forbid")

    en: str
    bn: str


class FileSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str = "file"
    path: str


class ActionSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    as_: str | None = Field(None, alias="as")
    http: str | None = None
    call: str | None = None
    args: dict[str, Any] = Field(default_factory=dict)
    json_: Any = Field(None, alias="json")
    query: dict[str, Any] = Field(default_factory=dict)
    form: dict[str, Any] = Field(default_factory=dict)
    file: FileSpec | None = None
    expect_status: int | list[int] | None = None
    save: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _one_kind(self) -> "ActionSpec":
        if (self.http is None) == (self.call is None):
            raise ValueError(f"action {self.id}: give exactly one of http / call")
        if self.http and not re.match(r"^(GET|POST|PUT|PATCH|DELETE) /", self.http):
            raise ValueError(f"action {self.id}: http must look like 'POST /path'")
        return self


class CheckSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    label: Bi
    at: str
    eq: Any = None
    ne: Any = None
    in_: list[Any] | None = Field(None, alias="in")
    gte: Any = None
    lte: Any = None
    contains: Any = None
    matches: str | None = None
    truthy: bool | None = None
    falsy: bool | None = None
    len_gte: int | None = None
    startswith: str | None = None

    @model_validator(mode="after")
    def _one_op(self) -> "CheckSpec":
        ops = [
            self.eq is not None,
            self.ne is not None,
            self.in_ is not None,
            self.gte is not None,
            self.lte is not None,
            self.contains is not None,
            self.matches is not None,
            self.truthy is not None,
            self.falsy is not None,
            self.len_gte is not None,
            self.startswith is not None,
        ]
        if sum(ops) != 1:
            raise ValueError(f"check at {self.at}: give exactly one operator")
        return self


class SceneSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    k: int
    view: View
    login_as: str
    route: str
    highlight: str | None = None
    caption: Bi
    actions: list[ActionSpec]
    expect: list[CheckSpec] = Field(default_factory=list)
    facts: dict[str, str] = Field(default_factory=dict)


class StepSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    n: int
    id: str
    tag: Tag
    title: Bi
    narration: Bi
    notes: Bi
    scenes: list[SceneSpec]


class ScoreSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    group: Tag
    after: str
    link: str
    label: Bi


class Script(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    scorecard: list[ScoreSpec]
    steps: list[StepSpec]

    @model_validator(mode="after")
    def _consistent(self) -> "Script":
        scene_ids = {f"{s.n}.{c.k}" for s in self.steps for c in s.scenes}
        if [s.n for s in self.steps] != list(range(1, len(self.steps) + 1)):
            raise ValueError("steps must be numbered 1..N in order")
        for s in self.steps:
            if [c.k for c in s.scenes] != list(range(1, len(s.scenes) + 1)):
                raise ValueError(f"step {s.n}: scenes must be numbered 1..N in order")
        ids = [s.id for s in self.steps]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate step ids")
        for item in self.scorecard:
            if item.after not in scene_ids:
                raise ValueError(f"scorecard item {item.id}: unknown scene {item.after}")
        if len({i.id for i in self.scorecard}) != len(self.scorecard):
            raise ValueError("duplicate scorecard ids")
        for s in self.steps:
            for c in s.scenes:
                for a in c.actions:
                    if a.id in RESERVED:
                        raise ValueError(
                            f"scene {s.n}.{c.k}: action id {a.id!r} is a reserved name"
                        )
        return self

    def scene_ids(self) -> list[tuple[int, int]]:
        return [(s.n, c.k) for s in self.steps for c in s.scenes]

    def find(self, n: int, k: int) -> tuple[StepSpec, SceneSpec]:
        for s in self.steps:
            if s.n == n:
                for c in s.scenes:
                    if c.k == k:
                        return s, c
        raise KeyError(f"no scene {n}.{k}")


@lru_cache(maxsize=4)
def _load(path: str, mtime: float) -> Script:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return Script.model_validate(data)


def load_script(path: Path | None = None) -> Script:
    p = path or get_settings().demo_steps_path
    return _load(str(p), p.stat().st_mtime)


# --- expressions ----------------------------------------------------------------------------

_TOKEN = re.compile(r"\[[^\]]*\]|[^.\[\]]+")
_TEMPLATE = re.compile(r"\{([A-Za-z0-9_.]+)\}")


class ScriptError(RuntimeError):
    pass


def dig(root: Any, path: str) -> Any:
    """Read `path` from nested dicts/lists; anything missing is None."""
    cur = root
    for tok in _TOKEN.findall(path):
        if cur is None:
            return None
        if tok.startswith("["):
            inner = tok[1:-1]
            if inner.lstrip("-").isdigit():
                idx = int(inner)
                cur = cur[idx] if isinstance(cur, list) and -len(cur) <= idx < len(cur) else None
            elif "~=" in inner or "=" in inner:
                contains = "~=" in inner
                key, _, want = inner.partition("~=" if contains else "=")
                if not isinstance(cur, list):
                    return None
                cur = [
                    x
                    for x in cur
                    if isinstance(x, dict)
                    and (
                        want.lower() in str(x.get(key, "")).lower()
                        if contains
                        else str(x.get(key)) == want
                    )
                ]
            else:
                raise ScriptError(f"bad path segment {tok!r}")
        else:
            cur = cur.get(tok) if isinstance(cur, dict) else None
    return cur


def render(value: Any, variables: dict[str, Any]) -> Any:
    """Fill `{a.b}` templates. A string that is exactly one template keeps the value's type."""
    if isinstance(value, str):
        whole = _TEMPLATE.fullmatch(value)
        if whole:
            found = dig(variables, whole.group(1))
            if found is None:
                raise ScriptError(f"unknown variable {{{whole.group(1)}}}")
            return found

        def one(m: re.Match[str]) -> str:
            found = dig(variables, m.group(1))
            if found is None:
                raise ScriptError(f"unknown variable {{{m.group(1)}}}")
            return str(found)

        return _TEMPLATE.sub(one, value)
    if isinstance(value, dict):
        return {k: render(v, variables) for k, v in value.items()}
    if isinstance(value, list):
        return [render(v, variables) for v in value]
    return value


def _dec(x: Any) -> Decimal | None:
    if isinstance(x, bool) or x is None:
        return None
    try:
        return Decimal(str(x).replace(",", ""))
    except (InvalidOperation, ValueError):
        return None


def same(actual: Any, expected: Any) -> bool:
    a, b = _dec(actual), _dec(expected)
    if a is not None and b is not None:
        return a == b
    return str(actual) == str(expected)


def text(x: Any, limit: int = 140) -> str:
    s = x if isinstance(x, str) else repr(x) if not isinstance(x, (dict, list)) else str(x)
    return s if len(s) <= limit else s[: limit - 1] + "…"


def check(spec: CheckSpec, variables: dict[str, Any]) -> tuple[bool, str, str]:
    """(ok, expected, actual) for one check against the scene's variables."""
    actual = dig(variables, spec.at)
    if spec.eq is not None:
        return same(actual, spec.eq), f"= {spec.eq}", text(actual)
    if spec.ne is not None:
        return not same(actual, spec.ne), f"≠ {spec.ne}", text(actual)
    if spec.in_ is not None:
        return any(same(actual, e) for e in spec.in_), f"in {spec.in_}", text(actual)
    if spec.gte is not None:
        a, b = _dec(actual), _dec(spec.gte)
        return a is not None and b is not None and a >= b, f"≥ {spec.gte}", text(actual)
    if spec.lte is not None:
        a, b = _dec(actual), _dec(spec.lte)
        return a is not None and b is not None and a <= b, f"≤ {spec.lte}", text(actual)
    if spec.contains is not None:
        if isinstance(actual, str):
            ok = str(spec.contains) in actual
        elif isinstance(actual, list):
            ok = any(same(x, spec.contains) for x in actual)
        else:
            ok = False
        return ok, f"contains {spec.contains}", text(actual)
    if spec.matches is not None:
        ok = actual is not None and re.search(spec.matches, str(actual)) is not None
        return ok, f"matches {spec.matches}", text(actual, 80)
    if spec.truthy is not None:
        return bool(actual) is spec.truthy, "true" if spec.truthy else "false", text(actual)
    if spec.falsy is not None:
        return (not actual) is spec.falsy, "empty / false" if spec.falsy else "set", text(actual)
    if spec.len_gte is not None:
        ok = isinstance(actual, (list, str, dict)) and len(actual) >= spec.len_gte
        return ok, f"at least {spec.len_gte} items", text(len(actual) if ok else actual)
    assert spec.startswith is not None
    ok = isinstance(actual, str) and actual.startswith(spec.startswith)
    return ok, f"starts with {spec.startswith}", text(actual)
