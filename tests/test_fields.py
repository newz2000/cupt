import json
from unittest.mock import MagicMock, patch

from cupt.errors import EXIT_API, EXIT_INVALID_INPUT
from cupt.exceptions import APIError
from cupt.fields import field_group
from cupt.services.field_service import FieldService


def _ctx(mock_config, mock_client, team_id="team1"):
    return (mock_config, mock_client, team_id)


def _task():
    return {
        "id": "t1",
        "custom_fields": [
            {"id": "f-text", "name": "Notes", "type": "text", "value": "hello"},
            {"id": "f-num", "name": "Size", "type": "number", "value": None},
            {
                "id": "f-drop",
                "name": "Release group",
                "type": "drop_down",
                "type_config": {
                    "options": [
                        {"id": "opt-1", "name": "Alpha"},
                        {"id": "opt-2", "name": "Beta"},
                    ]
                },
                "value": "opt-2",
            },
            {"id": "f-check", "name": "Done?", "type": "checkbox", "value": None},
        ],
    }


def test_field_list_human(runner, mock_config, mock_client):
    mock_client.get_task.return_value = _task()
    with patch(
        "cupt.fields.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        result = runner.invoke(field_group, ["list", "t1"])
        assert result.exit_code == 0
        assert "Notes" in result.output
        assert "hello" in result.output
        assert "Release group" in result.output
        # Dropdown must render the option NAME, never the uuid.
        assert "Beta" in result.output
        assert "opt-2" not in result.output


def test_field_list_json(runner, mock_config, mock_client):
    mock_client.get_task.return_value = _task()
    with patch(
        "cupt.fields.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        result = runner.invoke(field_group, ["list", "t1", "--json"])
        assert result.exit_code == 0
        fields = json.loads(result.output)
        assert fields == [
            {"id": "f-text", "name": "Notes", "type": "text", "value": "hello"},
            {"id": "f-num", "name": "Size", "type": "number", "value": None},
            {
                "id": "f-drop",
                "name": "Release group",
                "type": "drop_down",
                "value": "Beta",
            },
            {"id": "f-check", "name": "Done?", "type": "checkbox", "value": None},
        ]


def test_field_set_text(runner, mock_config, mock_client):
    mock_client.get_task.return_value = _task()
    with patch(
        "cupt.fields.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        result = runner.invoke(field_group, ["set", "t1", "Notes", "hi there"])
        assert result.exit_code == 0
        mock_client.set_task_custom_field.assert_called_once_with(
            "t1", "f-text", "hi there"
        )
        assert "Notes" in result.output


def test_field_set_number(runner, mock_config, mock_client):
    mock_client.get_task.return_value = _task()
    with patch(
        "cupt.fields.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        result = runner.invoke(field_group, ["set", "t1", "Size", "3"])
        assert result.exit_code == 0
        mock_client.set_task_custom_field.assert_called_once_with("t1", "f-num", 3)


def test_field_set_number_float(runner, mock_config, mock_client):
    mock_client.get_task.return_value = _task()
    with patch(
        "cupt.fields.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        result = runner.invoke(field_group, ["set", "t1", "Size", "2.5"])
        assert result.exit_code == 0
        mock_client.set_task_custom_field.assert_called_once_with("t1", "f-num", 2.5)


def test_field_set_number_invalid(runner, mock_config, mock_client):
    mock_client.get_task.return_value = _task()
    with patch(
        "cupt.fields.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        result = runner.invoke(field_group, ["set", "t1", "Size", "abc"])
        assert result.exit_code == EXIT_INVALID_INPUT
        mock_client.set_task_custom_field.assert_not_called()


def test_field_set_checkbox(runner, mock_config, mock_client):
    mock_client.get_task.return_value = _task()
    with patch(
        "cupt.fields.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        result = runner.invoke(field_group, ["set", "t1", "Done?", "yes"])
        assert result.exit_code == 0
        mock_client.set_task_custom_field.assert_called_once_with("t1", "f-check", True)


def test_field_set_dropdown(runner, mock_config, mock_client):
    mock_client.get_task.return_value = _task()
    with patch(
        "cupt.fields.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        result = runner.invoke(field_group, ["set", "t1", "Release group", "alpha"])
        assert result.exit_code == 0
        # The uuid of the matched option must be sent, never the raw string.
        mock_client.set_task_custom_field.assert_called_once_with(
            "t1", "f-drop", "opt-1"
        )
        assert "Alpha" in result.output


def test_field_set_unknown_field(runner, mock_config, mock_client):
    mock_client.get_task.return_value = _task()
    with patch(
        "cupt.fields.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        result = runner.invoke(field_group, ["set", "t1", "Nonexistent", "x"])
        assert result.exit_code == EXIT_INVALID_INPUT
        assert "Nonexistent" in result.output
        for name in ("Notes", "Size", "Release group", "Done?"):
            assert name in result.output
        mock_client.set_task_custom_field.assert_not_called()


def test_field_set_unknown_dropdown_option(runner, mock_config, mock_client):
    mock_client.get_task.return_value = _task()
    with patch(
        "cupt.fields.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        result = runner.invoke(field_group, ["set", "t1", "Release group", "Gamma"])
        assert result.exit_code == EXIT_INVALID_INPUT
        assert "Alpha" in result.output
        assert "Beta" in result.output
        mock_client.set_task_custom_field.assert_not_called()


def test_field_clear(runner, mock_config, mock_client):
    mock_client.get_task.return_value = _task()
    with patch(
        "cupt.fields.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        result = runner.invoke(field_group, ["clear", "t1", "Notes"])
        assert result.exit_code == 0
        mock_client.remove_task_custom_field.assert_called_once_with("t1", "f-text")


def test_field_list_api_error(runner, mock_config, mock_client):
    mock_client.get_task.side_effect = APIError("HTTP 500")
    with patch(
        "cupt.fields.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        result = runner.invoke(field_group, ["list", "t1"])
        assert result.exit_code == EXIT_API
        assert result.exit_code != 0


def test_field_set_api_error(runner, mock_config, mock_client):
    mock_client.get_task.side_effect = APIError("HTTP 500")
    with patch(
        "cupt.fields.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        result = runner.invoke(field_group, ["set", "t1", "Notes", "hi"])
        assert result.exit_code == EXIT_API


def test_field_list_empty(runner, mock_config, mock_client):
    mock_client.get_task.return_value = {"id": "t1", "custom_fields": []}
    with patch(
        "cupt.fields.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        result = runner.invoke(field_group, ["list", "t1"])
        assert result.exit_code == 0
        assert "No custom fields" in result.output


def test_field_set_checkbox_false(runner, mock_config, mock_client):
    mock_client.get_task.return_value = _task()
    with patch(
        "cupt.fields.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        result = runner.invoke(field_group, ["set", "t1", "Done?", "no"])
        assert result.exit_code == 0
        mock_client.set_task_custom_field.assert_called_once_with(
            "t1", "f-check", False
        )


def test_field_set_checkbox_invalid(runner, mock_config, mock_client):
    mock_client.get_task.return_value = _task()
    with patch(
        "cupt.fields.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        result = runner.invoke(field_group, ["set", "t1", "Done?", "maybe"])
        assert result.exit_code == EXIT_INVALID_INPUT
        mock_client.set_task_custom_field.assert_not_called()


def test_field_set_no_fields_available(runner, mock_config, mock_client):
    mock_client.get_task.return_value = {"id": "t1", "custom_fields": []}
    with patch(
        "cupt.fields.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        result = runner.invoke(field_group, ["set", "t1", "Anything", "x"])
        assert result.exit_code == EXIT_INVALID_INPUT
        assert "No custom fields are available" in result.output


def test_field_list_labels_multiselect(runner, mock_config, mock_client):
    task = {
        "id": "t1",
        "custom_fields": [
            {
                "id": "f-labels",
                "name": "Areas",
                "type": "labels",
                "type_config": {
                    "options": [
                        {"id": "lbl-1", "label": "Backend"},
                        {"id": "lbl-2", "label": "Frontend"},
                    ]
                },
                "value": ["lbl-1", "lbl-2"],
            }
        ],
    }
    mock_client.get_task.return_value = task
    with patch(
        "cupt.fields.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        result = runner.invoke(field_group, ["list", "t1", "--json"])
        assert result.exit_code == 0
        fields = json.loads(result.output)
        assert fields[0]["value"] == ["Backend", "Frontend"]


def test_field_list_dropdown_orderindex_value(runner, mock_config, mock_client):
    """Some payloads carry the dropdown's option orderindex instead of a uuid."""
    task = {
        "id": "t1",
        "custom_fields": [
            {
                "id": "f-drop",
                "name": "Priority",
                "type": "drop_down",
                "type_config": {
                    "options": [
                        {"id": "opt-1", "name": "Low", "orderindex": 0},
                        {"id": "opt-2", "name": "High", "orderindex": 1},
                    ]
                },
                "value": 1,
            }
        ],
    }
    mock_client.get_task.return_value = task
    with patch(
        "cupt.fields.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        result = runner.invoke(field_group, ["list", "t1", "--json"])
        assert result.exit_code == 0
        fields = json.loads(result.output)
        assert fields[0]["value"] == "High"


# ---------------------------------------------------------------------------
# A stored value that matches no current option
# ---------------------------------------------------------------------------


def _task_with_field(field):
    client = MagicMock()
    client.get_task.return_value = {"id": "t1", "custom_fields": [field]}
    return client


def test_unresolvable_dropdown_value_never_leaks_the_raw_uuid():
    """An option deleted or renamed since the value was written leaves a uuid
    ClickUp still stores. Reporting it verbatim would put an id in front of a
    caller who addresses everything by name, so it reads as unset instead."""
    client = _task_with_field(
        {
            "id": "f1",
            "name": "Release group",
            "type": "drop_down",
            "type_config": {"options": [{"id": "opt-1", "name": "Alpha"}]},
            "value": "uuid-of-a-deleted-option",
        }
    )
    assert FieldService(client).list_fields("t1")[0]["value"] is None


def test_stale_index_does_not_resolve_to_an_unrelated_option():
    """Positional resolution was removed deliberately: a stale orderindex must
    not land on whichever option now happens to sit at that position."""
    client = _task_with_field(
        {
            "id": "f1",
            "name": "Release group",
            "type": "drop_down",
            "type_config": {
                "options": [
                    {"id": "opt-a", "name": "Alpha", "orderindex": 10},
                    {"id": "opt-b", "name": "Beta", "orderindex": 11},
                ]
            },
            "value": 1,
        }
    )
    value = FieldService(client).list_fields("t1")[0]["value"]
    assert value is None
    assert value != "Beta"


def test_unresolvable_label_entries_are_dropped_not_echoed():
    client = _task_with_field(
        {
            "id": "f1",
            "name": "Topics",
            "type": "labels",
            "type_config": {"options": [{"id": "l1", "label": "Backend"}]},
            "value": ["l1", "l-deleted"],
        }
    )
    assert FieldService(client).list_fields("t1")[0]["value"] == ["Backend"]


def test_label_field_with_only_unresolvable_entries_reads_as_unset():
    client = _task_with_field(
        {
            "id": "f1",
            "name": "Topics",
            "type": "labels",
            "type_config": {"options": [{"id": "l1", "label": "Backend"}]},
            "value": ["l-deleted"],
        }
    )
    assert FieldService(client).list_fields("t1")[0]["value"] is None
