from cupt.config import ConfigManager
from cupt.api import ClickUpClient
from cupt.services.note_service import NoteService
from cupt.utils import print_error, print_success, print_warning, format_date

import click

@click.command(name='note')
@click.argument('task_id')
@click.argument('note_text')
def add_note(task_id, note_text):
    """Add a quick note (comment) to a task"""
    config = ConfigManager()
    if not config.is_authenticated():
        print_error("Not authenticated. Run 'cupt auth' to authenticate.")
        return

    try:
        client = ClickUpClient(config.get('auth.access_token'))
        service = NoteService(client)
        service.add_note(task_id, note_text)
        print_success(f"Note added to task {task_id}")
    except Exception as e:
        print_error(f"Failed to add note: {e}")

@click.command(name='notes')
@click.argument('task_id')
def list_notes(task_id):
    """List all notes (comments) for a task"""
    config = ConfigManager()
    if not config.is_authenticated():
        print_error("Not authenticated. Run 'cupt auth' to authenticate.")
        return

    try:
        client = ClickUpClient(config.get('auth.access_token'))
        service = NoteService(client)
        comments = service.list_notes(task_id)
        
        if not comments:
            print_warning(f"No notes found for task {task_id}")
            return

        click.echo(f"\nNotes for task {task_id}:")
        click.echo("=" * 80)
        
        for msg in comments:
            author = msg.get('user', {}).get('username', 'Unknown')
            text = msg.get('text', '')
            date = format_date(msg.get('date'))
            click.echo(f"[{date}] {author}:")
            # Handle multi-line comments
            lines = text.split('\n')
            for line in lines:
                click.echo(f"  {line}")
            click.echo("-" * 20)
            
    except Exception as e:
        print_error(f"Failed to list notes: {e}")