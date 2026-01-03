"""
Time tracking commands for CUPT
"""

import click
from typing import Optional

from cupt.config import ConfigManager
from cupt.api import ClickUpClient
from cupt.utils import print_error, print_success, print_warning, parse_duration, format_duration

@click.group(name='time')
def time_group():
    """Time tracking commands"""
    pass

@time_group.command('start')
@click.argument('task_id')
def start_timer(task_id):
    """Start time tracking for a task"""
    config = ConfigManager()
    
    if not config.is_authenticated():
        print_error("Not authenticated. Run 'cupt auth' to authenticate.")
        return
    
    team_id = config.get('user.team_id')
    if not team_id:
        print_error("Team ID not set. Run 'cupt config --team-id <id>' first.")
        return
    
    try:
        client = ClickUpClient(config.get('auth.access_token'))
        
        # Check if timer is already running
        running_timer = client.get_running_timer(team_id)
        if running_timer:
            print_warning("Timer is already running. Stop current timer first.")
            return
        
        # Start new timer
        result = client.start_timer(team_id, task_id)
        print_success(f"Started tracking time for task {task_id}")
        
    except Exception as e:
        print_error(f"Failed to start timer: {e}")

@time_group.command('stop')
def stop_timer():
    """Stop current time tracking"""
    config = ConfigManager()
    
    if not config.is_authenticated():
        print_error("Not authenticated. Run 'cupt auth' to authenticate.")
        return
    
    team_id = config.get('user.team_id')
    if not team_id:
        print_error("Team ID not set. Run 'cupt config --team-id <id>' first.")
        return
    
    try:
        client = ClickUpClient(config.get('auth.access_token'))
        
        # Check if timer is running
        running_timer = client.get_running_timer(team_id)
        if not running_timer:
            print_warning("No timer is currently running.")
            return
        
        # Stop timer
        result = client.stop_timer(team_id)
        print_success("Timer stopped")
        
    except Exception as e:
        print_error(f"Failed to stop timer: {e}")

@time_group.command('status')
def timer_status():
    """Show current timer status"""
    config = ConfigManager()
    
    if not config.is_authenticated():
        print_error("Not authenticated. Run 'cupt auth' to authenticate.")
        return
    
    team_id = config.get('user.team_id')
    if not team_id:
        print_error("Team ID not set. Run 'cupt config --team-id <id>' first.")
        return
    
    try:
        client = ClickUpClient(config.get('auth.access_token'))
        running_timer = client.get_running_timer(team_id)
        
        if running_timer:
            task_id = running_timer.get('task_id', 'Unknown')
            start_time = running_timer.get('start', 0)
            
            click.echo(f"✅ Timer is running")
            click.echo(f"   Task ID: {task_id}")
            
            if start_time:
                from datetime import datetime
                start_dt = datetime.fromtimestamp(start_time / 1000)
                click.echo(f"   Started: {start_dt.strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            print_warning("No timer is currently running")
            
    except Exception as e:
        print_error(f"Failed to get timer status: {e}")

@time_group.command('add')
@click.argument('task_id')
@click.argument('duration')
@click.option('-m', '--message', help='Description for the time entry')
def add_time(task_id, duration, message):
    """Add manual time entry to a task
        
        DURATION format: '30m', '2h', '1h45m', etc.
        """
    config = ConfigManager()
    
    if not config.is_authenticated():
        print_error("Not authenticated. Run 'cupt auth' to authenticate.")
        return
    
    team_id = config.get('user.team_id')
    if not team_id:
        print_error("Team ID not set. Run 'cupt config --team-id <id>' first.")
        return
    
    # Parse duration
    duration_ms = parse_duration(duration)
    if duration_ms is None:
        print_error(f"Invalid duration format: {duration}")
        print_error("Valid formats: '30m', '2h', '1h45m', etc.")
        return
    
    try:
        client = ClickUpClient(config.get('auth.access_token'))
        
        # Add time entry
        result = client.add_time_entry(team_id, task_id, duration_ms, message)
        
        human_duration = format_duration(duration_ms)
        print_success(f"Added {human_duration} to task {task_id}")
        
        if message:
            print_success(f"Note: {message}")
            
    except Exception as e:
        print_error(f"Failed to add time entry: {e}")