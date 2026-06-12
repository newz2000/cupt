import click

from cupt.context import get_client_context
from cupt.i18n import format_message
from cupt.utils import print_error, print_success


@click.group(name="tag")
def tag_group():
    """Add or remove task tags"""
    pass


@tag_group.command("add")
@click.argument("task_id")
@click.argument("tag_name")
def add_tag(task_id, tag_name):
    """Add a tag to a task"""
    _, client, _ = get_client_context(need_workspace=False)
    if not client:
        return

    try:
        client.add_task_tag(task_id, tag_name)
        print_success(
            format_message(
                "Tagged {task_id} with '{tag_name}'", task_id=task_id, tag_name=tag_name
            )
        )
    except Exception as e:
        print_error(format_message("Failed to add tag: {error}", error=e))


@tag_group.command("remove")
@click.argument("task_id")
@click.argument("tag_name")
def remove_tag(task_id, tag_name):
    """Remove a tag from a task"""
    _, client, _ = get_client_context(need_workspace=False)
    if not client:
        return

    try:
        client.remove_task_tag(task_id, tag_name)
        print_success(
            format_message(
                "Removed '{tag_name}' from {task_id}",
                tag_name=tag_name,
                task_id=task_id,
            )
        )
    except Exception as e:
        print_error(format_message("Failed to remove tag: {error}", error=e))
