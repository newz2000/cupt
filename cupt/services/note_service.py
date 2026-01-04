from typing import List, Dict, Any
from cupt.api import ClickUpClient

class NoteService:
    def __init__(self, client: ClickUpClient):
        self.client = client

    def add_note(self, task_id: str, text: str) -> Dict[str, Any]:
        """Add a comment/note to a task"""
        return self.client.add_task_comment(task_id, text)

    def list_notes(self, task_id: str) -> List[Dict[str, Any]]:
        """Fetch comments for a task"""
        return self.client.get_task_comments(task_id)
