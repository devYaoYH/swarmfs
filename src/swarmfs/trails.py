"""Observed activity only: no content summaries or inferred shell read sets."""

import math
import sqlite3
import time
from collections import defaultdict
from contextlib import closing, contextmanager
from pathlib import PurePosixPath

KINDS = {"read", "edit"}
EXCLUDED = {".git", ".venv", "node_modules", "__pycache__", ".cache", ".env"}


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

    @contextmanager
    def connect(self):
        with closing(sqlite3.connect(self.db_path, timeout=10)) as db, db:
            yield db

    def deposit(self, episode: str, actor: str, event_id: str, path: str, kind: str) -> bool:
        if kind not in KINDS:
            raise ValueError("unsupported activity kind")
        if not all(isinstance(v, str) and 0 < len(v) <= 200 for v in (episode, actor, event_id)):
            raise ValueError("invalid event identity")
        path = normalize_path(path)
        with self.connect() as db:
            inserted = db.execute(
                "INSERT OR IGNORE INTO events VALUES (?, ?, ?, ?, ?, ?)",
                (episode, actor, event_id, path, kind, self.clock()),
            ).rowcount
        return bool(inserted)

    def lookup(self, episode: str, actor: str, *, half_life: float = 300, limit: int = 3):
        if not math.isfinite(half_life) or half_life <= 0:
            raise ValueError("half-life must be finite and positive")
        now = self.clock()
        with self.connect() as db:
            rows = db.execute(
                "SELECT actor, path, kind, observed_at FROM events "
                "WHERE episode=? AND actor!=? AND observed_at>=? AND observed_at<=?",
                (episode, actor, now - 3600, now),
            ).fetchall()
        # Repeated reads by one actor in one minute contribute once, at the latest time.
        buckets = {}
        for author, path, kind, at in rows:
            key = (author, path, kind, int(at // 60))
            buckets[key] = max(buckets.get(key, at), at)
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
            }
            for path, kind in ranked[:limit]
        ]
