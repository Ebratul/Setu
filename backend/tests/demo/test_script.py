"""The demo script and its expression language."""

from pathlib import Path

import pytest
import yaml

from app.demo.script import (
    CheckSpec,
    Script,
    ScriptError,
    check,
    dig,
    load_script,
    render,
)

STEPS = Path(__file__).resolve().parents[3] / "data" / "demo" / "demo_steps.yaml"


def spec(at: str, **op: object) -> CheckSpec:
    return CheckSpec.model_validate({"label": {"en": "x", "bn": "x"}, "at": at, **op})


def test_shipped_script_is_valid_and_complete() -> None:
    script = load_script()
    assert [s.n for s in script.steps] == list(range(1, 13))
    assert len(script.scene_ids()) == 27
    assert {i.group for i in script.scorecard} == {"TASK", "SECURITY", "INNOVATION"}
    for step in script.steps:  # every text exists in both languages
        assert step.title.en and step.title.bn and step.narration.bn and step.notes.bn
        for scene in step.scenes:
            assert scene.caption.en and scene.caption.bn
            assert scene.actions
    tags = {s.tag for s in script.steps}
    assert tags == {"TASK", "SECURITY", "INNOVATION"}


def test_every_step_has_a_check_that_proves_it() -> None:
    for step in load_script().steps:
        assert any(scene.expect for scene in step.scenes), f"step {step.n} has no expectation"


def _raw() -> dict:
    return yaml.safe_load(STEPS.read_text(encoding="utf-8"))


def test_duplicate_scorecard_target_must_exist() -> None:
    raw = _raw()
    raw["scorecard"][0]["after"] = "99.9"
    with pytest.raises(ValueError, match="unknown scene"):
        Script.model_validate(raw)


def test_reserved_action_names_are_rejected() -> None:
    raw = _raw()
    raw["steps"][0]["scenes"][0]["actions"][0]["id"] = "deal"
    with pytest.raises(ValueError, match="reserved"):
        Script.model_validate(raw)


def test_an_action_is_http_xor_call() -> None:
    raw = _raw()
    raw["steps"][0]["scenes"][0]["actions"][0]["call"] = "fx.route_compare"
    with pytest.raises(ValueError, match="exactly one of http / call"):
        Script.model_validate(raw)


def test_a_check_has_exactly_one_operator() -> None:
    with pytest.raises(ValueError, match="exactly one operator"):
        spec("a", eq=1, ne=2)
    with pytest.raises(ValueError, match="exactly one operator"):
        spec("a")


def test_scenes_must_be_numbered_in_order() -> None:
    raw = _raw()
    raw["steps"][1]["scenes"][0]["k"] = 2
    with pytest.raises(ValueError, match="numbered"):
        Script.model_validate(raw)


DATA = {
    "body": {
        "answer": "মোট খরচ USD 11,200.00",
        "alerts": [
            {"type": "SHORTFALL", "status": "OPEN", "amount": "1560.00", "title_en": "Cash gap"},
            {
                "type": "DEADLINE",
                "status": "OPEN",
                "amount": "800.00",
                "title_en": "Customs duty due",
            },
            {"type": "SHORTFALL", "status": "RESOLVED", "amount": "9.00", "title_en": "old"},
        ],
        "flag": True,
        "n": "5760.00",
    }
}


def test_dig_filters_indexes_and_missing_values() -> None:
    assert dig(DATA, "body.alerts[type=SHORTFALL][status=OPEN][0].amount") == "1560.00"
    assert dig(DATA, "body.alerts[title_en~=customs][0].amount") == "800.00"
    assert dig(DATA, "body.alerts[-1].amount") == "9.00"
    assert dig(DATA, "body.alerts[5].amount") is None
    assert dig(DATA, "body.nope.deeper") is None
    assert dig(DATA, "body.alerts[type=NOPE][0].amount") is None


def test_numbers_compare_as_decimals_not_strings() -> None:
    assert check(spec("body.n", eq="5760"), DATA)[0]
    assert check(spec("body.n", eq=5760.0), DATA)[0]
    assert not check(spec("body.n", eq="5761"), DATA)[0]
    assert check(spec("body.n", gte="5760.00"), DATA)[0]
    assert check(spec("body.n", lte=6000), DATA)[0]
    assert not check(spec("body.n", gte="5760.01"), DATA)[0]


def test_other_operators() -> None:
    assert check(spec("body.answer", matches="11,?200"), DATA)[0]
    assert check(spec("body.answer", contains="USD"), DATA)[0]
    assert check(spec("body.answer", startswith="মোট"), DATA)[0]
    assert check(spec("body.alerts", len_gte=3), DATA)[0]
    assert not check(spec("body.alerts", len_gte=4), DATA)[0]
    assert check(spec("body.flag", truthy=True), DATA)[0]
    assert check(spec("body.absent", falsy=True), DATA)[0]
    assert check(spec("body.n", **{"in": ["1", "5760.00"]}), DATA)[0]
    assert check(spec("body.n", ne="1"), DATA)[0]


def test_render_templates_keep_types_and_fail_loudly() -> None:
    variables = {"deal": {"ref": "SETU-2026-0001"}, "gap": {"body": {"peak": {"USD": "2160.00"}}}}
    assert render("/deals/{deal.ref}/x", variables) == "/deals/SETU-2026-0001/x"
    assert render("{gap.body.peak}", variables) == {"USD": "2160.00"}
    assert render({"a": ["{deal.ref}"]}, variables) == {"a": ["SETU-2026-0001"]}
    with pytest.raises(ScriptError, match="unknown variable"):
        render("{nope.here}", variables)
