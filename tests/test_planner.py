import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from commerce.config import Settings
from commerce.planner import CodexPlanner, ModelUnavailable, strict_output_schema
from commerce.schemas import Intent


def test_strict_model_schema_requires_every_property():
    schema = strict_output_schema(Intent.model_json_schema())
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["additionalProperties"] is False
    assert "default" not in schema["properties"]["query"]
    assert {"type": "null"} in schema["properties"]["max_amount_minor"]["anyOf"]


def test_known_kiosk_alias_is_normalized_without_widening_scope():
    assert Intent(kiosk_id="Kiosk A").kiosk_id == "kiosk-a"
    assert Intent(kiosk_id="Kiosk B").kiosk_id == "kiosk-b"
    assert Intent(kiosk_id="attacker-site").kiosk_id == "attacker-site"


def test_codex_adapter_is_ephemeral_uses_stdin_and_disables_general_tools():
    settings = Settings(_env_file=None)

    def run(command, **kwargs):
        assert "--ephemeral" in command
        assert "--ignore-user-config" in command
        assert "features.shell_tool=false" in command
        assert "features.plugins=false" in command
        assert 'web_search="disabled"' in command
        assert command[-1] == "-"
        assert "untrusted shopping request" not in " ".join(command)
        payload = json.loads(kwargs["input"])
        assert payload["data"]["request"] == "untrusted shopping request"
        assert kwargs["timeout"] == 120
        path = Path(command[command.index("--output-last-message") + 1])
        assert path.parent == Path(kwargs["cwd"])
        path.write_text(
            json.dumps(Intent(category="protein-bar", max_amount_minor=400).model_dump())
        )
        return subprocess.CompletedProcess(
            command, 0, '{"type":"turn.completed","usage":{"input_tokens":10}}\n', ""
        )

    planner = CodexPlanner(settings)
    with patch("commerce.planner.subprocess.run", side_effect=run):
        assert planner.intent("untrusted shopping request").max_amount_minor == 400
        assert planner.last_usage["input_tokens"] == 10


@pytest.mark.parametrize("failure", ["timeout", "exit", "invalid", "tool"])
def test_codex_failure_never_becomes_a_valid_intent(failure):
    def run(command, **kwargs):
        if failure == "timeout":
            raise subprocess.TimeoutExpired(command, 120)
        path = Path(command[command.index("--output-last-message") + 1])
        if failure == "invalid":
            path.write_text('{"invented":"value"}')
        if failure == "tool":
            path.write_text(json.dumps(Intent(max_amount_minor=400).model_dump()))
        stdout = '{"item":{"type":"command_execution"}}\n' if failure == "tool" else ""
        return subprocess.CompletedProcess(
            command, 1 if failure == "exit" else 0, stdout, "private diagnostics"
        )

    with patch("commerce.planner.subprocess.run", side_effect=run), pytest.raises(ModelUnavailable):
        CodexPlanner(Settings(_env_file=None)).intent("Buy something")
