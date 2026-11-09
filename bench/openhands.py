"""OpenHands event callback; also works offline against recorded SDK events."""

import json
import os
import urllib.error
import urllib.request
import uuid

from swarmfs.trails import normalize_path


class TrailClient:
    def __init__(self, url=None, token=None, post=None):
        self.url = url or os.environ.get("TRAIL_GATEWAY", "")
        self.token = token or os.environ.get("LLM_API_KEY", "")
        self.counts = {"deposits": 0, "errors": 0}
        self.post = post or self._post

    def _post(self, event):
        request = urllib.request.Request(
            self.url + "/events",
            data=json.dumps(event).encode(),
            headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=3) as response:
            response.read()

    def emit(self, event):
        try:
            self.post(event)
            self.counts["deposits"] += 1
        except (OSError, urllib.error.URLError):
            self.counts["errors"] += 1


class FileActivity:
    """Synchronous tool wrapper: publish intent before invoking the file executor."""

    def __init__(self, client=None):
        self.client = client or TrailClient()

    def run(self, action: dict, execute):
        observed = file_observation({**action, "kind": "FileEditorAction"}, {})
        # Excluded/out-of-repository paths still use the original tool normally.
        if observed is None:
            return execute()
        path, kind = observed
        identity = str(uuid.uuid4())
        event = {
            "action_id": identity,
            "path": path,
            "kind": kind,
            "intent": action["intent"],
            "note": action["intent_note"],
        }

        def mark(phase):
            self.client.emit({**event, "event_id": identity + ":" + phase, "phase": phase})

        mark("declared")
        try:
            result = execute()
        except Exception:
            mark("failed")
            raise
        mark("failed" if result.is_error else "succeeded")
        return result


class ActivityHook(TrailClient):
    """Legacy observation capture; intent-aware actions are recorded by the executor."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.pending = {}
        self.counts.update(actions=0, observations=0)

    def on_event(self, event):
        if event.get("kind") == "ActionEvent":
            self.counts["actions"] += 1
            action = event.get("action", {})
            if action.get("kind") != "TrailFileEditorAction":
                self.pending[event["id"]] = action
        elif event.get("kind") == "ObservationEvent":
            self.counts["observations"] += 1
            action = self.pending.pop(event.get("action_id"), {})
            observed = file_observation(action, event.get("observation", {}))
            if observed:
                path, kind = observed
                self.emit({"event_id": event["id"], "path": path, "kind": kind})


def file_observation(action: dict, observation: dict) -> tuple[str, str] | None:
    """Accept only completed, successful structured file-editor operations."""
    if observation.get("is_error") or observation.get("error"):
        return None
    if "fileeditor" not in str(action.get("kind", "")).lower().replace("_", ""):
        return None
    command = action.get("command")
    if command not in {"view", "create", "str_replace", "insert", "undo_edit"}:
        return None
    try:
        raw_path = action.get("path", "")
        path = normalize_path(raw_path.removeprefix("/workspace/repo/"))
    except (ValueError, TypeError):
        return None
    return path, "read" if command == "view" else "edit"
