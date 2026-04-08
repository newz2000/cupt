"""
ClickUp API client
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class ClickUpClient:
    """ClickUp API client with connection pooling, retry logic, and request timeout."""

    BASE_URL = "https://api.clickup.com/api/v2"
    TIMEOUT = 10  # seconds — prevents the CLI from hanging on a slow/unresponsive API

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": self.access_token,
            "Content-Type": "application/json",
        })

        # Retry transient server errors with exponential backoff.
        # Retries: 500/502/503/504 only — not 4xx client errors.
        _retry = Retry(
            total=2,
            backoff_factor=0.3,
            status_forcelist=[500, 502, 503, 504],
            raise_on_status=False,
        )
        # Pool keeps persistent TCP connections open across requests in the
        # same process (the default pool size of 10 is fine here).
        _adapter = HTTPAdapter(max_retries=_retry)
        self.session.mount("https://", _adapter)
        self.session.mount("http://", _adapter)

    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Make an API request with error handling, timeout, and retry."""
        url = f"{self.BASE_URL}/{endpoint.lstrip('/')}"

        try:
            if method.upper() == "GET":
                response = self.session.get(url, params=params, timeout=self.TIMEOUT)
            elif method.upper() == "POST":
                response = self.session.post(url, json=data, timeout=self.TIMEOUT)
            elif method.upper() == "PUT":
                response = self.session.put(url, json=data, timeout=self.TIMEOUT)
            elif method.upper() == "DELETE":
                response = self.session.delete(url, timeout=self.TIMEOUT)
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
        except requests.exceptions.Timeout:
            raise Exception(f"Request timed out after {self.TIMEOUT}s: {endpoint}")
        except requests.exceptions.RequestException as e:
            raise Exception(f"Request failed: {e}")
        except json.JSONDecodeError as e:
            raise Exception(f"Invalid JSON response: {e}")

    # ------------------------------------------------------------------
    # Auth / user
    # ------------------------------------------------------------------

    def get_user(self) -> Dict[str, Any]:
        return self._make_request("GET", "/user")

    def get_teams(self) -> List[Dict[str, Any]]:
        return self._make_request("GET", "/team").get("teams", [])

    # ------------------------------------------------------------------
    # Tasks
    # ------------------------------------------------------------------

    def get_team_tasks(self, team_id: str, filters: Optional[Dict] = None) -> List[Dict[str, Any]]:
        params: Dict = {}
        if filters:
            params.update(filters)
        return self._make_request("GET", f"/team/{team_id}/task", params=params).get("tasks", [])

    def get_tasks_by_ids(self, team_id: str, task_ids: List[str]) -> List[Dict[str, Any]]:
        """Bulk-fetch up to 100 tasks by ID."""
        if not task_ids:
            return []
        params = {"ids[]": task_ids[:100], "include_subtasks": "true"}
        return self._make_request("GET", f"/team/{team_id}/task", params=params).get("tasks", [])

    def get_task(self, task_id: str) -> Dict[str, Any]:
        return self._make_request("GET", f"/task/{task_id}")

    def get_task_children(self, team_id: str, parent_id: str, params: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """Fetch direct subtasks of a task."""
        p: Dict = {"parent": parent_id}
        if params:
            p.update(params)
        return self._make_request("GET", f"/team/{team_id}/task", params=p).get("tasks", [])

    def update_task(self, task_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._make_request("PUT", f"/task/{task_id}", data=data)

    # ------------------------------------------------------------------
    # Statuses
    # ------------------------------------------------------------------

    def get_list_statuses(self, list_id: str) -> List[Dict[str, Any]]:
        return self._make_request("GET", f"/list/{list_id}").get("statuses", [])

    def get_space_statuses(self, space_id: str) -> List[Dict[str, Any]]:
        return self._make_request("GET", f"/space/{space_id}").get("statuses", [])

    # ------------------------------------------------------------------
    # Comments / notes
    # ------------------------------------------------------------------

    def get_task_comments(self, task_id: str) -> List[Dict[str, Any]]:
        return self._make_request("GET", f"/task/{task_id}/comment").get("comments", [])

    def add_task_comment(self, task_id: str, comment_text: str, notify_all: bool = False) -> Dict[str, Any]:
        data = {"comment_text": comment_text, "notify_all": notify_all, "assignee": None}
        return self._make_request("POST", f"/task/{task_id}/comment", data=data)

    # ------------------------------------------------------------------
    # Time tracking
    # ------------------------------------------------------------------

    def start_timer(self, team_id: str, task_id: Optional[str] = None) -> Dict[str, Any]:
        data: Dict = {}
        if task_id:
            data["task_id"] = task_id
            data["tid"] = task_id
        return self._make_request("POST", f"/team/{team_id}/time_entries/start", data=data)

    def stop_timer(self, team_id: str) -> Dict[str, Any]:
        return self._make_request("POST", f"/team/{team_id}/time_entries/stop")

    def get_running_timer(self, team_id: str) -> Optional[Dict[str, Any]]:
        try:
            return self._make_request("GET", f"/team/{team_id}/time_entries/current").get("data")
        except Exception:
            return None

    def add_time_entry(self, team_id: str, task_id: str, duration: int, description: Optional[str] = None) -> Dict[str, Any]:
        now_ms = int(datetime.now().timestamp() * 1000)
        data: Dict = {
            "task_id": task_id,
            "tid": task_id,
            "duration": duration,
            "start": now_ms - duration,
            "end": now_ms,
        }
        if description:
            data["description"] = description
        return self._make_request("POST", f"/team/{team_id}/time_entries", data=data)

    # ------------------------------------------------------------------
    # Hierarchy
    # ------------------------------------------------------------------

    def get_spaces(self, team_id: str) -> List[Dict[str, Any]]:
        return self._make_request("GET", f"/team/{team_id}/space").get("spaces", [])

    def get_lists(self, space_id: str) -> List[Dict[str, Any]]:
        return self._make_request("GET", f"/space/{space_id}/list").get("lists", [])
