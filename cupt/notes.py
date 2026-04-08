import click

from cupt.context import get_client_context
from cupt.services.note_service import NoteService
from cupt.utils import format_date, print_error, print_success, print_warning


@click.command(name="note")
@click.argument("task_id")
@click.argument("note_text")
def add_note(task_id, note_text):
    """Add a quick note (comment) to a task"""
    _, client, _ = get_client_context(need_team=False)
    if not client:
        return

    try:
        NoteService(client).add_note(task_id, note_text)
        print_success(f"Note added to task {task_id}")
    except Exception as e:
        print_error(f"Failed to add note: {e}")


@click.command(name="notes")
@click.argument("task_id")
def list_notes(task_id):
    """List all notes (comments) for a task"""
    _, client, _ = get_client_context(need_team=False)
    if not client:
        return

    try:
        comments = NoteService(client).list_notes(task_id)

        if not comments:
            print_warning(f"No notes found for task {task_id}")
            return

        click.echo(f"\nNotes for task {task_id}:")
        click.echo("=" * 80)

        for msg in comments:
            author = msg.get("user", {}).get("username", "Unknown")
            text = msg.get("text", "")
            date = format_date(msg.get("date"))
            click.echo(f"[{date}] {author}:")
            for line in text.split("\n"):
                click.echo(f"  {line}")
            click.echo("-" * 20)

    except Exception as e:
        print_error(f"Failed to list notes: {e}")
