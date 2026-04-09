from typing import Any, Dict, Optional

from cupt.api import ClickUpClient


class TimeService:
    def __init__(self, client: ClickUpClient, team_id: str):
        self.client = client
        self.team_id = team_id

    def get_running_timer(self) -> Optional[Dict[str, Any]]:
        """Fetch currently running time entry"""
        return self.client.get_running_timer(self.team_id)

    def start_timer(self, task_id: str) -> Dict[str, Any]:
        """Start tracking time for a task"""
        return self.client.start_timer(self.team_id, task_id)

    def stop_timer(self) -> Dict[str, Any]:
        """Stop current tracking"""
        return self.client.stop_timer(self.team_id)

    def add_manual_time(
        self, task_id: str, duration_ms: int, description: Optional[str] = None
    ) -> Dict[str, Any]:
        """Add a manual time entry"""
        return self.client.add_time_entry(
            self.team_id, task_id, duration_ms, description
        )
