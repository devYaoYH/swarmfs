"""Model-free integration checks inside the pinned OpenHands image.

Run with `python -m bench.sdk_check`; no pytest or provider credentials required.
"""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from openhands.sdk.event import ActionEvent, Event
from openhands.sdk.tool import Tool, resolve_tool
from pydantic import ValidationError

from bench.intent_editor import TrailFileEditorAction, TrailFileEditorTool
from bench.openhands import ActivityHook, FileActivity, TrailClient
from swarmfs import TrailStore


class SDKChecks(unittest.TestCase):
    def test_schema_requires_note_and_consistent_intent(self):
        schema = TrailFileEditorAction.model_json_schema()
        self.assertTrue({"intent", "intent_note"} <= set(schema["required"]))
        self.assertEqual(schema["properties"]["intent"]["enum"], ["read", "read_for_edit", "write"])
        for arguments in (
            {},
            {"intent": "write", "intent_note": "Inspect"},
            {"intent": "read", "intent_note": " "},
            {"intent": "read", "intent_note": "x" * 121},
        ):
            with self.assertRaises(ValidationError):
                TrailFileEditorAction(command="view", path="a.py", **arguments)

    def test_registered_tool_real_io_and_attributed_lifecycle(self):
        with tempfile.TemporaryDirectory(prefix="swarmfs-check-", dir="/workspace/repo") as folder:
            path = Path(folder) / "example.py"
            relative = str(path).removeprefix("/workspace/repo/")
            store = TrailStore(str(Path(folder) / "trails.db"))
            state = SimpleNamespace(
                workspace=SimpleNamespace(working_dir="/workspace/repo"),
                agent=SimpleNamespace(llm=SimpleNamespace(vision_is_active=lambda: False)),
            )
            tool = resolve_tool(Tool(name=TrailFileEditorTool.name), state)[0]
            self.assertIs(tool.action_type, TrailFileEditorAction)
            # Match the remote SDK's JSON serialization boundary.
            restored = TrailFileEditorTool.model_validate(tool.model_dump(mode="json"))
            self.assertIs(restored.action_type, TrailFileEditorAction)
            events = []

            def capture(event):
                store.deposit("pair", "pair:agent1", **event)
                events.append(event)
                if len(events) == 1:
                    self.assertFalse(path.exists())
                    peer = store.lookup("pair", "pair:agent2")[0]["contributors"][0]
                    self.assertEqual(peer["phase"], "declared")

            tool.executor.activity = FileActivity(TrailClient(post=capture))
            created = tool(
                tool.action_from_arguments(
                    {
                        "command": "create",
                        "path": str(path),
                        "file_text": "value = 1\n",
                        "intent": "write",
                        "intent_note": "Add example value",
                    }
                )
            )
            self.assertFalse(created.is_error)
            self.assertEqual(path.read_text(), "value = 1\n")
            viewed_action = tool.action_from_arguments(
                {
                    "command": "view",
                    "path": str(path),
                    "intent": "read_for_edit",
                    "intent_note": "Check value before changing it",
                }
            )
            self.assertEqual(viewed_action.model_dump()["kind"], "TrailFileEditorAction")
            action_event = ActionEvent(
                thought=[],
                action=viewed_action,
                tool_name=tool.name,
                tool_call_id="call-check",
                llm_response_id="mock-response",
                tool_call={
                    "id": "call-check",
                    "name": tool.name,
                    "arguments": json.dumps(viewed_action.model_dump()),
                    "origin": "completion",
                },
            )
            decoded = Event.model_validate_json(action_event.model_dump_json())
            self.assertIsInstance(decoded.action, TrailFileEditorAction)
            viewed = tool(viewed_action)
            self.assertFalse(viewed.is_error)
            self.assertIn("value = 1", viewed.text)
            failed = tool(
                tool.action_from_arguments(
                    {
                        "command": "str_replace",
                        "path": str(path),
                        "old_str": "missing",
                        "new_str": "value = 2",
                        "intent": "write",
                        "intent_note": "Change value",
                    }
                )
            )
            self.assertTrue(failed.is_error)
            self.assertEqual(
                [e["phase"] for e in events],
                [
                    "declared",
                    "succeeded",
                    "declared",
                    "succeeded",
                    "declared",
                    "failed",
                ],
            )
            rows = store.lookup("pair", "pair:agent2")
            self.assertEqual(sum(r["actions"] for r in rows), 3)
            self.assertTrue(all(r["path"] == relative and r["actors"] == 1 for r in rows))
            self.assertEqual(store.lookup("pair", "pair:agent1"), [])
            callback_events = []
            hook = ActivityHook(post=callback_events.append)
            hook.on_event({"kind": "ActionEvent", "id": "a", "action": viewed_action.model_dump()})
            hook.on_event(
                {
                    "kind": "ObservationEvent",
                    "action_id": "a",
                    "id": "o",
                    "observation": viewed.model_dump(),
                }
            )
            self.assertEqual(callback_events, [])


if __name__ == "__main__":
    unittest.main()
