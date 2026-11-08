import json
import threading
from types import SimpleNamespace

import httpx

from bench.gateway import Gateway
from bench.llm import MODEL_ALIAS, ModelClient
from swarmfs.trails import TrailStore


def test_offline_gateway_auth_routing_usage_and_model_guard(tmp_path, make_budget, luna_config):
    seen = []

    def upstream(**request):
        seen.append(request)
        assert request["api_key"] == "fake-key-never-live"
        assert request["reasoning_effort"] == "none"
        if request["messages"] == [{"role": "user", "content": "fail"}]:
            raise RuntimeError("mock failure with fake-key-never-live")
        return SimpleNamespace(
            model_dump=lambda **_: {
                "id": "mock",
                "choices": [],
                "usage": {"prompt_tokens": 12, "completion_tokens": 4},
            }
        )

    budget = make_budget()
    service = Gateway(
        ("127.0.0.1", 0),
        trails=TrailStore(str(tmp_path / "trails.db")),
        budget=budget,
        llm=ModelClient(luna_config, "fake-key-never-live", completion=upstream),
        tokens={"a": "pair:a", "b": "pair:b"},
    )
    thread = threading.Thread(target=service.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{service.server_port}", trust_env=False) as c:
            body = {"model": MODEL_ALIAS, "messages": [], "max_completion_tokens": 16}
            assert c.post("/v1/chat/completions", json=body).status_code == 401
            response = c.post(
                "/v1/chat/completions", json=body, headers={"Authorization": "Bearer a"}
            )
            assert response.status_code == 200
            assert len(seen) == 1 and budget.snapshot()["agents"][0]["input_tokens"] == 12
            body["model"] = "forbidden"
            assert (
                c.post(
                    "/v1/chat/completions", json=body, headers={"Authorization": "Bearer a"}
                ).status_code
                == 400
            )
            assert len(seen) == 1
            event = {"event_id": "1", "path": "src/a.py", "kind": "edit"}
            assert c.post("/events", json=event, headers={"Authorization": "Bearer a"}).is_success
            reply = c.post("/trail", json={}, headers={"Authorization": "Bearer b"}).json()
            assert "src/a.py" in reply["block"]
            assert "fake-key-never-live" not in json.dumps(reply)
            # A new peer event may be injected only into the visible arm, at cadence.
            event.update(event_id="2", path="src/b.py")
            c.post("/events", json=event, headers={"Authorization": "Bearer a"})
            service.visible_actors.add("pair:b")
            body = {
                "model": MODEL_ALIAS,
                "messages": [],
                "max_completion_tokens": 16,
                "tools": [{"type": "function", "function": {"name": "test_tool"}}],
            }
            for _ in range(3):
                response = c.post(
                    "/v1/chat/completions", json=body, headers={"Authorization": "Bearer b"}
                )
                assert response.status_code == 200
            assert seen[-2]["messages"] == []
            assert "src/b.py" in seen[-1]["messages"][-1]["content"]
            with service.trails.connect() as db:
                assert db.execute("SELECT COUNT(*) FROM delivered").fetchone()[0] == 1
            failed = c.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer a"},
                json={
                    "model": MODEL_ALIAS,
                    "messages": [{"role": "user", "content": "fail"}],
                    "max_tokens": 16,
                },
            )
            assert failed.status_code == 502
            assert "fake-key-never-live" not in failed.text
            assert "[redacted]" in failed.text
            actors = {a["actor"]: a for a in budget.snapshot()["agents"]}
            assert actors["pair:a"]["unsettled_requests"] == 1
    finally:
        service.shutdown()
        service.server_close()
