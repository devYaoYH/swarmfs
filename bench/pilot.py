"""Run the pinned Harbor CooperBench sidecars locally with Docker Compose."""

import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import tomllib
from importlib.metadata import version
from pathlib import Path

import yaml
from dotenv import dotenv_values

from bench.budget import Budget
from bench.gateway import Gateway, new_token
from bench.llm import MODEL_ALIAS, ModelClient, ModelConfig
from swarmfs.trails import TrailStore

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / ".cache/upstream"
ARTIFACTS = ROOT / "artifacts"
TRAIL_PROTOCOL = "intent-v1"
DEFAULT_BASE = "a2920752fd111c2d52c88eb57487667b3cf0ea7b"


def config(path=None):
    return tomllib.loads(Path(path or ROOT / "pilot.toml").read_text())


def model_client(cfg):
    settings = ModelConfig(**cfg["llm"])
    key = dotenv_values(ROOT / ".env").get(settings.api_key_env) or os.environ.get(
        settings.api_key_env
    )
    if not key:
        raise RuntimeError(f"{settings.api_key_env} is missing")
    return ModelClient(settings, key)


def experiment_output(cfg):
    name = cfg["experiment_id"]
    if (
        not name
        or name in {".", ".."}
        or any(
            c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-"
            for c in name
        )
    ):
        raise ValueError("experiment_id must be a simple directory name")
    return ARTIFACTS / "pilot" / name


def freeze_config(cfg):
    output = experiment_output(cfg)
    output.mkdir(parents=True, exist_ok=True)
    manifest = output / "experiment.json"
    frozen = {
        "config": cfg,
        "litellm_version": version("litellm"),
        "trail_protocol": TRAIL_PROTOCOL,
    }
    if manifest.exists() and json.loads(manifest.read_text()) != frozen:
        raise ValueError("experiment settings changed; use a new experiment_id")
    manifest.write_text(json.dumps(frozen, indent=2))
    return output


def command(args, *, cwd=None, log=None, timeout=1200):
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if log:
        Path(log).write_text(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}): {args[0:3]}; see {log}")
    return result.stdout


def adapter_module():
    path = UPSTREAM / "harbor/adapters/cooperbench/src/cooperbench/adapter.py"
    spec = importlib.util.spec_from_file_location("pinned_cooperbench_adapter", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def task_paths(cfg):
    return [
        ARTIFACTS / "tasks" / f"cb-jinja-t{p['task_id']}-f{p['features'][0]}-{p['features'][1]}"
        for p in cfg["pairs"]
    ]


def task_runtime(task, cfg):
    path = task / "benchmark.json"
    return (
        json.loads(path.read_text())
        if path.exists()
        else {"base_commit": DEFAULT_BASE, "image": cfg["image"]}
    )


def workspace_entry(task, cfg, command):
    base = task_runtime(task, cfg)["base_commit"]
    if not re.fullmatch("[0-9a-f]{40}", base):
        raise ValueError("invalid pinned base commit")
    return [
        "bash",
        "-c",
        'git -C /workspace/repo checkout --detach "$1" && shift && exec "$@"',
        "swarmfs",
        base,
        *command,
    ]


def task_signature(task):
    digest = hashlib.sha256()
    for path in [
        task / "benchmark.json",
        *sorted((task / "tests").iterdir()),
        task / "solution/combined.patch",
    ]:
        digest.update(path.name.encode() + b"\0" + path.read_bytes())
    return digest.hexdigest()


def prepare(cfg=None):
    cfg = cfg or config()
    for repository, key in (("harbor", "harbor_revision"), ("CooperBench", "cooperbench_revision")):
        actual = command(["git", "-C", str(UPSTREAM / repository), "rev-parse", "HEAD"]).strip()
        if actual != cfg[key]:
            raise RuntimeError(f"{repository} must be pinned at {cfg[key]}")
    module = adapter_module()
    output = ARTIFACTS / "tasks"
    generated = []
    for pair in cfg["pairs"]:
        source = UPSTREAM / "CooperBench/dataset" / pair["repository"] / f"task{pair['task_id']}"
        base_commit = pair.get("base_commit", DEFAULT_BASE)
        features = []
        for feature_id in pair["features"]:
            folder = source / f"feature{feature_id}"
            features.append(
                module.CooperBenchFeature(
                    instance_id=f"jinja-{pair['task_id']}-{feature_id}",
                    repo="pallets/jinja",
                    base_commit=base_commit,
                    problem_statement=(folder / "feature.md").read_text(),
                    patch="",
                    test_patch=(folder / "tests.patch").read_text(),
                    version="pinned",
                    environment_setup_commit="",
                    hints_text=None,
                    cooperbench_task_id=str(pair["task_id"]),
                    cooperbench_feature_id=str(feature_id),
                )
            )
        module._combined_patch_cache[("pallets/jinja", str(pair["task_id"]))] = (
            source / "combined.patch"
        ).read_text()
        adapter = module.CooperBenchAdapter(output, agent_harness="openhands-sdk")
        path = adapter.generate_task(
            module.CooperBenchPair(
                repo="pallets/jinja",
                task_id=str(pair["task_id"]),
                base_commit=features[0].base_commit,
                feature_a=features[0],
                feature_b=features[1],
            ),
            overwrite=True,
        )
        # Both arms use the same intent-aware file tool, callbacks and LLM limits.
        # Native collaboration and the Harbor verifier are retained.
        for actor in ("agent1", "agent2"):
            script = path / "environment" / actor / "run_agent.py"
            text = script.read_text()
            text = text.replace(
                "    register_default_tools(enable_browser=False)",
                "    register_default_tools(enable_browser=False)\n"
                "    from bench.intent_editor import TrailFileEditorTool",
            )
            text = text.replace('Tool(name="file_editor")', "Tool(name=TrailFileEditorTool.name)")
            text = text.replace(
                "import os\n", 'import os\nos.makedirs("/logs/agent", exist_ok=True)\n', 1
            )
            text = text.replace(
                "    llm = LLM(**llm_kwargs)",
                "    llm_kwargs.update("
                + repr(
                    {
                        "stream": False,
                        "max_output_tokens": cfg.get("max_output_tokens"),
                        "num_retries": 0,
                        "max_input_tokens": cfg.get("max_input_tokens", 100000),
                        "disable_vision": True,
                        "reasoning_effort": cfg["llm"].get("reasoning_effort"),
                    }
                )
                + ")\n"
                "    llm = LLM(**llm_kwargs)",
            )
            text = text.replace(
                "    events_log: list[dict] = []",
                "    events_log: list[dict] = []\n"
                "    from bench.openhands import ActivityHook\n"
                "    activity_hook = ActivityHook()",
            )
            text = text.replace(
                '            events_log.append(event.model_dump(mode="json"))',
                "            raw_event = event.model_dump(mode='json')\n"
                "            events_log.append(raw_event)\n"
                "            activity_hook.on_event(raw_event)",
            )
            if (
                "activity_hook.on_event" not in text
                or "llm_kwargs.update(" not in text
                or "Tool(name=TrailFileEditorTool.name)" not in text
            ):
                raise RuntimeError("upstream SDK template changed")
            script.write_text(text)
            entrypoint = script.with_name("entrypoint.sh")
            entry = entrypoint.read_text()
            marker = "from openhands.agent_server.__main__ import main"
            if marker not in entry:
                raise RuntimeError("upstream server entrypoint changed")
            entrypoint.write_text(
                entry.replace(
                    marker, "from bench.intent_editor import TrailFileEditorTool\n" + marker
                )
            )
        (path / "trail-protocol.txt").write_text(TRAIL_PROTOCOL)
        shutil.copy(source / "runner.sh", path / "tests/runner.sh")
        (path / "benchmark.json").write_text(
            json.dumps(
                {
                    "repository": pair["repository"],
                    "task_id": pair["task_id"],
                    "features": pair["features"],
                    "base_commit": base_commit,
                    "image": pair.get("image", cfg["image"]),
                },
                indent=2,
            )
        )
        generated.append(path)
    return generated


def compose_file(task: Path, output: Path, *, actors: dict, port: int, cfg: dict):
    output.mkdir(parents=True, exist_ok=True)
    runtime = task_runtime(task, cfg)
    services = {
        "main": {
            "image": runtime["image"],
            "platform": cfg["platform"],
            "entrypoint": workspace_entry(task, cfg, ["sleep", "infinity"]),
            "volumes": [
                f"{task / 'tests'}:/tests:ro",
                f"{task / 'tests/runner.sh'}:/usr/local/bin/runner.sh:ro",
                f"{output / 'verifier'}:/logs/verifier",
                "agent1_out:/shared/agent1:ro",
                "agent2_out:/shared/agent2:ro",
            ],
        },
        "redis": {"image": "redis:7-alpine"},
    }
    for actor, token in actors.items():
        services[actor] = {
            "image": runtime["image"],
            "platform": cfg["platform"],
            "entrypoint": workspace_entry(task, cfg, ["bash", "/entrypoint.sh"]),
            "environment": {
                "AGENT_ID": actor,
                "AGENT_SERVER_PORT": "8000",
                "SIDECAR_MODEL": "openai/" + MODEL_ALIAS,
                "LLM_API_KEY": token,
                "LLM_BASE_URL": f"http://host.docker.internal:{port}/v1",
                "TRAIL_GATEWAY": f"http://host.docker.internal:{port}",
                "REDIS_URL": "redis://redis:6379",
                "AGENTS": "agent1,agent2",
                "AGENT_TIMEOUT": str(cfg["agent_timeout_seconds"]),
                "MAX_ITERATIONS": str(cfg["max_iterations"]),
                "PYTHONPATH": "/opt/swarm-src:/opt/swarm-bench",
                "LITELLM_LOG": "ERROR",
            },
            "volumes": [
                f"{task / 'environment' / actor / 'instruction.md'}:/agent/instruction.md:ro",
                f"{task / 'environment' / actor / 'run_agent.py'}:/opt/cooperbench/run_agent.py:ro",
                f"{task / 'environment' / actor / 'entrypoint.sh'}:/entrypoint.sh:ro",
                f"{ROOT / 'src'}:/opt/swarm-src:ro",
                f"{ROOT / 'bench'}:/opt/swarm-bench/bench:ro",
                f"{actor}_out:/agent_output",
            ],
            "depends_on": ["redis"],
        }
    data = {
        "services": services,
        "volumes": {"agent1_out": {}, "agent2_out": {}},
        "networks": {"default": {"ipam": {"config": [{"subnet": "10.254.254.0/28"}]}}},
    }
    path = output / "compose.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    path.chmod(0o600)  # Contains disposable gateway tokens, never the OpenAI key.
    return path


def verify(cfg=None):
    """No models: both combined reference and untouched-base negative control."""
    cfg = cfg or config()
    tasks = prepare(cfg)
    records = []
    for task in tasks:
        runtime = task_runtime(task, cfg)
        for mode in ("oracle", "untouched"):
            output = ARTIFACTS / "validation" / task.name / mode
            output.mkdir(parents=True, exist_ok=True)
            patches = output / "patches"
            patches.mkdir(exist_ok=True)
            if mode == "oracle":
                shutil.copy(task / "solution/combined.patch", patches / "combined.patch")
                entry = ["bash", "/tests/test.sh"]
            else:
                for name in ("tests1.patch", "tests2.patch"):
                    shutil.copy(task / "tests" / name, patches / name)
                # Run actual tests on base bytes, without applying an empty patch.
                script = """
import json, subprocess
from pathlib import Path
results = []
for name in ('tests1.patch', 'tests2.patch'):
    run = subprocess.run(['bash', '/usr/local/bin/runner.sh', name],
                         capture_output=True, text=True)
    Path('/logs/verifier/' + name + '.log').write_text(run.stdout + run.stderr)
    results.append(run.returncode == 0)
Path('/logs/verifier/reward.json').write_text(json.dumps({
    'reward': int(all(results)), 'feature1_passed': results[0],
    'feature2_passed': results[1], 'strategy': 'untouched-base'}))
"""
                entry = ["python3", "-c", script]
            # Use the unmodified upstream verifier and exact benchmark runner.
            try:
                entry = workspace_entry(task, cfg, entry)
                command(
                    [
                        "docker",
                        "run",
                        "--rm",
                        "--platform",
                        cfg["platform"],
                        "--entrypoint",
                        entry[0],
                        "-v",
                        f"{task / 'tests'}:/tests:ro",
                        "-v",
                        f"{task / 'tests/runner.sh'}:/usr/local/bin/runner.sh:ro",
                        "-v",
                        f"{patches}:/patches",
                        "-v",
                        f"{output}:/logs/verifier",
                        runtime["image"],
                        *entry[1:],
                    ],
                    log=output / "execution.log",
                )
                reward = json.loads((output / "reward.json").read_text())
                records.append(
                    {"task": task.name, "mode": mode, "signature": task_signature(task), **reward}
                )
            except (RuntimeError, OSError) as exc:
                records.append({"task": task.name, "mode": mode, "error": str(exc)})
            print(json.dumps(records[-1]), flush=True)
    (ARTIFACTS / "validation.json").write_text(json.dumps(records, indent=2))
    valid = all(
        (r.get("reward") == 1 if r["mode"] == "oracle" else r.get("reward") == 0)
        and not r.get("error")
        for r in records
    )
    if not valid:
        raise RuntimeError("reference/negative validation failed; model runs are disabled")
    return records


def run_pilot(cfg=None):
    cfg = cfg or config()
    validation = json.loads((ARTIFACTS / "validation.json").read_text())
    if not validation or any(
        r.get("error") or r.get("reward") != (r["mode"] == "oracle") for r in validation
    ):
        raise RuntimeError("run offline verifier validation first")
    tasks = task_paths(cfg)
    if not tasks or any(
        not (task / "trail-protocol.txt").exists()
        or (task / "trail-protocol.txt").read_text() != TRAIL_PROTOCOL
        for task in tasks
    ):
        raise RuntimeError("run prepare first: task scripts must use the current trail protocol")
    expected = {
        (task.name, mode, task_signature(task))
        for task in tasks
        for mode in ("oracle", "untouched")
    }
    if {(r["task"], r["mode"], r.get("signature")) for r in validation} != expected:
        raise RuntimeError("run verify first: validation must cover these exact task inputs")
    client = model_client(cfg)
    output = freeze_config(cfg)
    budget = Budget(
        str(ARTIFACTS / "pilot/budget.db"),
        model=client.config.model,
        input_usd_per_million=client.config.input_usd_per_million,
        output_usd_per_million=client.config.output_usd_per_million,
        total=cfg["budget_usd"],
        per_agent=cfg["per_agent_budget_usd"],
        provider_max_output_tokens=cfg.get("provider_max_output_tokens"),
    )
    gateway = Gateway(
        ("0.0.0.0", 0),
        trails=TrailStore(str(output / "trails.db")),
        budget=budget,
        llm=client,
        tokens={},
        half_life=cfg["half_life_seconds"],
    )
    thread = threading.Thread(target=gateway.serve_forever, daemon=True)
    thread.start()
    results = []
    try:
        for repetition in range(cfg["repetitions"]):
            for task_index, task in enumerate(tasks):
                # Counterbalance arm order, including across repetitions.
                arms = (
                    ["baseline", "trails"]
                    if (repetition + task_index) % 2 == 0
                    else ["trails", "baseline"]
                )
                for arm in arms:
                    episode = f"{cfg['experiment_id']}-{task.name}-r{repetition}-{arm}"
                    run_dir = output / episode
                    if (run_dir / "result.json").exists():
                        results.append(json.loads((run_dir / "result.json").read_text()))
                        continue
                    actors = {name: new_token() for name in ("agent1", "agent2")}
                    for name, token in actors.items():
                        identity = episode + ":" + name
                        gateway.tokens[token] = identity
                        if arm == "trails":
                            gateway.visible_actors.add(identity)
                    path = compose_file(
                        task, run_dir, actors=actors, port=gateway.server_port, cfg=cfg
                    )
                    project = "swarm-" + str(len(results)) + "-" + str(os.getpid())
                    base = ["docker", "compose", "-p", project, "-f", str(path)]
                    started = time.monotonic()
                    record = {
                        "episode": episode,
                        "arm": arm,
                        "task": task.name,
                        "repetition": repetition,
                        "model": client.config.model,
                        "llm": client.config.manifest(),
                        "litellm_version": version("litellm"),
                        "trail_protocol": TRAIL_PROTOCOL,
                        "runtime": task_runtime(task, cfg),
                        "max_iterations": cfg["max_iterations"],
                        "agent_timeout_seconds": cfg["agent_timeout_seconds"],
                        "per_agent_budget_usd": cfg["per_agent_budget_usd"],
                        "provider_max_output_tokens": cfg.get("provider_max_output_tokens"),
                        "max_output_tokens": cfg.get("max_output_tokens"),
                        "max_input_tokens": cfg.get("max_input_tokens", 100000),
                        "harness": "openhands-sdk",
                        "reasoning_effort": client.config.reasoning_effort,
                        "harbor_revision": cfg["harbor_revision"],
                        "cooperbench_revision": cfg["cooperbench_revision"],
                    }
                    try:
                        command([*base, "up", "-d"], log=run_dir / "startup.log")
                        # SDK entrypoints time out and extract patches on exit.
                        for actor in actors:
                            container = command([*base, "ps", "-aq", actor]).strip()
                            command(
                                ["docker", "wait", container],
                                timeout=cfg["agent_timeout_seconds"] + 180,
                                log=run_dir / f"{actor}-wait.log",
                            )
                        command(
                            [*base, "exec", "-T", "main", "bash", "/tests/test.sh"],
                            log=run_dir / "evaluation.log",
                        )
                        record.update(json.loads((run_dir / "verifier/reward.json").read_text()))
                    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
                        record.update(reward=0, error=str(exc))
                    finally:
                        for actor in actors:
                            destination = run_dir / actor
                            destination.mkdir(exist_ok=True)
                            subprocess.run(
                                [*base, "cp", f"{actor}:/agent_output/.", str(destination)],
                                capture_output=True,
                                timeout=60,
                            )
                        subprocess.run(
                            [*base, "logs", "--no-color"],
                            stdout=(run_dir / "containers.log").open("w"),
                            stderr=subprocess.STDOUT,
                        )
                        subprocess.run([*base, "down", "-v"], capture_output=True, timeout=120)
                    record["seconds"] = time.monotonic() - started
                    record["upstream_errors"] = [
                        e for e in gateway.errors if e["actor"].startswith(episode + ":")
                    ]
                    record["budget"] = budget.snapshot()
                    (run_dir / "result.json").write_text(json.dumps(record, indent=2))
                    results.append(record)
                    (output / "results.json").write_text(json.dumps(results, indent=2))
                    print(
                        json.dumps(
                            {
                                k: record.get(k)
                                for k in (
                                    "episode",
                                    "reward",
                                    "seconds",
                                    "error",
                                    "upstream_errors",
                                )
                            }
                        ),
                        flush=True,
                    )
                    # Stop on a configuration/access error instead of repeating paid failures.
                    if record["upstream_errors"]:
                        raise RuntimeError(
                            "model endpoint rejected a request; inspect pilot results"
                        )
    finally:
        (output / "budget.json").write_text(json.dumps(budget.snapshot(), indent=2))
        gateway.shutdown()
        gateway.server_close()
    return results
