"""Local trail service and model gateway. Credentials never enter task containers."""

import json
import secrets
import threading
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import httpx

from bench.budget import MODEL, Budget, BudgetExceeded
from bench.context import TrailPresenter
from swarmfs.trails import TrailStore


class Gateway(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address,
        *,
        trails: TrailStore,
        budget: Budget,
        key: str,
        tokens: dict[str, str],
        half_life: float = 300,
        upstream=None,
    ):
        self.trails, self.budget, self.key, self.tokens = trails, budget, key, tokens
        self.upstream = upstream or httpx.Client(timeout=180, trust_env=False)
        self.presenter = TrailPresenter(trails)
        self.half_life = half_life
        self.visible_actors = set()
        self.calls = defaultdict(int)
        self.call_lock = threading.Lock()
        self.errors = []
        with trails.connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS delivered (actor TEXT, request_id TEXT, body TEXT)"
            )
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass  # Never log model request bodies or credentials.

    def reply(self, status: int, value: dict):
        data = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        auth = self.headers.get("Authorization", "").removeprefix("Bearer ")
        actor = self.server.tokens.get(auth)
        if actor is None:
            self.reply(401, {"error": {"message": "invalid pilot token", "type": "auth"}})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 750_000:
                raise ValueError("invalid request length")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("JSON object required")
            route = urlsplit(self.path).path
            if route == "/events":
                episode = actor.rsplit(":", 1)[0]
                inserted = self.server.trails.deposit(
                    episode,
                    actor,
                    payload["event_id"],
                    payload["path"],
                    payload["kind"],
                )
                self.reply(200, {"inserted": inserted})
            elif route == "/trail":
                episode = actor.rsplit(":", 1)[0]
                block = self.server.presenter.block(episode, actor, half_life=self.server.half_life)
                self.reply(200, {"block": block})
            elif route in {"/v1/chat/completions", "/v1/responses"}:
                self.model_request(actor, route, payload)
            else:
                self.reply(404, {"error": {"message": "unsupported route"}})
        except BudgetExceeded as exc:
            self.reply(402, {"error": {"message": str(exc), "type": "pilot_budget"}})
        except (ValueError, KeyError, TypeError) as exc:
            self.reply(400, {"error": {"message": str(exc), "type": "invalid_request"}})
        except httpx.HTTPError:
            self.reply(502, {"error": {"message": "upstream transport failed; reservation kept"}})

    def model_request(self, actor: str, route: str, payload: dict):
        if payload.get("stream"):
            raise ValueError("pilot gateway requires non-streaming model requests")
        payload["model"] = payload.get("model", "").removeprefix("openai/")
        if payload["model"] != MODEL:
            raise ValueError("model differs from the requested gpt-6-luna")
        if route.endswith("chat/completions"):
            # This pinned SDK omits "none" for models absent from its model table.
            # Enforce the endpoint-compatible setting at the final request boundary.
            payload["reasoning_effort"] = "none"
        block = ""
        with self.server.call_lock:
            self.server.calls[actor] += 1
            due = self.server.calls[actor] % 3 == 0
        # Inject at the request boundary, preserving the SDK's tool output.
        # Separate delivery records capture context absent from native SDK logs.
        if actor in self.server.visible_actors and due and payload.get("tools"):
            block = self.server.presenter.block(
                actor.rsplit(":", 1)[0], actor, half_life=self.server.half_life
            )
            if block:
                if route.endswith("chat/completions"):
                    payload["messages"].append({"role": "user", "content": block})
                elif isinstance(payload.get("input"), list):
                    payload["input"].append({"role": "user", "content": block})
                else:
                    block = ""
        identity = self.server.budget.reserve(actor, payload)
        response = self.server.upstream.post(
            "https://api.openai.com" + route,
            headers={"Authorization": "Bearer " + self.server.key},
            json=payload,
        )
        if not response.is_success:
            # An API rejection is not a completed generation. Keep its reservation
            # conservatively and return only status, never arbitrary upstream details.
            try:
                message = str(response.json().get("error", {}).get("message", "rejected"))
            except ValueError:
                message = "rejected"
            message = message.replace(self.server.key, "[redacted]")[:400]
            self.server.errors.append(
                {"actor": actor, "status": response.status_code, "message": message}
            )
            self.reply(
                response.status_code, {"error": {"message": message, "type": "upstream_error"}}
            )
            return
        data = response.json()
        self.server.budget.settle(identity, data)
        if block:
            with self.server.trails.connect() as db:
                db.execute("INSERT INTO delivered VALUES (?, ?, ?)", (actor, identity, block))
        self.reply(200, data)


def new_token() -> str:
    return secrets.token_urlsafe(24)
