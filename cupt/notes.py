import click

from cupt.context import get_client_context
from cupt.i18n import _, format_message
from cupt.resolver import IDResolutionError, resolve_task_id
from cupt.services.note_service import NoteService
from cupt.utils import (
    format_comment_author,
    format_comment_text,
    format_date,
    print_error,
    print_success,
    print_warning,
)


@click.command(name="note")
@click.argument("args", nargs=-1, required=True)
def add_note(args):
    """Add a quick note (comment) to a task.

    Two forms:

    \b
      cupt note <task_id> <note_text>   # explicit
      cupt note <note_text>             # uses active task (interactive only)
    """
    if len(args) == 2:
        task_id_arg, note_text = args
    elif len(args) == 1:
        task_id_arg, note_text = None, args[0]
    else:
        print_error(_("Usage: cupt note [<task_id>] <note_text>"))
        return

    try:
        task_id = resolve_task_id(task_id_arg)
    except IDResolutionError as e:
        print_error(str(e))
        return

    _config, client, _workspace_id = get_client_context(need_workspace=False)
    if not client:
        return

    try:
        NoteService(client).add_note(task_id, note_text)
        print_success(format_message("Note added to task {task_id}", task_id=task_id))
    except Exception as e:
        print_error(format_message("Failed to add note: {error}", error=e))


@click.command(name="notes")
@click.argument("task_id", required=False)
def list_notes(task_id):
    """List all notes (comments) for a task. Falls back to the active task."""
    try:
        task_id = resolve_task_id(task_id)
    except IDResolutionError as e:
        print_error(str(e))
        return

    _config, client, _workspace_id = get_client_context(need_workspace=False)
    if not client:
        return

    try:
        comments = NoteService(client).list_notes(task_id)

        if not comments:
            print_warning(
                format_message("No notes found for task {task_id}", task_id=task_id)
            )
            return

        click.echo("\n" + format_message("Notes for task {task_id}:", task_id=task_id))
        click.echo("=" * 80)

        for msg in comments:
            author = format_comment_author(msg, _("Unknown"))
            text = format_comment_text(msg)
            date = format_date(msg.get("date"))
            click.echo(f"[{date}] {author}:")
            for line in text.split("\n"):
                click.echo(f"  {line}")
            click.echo("-" * 20)

    except Exception as e:
        print_error(format_message("Failed to list notes: {error}", error=e))
