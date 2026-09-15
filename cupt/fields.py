"""CLI commands for reading and writing ClickUp custom fields on a task."""

import json

import click

from cupt.context import get_client_context
from cupt.errors import EXIT_INVALID_INPUT, fail
from cupt.i18n import format_message
from cupt.services.field_service import FieldService
from cupt.utils import print_success, print_warning


@click.group(name="field")
def field_group():
    """View and edit custom fields on a task"""
    pass


@field_group.command("list")
@click.argument("task_id")
@click.option("--json", "as_json", is_flag=True, help="Output fields as JSON")
def list_fields_cmd(task_id, as_json):
    """List a task's custom fields"""
    _, client, _ = get_client_context(need_workspace=False)
    if not client:
        return

    service = FieldService(client)
    try:
        fields = service.list_fields(task_id)
    except ValueError as e:
        fail(str(e), code=EXIT_INVALID_INPUT)
    except Exception as e:
        fail(format_message("Failed to list fields: {error}", error=e), e)

    if as_json:
        click.echo(json.dumps(fields, indent=2))
        return

    if not fields:
        # An empty result is a successful read, so it goes to stderr like
        # every other "nothing matched" notice — stdout stays data-only.
        print_warning(format_message("No custom fields on {task_id}", task_id=task_id))
        return

    name_width = max(len(str(f["name"])) for f in fields)
    for f in fields:
        click.echo(f"{f['name']:<{name_width}}  {_format_value(f['value'])}")


@field_group.command("set")
@click.argument("task_id")
@click.argument("field_name")
@click.argument("value")
def set_field_cmd(task_id, field_name, value):
    """Set a custom field on a task"""
    _, client, _ = get_client_context(need_workspace=False)
    if not client:
        return

    service = FieldService(client)
    try:
        result = service.set_field(task_id, field_name, value)
    except ValueError as e:
        fail(str(e), code=EXIT_INVALID_INPUT)
    except Exception as e:
        fail(format_message("Failed to set field: {error}", error=e), e)

    print_success(
        format_message(
            "Set '{field}' to '{display}' on {task_id}",
            field=result["field"],
            display=result["display"],
            task_id=task_id,
        )
    )


@field_group.command("clear")
@click.argument("task_id")
@click.argument("field_name")
def clear_field_cmd(task_id, field_name):
    """Clear a custom field on a task"""
    _, client, _ = get_client_context(need_workspace=False)
    if not client:
        return

    service = FieldService(client)
    try:
        result = service.clear_field(task_id, field_name)
    except ValueError as e:
        fail(str(e), code=EXIT_INVALID_INPUT)
    except Exception as e:
        fail(format_message("Failed to clear field: {error}", error=e), e)

    print_success(
        format_message(
            "Cleared '{field}' on {task_id}", field=result["field"], task_id=task_id
        )
    )


def _format_value(value) -> str:
    """Render a normalized field value for the human table."""
    if value is None:
        return "-"
    if isinstance(value, list):
        return ", ".join(str(v) for v in value) if value else "-"
    return str(value)
