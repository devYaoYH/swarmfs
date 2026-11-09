"""Decaying file activity: declared intent and linked execution outcomes."""

import math
import sqlite3
import time
from collections import defaultdict
from contextlib import closing, contextmanager
from pathlib import PurePosixPath

KINDS = {"read", "edit"}
INTENTS = {"read", "read_for_edit", "write"}
PHASES = {"declared", "succeeded", "failed", "observed"}
EXCLUDED = {".git", ".venv", "node_modules", "__pycache__", ".cache", ".env"}


def normalize_note(note: str) -> str:
    if not isinstance(note, str):
        raise ValueError("intent note must be text")
    note = " ".join(note.split())
    if len(note) > 120 or any(ord(c) < 32 or 127 <= ord(c) < 160 for c in note):
        raise ValueError("intent note must be at most 120 characters without controls")
    return note


def normalize_path(path: str) -> str:
    if not path or len(path) > 240 or any(ord(c) < 32 for c in path):
        raise ValueError("invalid repository path")
    parts = PurePosixPath(path).parts
    if path.startswith("/") or ".." in parts or not parts:
        raise ValueError("path must stay inside repository")
    if any(p in EXCLUDED or p.startswith(".env.") for p in parts):
        raise ValueError("excluded path")
    return str(PurePosixPath(path))


class TrailStore:
    def __init__(self, db_path: str, *, clock=time.time):
        self.db_path = db_path
        self.clock = clock
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS events (
                    episode TEXT, actor TEXT, event_id TEXT, path TEXT, kind TEXT,
                    observed_at REAL, PRIMARY KEY (episode, actor, event_id)
                );
                CREATE INDEX IF NOT EXISTS episode_time ON events(episode, observed_at);
            """)
            # Keep existing pilot databases readable; old rows remain observations.
            columns = {row[1] for row in db.execute("PRAGMA table_info(events)")}
            for name, definition in {
                "action_id": "TEXT",
                "intent": "TEXT",
                "note": "TEXT NOT NULL DEFAULT ''",
                "phase": "TEXT NOT NULL DEFAULT 'observed'",
            }.items():
                if name not in columns:
                    db.execute(f"ALTER TABLE events ADD COLUMN {name} {definition}")

    @contextmanager
    def connect(self):
        with closing(sqlite3.connect(self.db_path, timeout=10)) as db, db:
            yield db

    def deposit(
        self,
        episode: str,
        actor: str,
        event_id: str,
        path: str,
        kind: str,
        *,
        action_id: str | None = None,
        intent: str | None = None,
        note: str = "",
        phase: str = "observed",
    ) -> bool:
        if kind not in KINDS:
            raise ValueError("unsupported activity kind")
        if not all(
            isinstance(v, str) and 0 < len(v) <= 200 and not any(ord(c) < 32 for c in v)
            for v in (episode, actor, event_id, action_id or event_id)
        ):
            raise ValueError("invalid event identity")
        intent = intent or ("read" if kind == "read" else "write")
        if intent not in INTENTS or (kind == "edit") != (intent == "write"):
            raise ValueError("intent must match the file operation")
        if phase not in PHASES:
            raise ValueError("unsupported activity phase")
        note = normalize_note(note)
        if phase != "observed" and (not action_id or not note):
            raise ValueError("declared actions and outcomes require an action ID and note")
        path = normalize_path(path)
        with self.connect() as db:
            inserted = db.execute(
                "INSERT OR IGNORE INTO events "
                "(episode, actor, event_id, path, kind, observed_at, "
                "action_id, intent, note, phase) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    episode,
                    actor,
                    event_id,
                    path,
                    kind,
                    self.clock(),
                    action_id,
                    intent,
                    note,
                    phase,
                ),
            ).rowcount
        return bool(inserted)

    def lookup(self, episode: str, actor: str, *, half_life: float = 300, limit: int = 3):
        if not math.isfinite(half_life) or half_life <= 0:
            raise ValueError("half-life must be finite and positive")
        now = self.clock()
        with self.connect() as db:
            rows = db.execute(
                "SELECT actor, path, kind, observed_at, COALESCE(action_id, event_id), "
                "intent, note, phase FROM events "
                "WHERE episode=? AND actor!=? AND observed_at>=? AND observed_at<=?",
                (episode, actor, now - 3600, now),
            ).fetchall()
        # A declaration and its outcome describe ONE action. A late declaration
        # cannot turn a completed/failed action back into a pending intention.
        actions = {}
        for author, path, kind, at, action_id, intent, note, phase in rows:
            key = (author, action_id)
            rank = (phase != "declared", at)
            if key not in actions or rank > actions[key][0]:
                actions[key] = (rank, path, kind, at, intent, note, phase)
        buckets = {}
        contributors = defaultdict(dict)
        for (author, _), (_, path, kind, at, intent, note, phase) in actions.items():
            key = (author, path, kind, int(at // 60))
            buckets[key] = max(buckets.get(key, at), at)
            peers = contributors[(path, kind)]
            previous = peers.get(author)
            count = previous["actions"] + 1 if previous else 1
            if previous is None or at > previous["latest_at"]:
                peers[author] = {
                    "actor": author,
                    "actions": count,
                    "latest_at": at,
                    "age_seconds": now - at,
                    "intent": intent or ("read" if kind == "read" else "write"),
                    "note": note,
                    "phase": phase,
                }
            else:
                previous["actions"] = count
        per_actor = defaultdict(float)
        latest = defaultdict(float)
        authors = defaultdict(set)
        for (author, path, kind, _), at in buckets.items():
            per_actor[(author, path, kind)] += 2 ** (-(now - at) / half_life)
            latest[(path, kind)] = max(latest[(path, kind)], at)
            authors[(path, kind)].add(author)
        scores = defaultdict(float)
        for (_, path, kind), score in per_actor.items():
            scores[(path, kind)] += min(score, 3.0)
        ranked = sorted(scores, key=lambda key: (-scores[key], key))
        return [
            {
                "path": path,
                "kind": kind,
                "score": scores[(path, kind)],
                "age_seconds": now - latest[(path, kind)],
                "latest_at": latest[(path, kind)],
                "actors": len(authors[(path, kind)]),
                "actions": sum(p["actions"] for p in contributors[(path, kind)].values()),
                "contributors": sorted(
                    contributors[(path, kind)].values(),
                    key=lambda p: (-p["latest_at"], p["actor"]),
                ),
            }
            for path, kind in ranked[:limit]
        ]
