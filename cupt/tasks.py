from cupt.config import ConfigManager
from cupt.api import ClickUpClient
from cupt.utils import print_error, print_success, print_warning, print_info, format_date, truncate_text, format_task_status

import click
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Set

def get_active_statuses(client: ClickUpClient, team_id: str) -> List[str]:
    """Fetch all statuses that are not 'done' or 'closed' in the workspace"""
    try:
        active_statuses = set()
        spaces = client.get_spaces(team_id)
        for space in spaces:
            # Check space statuses
            for status in space.get('statuses', []):
                if status.get('type') not in ['done', 'closed']:
                    active_statuses.add(status.get('status'))
            
            # Check list statuses (important for overrides)
            lists = client.get_lists(space.get('id'))
            for lst in lists:
                # Some lists might have their own statuses
                for status in lst.get('statuses', []):
                    if status.get('type') not in ['done', 'closed']:
                        active_statuses.add(status.get('status'))
        
        return list(active_statuses)
    except Exception:
        # Fallback to some common ones if fetching fails
        return ['Open', 'to do', 'in progress', 'active', 'OPEN']

def get_filters(overdue: bool, today: bool, week: bool) -> Dict[str, Any]:
    """Build filter parameters based on options"""
    filters = {}
    
    # Enable subtasks by default to ensure we don't miss anything
    # 'subtasks' shows them nested, 'include_subtasks' shows them in the flat list
    # IMPORTANT: ClickUp API requires lowercase 'true' strings
    filters['subtasks'] = 'true'
    filters['include_subtasks'] = 'true'
    
    if overdue:
        # For overdue, we want tasks whose due_date is in the past
        now_ms = int(datetime.now().timestamp() * 1000)
        filters['due_date_lt'] = now_ms
        filters['order_by'] = 'due_date'
        filters['reverse'] = True  # Show most recent overdue first
    elif today:
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        filters['due_date_gt'] = int(today_start.timestamp() * 1000)
        filters['due_date_lt'] = int(today_end.timestamp() * 1000)
        filters['order_by'] = 'due_date'
        filters['reverse'] = False
    elif week:
        week_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        week_end = week_start + timedelta(days=7)
        filters['due_date_gt'] = int(week_start.timestamp() * 1000)
        filters['due_date_lt'] = int(week_end.timestamp() * 1000)
        filters['order_by'] = 'due_date'
        filters['reverse'] = False
    
    return filters

@click.command(name='list')
@click.option('--overdue', is_flag=True, help='Show overdue tasks')
@click.option('--today', is_flag=True, help='Show tasks due today')
@click.option('--week', is_flag=True, help='Show tasks due this week')
@click.option('-n', '--limit', type=int, help='Limit results')
@click.option('--verbose', is_flag=True, help='Show extra info')
@click.option('--team-id', help='Override team ID')
@click.option('--include-closed', is_flag=True, help='Include closed tasks')
@click.option('--mine', is_flag=True, default=True, help='Show only tasks assigned to you (default)')
@click.option('--all', 'show_all', is_flag=True, help='Show tasks for the whole team')
@click.option('--hide-subtasks', is_flag=True, help='Hide subtasks from the list')
def list_tasks_cmd(overdue, today, week, limit, verbose, team_id=None, include_closed=False, mine=True, show_all=False, hide_subtasks=False):
    """List tasks with optional filters"""
    # If --all is passed, it overrides the default --mine
    if show_all:
        mine = False
    return list_tasks(overdue, today, week, limit, verbose, team_id, include_closed, mine, hide_subtasks)

def list_tasks(overdue=False, today=False, week=False, limit=None, verbose=False, team_id=None, include_closed=False, mine=True, hide_subtasks=False):
    """Logic for listing tasks (can be called from CLI or code)"""
    config = ConfigManager()
    
    if not config.is_authenticated():
        print_error("Not authenticated. Run 'cupt auth' to authenticate.")
        return []
    
    selected_team_id = team_id or config.get('user.team_id')
    user_id = config.get('user.user_id')
    
    if not selected_team_id:
        print_error("Team ID not set. Run 'cupt config --team-id <id>' first.")
        return []
        
    # Build initial filters
    filters = get_filters(overdue, today, week)
    
    # filter by assignee to match personal reports
    if mine and user_id:
        filters['assignees[]'] = [user_id]
        if verbose:
            print_info(f"Filtering for tasks assigned to YOU (ID: {user_id})")
    
    # Ensure subtasks are included in the flat list
    # Use string 'true' because ClickUp API is picky about casing
    filters['subtasks'] = 'true'
    filters['include_subtasks'] = 'true'
    
    try:
        client = ClickUpClient(config.get('auth.access_token'))
        
        all_found = []
        page = 0
        # If showing all team tasks, limit searching depth slightly to avoid infinite loops
        # with thousands of closed tasks. If showing 'mine', we can go deeper safely.
        # Increased to 15 to handle deep backlogs.
        max_pages = 5 if not mine else 15
        
        while page < max_pages:
            filters['page'] = page
            tasks = client.get_team_tasks(selected_team_id, filters)
            
            if not tasks:
                break
                
            # Local filter for active/overdue tasks
            if not include_closed:
                # Strictly filter out 'done' and 'closed' status types
                filtered = [t for t in tasks if t.get('status', {}).get('type') not in ['done', 'closed']]
            else:
                filtered = tasks
                
            # Local filter for subtasks
            if hide_subtasks:
                filtered = [t for t in filtered if not t.get('parent')]
                
            all_found.extend(filtered)
            
            # If we already have a full page of filtering results, don't fetch forever
            if len(all_found) >= 100:
                break
            
            # If we didn't get a full page from API, it's the end of results
            if len(tasks) < 100:
                break
                
            page += 1
            
        tasks = all_found
        
        if not tasks:
            print_warning("No active tasks found matching criteria.")
            return []
        
        # Sort by due date (tasks without due dates at end)
        tasks.sort(key=lambda t: (
            t.get('due_date') is None, 
            int(t.get('due_date')) if t.get('due_date') else 9999999999999
        ))
        
        # Apply limit
        if limit:
            tasks = tasks[:limit]
            
        # Resolve parent names for subtasks
        parent_map = {}
        # Pre-populate map with tasks we already have in the list
        for t in tasks:
            parent_map[t['id']] = t['name']
            
        # Display tasks
        click.echo(f"\n{'ID':<12} {'Status':<12} {'Due':<18} {'Name'}")
        click.echo("-" * 120)
        
        for task in tasks:
            task_id = task.get('id', 'No ID')
            status_obj = task.get('status', {})
            status = status_obj.get('status', 'unknown')
            due_date = format_date(task.get('due_date'))
            
            name = task.get('name', 'No name')
            p_id = task.get('parent')
            
            if p_id:
                if p_id not in parent_map:
                    # Resolve parent name (cached for this list call)
                    try:
                        parent_task = client.get_task(p_id)
                        parent_map[p_id] = parent_task.get('name', p_id)
                    except Exception:
                        parent_map[p_id] = p_id
                
                p_name = parent_map.get(p_id, p_id)
                name = f"↳ {name} (sub of {p_name})"
            
            name = truncate_text(name, 75)
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
        
        # Add context info
        click.echo(f"Space:    {task.get('space', {}).get('id')}")
        click.echo(f"Folder:   {task.get('folder', {}).get('name', 'N/A')} ({task.get('folder', {}).get('id', 'N/A')})")
        click.echo(f"List:     {task.get('list', {}).get('name', 'N/A')} ({task.get('list', {}).get('id', 'N/A')})")
        
        if task.get('parent'):
            p_id = task.get('parent')
            try:
                parent_task = client.get_task(p_id)
                p_name = parent_task.get('name', 'Unknown')
                click.echo(f"Parent:   {p_name} ({p_id})")
            except Exception:
                click.echo(f"Parent:   {p_id}")
        
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
        
        # Get task to find its list_id and current status
        task = client.get_task(task_id)
        list_id = task.get('list', {}).get('id')
        
        if not list_id:
            print_error(f"Could not find list for task {task_id}")
            return
            
        # Get statuses for this list to find a 'closed' one
        # ClickUp API: /list/{list_id} returns everything about the list
        list_data = client._make_request('GET', f'/list/{list_id}')
        statuses = list_data.get('statuses', [])
        
        # If list statuses are empty, it might be using space statuses
        if not statuses:
            space_id = task.get('space', {}).get('id')
            if space_id:
                space_data = client._make_request('GET', f'/space/{space_id}')
                statuses = space_data.get('statuses', [])
        
        # Find a status with type 'closed'
        target_status = None
        for s in statuses:
            if s.get('type') == 'closed':
                target_status = s.get('status')
                break
        
        if not target_status:
            # Try to find 'complete' by name if no closed type found
            for s in statuses:
                if s.get('status').lower() in ['complete', 'closed', 'resolved', 'done']:
                    target_status = s.get('status')
                    break
                    
        if not target_status:
            # Absolute fallback
            target_status = 'complete'
            
        # Update status
        client.update_task(task_id, {'status': target_status})
        
        if note:
            client.add_task_comment(task_id, note)
            
        print_success(f"Task {task_id} marked as '{target_status}'!")
        
    except Exception as e:
        print_error(f"Failed to complete task: {e}")
@click.command(name='context')
@click.argument('task_id')
@click.option('--show-completed', is_flag=True, help='Include completed subtasks')
def context_cmd(task_id, show_completed):
    """Show task context (parent, siblings, subtasks)"""
    return show_context(task_id, show_completed)

def show_context(task_id: str, show_completed: bool = False):
    """Logic for showing task context"""
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
            
        # 1. Show Current Task Details
        click.echo(f"\nCONTEXT FOR TASK: {task.get('name')}")
        click.echo("=" * 60)
        click.echo(f"ID:       {task.get('id')}")
        click.echo(f"Status:   {task.get('status', {}).get('status', 'unknown').upper()}")
        click.echo(f"Due Date: {format_date(task.get('due_date'))}")
        
        desc = task.get('description', '')
        if desc:
            click.echo("\nDescription:")
            click.echo("-" * 20)
            click.echo(desc)
            
        # Show Notes (Comments)
        click.echo("\nNotes:")
        click.echo("-" * 20)
        comments = client.get_task_comments(task_id)
        if not comments:
            click.echo("No notes found.")
        for msg in comments:
            author = msg.get('user', {}).get('username', 'Unknown')
            text = msg.get('text', '')
            click.echo(f"[{author}]: {text}")

        # 2. Show Parent Details
        p_id = task.get('parent')
        if p_id:
            click.echo("\n" + "=" * 60)
            click.echo(f"PARENT TASK")
            click.echo("=" * 60)
            try:
                parent_task = client.get_task(p_id)
                click.echo(f"Name:     {parent_task.get('name')}")
                click.echo(f"ID:       {p_id}")
                click.echo(f"Status:   {parent_task.get('status', {}).get('status', 'unknown').upper()}")
                
                p_desc = parent_task.get('description', '')
                if p_desc:
                    click.echo("\nParent Description:")
                    click.echo("-" * 20)
                    click.echo(p_desc)
            except Exception:
                click.echo(f"ID:       {p_id} (Metadata fetch failed)")
        else:
            click.echo("\n" + "=" * 60)
            click.echo("PARENT TASK: (Top Level Task)")
            click.echo("=" * 60)

        # 3. Show Siblings (or subtasks if top level)
        # If it has a parent, show all subtasks of that parent (siblings)
        # If it has no parent, show its own subtasks
        click.echo("\n" + "=" * 60)
        if p_id:
            click.echo(f"SIBLINGS (Subtasks of {p_id})")
            target_parent = p_id
        else:
            click.echo(f"SUBTASKS (of {task_id})")
            target_parent = task_id
        click.echo("=" * 60)
        
        # Fetch chores for the target parent
        # We use a team-level fetch with parent filter to get everything
        team_id = config.get('user.team_id')
        params = {
            'parent': target_parent,
            'include_subtasks': 'true',
            'subtasks': 'true'
        }
        if show_completed:
            params['include_closed'] = 'true'
            
        resp = client._make_request('GET', f'/team/{team_id}/task', params=params)
        siblings = resp.get('tasks', [])
        
        # Local filter for active unless show_completed
        if not show_completed:
            siblings = [s for s in siblings if s.get('status', {}).get('type') not in ['done', 'closed']]
            
        if not siblings:
            click.echo("No relevant subtasks found.")
        else:
            click.echo(f"{'ID':<12} {'Status':<12} {'Name'}")
            click.echo("-" * 60)
            for s in siblings:
                s_id = s.get('id')
                s_status = s.get('status', {}).get('status', 'unknown').upper()
                s_name = s.get('name', 'No name')
                
                # Highlight current task
                if s_id == task_id:
                    marker = ">> "
                else:
                    marker = "   "
                    
                click.echo(f"{marker}{s_id:<9} {s_status:<12} {s_name}")
        
        click.echo("\n")
        
    except Exception as e:
        print_error(f"Failed to show context: {e}")

