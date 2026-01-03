"""
ClickUp API client
"""

import requests
from typing import Dict, Any, Optional, List
import json
from datetime import datetime

class ClickUpClient:
    """ClickUp API client"""
    
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.base_url = "https://api.clickup.com/api/v2"
        self.session = requests.Session()
        # ClickUp API accepts the token directly in the Authorization header
        self.session.headers.update({
            'Authorization': self.access_token,
            'Content-Type': 'application/json'
        })
    
    def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None, params: Optional[Dict] = None) -> Dict[str, Any]:
        """Make API request with error handling"""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        try:
            if method.upper() == 'GET':
                response = self.session.get(url, params=params)
            elif method.upper() == 'POST':
                response = self.session.post(url, json=data)
            elif method.upper() == 'PUT':
                response = self.session.put(url, json=data)
            elif method.upper() == 'DELETE':
                response = self.session.delete(url)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP {e.response.status_code}"
            if e.response.text:
                try:
                    error_data = e.response.json()
                    error_msg += f": {error_data.get('err', '')}"
                except json.JSONDecodeError:
                    error_msg += f": {e.response.text[:200]}"
            raise Exception(error_msg)
        except requests.exceptions.RequestException as e:
            raise Exception(f"Request failed: {e}")
        except json.JSONDecodeError as e:
            raise Exception(f"Invalid JSON response: {e}")
    
    def get_user(self) -> Dict[str, Any]:
        """Get authenticated user info"""
        return self._make_request('GET', '/user')
    
    def get_teams(self) -> List[Dict[str, Any]]:
        """Get user's teams/workspaces"""
        response = self._make_request('GET', '/team')
        return response.get('teams', [])
    
    def get_team_tasks(self, team_id: str, filters: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """Get filtered tasks for a team"""
        params = {}
        if filters:
            params.update(filters)
        
        response = self._make_request('GET', f'/team/{team_id}/task', params=params)
        return response.get('tasks', [])
    
    def get_task(self, task_id: str) -> Dict[str, Any]:
        """Get single task by ID"""
        return self._make_request('GET', f'/task/{task_id}')
    
    def update_task(self, task_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Update task"""
        return self._make_request('PUT', f'/task/{task_id}', data=data)
    
    def start_timer(self, team_id: str, task_id: Optional[str] = None) -> Dict[str, Any]:
        """Start time tracking"""
        data = {}
        if task_id:
            data['task_id'] = task_id
        
        return self._make_request('POST', f'/team/{team_id}/time_entries/start', data=data)
    
    def stop_timer(self, team_id: str) -> Dict[str, Any]:
        """Stop time tracking"""
        return self._make_request('POST', f'/team/{team_id}/time_entries/stop')
    
    def get_running_timer(self, team_id: str) -> Optional[Dict[str, Any]]:
        """Get currently running time entry"""
        try:
            response = self._make_request('GET', f'/team/{team_id}/time_entries/current')
            return response.get('data')
        except Exception:
            return None
    
    def add_time_entry(self, team_id: str, task_id: str, duration: int, description: Optional[str] = None) -> Dict[str, Any]:
        """Add manual time entry"""
        data = {
            'task_id': task_id,
            'duration': duration,  # in milliseconds
            'start': int(datetime.now().timestamp() * 1000 - duration),
            'end': int(datetime.now().timestamp() * 1000)
        }
        
        if description:
            data['description'] = description
        
        return self._make_request('POST', f'/team/{team_id}/time_entries', data=data)
    
    def get_task_comments(self, task_id: str) -> List[Dict[str, Any]]:
        """Get comments for a task"""
        response = self._make_request('GET', f'/task/{task_id}/comment')
        return response.get('comments', [])
    
    def add_task_comment(self, task_id: str, comment_text: str, notify_all: bool = False) -> Dict[str, Any]:
        """Add comment to task"""
        data = {
            'comment_text': comment_text,
            'notify_all': notify_all,
            'assignee': None
        }
        
        return self._make_request('POST', f'/task/{task_id}/comment', data=data)
    
    def get_spaces(self, team_id: str) -> List[Dict[str, Any]]:
        """Get spaces for a team"""
        response = self._make_request('GET', f'/team/{team_id}/space')
        return response.get('spaces', [])
    
    def get_lists(self, space_id: str) -> List[Dict[str, Any]]:
        """Get lists in a space"""
        response = self._make_request('GET', f'/space/{space_id}/list')
        return response.get('lists', [])