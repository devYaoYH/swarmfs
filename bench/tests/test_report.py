import json
import sqlite3

from bench.report import report, summarize
from swarmfs import TrailStore


def test_percentage_point_delta_includes_failed_attempts_and_all_tokens():
    runs = [
        {
            "arm": arm,
            "episode": f"{arm}{i}",
            "task": str(i),
            "repetition": 0,
            "reward": int(arm == "trails" or i == 0),
        }
        for arm in ("baseline", "trails")
        for i in range(2)
    ]
    budget = {
        "agents": [
            {
                "actor": f"{r['episode']}:a",
                "input_tokens": 100,
                "output_tokens": 20,
                "usd": 0.01,
                "unsettled_requests": 0,
            }
            for r in runs
        ]
    }
    result = summarize(runs, budget)
    assert result["success_delta_percentage_points"] == 50
    assert result["total_token_savings_percent"] == 0


def test_unmatched_arms_do_not_produce_comparative_claim():
    result = summarize(
        [{"arm": "baseline", "episode": "b", "task": "1", "repetition": 0, "reward": 0}],
        {"agents": []},
    )
    assert result["success_delta_percentage_points"] is None
    assert result["total_token_savings_percent"] is None


def test_different_models_are_not_treated_as_a_matched_comparison():
    result = summarize(
        [
            {"arm": arm, "episode": arm, "task": "1", "repetition": 0, "reward": 0, "model": model}
            for arm, model in (("baseline", "openai/luna"), ("trails", "openrouter/deepseek/flash"))
        ],
        {"agents": []},
    )
    assert result["matched"] is False
    assert result["success_delta_percentage_points"] is None


def test_intent_protocol_cannot_be_compared_with_the_old_observation_protocol():
    runs = [
        {
            "arm": arm,
            "episode": arm,
            "task": "1",
            "repetition": 0,
            "reward": 0,
            "model": "same",
            "trail_protocol": protocol,
        }
        for arm, protocol in (("baseline", "observed-v0"), ("trails", "intent-v1"))
    ]
    assert summarize(runs, {"agents": []})["matched"] is False


def test_report_counts_one_action_for_declaration_and_outcome(tmp_path):
    store = TrailStore(str(tmp_path / "trails.db"))
    fields = dict(action_id="a", intent="write", note="Add fallback")
    store.deposit("pair", "peer", "d", "a.py", "edit", phase="declared", **fields)
    store.deposit("pair", "peer", "s", "a.py", "edit", phase="succeeded", **fields)
    with sqlite3.connect(tmp_path / "trails.db") as db:
        db.execute("CREATE TABLE delivered (body TEXT)")
    (tmp_path / "results.json").write_text("[]")
    (tmp_path / "budget.json").write_text('{"agents":[],"conservative_usd":0}')
    report(tmp_path)
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary["captured_events"] == 2 and summary["captured_actions"] == 1
