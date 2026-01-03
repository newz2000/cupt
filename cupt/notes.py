"""
Note/comment management commands for CUPT
"""

import click
from typing import Optional

from cupt.config import ConfigManager
from cupt.api import ClickUpClient
from cupt.utils import print_error, print_success, print_warning, truncate_text, format_date

@click.command(name='note')
@click.argument('task_id')
@click.argument('note_text')
def add_note(task_id, note_text):
    """Add a note to a task"""
    config = ConfigManager()
    
    if not config.is_authenticated():
        print_error("Not authenticated. Run 'cupt auth' to authenticate.")
        return
    
    try:
        client = ClickUpClient(config.get('auth.access_token'))
        result = client.add_task_comment(task_id, note_text)
        print_success(f"Note added to task {task_id}")
        
    except Exception as e:
        print_error(f"Failed to add note: {e}")

@click.command(name='notes')
@click.argument('task_id')
def list_notes(task_id):
    """List all notes for a task"""
    config = ConfigManager()
    
    if not config.is_authenticated():
        print_error("Not authenticated. Run 'cupt auth' to authenticate.")
        return
    
    try:
        client = ClickUpClient(config.get('auth.access_token'))
        comments = client.get_task_comments(task_id)
        
        if not comments:
            print_warning(f"No notes found for task {task_id}")
            return
        
        click.echo(f"\nNotes for task {task_id}:")
        click.echo("-" * 80)
        
        for comment in comments:
            author = comment.get('user', {}).get('username', 'Unknown')
            text = comment.get('text', '')
            created = format_date(comment.get('date'))
            
            click.echo(f"[{created}] {author}:")
            # Handle multi-line comments
            lines = text.split('\n')
            for line in lines:
                click.echo(f"  {line}")
            click.echo()
        
    except Exception as e:
        print_error(f"Failed to list notes: {e}")