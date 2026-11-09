"""Report the observed pair-level effect, without treating a tiny pilot as powered."""

import json
import re
import sqlite3
from pathlib import Path
from statistics import median


def summarize(results: list[dict], budget: dict) -> dict:
    arms = {}
    for arm in ("baseline", "trails"):
        runs = [r for r in results if r["arm"] == arm]
        episodes = {r["episode"] for r in runs}
        actors = [a for a in budget["agents"] if a["actor"].rsplit(":", 1)[0] in episodes]
        arms[arm] = {
            "attempts": len(runs),
            "successes": sum(r.get("reward") == 1 for r in runs),
            "success_percent": 100 * sum(r.get("reward") == 1 for r in runs) / len(runs)
            if runs
            else None,
            "input_tokens": sum(a["input_tokens"] for a in actors),
            "output_tokens": sum(a["output_tokens"] for a in actors),
            "conservative_usd": sum(a["usd"] for a in actors),
            "provider_reported_usd": sum(a.get("provider_reported_usd") or 0 for a in actors)
            if any(a.get("provider_reported_usd") is not None for a in actors)
            else None,
            "reported_cost_requests": sum(a.get("reported_cost_requests", 0) for a in actors),
            "unsettled_requests": sum(a["unsettled_requests"] for a in actors),
            "errors": sum(bool(r.get("error") or r.get("upstream_errors")) for r in runs),
            "budget_cutoff_agents": sum(r.get("budget_cutoff_agents", 0) for r in runs),
            "iteration_cutoff_agents": sum(r.get("iteration_cutoff_agents", 0) for r in runs),
            "stuck_cutoff_agents": sum(r.get("stuck_cutoff_agents", 0) for r in runs),
        }
    matched = all(
        {(r["task"], r["repetition"]) for r in results if r["arm"] == arm}
        == {(r["task"], r["repetition"]) for r in results}
        for arm in arms
    ) and bool(results)
    settings = {
        json.dumps(
            {
                "llm": r.get("llm", {"model": r.get("model")}),
                "trail_protocol": r.get("trail_protocol", "observed-v0"),
                "limits": {
                    k: r.get(k)
                    for k in (
                        "max_iterations",
                        "agent_timeout_seconds",
                        "per_agent_budget_usd",
                        "provider_max_output_tokens",
                        "max_output_tokens",
                        "max_input_tokens",
                    )
                },
            },
            sort_keys=True,
        )
        for r in results
    }
    matched = matched and len(settings) == 1
    delta = (
        arms["trails"]["success_percent"] - arms["baseline"]["success_percent"] if matched else None
    )
    base_tokens = arms["baseline"]["input_tokens"] + arms["baseline"]["output_tokens"]
    trail_tokens = arms["trails"]["input_tokens"] + arms["trails"]["output_tokens"]
    savings = 100 * (base_tokens - trail_tokens) / base_tokens if matched and base_tokens else None
    return {
        "arms": arms,
        "matched": matched,
        "models": sorted({r.get("model", "legacy") for r in results}),
        "feature_pairs": len({r["task"] for r in results}),
        "task_families": len({r["task"].rsplit("-f", 1)[0] for r in results}),
        "success_delta_percentage_points": delta,
        "total_token_savings_percent": savings,
        "note": "Small exploratory pilot; paper baselines are context, not matched controls.",
    }


def report(output: Path):
    results = json.loads((output / "results.json").read_text())
    for record in results:
        log_path = output / record["episode"] / "containers.log"
        log = log_path.read_text() if log_path.exists() else ""
        record["budget_cutoff_agents"] = len(
            set(re.findall(r"^(agent\d+)-\d+[^\n]*pilot_budget", log, re.MULTILINE))
        )
        record["iteration_cutoff_agents"] = len(
            set(re.findall(r"^(agent\d+)-\d+[^\n]*Max iterations reached", log, re.MULTILINE))
        )
        record["stuck_cutoff_agents"] = len(
            set(
                re.findall(r"^(agent\d+)-\d+[^\n]*Remote conversation got stuck", log, re.MULTILINE)
            )
        )
    budget = json.loads((output / "budget.json").read_text())
    summary = summarize(results, budget)
    summary["cumulative_gateway_conservative_usd"] = budget["conservative_usd"]
    with sqlite3.connect(output / "trails.db") as db:
        summary["captured_events"] = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        columns = {row[1] for row in db.execute("PRAGMA table_info(events)")}
        summary["captured_actions"] = (
            db.execute(
                "SELECT COUNT(*) FROM (SELECT episode, actor, COALESCE(action_id, event_id) "
                "FROM events GROUP BY episode, actor, COALESCE(action_id, event_id))"
            ).fetchone()[0]
            if "action_id" in columns
            else summary["captured_events"]
        )
        blocks = [row[0] for row in db.execute("SELECT body FROM delivered")]
        summary["delivered_blocks"] = len(blocks)
    ages = [int(age) for block in blocks for age in re.findall(r"(\d+)s ago", block)]
    summary["displayed_age_seconds"] = {
        "median": median(ages) if ages else None,
        "max": max(ages) if ages else None,
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2))
    lines = [
        "# Preliminary CooperBench activity-trail pilot",
        "",
        "Models: " + ", ".join(summary["models"]) + " · OpenHands SDK · local Docker",
        "",
        "| Arm | Successful pairs | Success % | Input tokens | Output tokens | "
        "USD* | Budget / iteration / stuck stops |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    delta = summary["success_delta_percentage_points"]
    savings = summary["total_token_savings_percent"]
    for name, arm in summary["arms"].items():
        percent = f"{arm['success_percent']:.1f}" if arm["success_percent"] is not None else "n/a"
        lines.append(
            f"| {name} | {arm['successes']}/{arm['attempts']} | {percent} | "
            f"{arm['input_tokens']} | {arm['output_tokens']} | "
            f"${arm['conservative_usd']:.4f} | {arm['budget_cutoff_agents']} / "
            f"{arm['iteration_cutoff_agents']} / {arm['stuck_cutoff_agents']} |"
        )
    lines.extend(
        [
            "",
            f"Completion delta: {delta:.1f} percentage points."
            if delta is not None
            else "Completion delta: unavailable (unmatched arms).",
            f"Total token savings: {savings:.1f}%."
            if savings is not None
            else "Token comparison: unavailable (unmatched arms).",
            f"Cumulative gateway ledger, including other experiments/setup: "
            f"${budget['conservative_usd']:.4f}.",
            "",
            f"Captured file actions: {summary['captured_actions']} "
            f"({summary['captured_events']} lifecycle events); "
            f"trail blocks in successful API requests: {summary['delivered_blocks']}.",
            f"Displayed observation age: median {summary['displayed_age_seconds']['median']}s, "
            f"maximum {summary['displayed_age_seconds']['max']}s. "
            "This pilot compares visible decaying trails with capture-only control; "
            "it does not isolate decay from a non-decaying trail arm.",
            "",
            "*USD uses configured upper token rates without cache discounts; "
            "provider-reported costs are recorded separately and can increase the charge. "
            "unknown request outcomes retain their full spending reservation. "
            "This is not an account billing statement.",
            "Budget cutoffs count agents whose SDK logs report a pilot spending denial. "
            "Completion rates include those attempts; token savings must be read alongside "
            "success and cutoffs, since stopping early also reduces tokens.",
            "",
            f"{summary['feature_pairs']} feature pairs from {summary['task_families']} "
            "task families form a preliminary pilot, not a "
            "held-out evaluation. Timeouts, tiny sample size, shared family and partial "
            "structured-file capture limit interpretation. Baseline and treatment keep "
            "messaging, tools, model and verifier constant.",
            "",
            "The [CooperBench paper](https://arxiv.org/abs/2601.13295) reports roughly "
            "25% cooperative success for GPT-5 and Claude Sonnet 4.5 in its setting. "
            "Different models, task selection and budgets prevent direct subtraction "
            "from those published rates; our completion delta uses our own matched baseline.",
        ]
    )
    (output / "report.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(summary, indent=2))
