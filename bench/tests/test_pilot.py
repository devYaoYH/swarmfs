import json

import pytest
import yaml

from bench.llm import MODEL_ALIAS
from bench.pilot import compose_file, task_paths, workspace_entry


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
        assert "OPENROUTER_API_KEY" not in config["environment"]
        assert config["environment"]["SIDECAR_MODEL"] == "openai/" + MODEL_ALIAS
        assert config["environment"]["LLM_API_KEY"].startswith("disposable-")
        assert all("/tests" not in mount and ".env" not in mount for mount in config["volumes"])
    assert "redis" in services
    assert services["main"]["entrypoint"][-2:] == ["sleep", "infinity"]
    assert any("/usr/local/bin/runner.sh:ro" in v for v in services["main"]["volumes"])


def test_experiment_manifest_refuses_changed_model(tmp_path, monkeypatch):
    from bench import pilot

    monkeypatch.setattr(pilot, "ARTIFACTS", tmp_path)
    cfg = {"experiment_id": "test", "llm": {"model": "openai/first"}}
    pilot.freeze_config(cfg)
    pilot.freeze_config(cfg)
    assert (
        json.loads((tmp_path / "pilot/test/experiment.json").read_text())["trail_protocol"]
        == "intent-v1"
    )
    with pytest.raises(ValueError, match="new experiment_id"):
        pilot.freeze_config({**cfg, "llm": {"model": "openrouter/second"}})


def test_pilot_refuses_stale_task_scripts_before_loading_credentials(tmp_path, monkeypatch):
    from bench import pilot

    monkeypatch.setattr(pilot, "ARTIFACTS", tmp_path)
    (tmp_path / "validation.json").write_text('[{"mode":"oracle","reward":1}]')
    cfg = {"pairs": [{"task_id": 1, "features": [1, 2]}]}
    (tmp_path / "tasks/cb-jinja-t1-f1-2").mkdir(parents=True)

    def forbidden(_):
        raise AssertionError("must not access credentials or prepare a model client")

    monkeypatch.setattr(pilot, "model_client", forbidden)
    with pytest.raises(RuntimeError, match="run prepare first"):
        pilot.run_pilot(cfg)


def test_task_selection_uses_profile_and_pins_each_workspace_base(tmp_path, monkeypatch):
    from bench import pilot

    monkeypatch.setattr(pilot, "ARTIFACTS", tmp_path)
    cfg = {
        "image": "fallback",
        "platform": "linux/amd64",
        "pairs": [{"task_id": 1465, "features": [1, 3]}],
    }
    task = task_paths(cfg)[0]
    assert task.name == "cb-jinja-t1465-f1-3"
    task.mkdir(parents=True)
    base = "20eb7f5e33120f1717b78bdf85540ab75631187a"
    (task / "benchmark.json").write_text(json.dumps({"base_commit": base, "image": "pinned"}))
    assert workspace_entry(task, cfg, ["sleep", "infinity"])[4:] == [base, "sleep", "infinity"]
    services = yaml.safe_load(
        compose_file(task, tmp_path / "run", actors={}, port=1, cfg=cfg).read_text()
    )["services"]
    assert services["main"]["image"] == "pinned"


def test_shared_agents_mount_one_tree_after_init_and_verifier_cannot_write_it(tmp_path):
    cfg = {
        "workspace_mode": "shared",
        "image": "pinned",
        "platform": "linux/amd64",
        "agent_timeout_seconds": 60,
        "max_iterations": 5,
    }
    data = yaml.safe_load(
        compose_file(
            tmp_path / "task",
            tmp_path / "run",
            actors={"agent1": "a", "agent2": "b"},
            port=1,
            cfg=cfg,
        ).read_text()
    )
    services = data["services"]
    for actor in ("agent1", "agent2"):
        service = services[actor]
        mount = next(v for v in service["volumes"] if isinstance(v, dict))
        assert mount["source"] == "workspace" and mount["target"] == "/workspace/repo"
        assert service["entrypoint"] == ["bash", "/entrypoint.sh"]
        assert service["depends_on"]["init"]["condition"] == "service_completed_successfully"
        assert service["environment"]["OH_CONVERSATIONS_PATH"].startswith("/agent_output/")
    verifier_mount = next(v for v in services["main"]["volumes"] if isinstance(v, dict))
    assert verifier_mount["read_only"] is True
    assert verifier_mount["target"] == "/shared-workspace"
    assert not any("reference.patch" in str(v) for v in services["init"]["volumes"])
    with pytest.raises(ValueError, match="model-free"):
        compose_file(
            tmp_path,
            tmp_path / "bad",
            actors={"agent1": "a"},
            port=1,
            cfg=cfg,
            reference_patch=tmp_path / "reference.patch",
        )


def test_pilot_rejects_an_old_workspace_manifest_before_credentials(tmp_path, monkeypatch):
    from bench import pilot

    monkeypatch.setattr(pilot, "ARTIFACTS", tmp_path)
    cfg = {"workspace_mode": "shared", "pairs": [{"task_id": 1, "features": [1, 2]}]}
    pilot.validation_path(cfg).write_text('[{"mode":"oracle","reward":1}]')
    task = pilot.task_paths(cfg)[0]
    task.mkdir(parents=True)
    (task / "trail-protocol.txt").write_text(pilot.TRAIL_PROTOCOL)
    (task / "harness.json").write_text('{"workspace_mode":"isolated"}')

    def forbidden(_):
        raise AssertionError("must not access credentials before workspace validation")

    monkeypatch.setattr(pilot, "model_client", forbidden)
    with pytest.raises(RuntimeError, match="workspace harness changed"):
        pilot.run_pilot(cfg)
