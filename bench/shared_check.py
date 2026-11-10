"""Run two real SDK sidecars against scripted replies; never read provider keys."""

import json
import os
import shlex
import shutil
import subprocess
import threading
import time
import uuid
from types import SimpleNamespace

from bench.budget import Budget
from bench.gateway import Gateway, new_token
from bench.llm import ModelClient, ModelConfig
from bench.pilot import ARTIFACTS, command, compose_file, prepare, task_runtime, workspace_mode
from swarmfs import TrailStore

PROBE = "/workspace/repo/src/swarmfs_shared_probe.py"


def wait_for(condition):
    code = (
        "from pathlib import Path\nimport time\n"
        f"p = Path({PROBE!r})\n"
        "deadline = time.monotonic() + 45\n"
        f"while not ({condition}):\n"
        "    assert time.monotonic() < deadline, 'peer edit not visible'\n"
        "    time.sleep(0.1)\n"
        "print(p.read_text())\n"
    )
    return "terminal", {"command": "python3 -c " + shlex.quote(code)}


def scripted_client(*, solo=False, feature_ids=()):
    view = {"command": "view", "path": PROBE, "intent": "read", "intent_note": "Read peer edit"}
    scripts = {
        "agent1": [
            (
                "trail_file_editor",
                {
                    "command": "create",
                    "path": PROBE,
                    "file_text": "first = 1\n",
                    "intent": "write",
                    "intent_note": "Create shared probe",
                },
            ),
            wait_for("p.exists() and 'second = 2' in p.read_text()"),
            ("trail_file_editor", view),
            ("finish", {"message": "Observed agent2's edit in the shared file."}),
        ],
        "agent2": [
            wait_for("p.exists()"),
            ("trail_file_editor", view),
            (
                "trail_file_editor",
                {
                    "command": "str_replace",
                    "path": PROBE,
                    "old_str": "first = 1",
                    "new_str": "first = 1\nsecond = 2",
                    "intent": "write",
                    "intent_note": "Extend peer's shared probe",
                },
            ),
            ("finish", {"message": "Read and extended agent1's shared file."}),
        ],
    }
    if solo:
        scripts = {
            "agent1": [
                scripts["agent1"][0],
                scripts["agent2"][2],
                scripts["agent1"][2],
                ("finish", {"message": "Both changes done."}),
            ]
        }
    calls = {a: 0 for a in scripts}

    def completion(**request):
        system = json.dumps([m for m in request["messages"] if m["role"] == "system"])
        actor = "agent1" if solo else next(a for a in scripts if f"You are {a} " in system)
        assert "separate, isolated workspaces" not in system
        if solo:
            assert "ONE SHARED working tree" not in system
            names = {t["function"]["name"] for t in request.get("tools", [])}
            assert not names & {"send_message", "receive_message"}
            prompt = json.dumps(request["messages"])
            assert all(f"## Feature {i}" in prompt for i in feature_ids)
        else:
            assert "ONE SHARED working tree" in system
        step = calls[actor]
        name, arguments = scripts[actor][step]
        calls[actor] += 1
        response = {
            "id": f"mock-{actor}-{step}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": "swarmfs-bench",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": f"call-{actor}-{step}",
                                "type": "function",
                                "function": {"name": name, "arguments": json.dumps(arguments)},
                            }
                        ],
                    },
                }
            ],
            "usage": {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16},
        }
        return SimpleNamespace(model_dump=lambda **_: response)

    settings = ModelConfig("openai/shared-check", "UNUSED_OFFLINE_KEY", 0.006, 0.50)
    return ModelClient(settings, "scripted-no-provider-key", completion=completion), calls


def shared_check(cfg):
    if workspace_mode(cfg) != "shared":
        raise ValueError("shared-check requires workspace_mode = shared")
    source = prepare(cfg)[0]
    output = ARTIFACTS / "shared-check" / uuid.uuid4().hex
    task = output / "task"
    shutil.copytree(source, task)
    solo = cfg.get("arms") == ["solo"]
    names = ("agent1",) if solo else ("agent1", "agent2")
    if not solo:
        for actor in names:
            (task / "environment" / actor / "instruction.md").write_text(
                "Offline shared-file validation. Follow the scripted tool calls."
            )
    client, calls = scripted_client(solo=solo, feature_ids=cfg["pairs"][0]["features"])
    budget = Budget(
        str(output / "mock-budget.db"),
        model=client.config.model,
        input_usd_per_million=0.006,
        output_usd_per_million=0.50,
        total=1,
        per_agent=0.50,
        provider_max_output_tokens=8192,
    )
    actors = {a: new_token() for a in names}
    gateway = Gateway(
        ("0.0.0.0", 0),
        trails=TrailStore(str(output / "trails.db")),
        budget=budget,
        llm=client,
        tokens={token: "check:" + a for a, token in actors.items()},
        workspace_mode="shared",
    )
    if not solo:
        gateway.visible_actors.update(gateway.tokens.values())
    threading.Thread(target=gateway.serve_forever, daemon=True).start()
    cfg = {**cfg, "max_iterations": 12, "solo_max_iterations": 12, "agent_timeout_seconds": 120}
    path = compose_file(
        task,
        output,
        actors=actors,
        port=gateway.server_port,
        cfg=cfg,
        arm="solo" if solo else "trails",
    )
    base = ["docker", "compose", "-p", f"swarm-shared-check-{os.getpid()}", "-f", str(path)]
    try:
        command([*base, "up", "-d"], log=output / "startup.log")
        for actor in actors:
            container = command([*base, "ps", "-aq", actor]).strip()
            command(["docker", "wait", container], timeout=300, log=output / f"{actor}-wait.log")
            destination = output / actor
            destination.mkdir()
            command([*base, "cp", f"{actor}:/agent_output/.", str(destination)])
            events = [
                json.loads(p.read_text()) for p in (destination / "logs/events").glob("*.json")
            ]
            assert any(e.get("tool_name") == "finish" for e in events), f"{actor} did not finish"
            assert not any(e.get("observation", {}).get("is_error") for e in events)
            assert list((destination / "sdk/conversations").iterdir()), "missing private SDK state"
            assert not (destination / "agent.patch").exists(), "agent staged a separate patch"
        # The verifier's read-only view must contain both writes, and its own Git
        # index must capture them without including either agent's private SDK state.
        code = (
            "from pathlib import Path\nfrom bench.shared import snapshot\n"
            "p = Path('/shared-workspace/src/swarmfs_shared_probe.py')\n"
            "assert p.read_text() == 'first = 1\\nsecond = 2\\n'\n"
            "assert not Path('/shared-workspace/workspace/conversations').exists()\n"
            "patch = snapshot(Path('/shared-workspace'), Path('/workspace/repo'), "
            f"{task_runtime(task, cfg)['base_commit']!r})\n"
            "assert b'+first = 1' in patch and b'+second = 2' in patch\n"
            "assert b'conversations/' not in patch and b'bash_events/' not in patch\n"
            "Path('/logs/verifier/final.patch').write_bytes(patch)\n"
        )
        command([*base, "exec", "-T", "main", "python3", "-c", code], log=output / "snapshot.log")
        assert calls == dict.fromkeys(names, 4), calls
        assert not gateway.errors, gateway.errors
        result = {
            "passed": True,
            "model_calls": 0,
            "agent_count": len(names),
            "scripted_replies": calls,
            "shared_file_roundtrip": True,
            "private_sdk_state": True,
            "single_snapshot": True,
            "output": str(output),
        }
        (output / "result.json").write_text(json.dumps(result, indent=2))
        return result
    finally:
        subprocess.run(
            [*base, "logs", "--no-color"],
            stdout=(output / "containers.log").open("w"),
            stderr=subprocess.STDOUT,
            timeout=60,
        )
        subprocess.run([*base, "down", "-v"], capture_output=True, timeout=120)
        gateway.shutdown()
        gateway.server_close()
