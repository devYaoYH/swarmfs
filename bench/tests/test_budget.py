from concurrent.futures import ThreadPoolExecutor

import pytest

from bench.budget import MODEL, Budget, BudgetExceeded


def request(**overrides):
    return {
        "model": MODEL,
        "messages": [{"role": "user", "content": "hello"}],
        "max_completion_tokens": 8192,
        **overrides,
    }


def test_concurrent_reservations_cannot_overspend(tmp_path):
    budget = Budget(str(tmp_path / "budget.db"), total=0.03, per_agent=0.03)

    def reserve(_):
        try:
            return budget.reserve("a", request())
        except BudgetExceeded:
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        reservations = list(pool.map(reserve, range(32)))
    assert 0 < sum(r is not None for r in reservations) < 32
    assert budget.snapshot()["conservative_usd"] <= 0.03


def test_settlement_and_persistence(tmp_path):
    path = str(tmp_path / "budget.db")
    budget = Budget(path)
    identity = budget.reserve("a", request())
    reserved = budget.snapshot()["conservative_usd"]
    budget.settle(identity, None)
    assert budget.snapshot()["conservative_usd"] == reserved
    budget.settle(identity, {"usage": {"prompt_tokens": 100, "completion_tokens": 20}})
    snapshot = Budget(path).snapshot()
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
def test_unbounded_requests_rejected(tmp_path, payload):
    budget = Budget(str(tmp_path / "budget.db"))
    with pytest.raises(ValueError):
        budget.reserve("a", payload)
    assert budget.snapshot()["conservative_usd"] == 0
