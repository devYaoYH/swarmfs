import json
import threading

import httpx

from bench.budget import MODEL, Budget
from bench.gateway import Gateway
from swarmfs.trails import TrailStore


def test_offline_gateway_auth_routing_usage_and_model_guard(tmp_path):
    seen = []

    def upstream(request):
        seen.append(request)
        assert request.headers["authorization"] == "Bearer fake-key-never-live"
        assert json.loads(request.content)["reasoning_effort"] == "none"
        return httpx.Response(
            200,
            json={
                "id": "mock",
                "choices": [],
                "usage": {"prompt_tokens": 12, "completion_tokens": 4},
            },
        )

    budget = Budget(str(tmp_path / "budget.db"))
    service = Gateway(
        ("127.0.0.1", 0),
        trails=TrailStore(str(tmp_path / "trails.db")),
        budget=budget,
        key="fake-key-never-live",
        tokens={"a": "pair:a", "b": "pair:b"},
        upstream=httpx.Client(transport=httpx.MockTransport(upstream)),
    )
    thread = threading.Thread(target=service.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{service.server_port}", trust_env=False) as c:
            body = {"model": MODEL, "messages": [], "max_completion_tokens": 16}
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
                "model": MODEL,
                "messages": [],
                "max_completion_tokens": 16,
                "tools": [{"type": "function", "function": {"name": "test_tool"}}],
            }
            for _ in range(3):
                response = c.post(
                    "/v1/chat/completions", json=body, headers={"Authorization": "Bearer b"}
                )
                assert response.status_code == 200
            assert json.loads(seen[-2].content)["messages"] == []
            assert "src/b.py" in json.loads(seen[-1].content)["messages"][-1]["content"]
            with service.trails.connect() as db:
                assert db.execute("SELECT COUNT(*) FROM delivered").fetchone()[0] == 1
    finally:
        service.shutdown()
        service.server_close()
