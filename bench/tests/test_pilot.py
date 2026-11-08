import yaml

from bench.pilot import compose_file


def test_agents_get_only_disposable_tokens_and_no_verifiers(tmp_path):
    task = tmp_path / "task"
    cfg = {
        "image": "image@sha256:pinned",
        "platform": "linux/amd64",
        "model": "gpt-6-luna",
        "agent_timeout_seconds": 60,
        "max_iterations": 5,
    }
    path = compose_file(
        task,
        tmp_path / "run",
        actors={"agent1": "disposable-a", "agent2": "disposable-b"},
        port=12345,
        cfg=cfg,
    )
    services = yaml.safe_load(path.read_text())["services"]
    for actor in ("agent1", "agent2"):
        config = services[actor]
        assert "OPENAI_API_KEY" not in config["environment"]
        assert config["environment"]["LLM_API_KEY"].startswith("disposable-")
        assert all("/tests" not in mount and ".env" not in mount for mount in config["volumes"])
    assert "redis" in services
