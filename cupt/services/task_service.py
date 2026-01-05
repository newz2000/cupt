from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timedelta
from cupt.api import ClickUpClient

class TaskService:
    def __init__(self, client: ClickUpClient):
        self.client = client

    def get_filters(self, overdue: bool = False, today: bool = False, week: bool = False) -> Dict[str, Any]:
        """Build filter parameters based on options"""
        filters = {
            'subtasks': 'true',
            'include_subtasks': 'true'
        }
        
        if overdue:
            now_ms = int(datetime.now().timestamp() * 1000)
            filters['due_date_lt'] = now_ms
            filters['order_by'] = 'due_date'
            filters['reverse'] = True
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

    def list_tasks(self, team_id: str, user_id: Optional[str] = None, 
                   overdue: bool = False, today: bool = False, week: bool = False,
                   include_closed: bool = False, mine: bool = True,
                   max_pages: int = 15) -> List[Dict[str, Any]]:
        """Fetch and filter tasks from API"""
        filters = self.get_filters(overdue, today, week)
        
        if mine and user_id:
            filters['assignees[]'] = [user_id]
            
        all_tasks = []
        page = 0
        limit_pages = 5 if not mine else max_pages
        
        while page < limit_pages:
            filters['page'] = page
            tasks = self.client.get_team_tasks(team_id, filters)
            
            if not tasks:
                break
                
            if not include_closed:
                filtered = [t for t in tasks if t.get('status', {}).get('type') not in ['done', 'closed']]
            else:
                filtered = tasks
                
            all_tasks.extend(filtered)
            
            if len(all_tasks) >= 100 or len(tasks) < 100:
                break
            page += 1
            
        # Sort by due date
        all_tasks.sort(key=lambda t: (
            t.get('due_date') is None, 
            int(t.get('due_date')) if t.get('due_date') else 9999999999999
        ))
        
        return all_tasks

    def resolve_parent_names(self, team_id: str, tasks: List[Dict[str, Any]], parent_cache: Dict[str, str]) -> None:
        """Enrich tasks with parent names using a local cache and bulk API calls"""
        missing_ids = []
        for task in tasks:
            p_id = task.get('parent')
            if p_id and p_id not in parent_cache:
                missing_ids.append(p_id)
        
        if not missing_ids:
            return

        # Fetch missing parents in bulk
        try:
            # Remove duplicates from missing_ids
            unique_missing = list(set(missing_ids))
            # Fetch up to 100 at a time (ClickUp limit)
            for i in range(0, len(unique_missing), 100):
                chunk = unique_missing[i:i+100]
                parent_tasks = self.client.get_tasks_by_ids(team_id, chunk)
                for pt in parent_tasks:
                    parent_cache[pt['id']] = pt.get('name', pt['id'])
            
            # For any still missing (e.g. not found), set to ID to avoid repeated fetching
            for p_id in unique_missing:
                if p_id not in parent_cache:
                    parent_cache[p_id] = p_id
        except Exception:
            # Fallback to just using ID if bulk fetch fails
            for p_id in missing_ids:
                if p_id not in parent_cache:
                    parent_cache[p_id] = p_id

    def get_task_context(self, task_id: str, team_id: str, show_completed: bool = False) -> Dict[str, Any]:
        """Get structural context for a task (parent, siblings, subtasks)"""
        task = self.client.get_task(task_id)
        if not task:
            return None
            
        notes = self.client.get_task_comments(task_id)
        
        p_id = task.get('parent')
        parent_task = None
        if p_id:
            try:
                parent_task = self.client.get_task(p_id)
            except Exception:
                pass
                
        # Sibling list
        target_parent = p_id if p_id else task_id
        params = {
            'parent': target_parent,
            'include_subtasks': 'true',
            'subtasks': 'true'
        }
        if show_completed:
            params['include_closed'] = 'true'
            
        resp = self.client._make_request('GET', f'/team/{team_id}/task', params=params)
        siblings = resp.get('tasks', [])
        
        if not show_completed:
            siblings = [s for s in siblings if s.get('status', {}).get('type') not in ['done', 'closed']]
            
        return {
            'task': task,
            'notes': notes,
            'parent_task': parent_task,
            'siblings': siblings,
            'is_subtask': bool(p_id)
        }
