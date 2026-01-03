"""
Utility functions for CUPT CLI (basic version)
"""

import re
from datetime import datetime, timedelta
from typing import Optional

def parse_duration(duration_str: str) -> Optional[int]:
    """
    Parse duration string and return milliseconds.
    
    Supported formats:
    - "30m" -> 30 minutes
    - "2h" -> 2 hours
    - "1h45m" -> 1 hour 45 minutes
    - "45m" -> 45 minutes
    - "0h15m" -> 15 minutes
    
    Returns None if format is invalid.
    """
    if not duration_str or not isinstance(duration_str, str):
        return None
    
    # Remove whitespace and convert to lowercase
    duration_str = duration_str.strip().lower()
    
    # Pattern to match duration strings
    pattern = r'^(\d+h)?(\d+m)?$'
    if not re.match(pattern, duration_str):
        return None
    
    hours = 0
    minutes = 0
    
    # Extract hours
    hours_match = re.search(r'(\d+)h', duration_str)
    if hours_match:
        hours = int(hours_match.group(1))
    
    # Extract minutes
    minutes_match = re.search(r'(\d+)m', duration_str)
    if minutes_match:
        minutes = int(minutes_match.group(1))
    
    # Convert to milliseconds
    total_minutes = hours * 60 + minutes
    return total_minutes * 60 * 1000

def format_duration(milliseconds: int) -> str:
    """Convert milliseconds to human readable format"""
    if not milliseconds:
        return "0m"
    
    total_minutes = milliseconds // (60 * 1000)
    hours = total_minutes // 60
    minutes = total_minutes % 60
    
    if hours > 0:
        return f"{hours}h{minutes}m" if minutes > 0 else f"{hours}h"
    else:
        return f"{minutes}m"

def format_date(timestamp: Optional[Any]) -> str:
    """Format timestamp to readable date"""
    if not timestamp:
        return "No date"
    
    try:
        # ClickUp timestamps are sometimes strings in some API versions/fields
        ts = int(timestamp)
        dt = datetime.fromtimestamp(ts / 1000)
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, OSError, TypeError):
        return "Invalid date"

def truncate_text(text: str, max_length: int = 50) -> str:
    """Truncate text to specified length"""
    if not text:
        return ""
    
    if len(text) <= max_length:
        return text
    
    return text[:max_length-3] + "..."

def print_info(message: str):
    """Print info message"""
    print(f"ℹ️  {message}")

def print_error(message: str):
    """Print error message"""
    print(f"❌ {message}")

def print_success(message: str):
    """Print success message"""
    print(f"✅ {message}")

def print_warning(message: str):
    """Print warning message"""
    print(f"⚠️  {message}")

def format_task_status(status: str) -> str:
    """Format task status with emoji"""
    status_map = {
        'complete': '✓',
        'in progress': '⟳',
        'to do': '○',
    }
    
    return status_map.get(status.lower(), '?')