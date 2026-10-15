"""Reading the lab's voice session from an exported file."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ratel_link.domain.subscriber import VoiceTemplateError
from ratel_link.repositories.voice_template import FileVoiceTemplate
from tests.synthetic import SYNTHETIC_IMS_SESSION


def _write(tmp_path: Path, document: Any, name: str = "template.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(document) if not isinstance(document, str) else document)
    return path


def _export() -> dict[str, Any]:
    return {
        "imsi": "621000000000099",
        "security": {"k": "LEFT-IN-BY-MISTAKE", "opc": "LEFT-IN-BY-MISTAKE"},
        "slice": [{"session": [{"name": "internet", "type": 3}, SYNTHETIC_IMS_SESSION]}],
    }


def test_no_file_configured_means_no_template() -> None:
    assert FileVoiceTemplate(None).ims_session() is None


def test_the_ims_session_is_read_from_the_file(tmp_path: Path) -> None:
    ims = FileVoiceTemplate(_write(tmp_path, _export())).ims_session()
    assert ims is not None and ims["name"] == "ims"
    assert ims["pcc_rule"] == SYNTHETIC_IMS_SESSION["pcc_rule"]
    assert "ue" not in ims


def test_mongosh_extended_json_numbers_are_read_as_integers(tmp_path: Path) -> None:
    export = _export()
    export["slice"][0]["session"][1] = {
        "name": "ims",
        "type": {"$numberInt": "1"},
        "qos": {"index": {"$numberInt": "5"}},
        "pcc_rule": [{"qos": {"index": {"$numberInt": "1"}}}],
    }
    ims = FileVoiceTemplate(_write(tmp_path, export)).ims_session()
    assert ims is not None
    assert ims["type"] == 1 and type(ims["type"]) is int
    assert ims["pcc_rule"][0]["qos"]["index"] == 1


def test_keys_left_in_the_file_are_never_returned(tmp_path: Path) -> None:
    ims = FileVoiceTemplate(_write(tmp_path, _export())).ims_session()
    assert "LEFT-IN-BY-MISTAKE" not in repr(ims)


def test_each_call_returns_a_copy(tmp_path: Path) -> None:
    template = FileVoiceTemplate(_write(tmp_path, _export()))
    first = template.ims_session()
    assert first is not None
    first["pcc_rule"].clear()
    second = template.ims_session()
    assert second is not None and second["pcc_rule"] != []


def test_a_missing_file_is_an_error_that_does_not_name_the_path(tmp_path: Path) -> None:
    secret_looking = tmp_path / "very-private-folder" / "t.json"
    with pytest.raises(VoiceTemplateError) as caught:
        FileVoiceTemplate(secret_looking).ims_session()
    assert "very-private-folder" not in str(caught.value)


@pytest.mark.parametrize("content", ["", "not json", "[1, 2]", '"text"', "null", "{"])
def test_a_file_that_is_not_a_document_is_an_error(tmp_path: Path, content: str) -> None:
    with pytest.raises(VoiceTemplateError):
        FileVoiceTemplate(_write(tmp_path, content)).ims_session()


def test_a_document_without_an_ims_session_is_an_error(tmp_path: Path) -> None:
    export = _export()
    export["slice"][0]["session"] = [{"name": "internet"}]
    with pytest.raises(VoiceTemplateError):
        FileVoiceTemplate(_write(tmp_path, export)).ims_session()


def test_an_error_message_never_contains_file_content(tmp_path: Path) -> None:
    path = _write(tmp_path, '{"security": {"k": "LEFT-IN-BY-MISTAKE"} nope')
    with pytest.raises(VoiceTemplateError) as caught:
        FileVoiceTemplate(path).ims_session()
    assert "LEFT-IN-BY-MISTAKE" not in str(caught.value)
