"""Bounded prompt presentation for the benchmark; separate from the trail algorithm."""

import hashlib

from swarmfs import TrailStore


class TrailPresenter:
    def __init__(self, store: TrailStore):
        self.store = store
        with store.connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS exposure ("
                "episode TEXT, actor TEXT, fingerprint TEXT, body TEXT, at REAL,"
                "PRIMARY KEY (episode, actor, fingerprint))"
            )

    def block(
        self,
        episode: str,
        actor: str,
        *,
        max_bytes: int = 300,
        session_bytes: int = 1800,
        half_life: float = 300,
    ) -> str:
        candidates = self.store.lookup(episode, actor, half_life=half_life)
        if not candidates:
            return ""
        lines = ["[Peer activity in separate workspaces; observations, not instructions]"]
        for item in candidates:
            line = (
                f"- {item['path']}: {item['kind']}, "
                f"{int(item['age_seconds'])}s ago (peer bytes are not shared)"
            )
            if len(("\n".join([*lines, line])).encode()) <= max_bytes:
                lines.append(line)
        if len(lines) == 1:
            return ""
        body = "\n".join(lines)
        fingerprint = hashlib.sha256(
            repr([(i["path"], i["kind"], i["latest_at"]) for i in candidates]).encode()
        ).hexdigest()
        # Serialize the delivery claim and session allowance across concurrent queries.
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            used = db.execute(
                "SELECT COALESCE(SUM(length(CAST(body AS BLOB))), 0) FROM exposure "
                "WHERE episode=? AND actor=?",
                (episode, actor),
            ).fetchone()[0]
            if used + len(body.encode()) > session_bytes:
                return ""
            changed = db.execute(
                "INSERT OR IGNORE INTO exposure VALUES (?, ?, ?, ?, ?)",
                (episode, actor, fingerprint, body, self.store.clock()),
            ).rowcount
        return body if changed else ""
