"""Combine saved shared-team and solo results without rerunning completed attempts."""

import json
import sqlite3
from pathlib import Path

from bench.pilot import evaluation_signature, task_paths
from bench.report import report
from swarmfs import TrailStore


def compare(team: Path, solo: Path, output: Path):
    if output.resolve() in {team.resolve(), solo.resolve()}:
        raise ValueError("comparison output must not overwrite either source experiment")
    sources = [json.loads((p / "experiment.json").read_text()) for p in (team, solo)]
    configs = [s["config"] for s in sources]
    # Solo intentionally changes team size and the per-agent allocation, while
    # keeping total task dollars/iterations and the wall-clock limit equal.
    ignored = {"experiment_id", "arms", "solo_budget_usd", "solo_max_iterations"}
    if {k: v for k, v in configs[0].items() if k not in ignored} != {
        k: v for k, v in configs[1].items() if k not in ignored
    }:
        raise ValueError("model, tasks, limits and trail settings must otherwise match")
    if any(s[k] != sources[0][k] for s in sources for k in ("litellm_version", "trail_protocol")):
        raise ValueError("model client and tool protocol must match")
    inputs = [{t.name: evaluation_signature(t) for t in task_paths(c)} for c in configs]
    if inputs[0] != inputs[1]:
        raise ValueError("evaluation inputs differ")
    records = []
    for directory in (team, solo):
        for r in json.loads((directory / "results.json").read_text()):
            r = dict(r)
            count = r.get("agent_count", 1 if r["arm"] == "solo" else 2)
            r["agent_count"] = count
            r["task_budget_usd"] = r["per_agent_budget_usd"] * count
            r["task_iteration_allowance"] = r["max_iterations"] * count
            r["evaluation_signature"] = inputs[0][r["task"]]
            records.append(r)
    keys = [(r["task"], r["repetition"], r["arm"]) for r in records]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate attempts")
    expected = {(task, i) for task in inputs[0] for i in range(configs[0].get("repetitions", 1))}
    if {(r["task"], r["repetition"]) for r in records} != expected:
        raise ValueError("comparison requires every configured task and repetition")
    for task, repetition in {(r["task"], r["repetition"]) for r in records}:
        runs = [r for r in records if r["task"] == task and r["repetition"] == repetition]
        if {r["arm"] for r in runs} != {"baseline", "trails", "solo"}:
            raise ValueError("each task needs all three conditions")
        if (
            len(
                {
                    (
                        r["task_budget_usd"],
                        r["task_iteration_allowance"],
                        r["agent_timeout_seconds"],
                    )
                    for r in runs
                }
            )
            != 1
        ):
            raise ValueError("aggregate dollars/iterations and task wall limit must match")
    output.mkdir(parents=True, exist_ok=True)
    (output / "results.json").write_text(json.dumps(records, indent=2))
    # The latest cumulative ledger contains all actors; report filters by episode.
    budget = json.loads((solo / "budget.json").read_text())
    selected = {r["episode"] for r in records}
    present = {a["actor"].rsplit(":", 1)[0] for a in budget["agents"]}
    if not selected <= present:
        raise ValueError("latest ledger is missing selected episodes")
    (output / "budget.json").write_text(json.dumps(budget, indent=2))
    # Preserve source attempts and their operational logs; no model requests here.
    for directory in (team, solo):
        for r in json.loads((directory / "results.json").read_text()):
            link = output / r["episode"]
            if not link.exists():
                link.symlink_to((directory / r["episode"]).resolve(), target_is_directory=True)
    TrailStore(str(output / "trails.db"))
    with sqlite3.connect(output / "trails.db") as destination:
        for directory in (team, solo):
            with sqlite3.connect(directory / "trails.db") as source:
                columns = [r[1] for r in source.execute("PRAGMA table_info(events)")]
                rows = source.execute("SELECT * FROM events").fetchall()
                placeholders = ",".join("?" for _ in columns)
                destination.executemany(
                    f"INSERT OR IGNORE INTO events ({','.join(columns)}) VALUES ({placeholders})",
                    rows,
                )
                destination.execute(
                    "CREATE TABLE IF NOT EXISTS delivered (actor TEXT, request_id TEXT, body TEXT)"
                )
                destination.executemany(
                    "INSERT INTO delivered SELECT ?,?,? WHERE NOT EXISTS "
                    "(SELECT 1 FROM delivered WHERE actor=? AND request_id=?)",
                    [(*r, r[0], r[1]) for r in source.execute("SELECT * FROM delivered")],
                )
    (output / "comparison.json").write_text(
        json.dumps(
            {
                "sources": [str(team), str(solo)],
                "manifests": sources,
                "evaluation_inputs": inputs[0],
                "allocation": {
                    "task_budget_usd": records[0]["task_budget_usd"],
                    "task_sdk_iterations": records[0]["task_iteration_allowance"],
                    "wall_limit_seconds": records[0]["agent_timeout_seconds"],
                    "note": "Solo is serial; team has two concurrent agents.",
                },
                "note": "Solo appended after saved team runs; "
                "not a concurrently randomized three-arm experiment.",
            },
            indent=2,
        )
    )
    report(output)
    summary = json.loads((output / "summary.json").read_text())
    single = summary["arms"]["solo"]
    solo_tokens = single["input_tokens"] + single["output_tokens"]
    summary["comparisons_to_solo"] = {
        arm: {
            "completion_delta_percentage_points": summary["arms"][arm]["success_percent"]
            - single["success_percent"],
            "token_reduction_percent": 100
            * (
                solo_tokens
                - summary["arms"][arm]["input_tokens"]
                - summary["arms"][arm]["output_tokens"]
            )
            / solo_tokens
            if solo_tokens
            else None,
        }
        for arm in ("baseline", "trails")
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2))
    allocation = records[0]
    with (output / "report.md").open("a") as doc:
        doc.write(
            "\n## Single-agent baseline\n\nOne agent receives both feature requests, "
            f"${allocation['task_budget_usd']:g} and {allocation['task_iteration_allowance']} "
            "SDK iterations; the two-agent arms share those total allowances. "
            "All conditions have the same "
            f"{allocation['agent_timeout_seconds']}-second wall limit. "
            "Solo was appended to saved team results.\n\n"
        )
        doc.write(
            "| Task / repetition | Shared control | Shared trails | Single agent, both features |\n"
        )
        doc.write("| --- | --- | --- | --- |\n")
        for task, repetition in sorted(expected):
            row = {
                r["arm"]: r.get("reward") == 1
                for r in records
                if r["task"] == task and r["repetition"] == repetition
            }
            doc.write(
                "| "
                + f"{task} / {repetition}"
                + " | "
                + " | ".join("Pass" if row[a] else "Fail" for a in ("baseline", "trails", "solo"))
                + " |\n"
            )
