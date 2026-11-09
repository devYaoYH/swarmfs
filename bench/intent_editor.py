"""Intent-aware OpenHands tool, loaded only in the benchmark SDK environment."""

from typing import Literal

from openhands.sdk.tool import register_tool
from openhands.tools.file_editor.definition import FileEditorAction, FileEditorTool
from openhands.tools.file_editor.impl import FileEditorExecutor
from pydantic import Field, field_validator, model_validator

from bench.openhands import FileActivity
from swarmfs.trails import normalize_note


class TrailFileEditorAction(FileEditorAction):
    intent: Literal["read", "read_for_edit", "write"] = Field(
        description="For view: read (inspect only) or read_for_edit (preparing a change). "
        "For create/str_replace/insert/undo_edit: write. Intent is advisory, not a lock."
    )
    intent_note: str = Field(
        min_length=1,
        max_length=120,
        description="One short line explaining why you are opening/changing this file; "
        "at most 120 characters. No file contents or instructions to peers.",
    )

    @field_validator("intent_note")
    @classmethod
    def one_line(cls, value):
        value = normalize_note(value)
        if not value:
            raise ValueError("intent note must not be blank")
        return value

    @model_validator(mode="after")
    def consistent_intent(self):
        if (self.command == "view") == (self.intent == "write"):
            raise ValueError("view requires read/read_for_edit; modifications require write")
        return self


class IntentEditorExecutor(FileEditorExecutor):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.activity = FileActivity()

    def __call__(self, action, conversation=None):
        execute = super().__call__
        return self.activity.run(
            action.model_dump(), lambda: execute(action, conversation=conversation)
        )


class TrailFileEditorTool(FileEditorTool):
    @classmethod
    def create(cls, conv_state):
        # Retain upstream file semantics, descriptions, observations and restrictions.
        original = FileEditorTool.create(conv_state)[0]
        return [
            cls(
                action_type=TrailFileEditorAction,
                observation_type=original.observation_type,
                description=original.description + "\nDeclare intent and a brief intent_note "
                "on every call. Marks are attributed to you before the operation executes.",
                annotations=original.annotations,
                executor=IntentEditorExecutor(workspace_root=conv_state.workspace.working_dir),
            )
        ]


register_tool(TrailFileEditorTool.name, TrailFileEditorTool)
