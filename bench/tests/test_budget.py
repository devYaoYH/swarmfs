import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from bench.budget import BudgetExceeded

MODEL = "openai/gpt-6-luna"


def request(**overrides):
    return {
        "model": MODEL,
        "messages": [{"role": "user", "content": "hello"}],
        "max_completion_tokens": 8192,
        **overrides,
    }


def test_concurrent_reservations_cannot_overspend(make_budget):
    budget = make_budget(total=0.03, per_agent=0.03)

    def reserve(_):
        try:
            return budget.reserve("a", request())
        except BudgetExceeded:
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        reservations = list(pool.map(reserve, range(32)))
    assert 0 < sum(r is not None for r in reservations) < 32
    assert budget.snapshot()["conservative_usd"] <= 0.03


def test_settlement_and_persistence(tmp_path, make_budget):
    path = str(tmp_path / "budget.db")
    budget = make_budget(path)
    identity = budget.reserve("a", request())
    reserved = budget.snapshot()["conservative_usd"]
    budget.settle(identity, None)
    assert budget.snapshot()["conservative_usd"] == reserved
    budget.settle(identity, {"usage": {"prompt_tokens": 100, "completion_tokens": 20}})
    snapshot = make_budget(path).snapshot()
    assert snapshot["conservative_usd"] == pytest.approx(0.000035)
    assert snapshot["agents"][0]["unsettled_requests"] == 0


@pytest.mark.parametrize(
    "payload",
    [
        request(model="different-model"),
        request(previous_response_id="resp_hidden"),
        request(max_completion_tokens=0),
        request(tools=[{"type": "web_search"}]),
        request(messages=[{"image_url": "x"}]),
    ],
)
def test_unbounded_requests_rejected(make_budget, payload):
    budget = make_budget()
    with pytest.raises(ValueError):
        budget.reserve("a", payload)
    assert budget.snapshot()["conservative_usd"] == 0


def test_prices_are_frozen_per_request_and_reported_cost_is_not_discounted(make_budget):
    original = make_budget()
    identity = original.reserve("a", request())
    other_model = make_budget(
        model="openrouter/deepseek/test", input_usd_per_million=0.001, output_usd_per_million=0.001
    )
    other_model.settle(identity, {"usage": {"prompt_tokens": 100, "completion_tokens": 20}})
    assert other_model.snapshot()["conservative_usd"] == pytest.approx(0.000035)
    identity = other_model.reserve("b", request(model="openrouter/deepseek/test"))
    other_model.settle(
        identity, {"usage": {"prompt_tokens": 100, "completion_tokens": 20, "cost": 0.002}}
    )
    actors = {a["actor"]: a for a in other_model.snapshot()["agents"]}
    assert actors["b"]["usd"] == 0.002
    assert actors["b"]["provider_reported_usd"] == 0.002


def test_existing_ledger_migration_keeps_unknown_old_charges(tmp_path, make_budget):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE requests (id TEXT PRIMARY KEY, actor TEXT, reserved REAL, "
            "charged REAL, status TEXT, input_tokens INTEGER, output_tokens INTEGER)"
        )
        db.execute("INSERT INTO requests VALUES ('old', 'a', .01, .01, 'reserved', 0, 0)")
    budget = make_budget(path)
    budget.settle("old", {"usage": {"prompt_tokens": 0, "completion_tokens": 0}})
    assert budget.snapshot()["conservative_usd"] == 0.01
    assert budget.snapshot()["agents"][0]["unsettled_requests"] == 1


def test_native_output_capacity_is_reduced_only_by_remaining_dollars(make_budget):
    budget = make_budget(
        total=4,
        per_agent=0.5,
        provider_max_output_tokens=943718,
        input_usd_per_million=0.006,
        output_usd_per_million=0.5,
    )
    body = request()
    body.pop("max_completion_tokens")
    identity = budget.reserve("a", body)
    assert body["max_tokens"] == 943718  # No former 4096/8192 cap.
    budget.settle(identity, {"usage": {"prompt_tokens": 10, "completion_tokens": 10, "cost": 0.49}})
    followup = request()
    followup.pop("max_completion_tokens")
    budget.reserve("a", followup)
    assert 1 <= followup["max_tokens"] < 20000
    assert budget.snapshot()["conservative_usd"] <= 0.5


def test_native_output_reservations_remain_atomic(make_budget):
    budget = make_budget(
        total=0.5,
        per_agent=0.5,
        provider_max_output_tokens=943718,
        input_usd_per_million=0.006,
        output_usd_per_million=0.5,
    )

    def reserve(_):
        try:
            return budget.reserve("a", request())
        except BudgetExceeded:
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        identities = list(pool.map(reserve, range(32)))
    assert any(identities) and budget.snapshot()["conservative_usd"] <= 0.5


def test_missing_output_limit_still_rejected_without_known_provider_capacity(make_budget):
    body = request()
    body.pop("max_completion_tokens")
    with pytest.raises(ValueError):
        make_budget().reserve("a", body)
