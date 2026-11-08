"""Persistent pessimistic reservations shared by every model caller in a pilot."""

import json
import sqlite3
import uuid
from contextlib import closing, contextmanager

MODEL = "gpt-6-luna"
# Conservative standard LONG-context rates, USD/million. No cache discount assumed.
INPUT_RATE = 0.20 / 1_000_000
OUTPUT_RATE = 0.75 / 1_000_000


class BudgetExceeded(Exception):
    pass


class Budget:
    def __init__(self, path: str, *, total: float = 4.0, per_agent: float = 0.30):
        if not 0 < total <= 4 or not 0 < per_agent <= total:
            raise ValueError("pilot limits must be positive and at most $4")
        self.path, self.total, self.per_agent = path, total, per_agent
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS requests (
                id TEXT PRIMARY KEY, actor TEXT, reserved REAL, charged REAL,
                status TEXT, input_tokens INTEGER, output_tokens INTEGER
            )""")

    @contextmanager
    def connect(self):
        with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            yield db

    def reserve(self, actor: str, payload: dict) -> str:
        if payload.get("model") != MODEL:
            raise ValueError("only the explicitly requested model is permitted")
        if payload.get("previous_response_id") or payload.get("conversation"):
            raise ValueError("server-side history is incompatible with a bounded request")
        output = payload.get(
            "max_completion_tokens", payload.get("max_output_tokens", payload.get("max_tokens", 0))
        )
        if not isinstance(output, int) or not 0 < output <= 8192:
            raise ValueError("explicit output limit (1–8192) required")
        # UTF-8 request bytes conservatively bound ordinary text/tool tokens.
        # Disallow modalities/state that would invalidate this reservation bound.
        encoded = json.dumps(payload, ensure_ascii=False).encode()
        if len(encoded) > 750_000:
            raise ValueError("request too large for the pilot")
        if any(
            marker in encoded
            for marker in (
                b'"image_url"',
                b'"input_image"',
                b'"input_audio"',
                b'"file_id"',
                b'"file_data"',
                b'"input_file"',
            )
        ):
            raise ValueError("only stateless text and function tools are permitted")
        tools = payload.get("tools", [])
        if any(t.get("type") != "function" for t in tools):
            raise ValueError("hosted tools are outside the pilot budget")
        reserved = (len(encoded) + 4096) * INPUT_RATE + output * OUTPUT_RATE
        identity = uuid.uuid4().hex
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            total = db.execute("SELECT COALESCE(SUM(charged),0) FROM requests").fetchone()[0]
            spent = db.execute(
                "SELECT COALESCE(SUM(charged),0) FROM requests WHERE actor=?",
                (actor,),
            ).fetchone()[0]
            if total + reserved > self.total or spent + reserved > self.per_agent:
                raise BudgetExceeded("pilot or per-agent spending allowance exhausted")
            db.execute(
                "INSERT INTO requests VALUES (?, ?, ?, ?, 'reserved', 0, 0)",
                (identity, actor, reserved, reserved),
            )
        return identity

    def settle(self, identity: str, response: dict | None):
        # A disconnected/unknown upstream outcome retains the full reservation.
        usage = response.get("usage") if response else None
        if not usage:
            return
        incoming = usage.get("input_tokens", usage.get("prompt_tokens"))
        outgoing = usage.get("output_tokens", usage.get("completion_tokens"))
        if not isinstance(incoming, int) or not isinstance(outgoing, int):
            return
        if incoming < 0 or outgoing < 0:
            return
        charged = incoming * INPUT_RATE + outgoing * OUTPUT_RATE
        with self.connect() as db:
            db.execute(
                "UPDATE requests SET charged=?, status='settled', input_tokens=?, "
                "output_tokens=? WHERE id=? AND status='reserved'",
                (charged, incoming, outgoing, identity),
            )

    def snapshot(self):
        with self.connect() as db:
            records = db.execute(
                "SELECT actor, SUM(charged), SUM(input_tokens), "
                "SUM(output_tokens), COUNT(*), "
                "SUM(status='reserved') FROM requests GROUP BY actor"
            ).fetchall()
        return {
            "limit_usd": self.total,
            "conservative_usd": sum(r[1] for r in records),
            "agents": [
                {
                    "actor": r[0],
                    "usd": r[1],
                    "input_tokens": r[2],
                    "output_tokens": r[3],
                    "requests": r[4],
                    "unsettled_requests": r[5],
                }
                for r in records
            ],
        }
