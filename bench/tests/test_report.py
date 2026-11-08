from bench.report import summarize


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
