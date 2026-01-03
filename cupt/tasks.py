from cupt.config import ConfigManager
from cupt.api import ClickUpClient
from cupt.utils import print_error, print_success, print_warning, print_info, format_date, truncate_text, format_task_status

import click
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

def get_filters(overdue: bool, today: bool, week: bool) -> Dict[str, Any]:
    """Build filter parameters based on options"""
    filters = {}
    
    if overdue:
        # For overdue, we want tasks whose due_date is in the past
        # Note: ClickUp API uses milliseconds
        now_ms = int(datetime.now().timestamp() * 1000)
        filters['due_date_lt'] = now_ms
    elif today:
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        filters['due_date_gte'] = int(today_start.timestamp() * 1000)
        filters['due_date_lt'] = int(today_end.timestamp() * 1000)
    elif week:
        week_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        # Week starts from today, looking forward 7 days
        week_end = week_start + timedelta(days=7)
        filters['due_date_gte'] = int(week_start.timestamp() * 1000)
        filters['due_date_lt'] = int(week_end.timestamp() * 1000)
    
    return filters

@click.command(name='list')
@click.option('--overdue', is_flag=True, help='Show overdue tasks')
@click.option('--today', is_flag=True, help='Show tasks due today')
@click.option('--week', is_flag=True, help='Show tasks due this week')
@click.option('-n', '--limit', type=int, help='Limit results')
@click.option('--verbose', is_flag=True, help='Show extra info')
@click.option('--team-id', help='Override team ID')
def list_tasks_cmd(overdue, today, week, limit, verbose, team_id=None):
    """List tasks with optional filters"""
    return list_tasks(overdue, today, week, limit, verbose, team_id)

def list_tasks(overdue=False, today=False, week=False, limit=None, verbose=False, team_id=None):
    """Logic for listing tasks (can be called from CLI or code)"""
    config = ConfigManager()
    
    if not config.is_authenticated():
        print_error("Not authenticated. Run 'cupt auth' to authenticate.")
        return []
    
    selected_team_id = team_id or config.get('user.team_id')
    if not selected_team_id:
        print_error("Team ID not set. Run 'cupt config --team-id <id>' first.")
        return []
    
    # Build filters
    filters = get_filters(overdue, today, week)
    
    try:
        client = ClickUpClient(config.get('auth.access_token'))
        
        if verbose:
            print_info(f"Fetching tasks with filters: {filters}")
        
        tasks = client.get_team_tasks(selected_team_id, filters)
        
        if not tasks:
            print_warning("No tasks found")
            return []
        
        # Sort by due date (tasks without due dates at end)
        tasks.sort(key=lambda t: (
            t.get('due_date') is None, 
            int(t.get('due_date')) if t.get('due_date') else 9999999999999
        ))
        
        # Apply limit
        if limit:
            tasks = tasks[:limit]
        
        # Display tasks
        click.echo(f"\n{'ID':<12} {'Status':<12} {'Due':<18} {'Name'}")
        click.echo("-" * 80)
        
        for task in tasks:
            task_id = task.get('id', 'No ID')
            status_obj = task.get('status', {})
            status = status_obj.get('status', 'unknown')
            due_date = format_date(task.get('due_date'))
            name = truncate_text(task.get('name', 'No name'), 40)
            
            click.echo(f"{task_id:<12} {status:<12} {due_date:<18} {name}")
        
        return tasks
        
    except Exception as e:
        print_error(f"Failed to list tasks: {e}")
        return []

@click.command(name='show')
@click.argument('task_id')
@click.option('--notes', is_flag=True, help='Show task notes')
def show_task_cmd(task_id, notes):
    """Show detailed task information"""
    return show_task(task_id, notes)

def show_task(task_id: str, include_notes: bool = False):
    """Logic for showing a single task"""
    config = ConfigManager()
    
    if not config.is_authenticated():
        print_error("Not authenticated. Run 'cupt auth' to authenticate.")
        return
    
    try:
        client = ClickUpClient(config.get('auth.access_token'))
        task = client.get_task(task_id)
        
        if not task:
            print_error(f"Task {task_id} not found")
            return
        
        click.echo(f"\nTask: {task.get('name')}")
        click.echo("=" * 40)
        click.echo(f"ID:       {task.get('id')}")
        click.echo(f"Status:   {task.get('status', {}).get('status', 'unknown').upper()}")
        click.echo(f"Priority: {task.get('priority', {}).get('priority', 'none').upper() if task.get('priority') else 'NONE'}")
        click.echo(f"Due Date: {format_date(task.get('due_date'))}")
        
        desc = task.get('description', '')
        if desc:
            click.echo("\nDescription:")
            click.echo("-" * 20)
            click.echo(desc)
        
        if include_notes:
            click.echo("\nNotes:")
            click.echo("-" * 20)
            comments = client.get_task_comments(task_id)
            if not comments:
                click.echo("No notes found.")
            for msg in comments:
                author = msg.get('user', {}).get('username', 'Unknown')
                text = msg.get('text', '')
                date = format_date(msg.get('date'))
                click.echo(f"[{date}] {author}: {text}")
                
    except Exception as e:
        print_error(f"Failed to show task: {e}")

@click.command(name='done')
@click.argument('task_id')
@click.option('--note', help='Add a completion note')
def complete_task_cmd(task_id, note):
    """Mark a task as complete"""
    return complete_task(task_id, note)

def complete_task(task_id: str, note: Optional[str] = None):
    """Logic for completing a task"""
    config = ConfigManager()
    
    if not config.is_authenticated():
        print_error("Not authenticated. Run 'cupt auth' to authenticate.")
        return
    
    try:
        client = ClickUpClient(config.get('auth.access_token'))
        
        # Update status to complete
        # ClickUp statuses are case-sensitive usually, 'complete' or 'Closed'
        # We try 'complete' first
        client.update_task(task_id, {'status': 'complete'})
        
        if note:
            client.add_task_comment(task_id, note)
            
        print_success(f"Task {task_id} marked as complete!")
        
    except Exception as e:
        print_error(f"Failed to complete task: {e}")