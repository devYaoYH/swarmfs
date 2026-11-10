import json
import sqlite3

import pytest

from bench.compare import compare
from swarmfs import TrailStore


def test_three_conditions_reuse_saved_results_and_enforce_equal_task_allowances(
    tmp_path, monkeypatch
):
    from bench import compare as module

    task = tmp_path / "task"
    (task / "tests").mkdir(parents=True)
    (task / "benchmark.json").write_text('{"base":"pinned"}')
    (task / "tests/runner.sh").write_text("pinned tests")
    monkeypatch.setattr(module, "task_paths", lambda _: [task])
    team, solo = tmp_path / "team", tmp_path / "solo"
    agents = []
    for directory, names in ((team, ["baseline", "trails"]), (solo, ["solo"])):
        directory.mkdir()
        cfg = {
            "workspace_mode": "shared",
            "per_agent_budget_usd": 0.5,
            "max_iterations": 100,
            "agent_timeout_seconds": 900,
            "experiment_id": directory.name,
            "arms": names,
        }
        (directory / "experiment.json").write_text(
            json.dumps({"config": cfg, "litellm_version": "same", "trail_protocol": "intent-v1"})
        )
        runs = []
        store = TrailStore(str(directory / "trails.db"))
        with sqlite3.connect(directory / "trails.db") as db:
            db.execute("CREATE TABLE delivered (actor TEXT, request_id TEXT, body TEXT)")
        for arm in names:
            episode = directory.name + "-" + arm
            folder = directory / episode
            folder.mkdir()
            (folder / "containers.log").write_text("")
            count = 1 if arm == "solo" else 2
            runs.append(
                {
                    "episode": episode,
                    "arm": arm,
                    "task": "task",
                    "repetition": 0,
                    "reward": int(arm != "baseline"),
                    "workspace_mode": "shared",
                    "model": "same",
                    "max_iterations": 200 if count == 1 else 100,
                    "agent_timeout_seconds": 900,
                    "per_agent_budget_usd": 1 if count == 1 else 0.5,
                }
            )
            store.deposit(episode, episode + ":agent1", "e", "src/a.py", "edit")
            agents.append(
                {
                    "actor": episode + ":agent1",
                    "input_tokens": 60 if count == 1 else 120,
                    "output_tokens": 0,
                    "usd": 0.01,
                    "unsettled_requests": 0,
                }
            )
        (directory / "results.json").write_text(json.dumps(runs))
    (solo / "budget.json").write_text(json.dumps({"agents": agents, "conservative_usd": 0.03}))
    destination = tmp_path / "combined"
    with pytest.raises(ValueError, match="overwrite"):
        compare(team, solo, team)
    compare(team, solo, destination)
    compare(team, solo, destination)  # Re-reporting must not duplicate captured activity.
    summary = json.loads((destination / "summary.json").read_text())
    assert set(summary["arms"]) == {"baseline", "trails", "solo"}
    assert summary["matched"] is True
    assert summary["captured_actions"] == 3
    assert summary["comparisons_to_solo"]["baseline"]["completion_delta_percentage_points"] == -100
    for directory in (team, solo):
        manifest = json.loads((directory / "experiment.json").read_text())
        manifest["config"]["repetitions"] = 2
        (directory / "experiment.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="every configured"):
        compare(team, solo, tmp_path / "incomplete")
    for directory in (team, solo):
        manifest = json.loads((directory / "experiment.json").read_text())
        manifest["config"].pop("repetitions")
        (directory / "experiment.json").write_text(json.dumps(manifest))
    runs = json.loads((solo / "results.json").read_text())
    runs[0]["per_agent_budget_usd"] = 0.5
    (solo / "results.json").write_text(json.dumps(runs))
    with pytest.raises(ValueError, match="allowances|must match"):
        compare(team, solo, tmp_path / "bad")
